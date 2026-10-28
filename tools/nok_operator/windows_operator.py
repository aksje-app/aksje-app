"""Existing NOK accounts: Windows SSH operator; prepare stops before personal B."""
import argparse
import base64
from datetime import datetime, timezone
import getpass
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import zipfile
import io

from wire import emit,line,send_file,receive_file,sha
import operator_common as shared

HERE=Path(__file__).resolve().parent
CERT_SHA='0929f27761b5049399b446c263dbede2f67741a9da54c2282e426b91d9eb419b'
ARCHIVE_CERT_SHA='cc866031f57998f88bb0dde22f149951c755b6037e2bd523b137d42da63cd63b'
RUN_LOCK=None
CIPHER_SHA='5e98f9c9d7f43ed477099f17f459ea7680ec61fb04d49f9f504191694b4ce158'
RENDER_HOST=shared.SERVICE+'@ssh.ohio.render.com'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def openssl_program():
    found=shutil.which('openssl')
    for path in [found,r'C:\Program Files\Git\usr\bin\openssl.exe',r'C:\Program Files\PostgreSQL\18\bin\openssl.exe']:
        if path and Path(path).is_file():return str(path)
    raise ValueError('Eksisterende OpenSSL-installasjon ble ikke funnet (Git/PostgreSQL18/PATH). Ingen produksjonshandling.')


def crypto(program,args,password=None):
    env=os.environ.copy()
    if password is not None:env['NOK_LOCAL_KEY_PASSWORD']=password
    options=['-passin','env:NOK_LOCAL_KEY_PASSWORD'] if password is not None else ['-passin','pass:']
    # passin is accepted by pkey/dgst/cms and never contains the secret itself.
    result=subprocess.run([program,args[0],*options,*map(str,args[1:])],capture_output=True,env=env,timeout=1800)
    if result.returncode:raise ValueError('Lokal OpenSSL-operasjon feilet; nøkkel/passord blir ikke skrevet ut')
    return result.stdout


def key_check(program,key,cert):
    public=subprocess.run([program,'x509','-in',str(cert),'-pubkey','-noout'],capture_output=True,timeout=30)
    if public.returncode:raise ValueError('Ugyldig eksisterende offentlig sertifikat')
    password=None
    try:actual=crypto(program,['pkey','-in',key,'-pubout'])
    except ValueError:
        password=getpass.getpass('Passord til eksisterende lokal nøkkel '+key.name+' (vises ikke): ')
        actual=crypto(program,['pkey','-in',key,'-pubout'],password)
    if actual.strip()!=public.stdout.strip():raise ValueError('Eksisterende privat nøkkel stemmer ikke med det pinnede offentlige sertifikatet')
    return password


def certificate_identity(path):
    """DER identity accepts PEM CRLF/LF without weakening production byte pinning."""
    import ssl
    try:
        if path.stat().st_size > 65536:return None
        return hashlib.sha256(ssl.PEM_cert_to_DER_cert(path.read_text(encoding='utf-8-sig'))).hexdigest()
    except (OSError,ValueError,UnicodeError):return None


