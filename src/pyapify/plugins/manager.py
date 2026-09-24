"""Runtime manager for PyAPIfy-only plugins."""
from __future__ import annotations
import importlib
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from .api import Plugin
from .runtime import PyAPIfyRuntime


class PluginManager:
    """Install, discover, load and manage PyAPIfy extension plugins."""

    def __init__(self, app):
        self.app = app
        self.plugins: dict[str, Plugin] = {}
        self.runtime = PyAPIfyRuntime()
        app.runtime = self.runtime
        self.runtime.log("info", "PyAPIfy plugin runtime initialized at %s", self.runtime.root)

    @staticmethod
    def default_directory() -> Path:
        explicit = os.environ.get("PYAPIFY_PLUGIN_DIR")
        if explicit:
            return Path(explicit).expanduser()
        android = Path("/storage/emulated/0/.pyapify/plugins")
        if android.is_dir() or Path("/storage/emulated/0").is_dir():
            return android
        return Path.home() / ".pyapify" / "plugins"

    def _directory(self, directory=None) -> Path:
        root = Path(directory).expanduser() if directory else self.default_directory()
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    def register(self, plugin: Plugin):
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
        self.runtime.log("info", "Plugin registered: %s %s", name, plugin.version())
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
        root = self._directory(directory)
        loaded = []
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / "main.py").is_file():
                try:
                    loaded.append(self.load(child))
                except Exception:
                    self.runtime.logger.exception("Failed to load plugin: %s", child)
        return loaded

    def use(self, plugin):
        """Register a plugin and return it, matching the public plugin.use() concept."""
        return self.register(plugin)

    def get(self, name):
        return self.plugins.get(name)

    def require(self, name):
        plugin = self.get(name)
        if plugin is None:
            raise KeyError(f"Plugin is not loaded: {name}")
        return plugin

    def exists(self, name):
        return name in self.plugins or (self._directory() / name).is_dir()

    def loaded(self, name):
        return name in self.plugins

    def enabled(self, name):
        return bool(self.require(name).enabled())

    def capabilities(self):
        return {cap for p in self.plugins.values() for cap in p.capabilities()}

    def extension_map(self):
        return {name: p.capabilities() for name, p in self.plugins.items()}

    def list(self):
        return tuple(self.plugins.values())

    def cache(self, plugin_name="pyapify"):
        return self.runtime.cache(plugin_name)

    def log(self, level="info", message="", *args, **kwargs):
        return self.runtime.log(level, message, *args, **kwargs)

    def install(self, source, *, name=None, overwrite=False):
        """Install a plugin directory or zip archive into .pyapify/plugins."""
        source = Path(source).expanduser().resolve()
        destination_root = self._directory()
        if source.is_dir():
            metadata = source / "info.json"
            plugin_name = name or source.name
            if metadata.is_file():
                plugin_name = name or Plugin(source).name()
            destination = destination_root / plugin_name
            if destination.exists():
                if not overwrite:
                    raise FileExistsError(f"Plugin already installed: {plugin_name}")
                shutil.rmtree(destination)
            shutil.copytree(source, destination)
        elif source.is_file() and source.suffix.lower() == ".zip":
            with tempfile.TemporaryDirectory() as temp:
                temp_root = Path(temp)
                with zipfile.ZipFile(source) as archive:
                    archive.extractall(temp_root)
                candidates = [p for p in temp_root.iterdir() if p.is_dir()]
                source_dir = candidates[0] if len(candidates) == 1 else temp_root
                plugin_name = name or Plugin(source_dir).name()
                destination = destination_root / plugin_name
                if destination.exists():
                    if not overwrite:
                        raise FileExistsError(f"Plugin already installed: {plugin_name}")
                    shutil.rmtree(destination)
                shutil.copytree(source_dir, destination)
        else:
            raise ValueError("Plugin source must be a directory or .zip archive")
        self.runtime.log("info", "Plugin installed: %s", destination)
        return destination

    def uninstall(self, name, *, remove_cache=True):
        plugin = self.plugins.pop(name, None)
        if plugin is not None:
            plugin.uninstall(self.app)
        directory = self._directory() / name
        if directory.exists():
            shutil.rmtree(directory)
        if remove_cache:
            cache = self.runtime.cache(name)
            cache.clear()
        self.runtime.log("info", "Plugin uninstalled: %s", name)
        return plugin

    def reload(self, name):
        old = self.plugins.pop(name, None)
        if old is not None:
            old.uninstall(self.app)
        directory = self._directory() / name
        if not directory.is_dir():
            raise FileNotFoundError(f"Installed plugin not found: {name}")
        result = self.load(directory)
        self.runtime.log("info", "Plugin reloaded: %s", name)
        return result

    def update(self, name, source=None, *, overwrite=True):
        """Replace an installed plugin from a local directory/zip source."""
        if source is None:
            raise ValueError("update() requires a local plugin source")
        self.uninstall(name)
        destination = self.install(source, name=name, overwrite=overwrite)
        result = self.load(destination)
        self.runtime.log("info", "Plugin updated: %s", name)
        return result

    def enable(self, name):
        result = self.require(name).enable()
        self.runtime.log("info", "Plugin enabled: %s", name)
        return result

    def disable(self, name):
        result = self.require(name).disable()
        self.runtime.log("info", "Plugin disabled: %s", name)
        return result

    async def startup(self):
        for plugin in self.plugins.values():
            try:
                result = plugin.startup(self.app)
                if hasattr(result, "__await__"):
                    await result
                self.runtime.log("info", "Plugin started: %s", plugin.name())
            except Exception:
                self.runtime.logger.exception("Plugin startup failed: %s", plugin.name())
                raise

    async def shutdown(self):
        for plugin in reversed(list(self.plugins.values())):
            try:
                result = plugin.shutdown(self.app)
                if hasattr(result, "__await__"):
                    await result
                self.runtime.log("info", "Plugin stopped: %s", plugin.name())
            except Exception:
                self.runtime.logger.exception("Plugin shutdown failed: %s", plugin.name())
                raise
        self.runtime.close()

    def remove(self, name):
        return self.uninstall(name)
