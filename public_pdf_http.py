"""Durable inline PDFs for native Pushover/iPhone viewers, without app sessions."""
from hashlib import sha256
from pathlib import PurePosixPath
import re
from urllib.parse import quote
from starlette.requests import Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response,RedirectResponse

TOKEN=re.compile(r'[A-Za-z0-9_-]{32,128}')
NO_STORE={'Cache-Control':'private, no-store, no-transform','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'}


def pdf_response(request):
    token=request.path_params['token']
    if not TOKEN.fullmatch(token):return Response('Rapporten finnes ikke eller er utløpt.',status_code=404,headers=NO_STORE)
    from public_report_store import load_public_pdf
    try:report=load_public_pdf(token)
    except Exception:
        return Response('Rapportlagringen er midlertidig utilgjengelig.',status_code=503,headers={**NO_STORE,'Retry-After':'60'})
    if not report:return Response('Rapporten finnes ikke eller er utløpt.',status_code=404,headers=NO_STORE)
    data=bytes(report['data']);size=len(data);etag='"'+sha256(data).hexdigest()+'"'
    name=PurePosixPath(str(report.get('filename') or 'rapport.pdf').replace('\\','/')).name
    name=name or 'rapport.pdf'
    if not name.lower().endswith('.pdf'):name+='.pdf'
    headers={**NO_STORE,'Content-Type':'application/pdf','Accept-Ranges':'bytes','ETag':etag,
        'Content-Disposition':"inline; filename=\"rapport.pdf\"; filename*=UTF-8''"+quote(name,safe='')}
    if request.headers.get('if-none-match')==etag:return Response(status_code=304,headers=headers)
    status=200
    value=request.headers.get('range','')
    if request.method=='GET' and value and request.headers.get('if-range',etag)==etag and ',' not in value:
        match=re.fullmatch(r'bytes=(\d{0,20})-(\d{0,20})',value.strip(),flags=re.I)
        start=end=None
        if match and any(match.groups()):
            left,right=match.groups()
            if left:start=int(left);end=min(int(right),size-1) if right else size-1
            elif int(right)>0:start=max(0,size-int(right));end=size-1
        if start is None or end is None or start> end or start>=size:
            return Response(status_code=416,headers={**headers,'Content-Range':'bytes */'+str(size)})
        data=data[start:end+1];status=206;headers['Content-Range']=f'bytes {start}-{end}/{size}'
    headers['Content-Length']=str(len(data))
    return Response(b'' if request.method=='HEAD' else data,status_code=status,headers=headers)


class ReportEntryMiddleware:
    """Old Pushover report links open the PDF; explicit page links retain the UI."""
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        # PDF readers request byte ranges. Serve these before Streamlit's
        # generic gzip middleware so offsets and Content-Length stay exact.
        if scope['type']=='http' and scope['method'] in {'GET','HEAD'}:
            match=re.fullmatch(r'/reports/([^/]+)\.pdf',scope['path'])
            if match:
                selected={**scope,'path_params':{'token':match.group(1)}}
                response=await run_in_threadpool(pdf_response,Request(selected))
                await response(scope,receive,send);return
        if scope['type']=='http' and scope['path']=='/' and scope['method'] in {'GET','HEAD'}:
            request=Request(scope)
            query=request.query_params
            if 'public_report_token' in query and 'public_file_token' not in query and query.get('report_view')!='page':
                tokens=query.getlist('public_report_token')
                if len(tokens)!=1 or not TOKEN.fullmatch(tokens[0]):
                    response=Response('Ugyldig rapportlenke.',status_code=404,headers=NO_STORE)
                else:response=RedirectResponse('/reports/'+tokens[0]+'.pdf',status_code=307,headers=NO_STORE)
                await response(scope,receive,send);return
        await self.app(scope,receive,send)
