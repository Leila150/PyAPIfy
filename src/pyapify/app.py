"""PyAPIfy application runtime and extension integration."""
from __future__ import annotations
import inspect, typing, types
from .routing.router import Router
from .http.request import Request
from .http.response import HTTPResponse, HTTP
from .http.status import validate_status
from .plugins.manager import PluginManager
from .routing.route import register_converter, unregister_converter


class Depends:
    def __init__(self, dependency, *, use_cache=True):
        self.dependency, self.use_cache = dependency, use_cache


def depends(fn, *, use_cache=True):
    return Depends(fn, use_cache=use_cache)


class BackgroundTasks:
    def __init__(self): self.tasks = []
    def add(self, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs)); return self
    async def run(self):
        for fn, args, kwargs in self.tasks:
            result = fn(*args, **kwargs)
            if inspect.isawaitable(result): await result


class PyAPIfy:
    """The central PyAPIfy application object.

    Plugins extend this object and its registries; they do not become a
    general-purpose Python plugin system.
    """
    def __init__(self, title='PyAPIfy API', version='0.1.0', debug=False, *, auth=None, max_body_size=16*1024*1024, docs=True, **properties):
        self.title, self.version, self.debug = title, version, debug
        self.name = properties.pop('name', self.title)
        self.description = properties.pop('description', '')
        self.author = properties.pop('author', '')
        self.environment = properties.pop('environment', 'development' if debug else 'production')
        self.charset = properties.pop('charset', 'utf-8')
        self.encoding = properties.pop('encoding', 'utf-8')
        self.host = properties.pop('host', '0.0.0.0')
        self.port = properties.pop('port', 8080)
        self.workers = properties.pop('workers', 1)
        self.timeout = properties.pop('timeout', None)
        self.extra_properties = properties
        self.router = Router()
        self._middleware, self.errors = [], {}
        self._startup, self._shutdown = [], []
        self.plugins, self.plugin_manager = [], PluginManager(self)
        self.auth, self.max_body_size = auth, max_body_size
        self._started = False
        self._plugin_extensions, self._plugin_hooks = {}, {}
        self.validators, self.model_types, self.dependencies = {}, {}, {}
        self.auth_providers, self.permissions = {}, {}
        self.route_types, self.http_methods, self.status_codes = {}, set(), {}
        self.request_handlers, self.response_types = {}, {}
        self.tasks, self.schedules = {}, {}
        self.openapi_extensions, self.documentation = {}, {}
        self.websocket_extensions, self.sse_extensions = {}, {}
        self.html_extensions, self.css_extensions, self.js_extensions = {}, {}, {}
        self.gui_extensions, self.groups, self.routers = {}, {}, {}
        self.storage_extensions, self.cache_extensions = {}, {}
        self.server_extensions, self.https_extensions = {}, {}
        self.log_handlers, self.environments = {}, {}
        self.plugin_extensions_registry = {}
        self.commands, self.tests = {}, {}
        if docs:
            self.get('/openapi.json', route_name='openapi')(lambda: self.openapi())
            self.get('/docs', route_name='docs')(lambda: HTTP.html('<!doctype html><html><head><meta charset="utf-8"><title>'+self.title+' — Docs</title><script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui-bundle.js"></script><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui.css"></head><body><div id="swagger-ui"></div><script>SwaggerUIBundle({url:"/openapi.json",dom_id:"#swagger-ui"})</script></body></html>'))
            self.get('/redoc', route_name='redoc')(lambda: HTTP.html('<!doctype html><html><head><meta charset="utf-8"><title>'+self.title+' — ReDoc</title><script src="https://cdn.jsdelivr.net/npm/redoc@latest/bundles/redoc.standalone.js"></script></head><body><redoc spec-url="/openapi.json"></redoc></body></html>'))

    def _register_plugin_extension(self, kind, name, value, meta, plugin):
        bucket = self._plugin_extensions.setdefault(kind, {})
        old = bucket.get(name)
        if old and old[1] is not plugin:
            raise ValueError(f'Plugin extension already exists: {kind}:{name}')
        bucket[name] = (value, plugin, dict(meta))
        if kind == 'converter': register_converter(name, value)
        elif kind == 'validator': self.validators[name] = value
        elif kind == 'model_type': self.model_types[name] = value
        elif kind == 'dependency': self.dependencies[name] = value
        elif kind == 'auth': self.auth_providers[name] = value
        elif kind == 'permission': self.permissions[name] = value
        elif kind == 'error_handler': self.errors[name] = value
        elif kind == 'route_type': self.route_types[name] = value
        elif kind == 'http_method': self.http_methods.add(name.upper())
        elif kind == 'status_code': self.status_codes[name] = value
        elif kind in ('request_handler','response_type'): getattr(self, kind+'s')[name] = value
        elif kind in ('task','schedule'): getattr(self, kind+'s')[name] = value
        elif kind == 'openapi': self.openapi_extensions[name] = value
        elif kind == 'documentation': self.documentation[name] = value
        elif kind in ('websocket','sse','html','css','js','gui'): getattr(self, kind+'_extensions')[name] = value
        elif kind in ('group','router'): getattr(self, kind+'s')[name] = value
        elif kind in ('storage','cache','server','https','log_handler','environment'): getattr(self, kind+'_extensions' if kind in ('storage','cache','server','https') else ('log_handlers' if kind=='log_handler' else 'environments'))[name] = value
        elif kind == 'plugin_extension': self.plugin_extensions_registry[name] = value
        elif kind == 'command': self.commands[name] = value
        elif kind == 'test': self.tests[name] = value
        elif kind in ('function','run','decorator'):
            if hasattr(self, name) and name not in self._plugin_extensions.get(kind, {}):
                raise ValueError(f'Plugin extension conflicts with app attribute: {name}')
            def extension(*args, __value=value, **kwargs): return __value(self, *args, **kwargs)
            extension.__name__ = name; extension.__doc__ = getattr(value, '__doc__', None); setattr(self, name, extension)
        elif kind == 'hook': self._plugin_hooks[name] = value
        elif kind == 'middleware':
            if value not in self._middleware: self._middleware.append(value)
        elif kind == 'lifecycle':
            phase = meta.get('phase') or name
            (self._startup if phase in ('startup','start') else self._shutdown if phase in ('shutdown','stop') else self._startup).append(value)

    def _unregister_plugin_extension(self, kind, name, plugin):
        item = self._plugin_extensions.get(kind, {}).get(name)
        if not item or item[1] is not plugin: return
        value = item[0]; self._plugin_extensions[kind].pop(name, None)
        if kind == 'converter': unregister_converter(name)
        elif kind == 'validator': self.validators.pop(name, None)
        elif kind == 'model_type': self.model_types.pop(name, None)
        elif kind == 'dependency': self.dependencies.pop(name, None)
        elif kind == 'auth': self.auth_providers.pop(name, None)
        elif kind == 'permission': self.permissions.pop(name, None)
        elif kind == 'error_handler': self.errors.pop(name, None)
        elif kind == 'route_type': self.route_types.pop(name, None)
        elif kind == 'http_method': self.http_methods.discard(name.upper())
        elif kind == 'status_code': self.status_codes.pop(name, None)
        elif kind in ('request_handler','response_type'): getattr(self, kind+'s').pop(name, None)
        elif kind in ('task','schedule'): getattr(self, kind+'s').pop(name, None)
        elif kind == 'openapi': self.openapi_extensions.pop(name, None)
        elif kind == 'documentation': self.documentation.pop(name, None)
        elif kind in ('websocket','sse','html','css','js','gui'): getattr(self, kind+'_extensions').pop(name, None)
        elif kind in ('group','router'): getattr(self, kind+'s').pop(name, None)
        elif kind in ('storage','cache','server','https'): getattr(self, kind+'_extensions').pop(name, None)
        elif kind == 'log_handler': self.log_handlers.pop(name, None)
        elif kind == 'environment': self.environments.pop(name, None)
        elif kind == 'plugin_extension': self.plugin_extensions_registry.pop(name, None)
        elif kind == 'command': self.commands.pop(name, None)
        elif kind == 'test': self.tests.pop(name, None)
        elif kind in ('function','run','decorator'):
            current = getattr(self, name, None)
            if current is not None and getattr(current, '__name__', None) == name: delattr(self, name)
        elif kind == 'hook': self._plugin_hooks.pop(name, None)
        elif kind == 'middleware': self._middleware = [mw for mw in self._middleware if mw is not value]

    def plugin_extensions(self, kind=None):
        if kind is None: return {k: dict(v) for k,v in self._plugin_extensions.items()}
        return dict(self._plugin_extensions.get(kind, {}))

    def route(self, path, methods=None, *, route_name=None, name=None, **opts):
        methods = methods or ['GET']; logical_name = route_name or name
        def deco(fn):
            self.router.add(path, fn, methods, name=logical_name, auth=opts.get('auth', self.auth), tags=opts.get('tags', ()), websocket=opts.get('websocket', False)); return fn
        return deco
    def any(self, path, **opts): return self.route(path, ['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS','TRACE','CONNECT'], **opts)
    def sse(self, path, **opts):
        def deco(fn):
            async def endpoint(**kwargs):
                result = fn(**kwargs); result = await result if inspect.isawaitable(result) else result; return HTTP.sse(result)
            endpoint.__name__ = getattr(fn, '__name__', 'sse'); endpoint.__doc__ = fn.__doc__; return self.route(path, ['GET'], **opts)(endpoint)
        return deco
    def websocket(self, path, **opts): opts['websocket'] = True; return self.route(path, ['GET'], **opts)
    def middleware(self, fn=None):
        if fn is None: return lambda f: self.middleware(f)
        self._middleware.append(fn); return fn
    def add_middleware(self, middleware, *args, **kwargs): return self.middleware(middleware(*args, **kwargs) if inspect.isclass(middleware) else middleware)
    def error_handler(self, key):
        def deco(fn): self.errors[key] = fn; return fn
        return deco
    def startup(self, fn): self._startup.append(fn); return fn
    def shutdown(self, fn): self._shutdown.append(fn); return fn
    def router_group(self, prefix='', **kw): return Router(prefix, **kw)
    def group(self, prefix='', **kw):
        group = Router(prefix, auth=kw.get('auth', self.auth), tags=kw.get('tags', ())); self.routers[id(group)] = group; return group
    def include(self, router): self.router.routes.extend(router.routes); return router
    def use(self, plugin): self.plugin_manager.register(plugin); self.plugins.append(plugin); return plugin
    async def _lifecycle(self, funcs):
        for fn in funcs:
            result = fn(); result = await result if inspect.isawaitable(result) else result
    async def startup_async(self):
        if not self._started: await self.plugin_manager.startup(); await self._lifecycle(self._startup); self._started = True
    async def shutdown_async(self):
        if self._started: await self._lifecycle(reversed(self._shutdown)); await self.plugin_manager.shutdown(); self._started = False
    async def _resolve_dependency(self, dep, request, cache):
        if dep.use_cache and dep.dependency in cache: return cache[dep.dependency]
        fn, kwargs = dep.dependency, {}
        for name, p in inspect.signature(fn).parameters.items():
            if name in ('request','req') or p.annotation is Request: kwargs[name] = request
            elif name in request.params: kwargs[name] = _convert(request.params[name], p.annotation)
            elif isinstance(p.default, Depends): kwargs[name] = await self._resolve_dependency(p.default, request, cache)
            elif p.default is not inspect.Parameter.empty: kwargs[name] = p.default
            else: raise TypeError(f'Missing dependency parameter: {name}')
        value = fn(**kwargs); value = await value if inspect.isawaitable(value) else value
        if dep.use_cache: cache[fn] = value
        return value
    async def _call(self, fn, request, params, websocket=None):
        from .validation.models import Model
        sig, kwargs, bg, cache = inspect.signature(fn), {}, BackgroundTasks(), {}
        for name, p in sig.parameters.items():
            if name in params: kwargs[name] = params[name]; continue
            ann = p.annotation
            if name in ('socket','websocket'): kwargs[name] = websocket
            elif name in ('request','req') or ann is Request: kwargs[name] = request
            elif name in ('params','query'): kwargs[name] = request.params
            elif name == 'headers': kwargs[name] = request.headers
            elif name == 'cookies': kwargs[name] = request.cookies
            elif name in ('body','data'): kwargs[name] = request.json if request.content_type and request.content_type.split(';',1)[0].lower()=='application/json' else request.body
            elif name == 'form': kwargs[name] = request.form
            elif name in ('file','upload'): kwargs[name] = next(iter(request.files.values()), None)
            elif name in ('files','uploads'): kwargs[name] = request.files
            elif name in ('background','background_tasks'): kwargs[name] = bg
            elif isinstance(p.default, Depends): kwargs[name] = await self._resolve_dependency(p.default, request, cache)
            elif inspect.isclass(ann) and issubclass(ann, Model):
                payload = request.json
                if not isinstance(payload, dict): raise TypeError('Model body must be a JSON object')
                kwargs[name] = ann(**payload)
            elif name in request.params: kwargs[name] = _convert(request.params[name], ann)
            elif p.default is not inspect.Parameter.empty: kwargs[name] = p.default
            elif _is_optional(ann): kwargs[name] = None
            else: raise TypeError(f'Missing required parameter: {name}')
        result = fn(**kwargs); result = await result if inspect.isawaitable(result) else result; return result, bg
    async def _auth_async(self, auth, request):
        if auth is None: return True
        providers = auth if isinstance(auth,(list,tuple,set)) else [auth]
        for provider in providers:
            result = provider.authenticate(request) if hasattr(provider,'authenticate') else provider(request) if callable(provider) else ((request.headers.get('Authorization') or request.headers.get('X-API-Key')) in (provider, f'Bearer {provider}'))
            if inspect.isawaitable(result): result = await result
            if result: return True
        return False
    async def dispatch(self, request):
        if len(request.body) > self.max_body_size: return HTTP.status_code(code=413, detail='Request body too large')
        route, params = self.router.match(request.path, request.method)
        if route is None:
            methods = self.router.methods_for(request.path)
            return HTTP.status_code(code=405, detail='Method not allowed', headers={'Allow': ', '.join(sorted(methods))}) if methods else HTTP.status_code(code=404, detail='Not found')
        if route.websocket: return HTTP.status_code(code=426, detail='WebSocket upgrade required', headers={'Upgrade':'websocket'})
        if not await self._auth_async(route.auth, request): return HTTP.status_code(code=401, detail='Authentication required', headers={'WWW-Authenticate':'Bearer'})
        async def terminal(req):
            result, bg = await self._call(route.endpoint, req, params); response = result if isinstance(result, HTTPResponse) else HTTPResponse(result); await bg.run(); return response
        nxt = terminal
        for mw in reversed(self._middleware):
            previous = nxt
            async def wrapped(req, mw=mw, previous=previous):
                result = mw(req, previous); return await result if inspect.isawaitable(result) else result
            nxt = wrapped
        try: return await nxt(request)
        except HTTPResponse as e: return e
        except Exception as e:
            handler = self.errors.get(type(e)) or self.errors.get(500) or self.errors.get('*')
            if handler:
                result = handler(e); result = await result if inspect.isawaitable(result) else result; return result if isinstance(result,HTTPResponse) else HTTPResponse(result,500)
            return HTTPResponse({'error':type(e).__name__,'detail':str(e)} if self.debug else {'detail':'Internal server error'},500)
    def test(self): from .testing.client import TestClient; return TestClient(self)
    def openapi(self):
        from .validation.models import Model
        paths, components = {}, {'schemas': {}}
        injection={'request','req','headers','cookies','body','data','form','file','upload','files','uploads','background','background_tasks','params','query','socket','websocket'}
        for r in self.router.routes:
            item = paths.setdefault(r.path, {})
            for method in sorted(r.methods):
                op={'operationId':r.name or r.endpoint.__name__,'responses':{'200':{'description':'Success'}}}
                if r.tags: op['tags']=list(r.tags)
                params=[]; path_names={n for n,_ in getattr(r,'param_names',[])}
                for name, typ in getattr(r,'param_names',[]): params.append({'name':name,'in':'path','required':True,'schema':{'type':{'int':'integer','float':'number','bool':'boolean'}.get(typ,'string')}})
                try:
                    sig=inspect.signature(r.endpoint)
                    for name,p in sig.parameters.items():
                        if name in injection or isinstance(p.default,Depends) or name in path_names: continue
                        if p.annotation is not inspect.Parameter.empty: params.append({'name':name,'in':'query','required':p.default is inspect.Parameter.empty,'schema':_annotation_schema(p.annotation,components)})
                    for p in sig.parameters.values():
                        if inspect.isclass(p.annotation) and issubclass(p.annotation,Model):
                            model=p.annotation; components['schemas'][model.__name__]=model.model_json_schema(); op['requestBody']={'required':True,'content':{'application/json':{'schema':{'$ref':f'#/components/schemas/{model.__name__}'}}}}; break
                except (TypeError,ValueError): pass
                if params: op['parameters']=params
                if r.auth: op['security']=[{'ApiKeyAuth':[]}]
                item[method.lower()] = op
        doc={'openapi':'3.1.0','info':{'title':self.title,'version':self.version,'description':self.description},'paths':paths}
        if components['schemas']: doc['components']=components
        for name, extension in self.openapi_extensions.items():
            result = extension(doc, self) if callable(extension) else None
            if result is not None: doc = result
        return doc
    def run(self, host=None, port=None, debug=None, **kwargs):
        from .server.server import serve
        return serve(self, host or self.host, port or self.port, debug=self.debug if debug is None else debug, **kwargs)


