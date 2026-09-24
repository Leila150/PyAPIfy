"""Runtime manager for PyAPIfy-only plugins."""
from __future__ import annotations
import importlib, os, shutil, tempfile, zipfile
from pathlib import Path
from .api import Plugin
from .runtime import PyAPIfyRuntime
from .dependencies import dependency_parts, resolve as resolve_dependencies, satisfies


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

    def resolve(self):
        return tuple(resolve_dependencies(self))

    def dependency_status(self, name):
        plugin = self.require(name)
        required = []
        optional = []
        metadata = plugin.info()
        for raw in plugin.dependencies():
            dep_name, requirement = dependency_parts(raw)
            found = self.plugins.get(dep_name)
            required.append({"name": dep_name, "requirement": requirement,
                             "installed": found is not None,
                             "version": found.version() if found else None,
                             "satisfied": found is not None and (not requirement or satisfies(found.version(), requirement))})
        for raw in metadata.get("optionalDepends", []) or []:
            dep_name, requirement = dependency_parts(raw)
            found = self.plugins.get(dep_name)
            optional.append({"name": dep_name, "requirement": requirement,
                             "installed": found is not None,
                             "version": found.version() if found else None,
                             "satisfied": found is not None and (not requirement or satisfies(found.version(), requirement))})
        return {"required": tuple(required), "optional": tuple(optional)}

    def dependency_tree(self, name=None):
        names = [name] if name else list(self.plugins)
        tree = {}
        for plugin_name in names:
            plugin = self.require(plugin_name)
            tree[plugin_name] = [dependency_parts(x)[0] for x in plugin.dependencies() if dependency_parts(x)[0]]
        return tree

    def check_dependencies(self):
        order = self.resolve()
        for name in self.plugins:
            status = self.dependency_status(name)
            failed = [x for x in status["required"] if not x["satisfied"]]
            if failed:
                raise RuntimeError(f"Unsatisfied dependencies for {name}: {failed}")
        self.runtime.log("debug", "Plugin dependencies resolved: %s", order)
        return order

    def register(self, plugin: Plugin):
        if not isinstance(plugin, Plugin):
            raise TypeError("PyAPIfy plugins must be Plugin instances")
        name = plugin.name()
        if name in self.plugins:
            raise ValueError(f"Plugin already registered: {name}")
        plugin.bind(self.app)
        self.plugins[name] = plugin
        try:
            self.check_dependencies()
        except Exception:
            self.plugins.pop(name, None)
            plugin.uninstall(self.app)
            raise
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
        if isinstance(plugin, str):
            if plugin in self.plugins:
                return self.plugins[plugin]
            candidate = self._directory() / plugin
            if candidate.is_dir():
                return self.load(candidate)
            raise KeyError(f"Plugin is not installed: {plugin}")
        if isinstance(plugin, (Path,)):
            return self.load(plugin)
        return self.register(plugin)

    def get(self, name): return self.plugins.get(name)
    def require(self, name):
        plugin = self.get(name)
        if plugin is None:
            raise KeyError(f"Plugin is not loaded: {name}")
        return plugin
    def exists(self, name): return name in self.plugins or (self._directory() / name).is_dir()
    def loaded(self, name): return name in self.plugins
    def enabled(self, name): return bool(self.require(name).enabled())
    def capabilities(self): return {cap for p in self.plugins.values() for cap in p.capabilities()}
    def extension_map(self): return {name: p.capabilities() for name, p in self.plugins.items()}
    def list(self): return tuple(self.plugins.values())
    def cache(self, plugin_name="pyapify"): return self.runtime.cache(plugin_name)
    def log(self, level="info", message="", *args, **kwargs): return self.runtime.log(level, message, *args, **kwargs)

    def install(self, source, *, name=None, overwrite=False):
        source = Path(source).expanduser().resolve()
        destination_root = self._directory()
        if source.is_dir():
            plugin_name = name or (Plugin(source).name() if (source / "info.json").is_file() else source.name)
            destination = destination_root / plugin_name
            if destination.exists():
                if not overwrite: raise FileExistsError(f"Plugin already installed: {plugin_name}")
                shutil.rmtree(destination)
            shutil.copytree(source, destination)
        elif source.is_file() and source.suffix.lower() == ".zip":
            with tempfile.TemporaryDirectory() as temp:
                temp_root = Path(temp)
                with zipfile.ZipFile(source) as archive: archive.extractall(temp_root)
                candidates = [p for p in temp_root.iterdir() if p.is_dir()]
                source_dir = candidates[0] if len(candidates) == 1 else temp_root
                plugin_name = name or Plugin(source_dir).name()
                destination = destination_root / plugin_name
                if destination.exists():
                    if not overwrite: raise FileExistsError(f"Plugin already installed: {plugin_name}")
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
        if directory.exists(): shutil.rmtree(directory)
        if remove_cache: self.runtime.cache(name).clear()
        self.runtime.log("info", "Plugin uninstalled: %s", name)
        return plugin

    def reload(self, name):
        self.uninstall(name, remove_cache=False)
        directory = self._directory() / name
        if not directory.is_dir(): raise FileNotFoundError(f"Installed plugin not found: {name}")
        result = self.load(directory)
        self.runtime.log("info", "Plugin reloaded: %s", name)
        return result

    def update(self, name, source=None, *, overwrite=True):
        if source is None: raise ValueError("update() requires a local plugin source")
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
        for name in self.check_dependencies():
            plugin = self.plugins[name]
            try:
                result = plugin.startup(self.app)
                if hasattr(result, "__await__"): await result
                self.runtime.log("info", "Plugin started: %s", name)
            except Exception:
                self.runtime.logger.exception("Plugin startup failed: %s", name)
                raise

    async def shutdown(self):
        for name in reversed(self.check_dependencies()):
            plugin = self.plugins[name]
            try:
                result = plugin.shutdown(self.app)
                if hasattr(result, "__await__"): await result
                self.runtime.log("info", "Plugin stopped: %s", name)
            except Exception:
                self.runtime.logger.exception("Plugin shutdown failed: %s", name)
                raise
        self.runtime.close()

    def remove(self, name): return self.uninstall(name)
