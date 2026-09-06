"""Runtime manager for PyAPIfy-only plugins."""
from __future__ import annotations
import importlib
import os
from pathlib import Path
from .api import Plugin
from .runtime import PyAPIfyRuntime


class PluginManager:
    def __init__(self, app):
        self.app = app
        self.plugins = {}
        self.runtime = PyAPIfyRuntime()
        self.runtime.log('info', 'PyAPIfy plugin runtime initialized at %s', self.runtime.root)

    @staticmethod
    def default_directory():
        explicit = os.environ.get('PYAPIFY_PLUGIN_DIR')
        if explicit: return Path(explicit).expanduser()
        android = Path('/storage/emulated/0/.pyapify/plugins')
        if android.is_dir() or Path('/storage/emulated/0').is_dir(): return android
        return Path.home() / '.pyapify' / 'plugins'

    def register(self, plugin):
        if not isinstance(plugin, Plugin): raise TypeError('PyAPIfy plugins must be Plugin instances')
        name = plugin.name()
        if name in self.plugins: raise ValueError(f'Plugin already registered: {name}')
        for dep in plugin.dependencies():
            dep_name = dep.get('name') if isinstance(dep, dict) else str(dep)
            if dep_name and dep_name not in self.plugins: raise RuntimeError(f'Missing plugin dependency: {dep_name}')
        plugin.bind(self.app); self.plugins[name] = plugin
        self.runtime.log('info', 'Plugin registered: %s %s', name, plugin.version())
        return plugin

    def load(self, target):
        if isinstance(target, (str, Path)) and Path(target).is_dir():
            root = Path(target).resolve(); main = root / 'main.py'
            if not main.is_file(): raise FileNotFoundError(f'Plugin entry point not found: {main}')
            plugin = Plugin(root); plugin.load('main.py'); return self.register(plugin)
        obj = target
        if isinstance(target, str):
            mod, _, attr = target.partition(':')
            obj = getattr(importlib.import_module(mod), attr) if attr else importlib.import_module(mod)
        if isinstance(obj, type): obj = obj()
        return self.register(obj)

    def discover(self, directory=None):
        root = Path(directory).expanduser() if directory else self.default_directory()
        root.mkdir(parents=True, exist_ok=True)
        loaded=[]
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child/'main.py').is_file():
                try:
                    loaded.append(self.load(child))
                except Exception:
                    self.runtime.logger.exception('Failed to load plugin: %s', child)
        return loaded

    def get(self, name): return self.plugins.get(name)
    def capabilities(self): return {cap for p in self.plugins.values() for cap in p.capabilities()}
    def extension_map(self): return {name: p.capabilities() for name,p in self.plugins.items()}
    def cache(self, plugin_name='pyapify'):
        return self.runtime.cache(plugin_name)
    def log(self, level='info', message='', *args, **kwargs):
        return self.runtime.log(level, message, *args, **kwargs)

    async def startup(self):
        for p in self.plugins.values():
            try:
                result=p.startup(self.app)
                if hasattr(result,'__await__'): await result
                self.runtime.log('info', 'Plugin started: %s', p.name())
            except Exception:
                self.runtime.logger.exception('Plugin startup failed: %s', p.name())
                raise
    async def shutdown(self):
        for p in reversed(list(self.plugins.values())):
            try:
                result=p.shutdown(self.app)
                if hasattr(result,'__await__'): await result
                self.runtime.log('info', 'Plugin stopped: %s', p.name())
            except Exception:
                self.runtime.logger.exception('Plugin shutdown failed: %s', p.name())
                raise
        self.runtime.close()

    def remove(self, name):
        plugin=self.plugins.pop(name); plugin.uninstall(self.app); self.runtime.log('info', 'Plugin removed: %s', name); return plugin
    def enable(self, name):
        result = self.plugins[name].enable(); self.runtime.log('info', 'Plugin enabled: %s', name); return result
    def disable(self, name):
        result = self.plugins[name].disable(); self.runtime.log('info', 'Plugin disabled: %s', name); return result
