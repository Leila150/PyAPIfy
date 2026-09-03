"""Incoming request abstraction with cached parsing helpers."""
from __future__ import annotations
import json
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

class Request:
    def __init__(self,method='GET',target='/',headers=None,body=b'',client=None,scheme='http'):
        self.method=method.upper(); self.url=target; self.scheme=scheme; self.headers=Headers(headers or {}); self.body=body if isinstance(body,bytes) else bytes(body or b''); self.client=client; self.id=self.headers.get('X-Request-ID')
        p=urlsplit(target); self.path=p.path or '/'; self.query_string=p.query; self.params={k:(v[-1] if len(v)==1 else v) for k,v in parse_qs(p.query,keep_blank_values=True).items()}
        self._json=None; self._form=None; self._cookies=None
    @property
    def text(self): return self.body.decode(self.headers.get('Content-Type','').split('charset=')[-1] if 'charset=' in self.headers.get('Content-Type','') else 'utf-8',errors='replace')
    @property
    def json(self):
        if self._json is None: self._json=json.loads(self.body.decode('utf-8') or 'null')
        return self._json
    @property
    def form(self):
        if self._form is None: self._form={k:(v[-1] if len(v)==1 else v) for k,v in parse_qs(self.body.decode(),keep_blank_values=True).items()}
        return self._form
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