def discover(job,root):
    archive_der='c2822249ac8ca1100d4653c366c57ec61cac29b3830c49bad76e8542a8e64379'
    operator_der='cbac8cb4b165b49aa966f613f959cca63c03748d5a33296a0fb8fc2f83454547'
    location=shared.load(job/'job-location.json') if (job/'job-location.json').is_file() else {}
    pending=[Path(job),Path(root)]
    # The original package is documented in the existing Windows transcript.
    for variable in ('OneDrive','OneDriveConsumer','OneDriveCommercial'):
        if os.environ.get(variable):
            pending.append(Path(os.environ[variable])/'Documents'/'Codex'/'DB Backup 24.10.2026')
    if os.environ.get('USERPROFILE'):
        user=Path(os.environ['USERPROFILE'])
        pending.extend([user/'OneDrive'/'Documents'/'Codex'/'DB Backup 24.10.2026',
                        user/'Documents'/'Codex'/'DB Backup 24.10.2026'])
    ignored={'payload','archives','independent-archives','.git','.venv','node_modules','cache','logs',
             'pg18-tools','isolated-pg','data','verification-files'}
    fields={'keys_folder','package','local','certificate','private_key','keys','archive_certificate','operator_certificate'}
    def references(value):
        if isinstance(value,dict):
            for key,child in value.items():
                if key in fields and isinstance(child,str) and child:
                    candidate=Path(os.path.expandvars(child)).expanduser()
                    pending.append(candidate if candidate.is_dir() else candidate.parent)
                elif isinstance(child,(dict,list)):references(child)
        elif isinstance(value,list):
            for child in value:references(child)
    references(location)
    seen=set();candidates=[]
    while pending:
        folder=pending.pop()
        try:
            if folder.is_symlink() or not folder.is_dir():continue
            resolved=folder.resolve();identity=os.path.normcase(str(resolved))
            if identity in seen:continue
            seen.add(identity)
            if len(seen)>5000:raise ValueError('Avgrenset operatormappesok overskred grensen; ingen diskvid skanning startet')
            candidates.append(resolved)
            metadata=folder/'job-location.json'
            if metadata.is_file() and metadata.stat().st_size<=1024**2:
                references(shared.load(metadata))
            for child in folder.iterdir():
                if child.name.lower() not in ignored and not child.is_symlink() and child.is_dir():pending.append(child)
        except (OSError,UnicodeError,json.JSONDecodeError):continue
    cert=next((p/'archive-certificate.pem' for p in candidates
        if (p/'archive-key.pem').is_file() and (p/'archive-certificate.pem').is_file()
        and certificate_identity(p/'archive-certificate.pem')==archive_der),None)
    if cert is None:
        public_count=sum(1 for p in candidates if (p/'archive-certificate.pem').is_file())
        raise ValueError('Originalt arkivsertifikat/nokkelpar ble ikke funnet etter automatisk sok i '+str(len(candidates))+
            ' eksisterende operatormapper og jobbhenvisninger ('+str(public_count)+' arkivsertifikatfiler funnet). Ingen erstatning laget')
    operator=next((p/'operator-certificate.pem' for p in candidates
        if (p/'operator-key.pem').is_file() and (p/'operator-certificate.pem').is_file()
        and certificate_identity(p/'operator-certificate.pem')==operator_der),None)
    if operator is None:raise ValueError('Eksisterende operatorkey/sertifikatpar ikke funnet i opprinnelige operatormapper; ingen erstatning laget')
    return location,cert,cert.with_name('archive-key.pem'),operator,operator.with_name('operator-key.pem')

def verify_plaintext(packed,receipt,review):
    with tarfile.open(packed) as archive:
        members=archive.getmembers();names=[m.name for m in members]
        if len(names)!=len(set(names)) or any(not m.isfile() or m.name.startswith('/') or '..' in Path(m.name).parts for m in members):raise ValueError('Usikker arkivstruktur')
        manifest_member=archive.getmember('manifest.json')
        if manifest_member.size>32*1024**2:raise ValueError('For stort manifest')
        raw=archive.extractfile(manifest_member).read()
        if hashlib.sha256(raw).hexdigest()!=receipt['manifest_sha256']:raise ValueError('Manifest-kontrollsum avviker')
        manifest=json.loads(raw)
        if manifest['archive_id']!=shared.ARCHIVE or set(names)!=set(manifest['files'])|{'manifest.json'}:raise ValueError('Arkividentitet eller filomfang avviker')
        files={'manifest.json':hashlib.sha256(raw).hexdigest()}
        for name,expected in manifest['files'].items():
            value=hashlib.sha256()
            with archive.extractfile(name) as source:
                for chunk in iter(lambda:source.read(1024**2),b''):value.update(chunk)
            if value.hexdigest()!=expected['sha256'] or archive.getmember(name).size!=expected['bytes']:raise ValueError('Arkivfil avviker fra originalt manifest')
            files[name]=value.hexdigest()
        if files!=review['files']:raise ValueError('Filtre stemmer ikke med opprinnelig fysisk restore-kvittering')
    return manifest


