"""Public API for building PyAPIfy-only extension plugins."""
from __future__ import annotations
import importlib.util, inspect, json, os, sys
from pathlib import Path
from .runtime import PluginCache, PyAPIfyRuntime


class Plugin:
    """Builder, registry and lifecycle object for a PyAPIfy extension plugin."""
    EXTENSION_KINDS = (
        'decorator','function','hook','route_type','middleware','command','config','test','run',
        'request_handler','response_type','http_method','status_code','converter','validator','model_type',
        'dependency','auth','permission','error_handler','lifecycle','task','schedule','openapi','documentation',
        'websocket','sse','html','css','js','gui','group','router','storage','cache','server','https',
        'log_handler','environment','plugin_extension'
    )
    BUILTIN_CONVERTERS = {'str','int','float','path','bool'}

    def __init__(self, root: str | os.PathLike[str] | None = None):
        self.root = Path(root).resolve() if root else self._discover_root()
        self._registry={}; self._app=None; self._metadata={}; self._loaded={}
        self._enabled=True; self._registered=False; self._started=False; self._used_plugins=[]; self._cache=None
        self._read_metadata()

    def _discover_root(self):
        for frame in inspect.stack()[1:]:
            filename=Path(frame.filename).resolve()
            if filename.name=='main.py': return filename.parent
        return Path.cwd().resolve()

    def _project_runtime_root(self):
        for parent in (self.root, *self.root.parents):
            if parent.name == '.pyapify': return parent
        return Path.cwd().resolve() / '.pyapify'

    def _read_metadata(self):
        path=self.root/'info.json'
        if path.is_file():
            try:
                data=json.loads(path.read_text(encoding='utf-8'))
                if isinstance(data,dict): self._metadata=data
            except (OSError,ValueError): self._metadata={}

    def load(self,path):
        target=(self.root/path).resolve()
        try: target.relative_to(self.root)
        except ValueError: raise ValueError('Plugin files must stay inside the plugin directory')
        if not target.is_file(): raise FileNotFoundError(target)
        module_name=f'pyapify_plugin_{self.name()}_{len(self._loaded)}'
        spec=importlib.util.spec_from_file_location(module_name,target)
        if spec is None or spec.loader is None: raise ImportError(f'Unable to load plugin file: {target}')
        module=importlib.util.module_from_spec(spec); sys.modules[module_name]=module; spec.loader.exec_module(module)
        self._loaded[str(target)]=module; return module

    def info(self): return dict(self._metadata)
    def path(self): return self.root
    def name(self): return self._metadata.get('name',self.root.name)
    def version(self): return self._metadata.get('version','0.0.0')
    def dependencies(self):
        value=self._metadata.get('dependencies',[])
        return list(value) if isinstance(value,(list,tuple,set)) else [value]
    def require(self,*dependencies):
        current=self._metadata.setdefault('dependencies',[])
        if not isinstance(current,list): current=list(current) if current else []; self._metadata['dependencies']=current
        for dependency in dependencies:
            if dependency not in current: current.append(dependency)
        return self

    def use(self, plugin):
        """Declare another PyAPIfy plugin as a runtime extension dependency."""
        if not isinstance(plugin, Plugin): raise TypeError('plugin.use() expects a Plugin instance')
        if plugin is self: raise ValueError('A plugin cannot use itself')
        if plugin not in self._used_plugins: self._used_plugins.append(plugin)
        if self._app is not None and plugin not in self._app.plugins: self._app.use(plugin)
        return plugin

    def used_plugins(self): return tuple(self._used_plugins)

    def cache(self, *, name=None):
        """Return this plugin's persistent cache in ``.pyapify/cache/plugins_cache``."""
        if self._cache is None or name is not None:
            runtime = self._app.runtime if self._app is not None and hasattr(self._app, 'runtime') else None
            self._cache = runtime.cache(name or self.name()) if runtime else PluginCache(self._project_runtime_root(), name or self.name())
        return self._cache

    def log(self, level='info', message='', *args, **kwargs):
        """Write a message to the active PyAPIfy project log."""
        if self._app is not None and hasattr(self._app, 'runtime'):
            return self._app.runtime.log(level, message, *args, **kwargs)
        runtime = PyAPIfyRuntime(self._project_runtime_root())
        try: return runtime.log(level, message, *args, **kwargs)
        finally: runtime.close()

    def _create(self,kind,name,value,**meta):
        if kind not in self.EXTENSION_KINDS: raise ValueError(f'Unknown PyAPIfy extension kind: {kind}')
        key=name or getattr(value,'__name__',None)
        if not key: raise ValueError(f'{kind} requires a name')
        if kind=='converter' and key in self.BUILTIN_CONVERTERS: raise ValueError(f'Cannot replace built-in converter: {key}')
        bucket=self._registry.setdefault(kind,{})
        if key in bucket: raise ValueError(f'{kind} already exists: {key}')
        item={'value':value,**meta}
        bucket[key]=item
        try:
            self._attach(kind,key,value,item)
        except Exception:
            bucket.pop(key,None)
            raise
        return value

    def _edit(self,kind,name,value=None,**meta):
        bucket=self._registry.setdefault(kind,{})
        if name not in bucket: raise KeyError(f'Unknown {kind}: {name}')
        if kind=='converter' and name in self.BUILTIN_CONVERTERS: raise ValueError(f'Cannot edit built-in converter: {name}')
        item=bucket[name]
        previous=dict(item)
        if value is not None: item['value']=value
        item.update(meta)
        try:
            self._attach(kind,name,item['value'],item)
        except Exception:
            item.clear()
            item.update(previous)
            raise
        return item['value']

    def _delete(self,kind,name):
        bucket=self._registry.setdefault(kind,{})
        if kind=='converter' and name in self.BUILTIN_CONVERTERS: raise ValueError(f'Cannot delete built-in converter: {name}')
        item=bucket.get(name)
        if item is None: raise KeyError(f'Unknown {kind}: {name}')
        self._detach(kind,name)
        bucket.pop(name,None)
        return item['value']

    def _attach(self,kind,name,value,meta):
        if self._app is not None and self._enabled: self._app._register_plugin_extension(kind,name,value,meta,self)
    def _detach(self,kind,name):
        if self._app is not None: self._app._unregister_plugin_extension(kind,name,self)

    def bind(self,app):
        previous_app=self._app
        previous_registered=self._registered
        attached=[]
        added_used=[]
        try:
            self._app=app
            for used in self._used_plugins:
                if used not in app.plugins:
                    app.use(used)
                    added_used.append(used)
            if self._enabled:
                for kind,items in self._registry.items():
                    for name,item in items.items():
                        self._attach(kind,name,item['value'],item)
                        attached.append((kind,name))
            self._registered=True
            return self
        except Exception:
            for kind,name in reversed(attached):
                try:
                    app._unregister_plugin_extension(kind,name,self)
                except Exception:
                    pass
            for used in reversed(added_used):
                try:
                    if used in app.plugins:
                        app.plugins.remove(used)
                except Exception:
                    pass
            self._app=previous_app
            self._registered=previous_registered
            raise
    def _decorator(self,kind,name=None,**meta):
        def register(value): return self._create(kind,name,value,**meta)
        return register

    def create_decorator(self,name=None,**meta): return self._decorator('decorator',name,**meta)
    def edit_decorator(self,name,value=None,**meta): return self._edit('decorator',name,value,**meta)
    def delete_decorator(self,name): return self._delete('decorator',name)
    def create_function(self,name=None,**meta): return self._decorator('function',name,**meta)
    def edit_function(self,name,value=None,**meta): return self._edit('function',name,value,**meta)
    def delete_function(self,name): return self._delete('function',name)
    def create_hook(self,name=None,**meta): return self._decorator('hook',name,**meta)
    def edit_hook(self,name,value=None,**meta): return self._edit('hook',name,value,**meta)
    def delete_hook(self,name): return self._delete('hook',name)
    def create_route_type(self,name=None,**meta): return self._decorator('route_type',name,**meta)
    def edit_route_type(self,name,value=None,**meta): return self._edit('route_type',name,value,**meta)
    def delete_route_type(self,name): return self._delete('route_type',name)
    def create_middleware(self,name=None,**meta): return self._decorator('middleware',name,**meta)
    def edit_middleware(self,name,value=None,**meta): return self._edit('middleware',name,value,**meta)
    def delete_middleware(self,name): return self._delete('middleware',name)
    def create_command(self,name=None,**meta): return self._decorator('command',name,**meta)
    def edit_command(self,name,value=None,**meta): return self._edit('command',name,value,**meta)
    def delete_command(self,name): return self._delete('command',name)
    def create_config(self,name=None,**meta): return self._decorator('config',name,**meta)
    def edit_config(self,name,value=None,**meta): return self._edit('config',name,value,**meta)
    def delete_config(self,name): return self._delete('config',name)
    def create_test(self,name=None,**meta): return self._decorator('test',name,**meta)
    def edit_test(self,name,value=None,**meta): return self._edit('test',name,value,**meta)
    def delete_test(self,name): return self._delete('test',name)
    def create_run(self,name=None,**meta): return self._decorator('run',name,**meta)
    def edit_run(self,name,value=None,**meta): return self._edit('run',name,value,**meta)
    def delete_run(self,name): return self._delete('run',name)
    def _simple_create(self,kind,name=None,**meta): return self._decorator(kind,name,**meta)
    def _simple_edit(self,kind,name,value=None,**meta): return self._edit(kind,name,value,**meta)
    def _simple_delete(self,kind,name): return self._delete(kind,name)

    @classmethod
    def _install_extension_methods(cls):
        for kind in cls.EXTENSION_KINDS:
            if hasattr(cls,f'create_{kind}'): continue
            setattr(cls,f'create_{kind}',lambda self,name=None,_k=kind,**meta:self._simple_create(_k,name,**meta))
            setattr(cls,f'edit_{kind}',lambda self,name,value=None,_k=kind,**meta:self._simple_edit(_k,name,value,**meta))
            setattr(cls,f'delete_{kind}',lambda self,name,_k=kind:self._simple_delete(_k,name))
    def __getattr__(self,attr):
        if attr.startswith('create_'): return lambda name=None,**meta:self._simple_create(attr[7:],name,**meta)
        if attr.startswith('edit_'): return lambda name,value=None,**meta:self._simple_edit(attr[5:],name,value,**meta)
        if attr.startswith('delete_'): return lambda name:self._simple_delete(attr[7:],name)
        raise AttributeError(attr)

    def register(self):
        self._registered=True
        if self._app is not None: self.bind(self._app)
        return self
    def unregister(self):
        if self._app is not None and self._registered:
            detached=[]
            try:
                for kind,items in self._registry.items():
                    for name in list(items):
                        self._detach(kind,name)
                        detached.append((kind,name))
            except Exception:
                for kind,name in detached:
                    try:
                        item=self._registry[kind][name]
                        self._attach(kind,name,item['value'],item)
                    except Exception:
                        pass
                raise
        self._registered=False
        self._started=False
        return self

    def enable(self):
        if self._enabled:
            return self
        self._enabled=True
        try:
            if self._app is not None:
                self.bind(self._app)
        except Exception:
            self._enabled=False
            raise
        return self

    def disable(self):
        if not self._enabled:
            return self
        if self._app is not None:
            detached=[]
            try:
                for kind,items in self._registry.items():
                    for name in list(items):
                        self._detach(kind,name)
                        detached.append((kind,name))
            except Exception:
                for kind,name in detached:
                    try:
                        item=self._registry[kind][name]
                        self._attach(kind,name,item['value'],item)
                    except Exception:
                        pass
                raise
        self._enabled=False
        self._started=False
        return self
    def enabled(self): return self._enabled
    def is_registered(self): return self._registered
    def started(self): return self._started
    def startup(self,app):
        if not self._enabled or self._started: return None
        hook=self._registry.get('hook',{}).get('startup')
        if hook:
            result=hook['value'](app)
            if inspect.isawaitable(result):
                async def finish():
                    await result
                    self._started=True
                return finish()
        self._started=True
        return None
    def shutdown(self,app):
        if not self._started: return None
        hook=self._registry.get('hook',{}).get('shutdown')
        if hook:
            result=hook['value'](app)
            if inspect.isawaitable(result):
                async def finish():
                    await result
                    self._started=False
                return finish()
        self._started=False
        return None
    def uninstall(self,app=None):
        target=app or self._app
        detached=[]
        try:
            if target is not None:
                for kind,items in self._registry.items():
                    for name in list(items):
                        target._unregister_plugin_extension(kind,name,self)
                        detached.append((kind,name))
        except Exception:
            if target is not None:
                for kind,name in reversed(detached):
                    try:
                        item=self._registry[kind][name]
                        target._register_plugin_extension(kind,name,item['value'],item,self)
                    except Exception:
                        pass
            raise
        for module_name in list(sys.modules):
            if module_name.startswith(f'pyapify_plugin_{self.name()}_'):
                sys.modules.pop(module_name, None)
        self._loaded.clear()
        self._app=None
        self._registered=False
        self._started=False
        return self
    def state(self):
        return {
            'name': self.name(),
            'version': self.version(),
            'path': str(self.path()),
            'enabled': self.enabled(),
            'registered': self.is_registered(),
            'started': self.started(),
            'capabilities': tuple(sorted(self.capabilities())),
        }
    def capabilities(self): return set(self._registry)


Plugin._install_extension_methods()
