"""Rich HTTP responses. Response objects are also raisable for ergonomic errors."""
from __future__ import annotations
import json, mimetypes
from http.cookies import SimpleCookie
from pathlib import Path
from collections.abc import Iterable
from .status import validate_status, Status

class HTTPResponse(Exception):
    def __init__(self,data=None,status=200,*,detail=None,headers=None,content_type=None):
        super().__init__(detail); self.data=data; self.status=validate_status(status); self.detail=detail
        self.headers={str(k):str(v) for k,v in (headers or {}).items()}; self.content_type=content_type; self.cookies=SimpleCookie()
    def header(self,name,value): self.headers[str(name)]=str(value); return self
    def cookie(self,name,value,**kwargs):
        self.cookies[name]=value
        for k,v in kwargs.items():
            key={'max_age':'max-age','http_only':'httponly','same_site':'samesite'}.get(k,k.replace('_','-'))
            self.cookies[name][key]=v
        return self
    def _body_iter(self):
        data=self.data
        if self.detail is not None and data is None: data={'detail':self.detail}
        if data is None: return iter(())
        if isinstance(data,bytes): return iter((data,))
        if isinstance(data,str): return iter((data.encode('utf-8'),))
        if isinstance(data,dict): return iter((json.dumps(data,ensure_ascii=False,separators=(',',':'),default=str).encode('utf-8'),))
        if isinstance(data,(list,tuple,set)):
            return iter((json.dumps(data,ensure_ascii=False,separators=(',',':'),default=str).encode('utf-8'),))
        if isinstance(data,Iterable):
            def chunks():
                for chunk in data:
                    if chunk is None: continue
                    yield chunk if isinstance(chunk,bytes) else str(chunk).encode('utf-8')
            return chunks()
        return iter((json.dumps(data,ensure_ascii=False,default=str).encode('utf-8'),))
    def _headers(self,body_length=None):
        headers=dict(self.headers)
        if self.content_type and not any(k.lower()=='content-type' for k in headers): headers['Content-Type']=self.content_type
        elif not any(k.lower()=='content-type' for k in headers) and self.data is not None:
            headers['Content-Type']='application/json; charset=utf-8' if not isinstance(self.data,(str,bytes)) else ('text/plain; charset=utf-8' if isinstance(self.data,str) else 'application/octet-stream')
        if body_length is not None: headers.setdefault('Content-Length',str(body_length))
        if self.cookies:
            for morsel in self.cookies.values():
                existing=headers.get('Set-Cookie'); value=morsel.OutputString(); headers['Set-Cookie']=f'{existing}\n{value}' if existing else value
        return headers
    def serialize(self):
        body=b''.join(self._body_iter()); return self.status,self._headers(len(body)),body

class HTTP:
    OK=Status.OK; CREATED=Status.CREATED; ACCEPTED=Status.ACCEPTED; NO_CONTENT=Status.NO_CONTENT; BAD_REQUEST=Status.BAD_REQUEST; UNAUTHORIZED=Status.UNAUTHORIZED; FORBIDDEN=Status.FORBIDDEN; NOT_FOUND=Status.NOT_FOUND; METHOD_NOT_ALLOWED=Status.METHOD_NOT_ALLOWED; UNPROCESSABLE_CONTENT=Status.UNPROCESSABLE_CONTENT; TOO_MANY_REQUESTS=Status.TOO_MANY_REQUESTS; INTERNAL_SERVER_ERROR=Status.INTERNAL_SERVER_ERROR; NOT_IMPLEMENTED=Status.NOT_IMPLEMENTED; SERVICE_UNAVAILABLE=Status.SERVICE_UNAVAILABLE
    @staticmethod
    def status_code(data=None,*,status=200,detail=None,headers=None): return HTTPResponse(data,status,detail=detail,headers=headers)
    @staticmethod
    def response(data=None,*,status=200,headers=None): return HTTPResponse(data,status,headers=headers)
    @staticmethod
    def json(data,*,status=200,headers=None): return HTTPResponse(data,status,headers=headers,content_type='application/json; charset=utf-8')
    @staticmethod
    def text(data,*,status=200,headers=None): return HTTPResponse(str(data),status,headers=headers,content_type='text/plain; charset=utf-8')
    @staticmethod
    def html(data,*,status=200,headers=None): return HTTPResponse(str(data),status,headers=headers,content_type='text/html; charset=utf-8')
    @staticmethod
    def xml(data,*,status=200,headers=None): return HTTPResponse(str(data),status,headers=headers,content_type='application/xml; charset=utf-8')
    @staticmethod
    def bytes(data,*,status=200,headers=None): return HTTPResponse(bytes(data),status,headers=headers,content_type='application/octet-stream')
    @staticmethod
    def file(path,*,status=200,filename=None,headers=None):
        p=Path(path)
        if not p.is_file(): raise FileNotFoundError(str(p))
        h=dict(headers or {}); h.setdefault('Content-Disposition',f'attachment; filename="{filename or p.name}"'); h.setdefault('Content-Type',mimetypes.guess_type(p.name)[0] or 'application/octet-stream')
        return HTTPResponse(p.read_bytes(),status,headers=h)
    @staticmethod
    def stream(chunks,*,status=200,content_type='application/octet-stream',headers=None): return HTTPResponse(chunks,status,headers=headers,content_type=content_type)
    @staticmethod
    def sse(events,*,headers=None):
        def encode():
            for event in events:
                if isinstance(event,dict):
                    if 'id' in event: yield f'id: {event["id"]}\n'.encode()
                    if 'event' in event: yield f'event: {event["event"]}\n'.encode()
                    if 'retry' in event: yield f'retry: {event["retry"]}\n'.encode()
                    data=event.get('data',event.get('message',''))
                else: data=event
                for line in str(data).splitlines() or ['']: yield f'data: {line}\n'.encode()
                yield b'\n'
        h={'Cache-Control':'no-cache','Connection':'keep-alive','X-Accel-Buffering':'no'}; h.update(headers or {}); return HTTPResponse(encode(),200,headers=h,content_type='text/event-stream')
    @staticmethod
    def redirect(url,*,status=302,headers=None): h=dict(headers or {}); h['Location']=url; return HTTPResponse(None,status,headers=h)
    @staticmethod
    def empty(*,status=204,headers=None): return HTTPResponse(None,status,headers=headers)

# Tiny status helpers keep normal endpoints readable while retaining the full API.
def _shortcut(status):
    def make(data=None, *, detail=None, headers=None):
        return HTTPResponse(data, status, detail=detail, headers=headers)
    return staticmethod(make)

HTTP.ok = _shortcut(HTTP.OK)
HTTP.created = _shortcut(HTTP.CREATED)
HTTP.accepted = _shortcut(HTTP.ACCEPTED)
HTTP.no_content = staticmethod(lambda *, headers=None: HTTPResponse(None, HTTP.NO_CONTENT, headers=headers))
HTTP.bad_request = _shortcut(HTTP.BAD_REQUEST)
HTTP.unauthorized = _shortcut(HTTP.UNAUTHORIZED)
HTTP.forbidden = _shortcut(HTTP.FORBIDDEN)
HTTP.not_found = _shortcut(HTTP.NOT_FOUND)
HTTP.method_not_allowed = _shortcut(HTTP.METHOD_NOT_ALLOWED)
HTTP.unprocessable = _shortcut(HTTP.UNPROCESSABLE_CONTENT)
HTTP.too_many_requests = _shortcut(HTTP.TOO_MANY_REQUESTS)
HTTP.server_error = _shortcut(HTTP.INTERNAL_SERVER_ERROR)
