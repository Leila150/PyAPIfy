"""PyAPIfy application: routing, injection, middleware, errors and lifecycle."""
from __future__ import annotations
import asyncio, inspect, json, os
from dataclasses import dataclass
from .routing.router import Router
from .http.request import Request
from .http.response import HTTPResponse,HTTP

class Depends:
    def __init__(self,dependency): self.dependency=dependency

def depends(fn): return Depends(fn)

class BackgroundTasks:
    def __init__(self): self.tasks=[]
    def add(self,fn,*args,**kwargs): self.tasks.append((fn,args,kwargs)); return self
    async def run(self):
        for fn,args,kwargs in self.tasks:
            r=fn(*args,**kwargs); await r if inspect.isawaitable(r) else asyncio.sleep(0)

class PyAPIfy:
    def __init__(self,title='PyAPIfy API',version='0.1.0',debug=False):
        self.title=title; self.version=version; self.debug=debug; self.router=Router(); self.middleware=[]; self.errors={}; self.startup=[]; self.shutdown=[]; self.plugins=[]
    def route(self,path,methods=None,**opts):
        methods=methods or ['GET']
        def deco(fn): self.router.add(path,fn,methods,name=opts.get('name'),auth=opts.get('auth'),tags=opts.get('tags',())); return fn
        return deco
    def _method(self,m): return lambda path,**kw: self.route(path,[m],**kw)
    get=_method(None,'GET') if False else None
    def middleware_handler(self,fn): self.middleware.append(fn); return fn
    middleware=middleware_handler
    def error_handler(self,key):
        def deco(fn): self.errors[key]=fn; return fn
        return deco
    def startup(self,fn): self.startup.append(fn); return fn
    def shutdown(self,fn): self.shutdown.append(fn); return fn
    def router_group(self,prefix='',**kw): return Router(prefix,**kw)
    def include(self,router): self.router.routes.extend(router.routes); return router
    def use(self,plugin): self.plugins.append(plugin); plugin.install(self) if hasattr(plugin,'install') else plugin(self); return plugin
    async def _call(self,fn,request,params):
        sig=inspect.signature(fn); kwargs={}; bg=BackgroundTasks()
        for name,p in sig.parameters.items():
            if name in params: kwargs[name]=params[name]; continue
            ann=p.annotation
            if name in ('request','req') or ann is Request: kwargs[name]=request
            elif name in ('params','query'): kwargs[name]=request.params
            elif name in ('headers',): kwargs[name]=request.headers
            elif name in ('cookies',): kwargs[name]=request.cookies
            elif name in ('body','data'):
                kwargs[name]=request.json if request.content_type=='application/json' else request.body
            elif name in ('form',): kwargs[name]=request.form
            elif name in ('background','background_tasks'): kwargs[name]=bg
            elif isinstance(p.default,Depends):
                d=p.default.dependency; val=d(request) if 'request' in inspect.signature(d).parameters else d(); kwargs[name]=await val if inspect.isawaitable(val) else val
            elif p.default is not inspect.Parameter.empty: kwargs[name]=p.default
        result=fn(**kwargs); result=await result if inspect.isawaitable(result) else result
        return result,bg
    def _auth(self,auth,request):
        if auth is None:return True
        values=auth if isinstance(auth,(list,tuple,set)) else [auth]
        supplied=request.headers.get('Authorization') or request.headers.get('X-API-Key')
        for v in values:
            if callable(v):
                r=v(request); r=asyncio.run(r) if inspect.iscoroutine(r) else r
                if r:return True
            elif supplied==v or supplied==f'Bearer {v}': return True
        return False
    async def dispatch(self,request):
        route,params=self.router.match(request.path,request.method)
        if route is None:
            methods=self.router.methods_for(request.path)
            if methods:return HTTP.status_code(status=405,detail='Method not allowed',headers={'Allow':', '.join(sorted(methods))})
            return HTTP.status_code(status=404,detail='Not found')
        if not self._auth(route.auth,request): return HTTP.status_code(status=401,detail='Authentication required',headers={'WWW-Authenticate':'Bearer'})
        async def terminal(req):
            result,bg=await self._call(route.endpoint,req,params)
            response=result if isinstance(result,HTTPResponse) else HTTPResponse(result)
            await bg.run(); return response
        nxt=terminal
        for mw in reversed(self.middleware):
            previous=nxt
            async def wrapped(req,mw=mw,previous=previous):
                r=mw(req,previous); return await r if inspect.isawaitable(r) else r
            nxt=wrapped
        try:return await nxt(request)
        except HTTPResponse as e:return e
        except Exception as e:
            handler=self.errors.get(type(e)) or self.errors.get(500)
            if handler:
                r=handler(e); r=await r if inspect.isawaitable(r) else r; return r if isinstance(r,HTTPResponse) else HTTPResponse(r,500)
            if self.debug:return HTTPResponse({'error':type(e).__name__,'detail':str(e)},500)
            return HTTPResponse({'detail':'Internal server error'},500)
    def test(self):
        from .testing.client import TestClient; return TestClient(self)
    def openapi(self):
        paths={}
        for r in self.router.routes:
            item=paths.setdefault(r.path,{})
            for m in r.methods:item[m.lower()]={'operationId':r.name,'tags':list(r.tags),'responses':{'200':{'description':'Success'}}}
        return {'openapi':'3.1.0','info':{'title':self.title,'version':self.version},'paths':paths}
    def run(self,host='127.0.0.1',port=8000,debug=None,**kwargs):
        from .server.server import serve; return serve(self,host,port,debug=self.debug if debug is None else debug,**kwargs)

# Attach method decorators without metaprogramming in the class body.
for _m in ('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS','TRACE','CONNECT'):
    setattr(PyAPIfy,_m.lower(),lambda self,path,_m=_m,**kw:self.route(path,[_m],**kw))
PyAPIfy.depends=staticmethod(depends)
