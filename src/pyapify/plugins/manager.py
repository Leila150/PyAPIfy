"""Runtime manager for PyAPIfy-only plugins."""
from __future__ import annotations

import importlib
from pathlib import Path

from .api import Plugin


class PluginManager:
    def __init__(self, app):
        self.app = app
        self.plugins = {}

    def register(self, plugin):
        if not isinstance(plugin, Plugin):
            raise TypeError("PyAPIfy plugins must be Plugin instances")
        name = plugin.name()
        if name in self.plugins:
            raise ValueError(f"Plugin already registered: {name}")
        for dep in plugin.dependencies():
            dep_name = dep.get("name") if isinstance(dep, dict) else str(dep)
            if dep_name and dep_name not in self.plugins:
                raise RuntimeError(f"Missing plugin dependency: {dep_name}")
        plugin.bind(self.app)
        self.plugins[name] = plugin
        return plugin

    def load(self, target):
        if isinstance(target, (str, Path)) and Path(target).is_dir():
            root = Path(target).resolve()
            main = root / "main.py"
            if not main.is_file():
                raise FileNotFoundError(f"Plugin entry point not found: {main}")
            plugin = Plugin(root)
            plugin.load("main.py")
            return self.register(plugin)

        obj = target
        if isinstance(target, str):
            mod, _, attr = target.partition(":")
            obj = getattr(importlib.import_module(mod), attr) if attr else importlib.import_module(mod)
        if isinstance(obj, type):
            obj = obj()
        return self.register(obj)

    def discover(self, directory=None):
        root = Path(directory or (Path.home() / ".pyapify" / "plugins")).expanduser()
        if not root.is_dir():
            return []
        loaded = []
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / "main.py").is_file():
                loaded.append(self.load(child))
        return loaded

    def get(self, name):
        return self.plugins.get(name)

    def capabilities(self):
        return {cap for p in self.plugins.values() for cap in p.capabilities()}

    async def startup(self):
        for p in self.plugins.values():
            result = p.startup(self.app)
            if hasattr(result, "__await__"):
                await result

    async def shutdown(self):
        for p in reversed(list(self.plugins.values())):
            result = p.shutdown(self.app)
            if hasattr(result, "__await__"):
                await result

    def remove(self, name):
        plugin = self.plugins.pop(name)
        plugin.uninstall(self.app)
        return plugin