def _is_optional(annotation):
    origin=typing.get_origin(annotation); return origin in (typing.Union,types.UnionType) and type(None) in typing.get_args(annotation)

def _convert(value, annotation):
    if annotation is inspect.Parameter.empty or annotation is str or annotation is typing.Any: return value
    if _is_optional(annotation):
        non_none=[x for x in typing.get_args(annotation) if x is not type(None)]; return None if value in ('','null','None') else _convert(value,non_none[0])
    origin=typing.get_origin(annotation)
    if origin in (typing.Union,types.UnionType):
        for t in typing.get_args(annotation):
            try: return _convert(value,t)
            except (TypeError,ValueError): pass
    if annotation is bool: return str(value).lower() in ('1','true','yes','on')
    if annotation in (int,float): return annotation(value)
    return value

def _annotation_schema(annotation, components):
    from .validation.models import Model
    if inspect.isclass(annotation) and issubclass(annotation,Model): components['schemas'][annotation.__name__]=annotation.model_json_schema(); return {'$ref':f'#/components/schemas/{annotation.__name__}'}
    origin,args=typing.get_origin(annotation),typing.get_args(annotation)
    if origin in (list,typing.List): return {'type':'array','items':_annotation_schema(args[0] if args else str,components)}
    if annotation is int:return {'type':'integer'}
    if annotation is float:return {'type':'number'}
    if annotation is bool:return {'type':'boolean'}
    return {'type':'string'}

for _m in ('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS','TRACE','CONNECT'):
    setattr(PyAPIfy, _m.lower(), lambda self, path, _m=_m, **kw: self.route(path, [_m], **kw))
PyAPIfy.depends = staticmethod(depends)
