"""Production-oriented middleware that depends only on PyAPIfy primitives."""
from __future__ import annotations
import time, uuid, asyncio
from collections import defaultdict, deque
from ..http.response import HTTPResponse, HTTP

class CORSMiddleware:
    def __init__(self, allow_origins='*', allow_methods='*', allow_headers='*', allow_credentials=False, max_age=600):
        self.allow_origins=allow_origins; self.allow_methods=allow_methods; self.allow_headers=allow_headers; self.allow_credentials=allow_credentials; self.max_age=max_age
    async def __call__(self, request, next):
        origin=request.headers.get('Origin')
        if request.method=='OPTIONS' and origin:
            response=HTTP.empty(status=204)
        else: response=await next(request)
        if not isinstance(response,HTTPResponse): response=HTTPResponse(response)
        if origin and (self.allow_origins=='*' or origin in self.allow_origins): response.header('Access-Control-Allow-Origin',origin if self.allow_origins!='*' or self.allow_credentials else '*')
        elif self.allow_origins=='*': response.header('Access-Control-Allow-Origin','*')
        response.header('Access-Control-Allow-Methods', self.allow_methods if isinstance(self.allow_methods,str) else ', '.join(self.allow_methods))
        response.header('Access-Control-Allow-Headers', self.allow_headers if isinstance(self.allow_headers,str) else ', '.join(self.allow_headers))
        response.header('Access-Control-Max-Age',self.max_age)
        if self.allow_credentials: response.header('Access-Control-Allow-Credentials','true')
        return response

class SecurityHeadersMiddleware:
    def __init__(self, *, content_security_policy=None, hsts=False): self.csp=content_security_policy; self.hsts=hsts
    async def __call__(self, request, next):
        response=await next(request)
        if not isinstance(response,HTTPResponse): response=HTTPResponse(response)
        defaults={'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'strict-origin-when-cross-origin','Permissions-Policy':'geolocation=(), microphone=(), camera=()'}
        for k,v in defaults.items(): response.headers.setdefault(k,v)
        if self.csp: response.headers.setdefault('Content-Security-Policy',self.csp)
        if self.hsts and request.scheme=='https': response.headers.setdefault('Strict-Transport-Security','max-age=31536000; includeSubDomains')
        return response

class RequestIDMiddleware:
    def __init__(self, header='X-Request-ID'): self.header=header
    async def __call__(self, request, next):
        rid=request.headers.get(self.header) or str(uuid.uuid4())
        request.id=rid
        response=await next(request)
        if not isinstance(response,HTTPResponse): response=HTTPResponse(response)
        response.header(self.header,rid); return response

class TimingMiddleware:
    def __init__(self, header='X-Response-Time'): self.header=header
    async def __call__(self, request, next):
        start=time.perf_counter(); response=await next(request)
        if not isinstance(response,HTTPResponse): response=HTTPResponse(response)
        response.header(self.header,f'{(time.perf_counter()-start)*1000:.3f}ms'); return response

class RateLimitMiddleware:
    def __init__(self, limit=60, window=60, key=lambda request: request.client_ip):
        self.limit,self.window,self.key=limit,window,key; self._hits=defaultdict(deque)
    async def __call__(self, request, next):
        now=time.monotonic(); key=self.key(request); q=self._hits[key]
        while q and now-q[0]>=self.window: q.popleft()
        if len(q)>=self.limit: return HTTP.status_code(status=429,detail='Rate limit exceeded',headers={'Retry-After':str(max(1,int(self.window-(now-q[0]))))})
        q.append(now); return await next(request)
