"""PyAPIfy application: routing, validation, injection, middleware, errors and lifecycle."""
from __future__ import annotations
import inspect, typing, types
from .routing.router import Router
from .http.request import Request
from .http.response import HTTPResponse, HTTP
from .plugins.manager import PluginManager

class Depends:
    def __init__(self, dependency, *, use_cache=True): self.dependency,self.use_cache=dependency,use_cache

def depends(fn, *, use_cache=True): return Depends(fn,use_cache=use_cache)

class BackgroundTasks:
    def __init__(self): self.tasks=[]
    def add(self,fn,*args,**kwargs): self.tasks.append((fn,args,kwargs)); return self
    async def run(self):
        for fn,args,kwargs in self.tasks:
            result=fn(*args,**kwargs); result=await result if inspect.isawaitable(result) else result

class PyAPIfy:
    def __init__(self,title='PyAPIfy API',version='0.1.0',debug=False,*,auth=None,max_body_size=16*1024*1024,docs=True):
        self.title,self.version,self.debug=title,version,debug; self.router=Router(); self._middleware=[]; self.errors={}; self._startup=[]; self._shutdown=[]; self.plugins=[]; self.plugin_manager=PluginManager(self); self.auth=auth; self.max_body_size=max_body_size; self._started=False
        if docs:
            self.get('/openapi.json',name='openapi')(lambda:self.openapi())
            self.get('/docs',name='docs')(lambda:HTTP.html('<!doctype html><html><head><meta charset="utf-8"><title>'+self.title+' — Docs</title><script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui-bundle.js"></script><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui.css"></head><body><div id="swagger-ui"></div><script>SwaggerUIBundle({url:"/openapi.json",dom_id:"#swagger-ui"})</script></div></body></html>'))
            self.get('/redoc',name='redoc')(lambda:HTTP.html('<!doctype html><html><head><meta charset="utf-8"><title>'+self.title+' — ReDoc</title><script src="https://cdn.jsdelivr.net/npm/redoc@latest/bundles/redoc.standalone.js"></script></head><body><redoc spec-url="/openapi.json"></redoc></body></html>'))
    def route(self,path,methods=None,**opts):
        methods=methods or ['GET']
        def deco(fn): self.router.add(path,fn,methods,name=opts.get('name'),auth=opts.get('auth',self.auth),tags=opts.get('tags',()),websocket=opts.get('websocket',False)); return fn
        return deco
    def any(self,path,**opts): return self.route(path,['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS','TRACE','CONNECT'],**opts)
    def sse(self,path,**opts):
        def deco(fn):
            async def endpoint(**kwargs):
                result=fn(**kwargs); result=await result if inspect.isawaitable(result) else result; return HTTP.sse(result)
            endpoint.__name__=getattr(fn,'__name__','sse'); endpoint.__doc__=fn.__doc__; return self.route(path,['GET'],**opts)(endpoint)
        return deco
    def websocket(self,path,**opts): opts['websocket']=True; return self.route(path,['GET'],**opts)
    def middleware(self,fn=None):
        if fn is None:return lambda f:self.middleware(f)
        self._middleware.append(fn); return fn
    def add_middleware(self,middleware,*args,**kwargs): return self.middleware(middleware(*args,**kwargs) if inspect.isclass(middleware) else middleware)
    def error_handler(self,key):
        def deco(fn): self.errors[key]=fn; return fn
        return deco
    def startup(self,fn): self._startup.append(fn); return fn
    def shutdown(self,fn): self._shutdown.append(fn); return fn
    def router_group(self,prefix='',**kw): return Router(prefix,**kw)
    def include(self,router): self.router.routes.extend(router.routes); return router
    def use(self,plugin): self.plugin_manager.register(plugin); self.plugins.append(plugin); return plugin
    async def _lifecycle(self,funcs):
        for fn in funcs:
            result=fn(); result=await result if inspect.isawaitable(result) else result
    async def startup_async(self):
        if not self._started: await self.plugin_manager.startup(); await self._lifecycle(self._startup); self._started=True
    async def shutdown_async(self):
        if self._started: await self._lifecycle(reversed(self._shutdown)); await self.plugin_manager.shutdown(); self._started=False
    async def _resolve_dependency(self,dep,request,cache):
        if dep.use_cache and dep.dependency in cache:return cache[dep.dependency]
        fn=dep.dependency; kwargs={}
        for name,p in inspect.signature(fn).parameters.items():
            if name in ('request','req') or p.annotation is Request: kwargs[name]=request
            elif name in request.params: kwargs[name]=_convert(request.params[name],p.annotation)
            elif isinstance(p.default,Depends): kwargs[name]=await self._resolve_dependency(p.default,request,cache)
            elif p.default is not inspect.Parameter.empty: kwargs[name]=p.default
            else: raise TypeError(f'Missing dependency parameter: {name}')
        value=fn(**kwargs); value=await value if inspect.isawaitable(value) else value
        if dep.use_cache: cache[fn]=value
        return value
    async def _call(self,fn,request,params,websocket=None):
        from .validation.models import Model
        sig=inspect.signature(fn); kwargs={}; bg=BackgroundTasks(); cache={}
        for name,p in sig.parameters.items():
            if name in params: kwargs[name]=params[name]; continue
            ann=p.annotation
            if name in ('socket','websocket'): kwargs[name]=websocket
            elif name in ('request','req') or ann is Request: kwargs[name]=request
            elif name in ('params','query'): kwargs[name]=request.params
            elif name=='headers': kwargs[name]=request.headers
            elif name=='cookies': kwargs[name]=request.cookies
            elif name in ('body','data'): kwargs[name]=request.json if request.content_type and request.content_type.split(';',1)[0].lower()=='application/json' else request.body
            elif name=='form': kwargs[name]=request.form
            elif name in ('file','upload'): kwargs[name]=next(iter(request.files.values()),None)
            elif name in ('files','uploads'): kwargs[name]=request.files
            elif name in ('background','background_tasks'): kwargs[name]=bg
            elif isinstance(p.default,Depends): kwargs[name]=await self._resolve_dependency(p.default,request,cache)
            elif inspect.isclass(ann) and issubclass(ann,Model):
                payload=request.json
                if not isinstance(payload,dict): raise TypeError('Model body must be a JSON object')
                kwargs[name]=ann(**payload)
            elif name in request.params: kwargs[name]=_convert(request.params[name],ann)
            elif p.default is not inspect.Parameter.empty: kwargs[name]=p.default
            elif _is_optional(ann): kwargs[name]=None
            else: raise TypeError(f'Missing required parameter: {name}')
        result=fn(**kwargs); result=await result if inspect.isawaitable(result) else result; return result,bg
    async def _auth_async(self,auth,request):
        if auth is None:return True
        for provider in auth if isinstance(auth,(list,tuple,set)) else [auth]:
            result=provider.authenticate(request) if hasattr(provider,'authenticate') else provider(request) if callable(provider) else ((request.headers.get('Authorization') or request.headers.get('X-API-Key')) in (provider,f'Bearer {provider}'))
            if inspect.isawaitable(result):result=await result
            if result:return True
        return False
    async def dispatch(self,request):
        if len(request.body)>self.max_body_size:return HTTP.status_code(status=413,detail='Request body too large')
        route,params=self.router.match(request.path,request.method)
        if route is None:
            methods=self.router.methods_for(request.path); return HTTP.status_code(status=405,detail='Method not allowed',headers={'Allow':', '.join(sorted(methods))}) if methods else HTTP.status_code(status=404,detail='Not found')
        if route.websocket:return HTTP.status_code(status=426,detail='WebSocket upgrade required',headers={'Upgrade':'websocket'})
        if not await self._auth_async(route.auth,request):return HTTP.status_code(status=401,detail='Authentication required',headers={'WWW-Authenticate':'Bearer'})
        async def terminal(req):
            result,bg=await self._call(route.endpoint,req,params); response=result if isinstance(result,HTTPResponse) else HTTPResponse(result); await bg.run(); return response
        nxt=terminal
        for mw in reversed(self._middleware):
            previous=nxt
            async def wrapped(req,mw=mw,previous=previous):
                result=mw(req,previous); return await result if inspect.isawaitable(result) else result
            nxt=wrapped
        try:return await nxt(request)
        except HTTPResponse as e:return e
        except Exception as e:
            handler=self.errors.get(type(e)) or self.errors.get(500)
            if handler:
                result=handler(e); result=await result if inspect.isawaitable(result) else result; return result if isinstance(result,HTTPResponse) else HTTPResponse(result,500)
            return HTTPResponse({'error':type(e).__name__,'detail':str(e)} if self.debug else {'detail':'Internal server error'},500)
    def test(self):from .testing.client import TestClient;return TestClient(self)
    def openapi(self):
        from .validation.models import Model
        paths={}; components={'schemas':{}}; injection={'request','req','headers','cookies','body','data','form','file','upload','files','uploads','background','background_tasks','params','query','socket','websocket'}
        for r in self.router.routes:
            item=paths.setdefault(r.path,{})
            for method in sorted(r.methods):
                op={'operationId':r.name or r.endpoint.__name__,'responses':{'200':{'description':'Success'}}};
                if r.tags:op['tags']=list(r.tags)
                params=[]; path_names={n for n,_ in getattr(r,'param_names',[])}
                for name,typ in getattr(r,'param_names',[]):params.append({'name':name,'in':'path','required':True,'schema':{'type':{'int':'integer','float':'number','bool':'boolean'}.get(typ,'string')}})
                try:
                    sig=inspect.signature(r.endpoint)
                    for name,p in sig.parameters.items():
                        if name in injection or isinstance(p.default,Depends) or name in path_names:continue
                        if p.annotation is not inspect.Parameter.empty:params.append({'name':name,'in':'query','required':p.default is inspect.Parameter.empty,'schema':_annotation_schema(p.annotation,components)})
                    for p in sig.parameters.values():
                        if inspect.isclass(p.annotation) and issubclass(p.annotation,Model):
                            model=p.annotation; components['schemas'][model.__name__]=model.model_json_schema(); op['requestBody']={'required':True,'content':{'application/json':{'schema':{'$ref':f'#/components/schemas/{model.__name__}'}}}}; break
                except (TypeError,ValueError):pass
                if params:op['parameters']=params
                if r.auth:op['security']=[{'ApiKeyAuth':[]}]
                item[method.lower()]=op
        doc={'openapi':'3.1.0','info':{'title':self.title,'version':self.version},'paths':paths};
        if components['schemas']:doc['components']=components
        return doc
    def run(self,host='0.0.0.0',port=8080,debug=None,**kwargs):
        """Start the PyAPIfy development server with automatic HTTPS by default.

        Pass ``certfile`` and ``keyfile`` to use an existing certificate. Set
        ``https=False`` when plain HTTP is explicitly desired.
        """
        from .server.server import serve; return serve(self,host,port,debug=self.debug if debug is None else debug,**kwargs)

