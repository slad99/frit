#!/usr/bin/python
"""
hashes command.
Computes files hashes (md5, sha1 ans ssdeep).
"""

import os
import sys
import fritutils.termout
import fritutils.fritobjects
import fritutils.fritdb as fritModel
import fritutils.frithashes
import fritutils.fritlog
import ssdeep

logger = fritutils.fritlog.loggers['hashesLog']

def updateDb(dbFile,hmd5,hsha1,hsha256):
    fname = os.path.join(dbFile.fullpath.fullpath,dbFile.filename)
    if not dbFile.md5:
        nMd5 = fritModel.Md5.query.filter_by(md5=hmd5).first()
        if not nMd5:
            nMd5 = fritModel.Md5()
            nMd5.md5 = hmd5
        nMd5.files.append(dbFile)
        fritModel.elixir.session.commit()
    else:
        fritutils.termout.printWarning('Md5 for "%s" is already in database.' % fname)
    if not dbFile.sha1:
        nSha1 = fritModel.Sha1.query.filter_by(sha1=hsha1).first()
        if not nSha1:
            nSha1 = fritModel.Sha1()
            nSha1.sha1 = hsha1
        nSha1.files.append(dbFile)
        fritModel.elixir.session.commit()
    else:
        fritutils.termout.printWarning('Sha1 for "%s" is already in database.' % fname)
    if not dbFile.sha256:
        nSha256 = fritModel.Sha256.query.filter_by(sha256=hsha256).first()
        if not nSha256:
            nSha256 = fritModel.Sha256()
            nSha256.sha256 = hsha256
        nSha256.files.append(dbFile)
        fritModel.elixir.session.commit()
    else:
        fritutils.termout.printWarning('Sha256 for "%s" is already in database.' % fname)

def hashFile(EviDb,FsDb,realFile,dbFile):
    dname = fritutils.unicodify(os.path.dirname(dbFile))
    bname = fritutils.unicodify(os.path.basename(dbFile))
    Fpath = fritModel.FullPath.query.filter_by(fullpath=dname).first()
    nFile = fritModel.File.query.filter_by(evidence=EviDb,filesystem=FsDb,filename=bname,fullpath=Fpath).first()
    if not nFile:
        fritutils.termout.printWarning('This file cannot be found in database: %s' % (dname + '/' + bname))
    else:
        # Now we do a little check to see if an md5 exists for the file
        # if yes, we assume that all hashes are already in databases
        # we do that to avoid to do the time consuming real hashes 
        # on files. We double check the database inside updateDb()
        if not nFile.md5:
            hashes = fritutils.frithashes.hashes(realFile)
            updateDb(nFile,unicode(hashes[0]),unicode(hashes[1]),unicode(hashes[2]))
        else:
            fritutils.termout.printWarning('Hashes for "%s" seems to be already in database.' % nFile.filename)

def update(Evidences):
    # First we check if the database exists
    if not os.path.exists(fritModel.DBFILE):
        fritutils.termout.printWarning('Datase does not exists yet. You should create it first with the store command.')
        sys.exit(1)
    for evi in Evidences:
        EviDb = fritModel.Evidence.query.filter_by(name=fritutils.unicodify(evi.fileName)).first()
        if not EviDb:
            fritutils.termout.printWarning('Cannot find this Evidence (%s) in database' % evi.fileName)
            break
        for fs in evi.fileSystems:
            logger.info('Starting to update hashes database for "%s/%s"' % (fs.evidence.configName, fs.configName))
            FsDb = fritModel.Filesystem.query.filter_by(evidence=EviDb,configName=fritutils.unicodify(fs.configName)).first()
            if not FsDb:
                fritutils.termout.printWarning('Cannot find this File System (%s - %s) in database' % (evi.fileName,fs.configName))
                break
            if fs.isLocked("store") or fs.isLocked("hashes"):
                fritutils.termout.printWarning('Filesystem "%s" is already locked by a "store" or a "hashes" instance.' % fs.configName)
                logger.warning('"%s/%s" is already locked by a "store" or "hashes" command.' % (fs.evidence.configName, fs.configName))
                break
            logger.info('Mounting filesystem "%s/%s" if needed' % (fs.evidence.configName, fs.configName))
            fs.mount('hashes', 'Hashing files')
            # Counting files for showing progress
            dbNbFiles = fs.dbCountFiles()['Normal']['Files']
            fritutils.termout.printNormal('Start inserting Hashes in database for regular files on "%s"\n' % fs.configName)
            filenb = 0
            spos = len(fs.fsMountPoint)
            for f in fs.listFiles():
                dbfile = f[spos:]
                fritutils.termout.printNormal('    Hashing file %d / %d' % (filenb,dbNbFiles))
                hashFile(EviDb,FsDb,f,dbfile)
                filenb += 1
            logger.info('Unmounting "%s/%s" if needed' % (fs.evidence.configName, fs.configName))
            fs.umount('hashes')
                
            fritutils.termout.printNormal('Start inserting Hashes in database for undeleted files on "%s"\n' % fs.configName)
            logger.info('Updating hashes for undeleted files for "%s/%s".' % (fs.evidence.configName, fs.configName))
            for f in fs.listUndeleted():
                hashFile(EviDb,FsDb,f,f)
        
            logger.info('Updating hashes for emails files for "%s/%s".' % (fs.evidence.configName, fs.configName))
            fritutils.termout.printNormal('Start inserting Hashes in database for emails files on "%s"\n' % fs.configName)
            for f in fs.listEmails():
                hashFile(EviDb,FsDb,f,f)
       
        evi.umount('hashes')

