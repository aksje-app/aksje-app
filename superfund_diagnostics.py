"""Bounded, local-only evidence bundle, available before the first snapshot."""
import base64
import gzip
import hashlib
from io import BytesIO
import json
import re
import zipfile
from datetime import datetime, timezone

MAX_RAW_BYTES=32*1024*1024
MAX_ZIP_BYTES=32*1024*1024


def _redact(value):
    if isinstance(value,dict):
        return {k:('[REDACTED]' if any(x in k.lower() for x in ('password','secret','api_key','authorization','database_url','token')) else _redact(v)) for k,v in value.items()}
    if isinstance(value,list):return [_redact(v) for v in value]
    if isinstance(value,str):
        value=re.sub(r'(?i)postgres(?:ql)?://\S+','[REDACTED_DATABASE_URL]',value)
        value=re.sub(r'(?i)(api_key|token|password|secret)=([^\s&]+)',r'\1=[REDACTED]',value)
    return value


def learning_summary(snapshot):
    learning=snapshot.get('learning',{});paired=learning.get('paired_dates',0)
    proposal=learning.get('proposal',{});validation=learning.get('validation',{})
    if proposal.get('state')=='WAITING_APPROVAL':return 'VENTER PÅ GODKJENNING'
    if proposal.get('state') in ('IMPLEMENTED','REJECTED'):return proposal['state']+' · Nytt forslag krever nye observasjoner og en ny kontrollperiode.'
    if learning.get('status')=='NO_VALIDATED_IMPROVEMENT':return 'INGEN VALIDERT FORBEDRING · observasjonstid, nye handler eller resultatkrav er ikke oppfylt.'
    if validation:return f"TESTER FORSLAG · {max(0,20-(paired-validation.get('started_dates',paired)))} nye parrede kursdatoer gjenstår før vurdering; handels- og resultatkrav gjelder også."
    return f"SAMLER DATA · {paired} parrede kursdatoer · minst {max(0,60-paired)} gjenstår før valg av utfordrer. Ingen dokumentert forbedring ennå."


def controls(snapshot,index):
    findings=[];model=snapshot.get('model',{})
    if not snapshot:findings.append({'check':'SNAPSHOT','state':'MISSING','detail':'Første komplette vurdering mangler.'})
    if not snapshot.get('learning',{}).get('paired_start'):
        findings.append({'check':'SHADOW_COMPARISON','state':'INCOMPLETE','detail':'Felles start mot kjøp-og-behold-referansen er ikke etablert.'})
    seen=set()
    for position in model.get('positions',{}).values():
        isin=position.get('isin')
        if isin in seen:findings.append({'check':'DUPLICATE_ISIN','state':'FAILED','isin':isin})
        seen.add(isin)
    if model.get('cash',0)<0:findings.append({'check':'CASH','state':'FAILED'})
    for name,book in snapshot.get('shadows',{}).items():
        if book.get('initial_capital')!=model.get('initial_capital'):
            findings.append({'check':'SHADOW_CAPITAL','state':'FAILED','shadow':name})
        if not snapshot.get('shadow_rules',{}).get(name):
            findings.append({'check':'SHADOW_RULES','state':'MISSING','shadow':name})
    return {'findings':findings,'learning_status':learning_summary(snapshot),
            'scope':'Lagret snapshot og inkluderte historikkrammer. Ingen nye markedsoppslag eller strategiforsøk.',
            'catalog_pages':len(index.get('pages',{})),'historical_test_minimum_days':80}