def bootstrap():
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in ('render_worker.py','wire.py','operator_common.py','openssl_delegate.py'):
            bundle.write(HERE/name,name)
    encoded=base64.b64encode(buffer.getvalue()).decode()
    code="import base64,io,zipfile,tempfile,os,sys,runpy;os.umask(0o077);p=tempfile.mkdtemp(prefix='nok-wire-code-');zipfile.ZipFile(io.BytesIO(base64.b64decode('"+encoded+"'))).extractall(p);sys.path.insert(0,p);runpy.run_path(p+'/render_worker.py',run_name='__main__')"
    # Bootstrap code contains no user data, private context, key or credentials.
    import shlex
    return 'python -u -c '+shlex.quote(code)


def sign_grants(folder,key,program,reference):
    catalog=shared.load(folder/'catalog.json')
    if digest(catalog)!=reference or sha(folder/'operator-certificate.PUBLIC.pem')!=CERT_SHA:raise ValueError('B-katalog eller pinnet sertifikat avviker')
    password=key_check(program,key,folder/'operator-certificate.PUBLIC.pem')
    grants={}
    with tempfile.TemporaryDirectory(prefix='nok-private-sign-') as temporary:
        root=Path(temporary);public=root/'public.pem'
        public.write_bytes(subprocess.run([program,'x509','-in',str(folder/'operator-certificate.PUBLIC.pem'),'-pubkey','-noout'],capture_output=True,check=True).stdout)
        for family in shared.FAMILIES:
            payload=shared.load(folder/(family+'-request.json'))
            if (digest(payload)!=catalog['requests'][family] or payload['period_id']!=shared.PERIOD
                or payload['family']!=family or payload['capital_nok']!=dict(zip(shared.FAMILIES,(100000,500000,1000000)))[family]
                or payload['archive']['archive_id']!=shared.ARCHIVE or payload['cost_policy']!=shared.policies()[family]):raise ValueError('Forespørsel endret etter personlig gjennomgang')
            data=root/'request.json';data.write_bytes(json.dumps(payload,sort_keys=True,separators=(',',':')).encode())
            signature=crypto(program,['dgst','-sha256','-sign',key,data],password)
            sig=root/'signature';sig.write_bytes(signature)
            verified=subprocess.run([program,'dgst','-sha256','-verify',str(public),'-signature',str(sig),str(data)],capture_output=True)
            if verified.returncode:raise ValueError('Signaturvalidering feilet')
            grants[family]=dict(payload=payload,signature=base64.b64encode(signature).decode())
    signed=folder/'signed-grants.json'
    if signed.exists():
        existing=shared.load(signed)
        if existing.get('personal_B_catalog_sha256')!=reference or existing.get('grants')!=grants:
            raise ValueError('Existing signed B package differs; no overwrite')
        return signed
    shared.save(signed,dict(personal_B_catalog_sha256=reference,signed_at=datetime.now(timezone.utc).isoformat(),grants=grants))
    return signed