def _is_optional(annotation):
    origin=typing.get_origin(annotation); return origin in (typing.Union,types.UnionType) and type(None) in typing.get_args(annotation)

def _convert(value,annotation):
    if annotation is inspect.Parameter.empty or annotation is str or annotation is typing.Any:return value
    if _is_optional(annotation):
        non_none=[x for x in typing.get_args(annotation) if x is not type(None)]; return None if value in ('','null','None') else _convert(value,non_none[0])
    origin=typing.get_origin(annotation)
    if origin in (typing.Union,types.UnionType):
        for t in typing.get_args(annotation):
            try:return _convert(value,t)
            except (TypeError,ValueError):pass
    if annotation is bool:return str(value).lower() in ('1','true','yes','on')
    if annotation in (int,float):return annotation(value)
    return value

def _annotation_schema(annotation,components):
    from .validation.models import Model
    if inspect.isclass(annotation) and issubclass(annotation,Model):components['schemas'][annotation.__name__]=annotation.model_json_schema();return {'$ref':f'#/components/schemas/{annotation.__name__}'}
    origin=typing.get_origin(annotation);args=typing.get_args(annotation)
    if origin in (list,typing.List):return {'type':'array','items':_annotation_schema(args[0] if args else str,components)}
    if annotation is int:return {'type':'integer'}
    if annotation is float:return {'type':'number'}
    if annotation is bool:return {'type':'boolean'}
    return {'type':'string'}

for _m in ('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS','TRACE','CONNECT'):setattr(PyAPIfy,_m.lower(),lambda self,path,_m=_m,**kw:self.route(path,[_m],**kw))
PyAPIfy.depends=staticmethod(depends)