def diagnostic_zip(progress=None):
    from superfund_runtime import read,storage,PREFIX,config
    from app_version import APP_VERSION
    stamp=datetime.now(timezone.utc).isoformat();out=BytesIO();used=0
    manifest={'created_at':stamp,'version':APP_VERSION,'included':[],'omitted':[],
              'limits':{'raw_bytes':MAX_RAW_BYTES,'zip_bytes':MAX_ZIP_BYTES},
              'consistency':'Hvert dokument leses én gang. Snapshot er atomisk; katalog kan oppdateres under eksport.'}
    index=read('catalog_index.json',{});snap=read('snapshot.json',{});archive=read('learning_index.json',{})
    checks=controls(snap,index)
    entries=[('snapshot.json',snap),('catalog_index.json',index),('learning_index.json',archive),('parameters.json',config())]
    entries += [(name,read(name,{})) for name in ('job.json','request.json','capacity_watch.json','parameter_audit.json','fx.json','news.json')]
    # Prioritise immutable learning/shadow evidence before catalogue bulk.
    paths=[f['key'][len(PREFIX):] for f in reversed(archive.get('frames',[])) if re.fullmatch(r'superfund/history/\d{4}-\d{2}-\d{2}\.json',f.get('key',''))]
    paths += ['details/'+k+'.json' for k in sorted(index.get('details',{})) if re.fullmatch(r'[A-Za-z0-9:._-]+',k)]
    paths += ['catalog/'+k+'.json' for k in sorted(index.get('pages',{})) if re.fullmatch(r'(fond|etf)-\d+',k)]
    total=len(entries)+len(paths)
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        def add(name,value):
            nonlocal used
            raw=json.dumps(_redact(value),ensure_ascii=False,default=str,indent=2).encode()
            if used+len(raw)>MAX_RAW_BYTES-128*1024 and name!='controls.json':
                manifest['omitted'].append({'path':name,'reason':'RAW_BUDGET','bytes':len(raw)});return False
            z.writestr(name,raw);used+=len(raw)
            manifest['included'].append({'path':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
            return True
        for n,(name,value) in enumerate(entries):
            add(name,value)
            if progress:progress(n+1,total,name)
        frame_lookup={f['key'][len(PREFIX):]:f for f in archive.get('frames',[]) if f.get('key','').startswith(PREFIX)}
        for n,name in enumerate(paths,len(entries)+1):
            value=read(name,None)
            if value is None:manifest['omitted'].append({'path':name,'reason':'MISSING'})
            elif name in frame_lookup:
                try:
                    packed=base64.b64decode(value['gzip_base64'],validate=True)
                    if hashlib.sha256(packed).hexdigest()!=frame_lookup[name]['sha256']:raise ValueError('Sjekksumfeil')
                    with gzip.GzipFile(fileobj=BytesIO(packed)) as handle:raw=handle.read(12*1024*1024+1)
                    if len(raw)>12*1024*1024:raise ValueError('Historikkramme for stor')
                    frame=json.loads(raw)
                    exported='frames/'+name.split('/')[-1]
                    if not add(exported,frame):
                        if progress:progress(n,total,name)
                        continue
                    from superfund_engine import at
                    future=any(at(i.get('observed_at'))>at(frame['at']) or (i.get('price_at') and at(i['price_at'])>at(frame['at'])) or (i.get('detail',{}).get('verified_at') and at(i['detail']['verified_at'])>at(frame['at'])) for i in frame['items'])
                    checks.setdefault('frames',[]).append({'path':name,'checksum':'OK','future_evidence':bool(future)})
                except Exception as exc:
                    checks.setdefault('frames',[]).append({'path':name,'error':str(exc)[:150]})
                    manifest['omitted'].append({'path':name,'reason':'INVALID_FRAME'})
            else:add(name,value)
            if progress:progress(n,total,name)
        add('controls.json',checks)
        z.writestr('README.txt','Superfond diagnose. snapshot.json inneholder hovedmodell, læring, skygger, regler, handler og kandidater. controls.json viser kontrollfunn. manifest.json viser eksakt dekning, sjekksummer og utelatelser. Ingen nye analyser utført. Historikk som mangler eller er utelatt er ikke kontrollert. Nedlastingen krever innlogget app.\n')
        z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    if out.tell()>MAX_ZIP_BYTES:raise ValueError('Diagnose-ZIP overskrider 32 MiB')
    return out.getvalue(),'Superfond_diagnose_'+stamp[:10]+'.zip'