def session(action,context,files,program,archive_key,archive_cert,password,local,header):
    ssh=shutil.which('ssh')
    if not ssh:raise ValueError('Eksisterende Windows OpenSSH ssh.exe mangler')
    command=[ssh,'-T','-i',str(context['ssh_key']),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
        '-o','StrictHostKeyChecking=yes','-o','UpdateHostKeys=no','-o','ConnectTimeout=20',
        '-o','ServerAliveInterval=30','-o','ServerAliveCountMax=3',RENDER_HOST,bootstrap()]
    # Strict known-hosts checking reuses the earlier trusted connection; no new trust prompts.
    log=local/'ssh-private.log'
    with log.open('xb') as errors:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors)
        watchdog=threading.Timer(7200,process.terminate)
        watchdog.daemon=True;watchdog.start()
        try:
            emit(process.stdin,dict(action=action,**header))
            state={};done=None
            while True:
                message=line(process.stdout);kind=message.get('kind')
                if kind=='context':
                    state['remote_work']=message['remote_work']
                    if action=='prepare' and context.get('state_path'):
                        saved=dict(local_package=str(local),remote_work=message['remote_work'],
                            result=dict(status='PREPARATION_IN_PROGRESS_OR_STOPPED',approval_B_ready=False))
                        temporary=context['state_path'].with_suffix('.new-'+os.urandom(4).hex())
                        shared.save(temporary,saved);os.replace(temporary,context['state_path'])
                elif kind=='upload':
                    name=message['name']
                    if name not in files:raise ValueError('Unexpected file request; no private-key file is transportable')
                    send_file(process.stdin,files[name],offset=message.get('offset',0),prefix_sha256=message.get('prefix_sha256'))
                elif kind=='decrypt':
                    if message.get('cipher_sha256')!=CIPHER_SHA or message.get('certificate_sha256')!=sha(archive_cert):raise ValueError('Forespurt dekryptering gjelder ikke godkjent originalarkiv')
                    if sha(files['archive.cms'])!=CIPHER_SHA:raise ValueError('Originalt kryptert arkiv endret')
                    print('Dekrypterer originalarkivet lokalt. Privat nøkkel blir på PC-en.',flush=True)
                    packed=local/('temporary-decryption-'+os.urandom(8).hex()+'.tar')
                    try:
                        crypto(program,['cms','-decrypt','-binary','-inform','DER','-in',files['archive.cms'],
                            '-recip',archive_cert,'-inkey',archive_key,'-out',packed],password)
                        verify_plaintext(packed,shared.load(files['archive-receipt.json']),shared.load(files['restore-result.json']))
                        send_file(process.stdin,packed)
                    finally:
                        if packed.exists():packed.unlink()  # only our newly made decrypted transport file.
                elif kind=='download':
                    name=message['name']
                    if Path(name).name!=name or name not in {'catalog.json','operator-certificate.PUBLIC.pem','input-sources.json',
                        'settings.json','cost-policies.json','status.json','postgres-activation-confirmation.json',
                        *[f+'-activation-preflight.json' for f in shared.FAMILIES],
                        *[f+'-request.json' for f in shared.FAMILIES],*[f+'-activation-receipt.json' for f in shared.FAMILIES]}:
                        raise ValueError('Unexpected receipt filename')
                    receive_file(process.stdout,local/name,message,limit=32*1024**2)
                elif kind=='progress':print(message['message'],flush=True)
                elif kind=='partial':
                    shared.save(local/'partial-activation.json',message)
                    print('STOPP. Allerede aktivert: '+str(message.get('activated'))+'; ingen automatisk repetisjon.',flush=True)
                elif kind=='error':raise ValueError(message.get('message') or message['error_type'])
                elif kind=='complete':done=message;break
                else:raise ValueError('Unexpected SSH protocol response')
            process.stdin.close();code=process.wait(timeout=45)
            if code!=0:raise ValueError('SSH prosessen stoppet; behold kvitteringene, ingen automatisk gjentakelse')
            return dict(**state,result=done)
        except (BrokenPipeError,EOFError) as error:
            process.terminate()
            process.wait(timeout=10)
            raise ValueError('SSH ble brutt. Privat logg: '+str(log)+'. Behold samme B-pakke; ny kjoring verifiserer status for hver konto for videreforing') from None
        except BaseException:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill()
            raise
        finally:
            watchdog.cancel()


