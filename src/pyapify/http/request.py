"""Incoming request abstraction with cached parsing helpers and multipart uploads."""
from __future__ import annotations
import json, re
from urllib.parse import urlsplit,parse_qs
from http.cookies import SimpleCookie

class Headers(dict):
    def __getitem__(self,k):
        for key,val in self.items():
            if key.lower()==k.lower(): return val
        raise KeyError(k)
    def get(self,k,default=None):
        try:return self[k]
        except KeyError:return default

class UploadFile:
    def __init__(self,name,filename,content_type,data,headers=None):
        self.name=name; self.filename=filename; self.content_type=content_type or 'application/octet-stream'; self.data=data; self.headers=Headers(headers or {})
    @property
    def size(self): return len(self.data)
    async def read(self,size=-1): return self.data if size<0 else self.data[:size]
    async def write(self,data): self.data += bytes(data); return len(data)
    async def close(self): return None

class Request:
    def __init__(self,method='GET',target='/',headers=None,body=b'',client=None,scheme='http'):
        self.method=method.upper(); self.url=target; self.scheme=scheme; self.headers=Headers(headers or {}); self.body=body if isinstance(body,bytes) else bytes(body or b''); self.client=client; self.id=self.headers.get('X-Request-ID')
        p=urlsplit(target); self.path=p.path or '/'; self.query_string=p.query; self.params={k:(v[-1] if len(v)==1 else v) for k,v in parse_qs(p.query,keep_blank_values=True).items()}
        self._json=None; self._form=None; self._cookies=None; self._files=None
    @property
    def text(self): return self.body.decode(self.headers.get('Content-Type','').split('charset=')[-1] if 'charset=' in self.headers.get('Content-Type','') else 'utf-8',errors='replace')
    @property
    def json(self):
        if self._json is None: self._json=json.loads(self.body.decode('utf-8') or 'null')
        return self._json
    @property
    def form(self):
        if self._form is None:
            if self.content_type=='multipart/form-data': self._parse_multipart()
            else: self._form={k:(v[-1] if len(v)==1 else v) for k,v in parse_qs(self.body.decode(),keep_blank_values=True).items()}
        return self._form
    @property
    def files(self):
        if self._files is None and self.content_type=='multipart/form-data': self._parse_multipart()
        return self._files or {}
    def _parse_multipart(self):
        match=re.search(r'boundary=(?:"([^"]+)"|([^;]+))',self.headers.get('Content-Type',''),re.I)
        if not match: raise ValueError('multipart/form-data boundary is missing')
        boundary=(match.group(1) or match.group(2)).encode(); self._form={}; self._files={}
        for part in self.body.split(b'--'+boundary)[1:]:
            if part in (b'--',b'--\r\n',b''): continue
            part=part.strip(b'\r\n-')
            if b'\r\n\r\n' not in part: continue
            raw_headers,data=part.split(b'\r\n\r\n',1); ph={}
            for line in raw_headers.decode('iso-8859-1').split('\r\n'):
                if ':' in line: k,v=line.split(':',1); ph[k.strip()]=v.strip()
            cd=ph.get('Content-Disposition',''); nm=re.search(r'name="([^"]*)"',cd); fm=re.search(r'filename="([^"]*)"',cd)
            if not nm: continue
            name=nm.group(1)
            if fm:
                upload=UploadFile(name,fm.group(1),ph.get('Content-Type'),data,ph); self._files[name]=upload
            else: self._form[name]=data.decode('utf-8','replace')
    @property
    def cookies(self):
        if self._cookies is None:
            c=SimpleCookie(self.headers.get('Cookie','')); self._cookies={k:v.value for k,v in c.items()}
        return self._cookies
    @property
    def content_type(self): return self.headers.get('Content-Type','').split(';',1)[0].strip().lower()
    @property
    def content_length(self):
        try:return int(self.headers.get('Content-Length','0'))
        except ValueError:return 0
    @property
    def host(self): return self.headers.get('Host','').split(':')[0]
    @property
    def port(self):
        try:return int(self.headers.get('Host','').rsplit(':',1)[1])
        except (ValueError,IndexError):return 443 if self.scheme=='https' else 80
    @property
    def client_ip(self): return self.client[0] if isinstance(self.client,tuple) else self.client
    async def body_async(self): return self.body
    async def json_async(self): return self.json
    async def form_async(self): return self.form
    async def stream(self,chunk_size=65536):
        for i in range(0,len(self.body),chunk_size): yield self.body[i:i+chunk_size]
