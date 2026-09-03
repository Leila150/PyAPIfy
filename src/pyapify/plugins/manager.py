"""Plugin registry with dependency checks and lifecycle management."""
import importlib
class PluginManager:
    def __init__(self,app): self.app=app; self.plugins={}
    def register(self,plugin):
        name=getattr(plugin,'name',plugin.__class__.__name__)
        if name in self.plugins: raise ValueError(f'Plugin already registered: {name}')
        for dep in getattr(plugin,'requires',()):
            if dep not in self.plugins: raise RuntimeError(f'Missing plugin dependency: {dep}')
        plugin.install(self.app); self.plugins[name]=plugin; return plugin
    def load(self,target):
        obj=target
        if isinstance(target,str):
            mod,_,attr=target.partition(':'); obj=getattr(importlib.import_module(mod),attr) if attr else importlib.import_module(mod)
        if isinstance(obj,type): obj=obj()
        return self.register(obj)
    def get(self,name): return self.plugins.get(name)
    def capabilities(self): return {cap for p in self.plugins.values() for cap in p.capabilities()}
    async def startup(self):
        for p in self.plugins.values(): await p.startup(self.app)
    async def shutdown(self):
        for p in reversed(list(self.plugins.values())): await p.shutdown(self.app)
    def remove(self,name):
        p=self.plugins.pop(name); p.uninstall(self.app); return p