def main():
    global RUN_LOCK
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','activate'))
    parser.add_argument('--job');parser.add_argument('--actor')
    args=parser.parse_args()
    if os.name!='nt':raise ValueError('Denne inngangen er for Windows-PC-en med de eksisterende private filene')
    base=Path(os.environ['LOCALAPPDATA'])/'AksjeNokOperator'
    job=Path(args.job) if args.job else base/'nok-job-20261024T165039Z'
    import msvcrt
    RUN_LOCK=(job/'nok-activation-run.lock').open('a+b')
    if RUN_LOCK.tell()==0:RUN_LOCK.write(b'0');RUN_LOCK.flush()
    RUN_LOCK.seek(0)
    try:msvcrt.locking(RUN_LOCK.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:raise ValueError('En annen Windows-operatørkjøring bruker allerede denne jobben')
    location,cert,key,operator_cert,operator_key=discover(job,base)
    review=shared.load(job/'restore-result.json');receipt=shared.load(job/'archive-receipt.json')
    if (review.get('review_sha256')!=shared.REVIEW_SHA or digest({k:v for k,v in review.items() if k!='review_sha256'})!=shared.REVIEW_SHA
        or review['status']!='RESTORED_AND_VERIFIED' or receipt['cipher_sha256']!=CIPHER_SHA):raise ValueError('Opprinnelige arkiv-/restore-kvitteringer stemmer ikke')
    archive=job/'independent-archives'/shared.ARCHIVE/'archive.cms'
    if not archive.is_file() or sha(archive)!=CIPHER_SHA:raise ValueError('Eksisterende uavhengig kryptert arkiv mangler/avviker')
    ssh_key=base/'nok-job-20261024T162543Z'/'render-operator-ssh'
    if not ssh_key.is_file():raise ValueError('Bekreftet eksisterende SSH-identitet mangler; ingen erstatning opprettes')
    program=openssl_program();password=key_check(program,key,cert)
    files={'config.json':job/'config.json','restore-result.json':job/'restore-result.json','archive-receipt.json':job/'archive-receipt.json',
        'archive-certificate.pem':cert,'archive.cms':archive}
    state_path=job/'nok-activation-windows-state.json'
    context=dict(ssh_key=ssh_key,state_path=state_path)
    if args.action=='prepare':
        actor=args.actor or os.environ.get('USERNAME') or getpass.getuser()
        local=job/('activation-requests-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+os.urandom(4).hex());local.mkdir()
        previous=shared.load(state_path) if state_path.is_file() else {}
        result=session('prepare',context,files,program,key,cert,password,local,dict(actor=actor,remote_work=previous.get('remote_work')))
        saved=dict(local_package=str(local),remote_work=result['remote_work'],result=result['result'])
        # Only our explicit resumable state pointer is updated. Original job evidence is never overwritten.
        temporary=state_path.with_suffix('.new-'+os.urandom(4).hex());shared.save(temporary,saved);os.replace(temporary,state_path)
        print('\nResultater: '+str(local))
        if result['result']['approval_B_ready']:
            print('STOPP VED PERSONLIG GODKJENNING B. Ingen konto aktivert.')
            print('Gjennomgå catalog.json, de tre *-request.json og kostnadspolicyene. B-referanse: '+result['result']['catalog_sha256'])
            print('Etter personlig B: kjør 2-GODKJENN-OG-AKTIVER.cmd. Nøkkelen signerer kun disse tre forespørslene.')
        else:
            print('Ingen aktivering eller signering. Følgende faktiske bevis gjenstår:')
            for blocker in result['result']['blockers']:print('- '+blocker)
            print('Kjør 1-KLARGJOR.cmd igjen etter at den oppgitte aktiveringsblokkeringen er rettet. Scheduleren forblir suspendert.')
    else:
        state=shared.load(state_path);result=state['result'];folder=Path(state['local_package'])
        if result.get('approval_B_ready') is not True:raise ValueError('Personlig B er sperret: nødvendige faktiske input/markedsbevis mangler')
        reference=result['catalog_sha256']
        print('Dette vil signere og aktivere de tre eksisterende kontoene. Scheduleren startes ikke.')
        print('Dokumentene som godkjennes: '+str(folder))
        if input('Skriv GODKJENNING B '+reference+': ').strip()!='GODKJENNING B '+reference:raise ValueError('Personlig B ikke gitt; ingen signering eller aktivering')
        if not operator_key.is_file():raise ValueError('Eksisterende lokal operatørnøkkel mangler; ingen erstatning laget')
        signed=sign_grants(folder,operator_key,program,reference);files['signed-grants.json']=signed
        for name in ['catalog.json','status.json']+[f+'-request.json' for f in shared.FAMILIES]:files[name]=folder/name
        local=folder/('activation-run-'+os.urandom(8).hex());local.mkdir()
        session('activate',context,files,program,key,cert,password,local,
            dict(remote_work=state['remote_work'],remote_package=result['remote_package'],approval_b=reference))
        print('Aktivering bekreftet direkte i PostgreSQL. Kvitteringer: '+str(local))
        print('Scheduleren er fortsatt ikke startet av dette skriptet.')

if __name__=='__main__':
    try:main()
    except (Exception,KeyboardInterrupt) as error:
        print('\nSTOPPET: '+(str(error) if isinstance(error,ValueError) else type(error).__name__)+'. Ingen automatisk gjentakelse.')
        raise SystemExit(1)