def searchFactory(hashlist,Evidences,hashtype):
    hashModel = { 'md5' : fritModel.Md5, 'sha1' : fritModel.Sha1, 'sha256' : fritModel.Sha256 }
    hashModelField = { 'md5' : fritModel.Md5.md5, 'sha1' : fritModel.Sha1.sha1, 'sha256' : fritModel.Sha256.sha256 }
    for evi in Evidences:
        fritutils.termout.printSuccess('Searching in %s (%s)' % (evi.configName,evi.fileName))
        for x in hashlist:
            if len(x) < 3:
                fritutils.termout.printWarning('"%s" is too short to be searched for.' % x)
            else:
                files = fritModel.File.query.join(fritModel.Evidence).filter_by(configName=fritutils.unicodify(evi.configName))
                files = files.join(hashModel[hashtype]).filter(hashModelField[hashtype].like(unicode(x + '%'))).all()
                if files:
                    for f in files:
                        fritutils.termout.printMessage("\t%s" % ( f.fullFileSpec(hashtype=hashtype)))
                else:
                    fritutils.termout.printNormal("\t%s NOT FOUND" % x)
                
def ssdeepsearch(args):
    """
    ssdeep support is based on pyssdep (http://code.google.com/p/pyssdeep/)
    args should contain a ssdeep hash and a minimal score
    """
    s = ssdeep.ssdeep()
    h = unicode(args[0].decode('utf-8'))
    mscore = int(args[1])
    if mscore < 10:
        fritutils.termout.printWarning('"%d" is too low to use as a score.' % mscore)
    else:
        fritutils.termout.printMessage("Starting to search for ssdeep hashes.")
        for f in fritModel.File.query.all():
            if f.ssdeep:
                score = s.compare(f.ssdeep.ssdeep,h)
                if score >= mscore:
                    fp = os.path.join(f.fullpath.fullpath, f.filename)
                    fritutils.termout.printNormal("Score: %d, %s " % ( score, f.fullFileSpec()))

def csvdump(Evidences):
    for evi in Evidences:
        for fs in evi.fileSystems:
            fso =  fs.getFsDb()          
            fq = fritModel.File.query.filter(fritModel.File.filesystem==fso)
            for f in fq:
                if f.md5:
                    if not f.ssdeep:
                        ssdeep = ''
                    else:
                        ssdeep = f.ssdeep.ssdeep
                    fritutils.termout.printNormal("%s,%s,%s,%s,%s,%s,%s,%s" % \
                    (f.evidence.configName, f.filesystem.configName,\
                     f.filename, f.md5.md5, f.sha1.sha1, f.sha256.sha256,\
                     ssdeep, f.state.state))

def factory(Evidences,args,options):
    """
    args are the hashes command arguments
    """
    logger.info('Starting hashes command.')
    validArgs = ('update','md5search','sha1search','sha256search', 'csvdump', 'ssdsearch')
    if not args or len(args) == 0:
        fritutils.termout.printWarning('hashes command need at least an argument. Exiting.')
        logger.error('No argument given.')
        sys.exit(1)
    elif args[0] not in validArgs:
        fritutils.termout.printWarning('hashes command need a valid argument (%s)' % ', '.join(validArgs))
        logger.error('"%s" in not a valid arguement. Exiting.' % args[0])
        sys.exit(1)
    elif not fritModel.dbExists():
        fritutils.termout.printWarning('Database not found. run the "frit store create", followed by "frit hashes update".')
        logger.error("No database found, exiting.")
        sys.exit(1)
    else:
        if args[0] == 'update':
            logger.info('Update arguement given. Starting update.')
            update(Evidences)
        if args[0] == 'md5search':
            args.remove('md5search')
            if len(args) < 1:
                fritutils.termout.printWarning('md5search command need at least one md5 to search for.')
                logger.error('md5search command but no argument to search for. Exiting.')
                sys.exit(1)
            else:
                searchFactory(args,Evidences,'md5')
        if args[0] == 'sha1search':
            args.remove('sha1search')
            if len(args) < 1:
                fritutils.termout.printWarning('sha1search command need at least one sha1 to search for.')
                logger.error('sha1search command but no argument to search for. Exiting.')
                sys.exit(1)
            else:
                searchFactory(args,Evidences,'sha1')
        if args[0] == 'sha256search':
            args.remove('sha256search')
            if len(args) < 1:
                fritutils.termout.printWarning('sha256search command need at least one sha256 to search for.')
                logger.error('sha256search command but no argument to search for. Exiting.')
                sys.exit(1)
            else:
                searchFactory(args,Evidences,'sha256')
        if args[0] == 'csvdump':
            csvdump(Evidences)
        if args[0] == 'ssdsearch':
            args.remove('ssdsearch')
            if len(args) < 2:
                fritutils.termout.printWarning('ssdsearch command need a ssdeep hash and a minimal score to match.')
                logger.error('ssdsearch command but not enough argument (hash and a score). Exiting.')
            else:
                ssdeepsearch(args)
