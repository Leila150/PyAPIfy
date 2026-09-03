"""PyAPIfy application: routing, injection, middleware, errors and lifecycle."""
from __future__ import annotations
import asyncio, inspect
from .routing.router import Router
from .http.request import Request
from .http.response import HTTPResponse, HTTP
from .plugins.manager import PluginManager

class Depends:
    def __init__(self, dependency, *, use_cache=True): self.dependency, self.use_cache = dependency, use_cache

def depends(fn, *, use_cache=True): return Depends(fn, use_cache=use_cache)

class BackgroundTasks:
    def __init__(self): self.tasks=[]
    def add(self, fn, *args, **kwargs): self.tasks.append((fn,args,kwargs)); return self
    async def run(self):
        for fn,args,kwargs in self.tasks:
            result=fn(*args,**kwargs)
            if inspect.isawaitable(result): await result

class PyAPIfy:
    def __init__(self, title='PyAPIfy API', version='0.1.0', debug=False, *, auth=None, max_body_size=16*1024*1024):
        self.title=title; self.version=version; self.debug=debug; self.router=Router(); self._middleware=[]
        self.errors={}; self._startup=[]; self._shutdown=[]; self.plugins=[]; self.plugin_manager=PluginManager(self)
        self.auth=auth; self.max_body_size=max_body_size; self._started=False
    def route(self, path, methods=None, **opts):
        methods=methods or ['GET']
        def deco(fn):
            self.router.add(path,fn,methods,name=opts.get('name'),auth=opts.get('auth',self.auth),tags=opts.get('tags',()))
            return fn
        return deco
    def any(self,path,**opts): return self.route(path,['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS','TRACE','CONNECT'],**opts)
    def middleware(self, fn=None):
        if fn is None: return lambda f: self.middleware(f)
        self._middleware.append(fn); return fn
    def add_middleware(self, middleware, *args, **kwargs):
        instance=middleware(*args,**kwargs) if inspect.isclass(middleware) else middleware
        return self.middleware(instance)
    def error_handler(self,key):
        def deco(fn): self.errors[key]=fn; return fn
        return deco
    def startup(self,fn): self._startup.append(fn); return fn
    def shutdown(self,fn): self._shutdown.append(fn); return fn
    def router_group(self,prefix='',**kw): return Router(prefix,**kw)
    def include(self,router): self.router.routes.extend(router.routes); return router
    def use(self,plugin): self.plugin_manager.register(plugin); self.plugins.append(plugin); return plugin
    async def _lifecycle(self, funcs):
        for fn in funcs:
            result=fn()
            if inspect.isawaitable(result): await result
    async def startup_async(self):
        if not self._started:
            await self.plugin_manager.startup(); await self._lifecycle(self._startup); self._started=True
    async def shutdown_async(self):
        if self._started:
            await self._lifecycle(reversed(self._shutdown)); await self.plugin_manager.shutdown(); self._started=False
    async def _resolve_dependency(self, dep, request, cache):
        if dep.use_cache and dep.dependency in cache: return cache[dep.dependency]
        fn=dep.dependency; sig=inspect.signature(fn); kwargs={}
        for name,p in sig.parameters.items():
            if name in ('request','req') or p.annotation is Request: kwargs[name]=request
            elif isinstance(p.default,Depends): kwargs[name]=await self._resolve_dependency(p.default,request,cache)
            elif p.default is not inspect.Parameter.empty: kwargs[name]=p.default
            else: raise TypeError(f'Missing dependency parameter: {name}')
        value=fn(**kwargs); value=await value if inspect.isawaitable(value) else value
        if dep.use_cache: cache[fn]=value
        return value
    async def _call(self,fn,request,params):
        sig=inspect.signature(fn); kwargs={}; bg=BackgroundTasks(); cache={}
        for name,p in sig.parameters.items():
            if name in params: kwargs[name]=params[name]; continue
            ann=p.annotation
            if name in ('request','req') or ann is Request: kwargs[name]=request
            elif name in ('params','query'): kwargs[name]=request.params
            elif name=='headers': kwargs[name]=request.headers
            elif name=='cookies': kwargs[name]=request.cookies
            elif name in ('body','data'): kwargs[name]=request.json if request.content_type=='application/json' else request.body
            elif name=='form': kwargs[name]=request.form
            elif name in ('background','background_tasks'): kwargs[name]=bg
            elif isinstance(p.default,Depends): kwargs[name]=await self._resolve_dependency(p.default,request,cache)
            elif p.default is not inspect.Parameter.empty: kwargs[name]=p.default
            else: raise TypeError(f'Missing required parameter: {name}')
        result=fn(**kwargs); result=await result if inspect.isawaitable(result) else result
        return result,bg
    async def _auth_async(self,auth,request):
        if auth is None:return True
        values=auth if isinstance(auth,(list,tuple,set)) else [auth]
        for provider in values:
            if hasattr(provider,'authenticate'):
                result=provider.authenticate(request)
            elif callable(provider):
                result=provider(request)
            else:
                supplied=request.headers.get('Authorization') or request.headers.get('X-API-Key')
                result=supplied==provider or supplied==f'Bearer {provider}'
            if inspect.isawaitable(result): result=await result
            if result:return True
        return False
    async def dispatch(self,request):
        if len(request.body)>self.max_body_size: return HTTP.status_code(status=413,detail='Request body too large')
        route,params=self.router.match(request.path,request.method)
        if route is None:
            methods=self.router.methods_for(request.path)
            return HTTP.status_code(status=405,detail='Method not allowed',headers={'Allow':', '.join(sorted(methods))}) if methods else HTTP.status_code(status=404,detail='Not found')
        if not await self._auth_async(route.auth,request): return HTTP.status_code(status=401,detail='Authentication required',headers={'WWW-Authenticate':'Bearer'})
        async def terminal(req):
            result,bg=await self._call(route.endpoint,req,params); response=result if isinstance(result,HTTPResponse) else HTTPResponse(result); await bg.run(); return response
        nxt=terminal
        for mw in reversed(self._middleware):
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
            return HTTPResponse({'error':type(e).__name__,'detail':str(e)} if self.debug else {'detail':'Internal server error'},500)
    def test(self):
        from .testing.client import TestClient; return TestClient(self)
    def openapi(self):
        paths={}
        for r in self.router.routes:
            item=paths.setdefault(r.path,{})
            for m in r.methods:
                item[m.lower()]={'operationId':r.name or r.endpoint.__name__,'tags':list(r.tags),'responses':{'200':{'description':'Success'}}}
        return {'openapi':'3.1.0','info':{'title':self.title,'version':self.version},'paths':paths}
    def run(self,host='127.0.0.1',port=8000,debug=None,**kwargs):
        from .server.server import serve; return serve(self,host,port,debug=self.debug if debug is None else debug,**kwargs)

for _m in ('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS','TRACE','CONNECT'):
    setattr(PyAPIfy,_m.lower(),lambda self,path,_m=_m,**kw:self.route(path,[_m],**kw))
PyAPIfy.depends=staticmethod(depends)
