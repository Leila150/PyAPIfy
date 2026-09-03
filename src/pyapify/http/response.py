"""Rich HTTP responses. Response objects are also raisable for ergonomic errors."""
from __future__ import annotations
import json, mimetypes
from http.cookies import SimpleCookie
from pathlib import Path
from .status import validate_status, Status

class HTTPResponse(Exception):
    def __init__(self,data=None,status=200,*,detail=None,headers=None,content_type=None):
        super().__init__(detail); self.data=data; self.status=validate_status(status); self.detail=detail; self.headers={str(k):str(v) for k,v in (headers or {}).items()}; self.content_type=content_type; self.cookies=SimpleCookie()
    def header(self,name,value): self.headers[str(name)]=str(value); return self
    def cookie(self,name,value,**kwargs):
        self.cookies[name]=value
        for k,v in kwargs.items(): self.cookies[name][{'max_age':'max-age','http_only':'httponly','same_site':'samesite'}.get(k,k.replace('_','-'))]=v
        return self
    def serialize(self):
        data=self.data
        if self.detail is not None and data is None:data={'detail':self.detail}
        if data is None: body=b''
        elif isinstance(data,bytes): body=data
        elif isinstance(data,str): body=data.encode()
        elif hasattr(data,'__iter__') and not isinstance(data,(dict,list,tuple,set)): body=b''.join(x if isinstance(x,bytes) else str(x).encode() for x in data)
        else: body=json.dumps(data,ensure_ascii=False,separators=(',',':'),default=str).encode()
        headers=dict(self.headers)
        if self.content_type and 'Content-Type' not in headers:headers['Content-Type']=self.content_type
        elif 'Content-Type' not in headers and body:headers['Content-Type']='application/json; charset=utf-8' if not isinstance(data,(str,bytes)) else ('text/plain; charset=utf-8' if isinstance(data,str) else 'application/octet-stream')
        headers.setdefault('Content-Length',str(len(body)))
        if self.cookies:headers['Set-Cookie']='; '.join(m.OutputString() for m in self.cookies.values())
        return self.status,headers,body

class HTTP:
    OK=Status.OK; CREATED=Status.CREATED; ACCEPTED=Status.ACCEPTED; NO_CONTENT=Status.NO_CONTENT; BAD_REQUEST=Status.BAD_REQUEST; UNAUTHORIZED=Status.UNAUTHORIZED; FORBIDDEN=Status.FORBIDDEN; NOT_FOUND=Status.NOT_FOUND; METHOD_NOT_ALLOWED=Status.METHOD_NOT_ALLOWED; UNPROCESSABLE_CONTENT=Status.UNPROCESSABLE_CONTENT; TOO_MANY_REQUESTS=Status.TOO_MANY_REQUESTS; INTERNAL_SERVER_ERROR=Status.INTERNAL_SERVER_ERROR; NOT_IMPLEMENTED=Status.NOT_IMPLEMENTED; SERVICE_UNAVAILABLE=Status.SERVICE_UNAVAILABLE
    @staticmethod
    def status_code(data=None,*,status=200,detail=None,headers=None):return HTTPResponse(data,status,detail=detail,headers=headers)
    @staticmethod
    def response(data=None,*,status=200,headers=None):return HTTPResponse(data,status,headers=headers)
    @staticmethod
    def json(data,*,status=200,headers=None):return HTTPResponse(data,status,headers=headers,content_type='application/json; charset=utf-8')
    @staticmethod
    def text(data,*,status=200,headers=None):return HTTPResponse(str(data),status,headers=headers,content_type='text/plain; charset=utf-8')
    @staticmethod
    def html(data,*,status=200,headers=None):return HTTPResponse(str(data),status,headers=headers,content_type='text/html; charset=utf-8')
    @staticmethod
    def xml(data,*,status=200,headers=None):return HTTPResponse(str(data),status,headers=headers,content_type='application/xml; charset=utf-8')
    @staticmethod
    def bytes(data,*,status=200,headers=None):return HTTPResponse(bytes(data),status,headers=headers,content_type='application/octet-stream')
    @staticmethod
    def file(path,*,status=200,filename=None,headers=None):
        p=Path(path); h=dict(headers or {}); h.setdefault('Content-Disposition',f'attachment; filename="{filename or p.name}"'); h.setdefault('Content-Type',mimetypes.guess_type(p.name)[0] or 'application/octet-stream'); return HTTPResponse(p.read_bytes(),status,headers=h)
    @staticmethod
    def stream(chunks,*,status=200,content_type='application/octet-stream',headers=None):return HTTPResponse(chunks,status,headers=headers,content_type=content_type)
    @staticmethod
    def sse(events,*,headers=None):
        def encode():
            for event in events:
                if isinstance(event,dict):
                    if 'id' in event:yield f'id: {event["id"]}\n'.encode()
                    if 'event' in event:yield f'event: {event["event"]}\n'.encode()
                    data=event.get('data',event.get('message',''))
                else:data=event
                for line in str(data).splitlines() or ['']:yield f'data: {line}\n'.encode()
                yield b'\n'
        h={'Cache-Control':'no-cache','Connection':'keep-alive','X-Accel-Buffering':'no'}; h.update(headers or {}); return HTTPResponse(encode(),200,headers=h,content_type='text/event-stream')
    @staticmethod
    def redirect(url,*,status=302,headers=None):h=dict(headers or {});h['Location']=url;return HTTPResponse(None,status,headers=h)
    @staticmethod
    def empty(*,status=204,headers=None):return HTTPResponse(None,status,headers=headers)
