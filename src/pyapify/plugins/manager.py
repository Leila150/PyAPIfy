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
        required, optional = [], []
        for raw in plugin.dependencies():
            dep_name, requirement = dependency_parts(raw)
            found = self.plugins.get(dep_name)
            required.append({"name": dep_name, "requirement": requirement, "installed": found is not None,
                             "version": found.version() if found else None,
                             "satisfied": found is not None and (not requirement or satisfies(found.version(), requirement))})
        for raw in plugin.info().get("optionalDepends", []) or []:
            dep_name, requirement = dependency_parts(raw)
            found = self.plugins.get(dep_name)
            optional.append({"name": dep_name, "requirement": requirement, "installed": found is not None,
                             "version": found.version() if found else None,
                             "satisfied": found is not None and (not requirement or satisfies(found.version(), requirement))})
        return {"required": tuple(required), "optional": tuple(optional)}

    def dependency_tree(self, name=None):
        names = [name] if name else list(self.plugins)
        return {n: [dependency_parts(x)[0] for x in self.require(n).dependencies() if dependency_parts(x)[0]] for n in names}

    def check_dependencies(self):
        order = self.resolve()
        for name in self.plugins:
            failed = [x for x in self.dependency_status(name)["required"] if not x["satisfied"]]
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
        if isinstance(plugin, Path):
            return self.load(plugin)
        return self.register(plugin)

    def get(self, name): return self.plugins.get(name)

    def require(self, name):
        plugin = self.get(name)
        if plugin is None:
            raise KeyError(f"Plugin is not loaded: {name}")
        return plugin

    def exists(self, name):
        return name in self.plugins or (self._directory() / name).is_dir()

    def loaded(self, name): return name in self.plugins
    def enabled(self, name): return bool(self.require(name).enabled())

    def started(self, name): return self.require(name).started()

    def dependents(self, name):
        self.require(name)
        return tuple(plugin.name() for plugin in self.plugins.values()
                     if any(dependency_parts(dep)[0] == name for dep in plugin.dependencies()))

    def start(self, name):
        plugin = self.require(name)
        self.check_dependencies()
        result = plugin.startup(self.app)
        self.runtime.log("info", "Plugin start requested: %s", name)
        return result

    def stop(self, name):
        plugin = self.require(name)
        result = plugin.shutdown(self.app)
        self.runtime.log("info", "Plugin stop requested: %s", name)
        return result

    def state(self, name):
        plugin = self.require(name)
        return {
            "name": plugin.name(),
            "version": plugin.version(),
            "path": str(plugin.path()),
            "loaded": self.loaded(name),
            "enabled": plugin.enabled(),
            "registered": plugin.is_registered(),
            "capabilities": tuple(sorted(plugin.capabilities())),
            "dependencies": self.dependency_status(name),
        }

    def states(self):
        return {name: self.state(name) for name in self.plugins}

    def capabilities(self): return {cap for p in self.plugins.values() for cap in p.capabilities()}
    def extension_map(self): return {name: p.capabilities() for name, p in self.plugins.items()}
    def list(self): return tuple(self.plugins.values())
    def cache(self, plugin_name="pyapify"): return self.runtime.cache(plugin_name)
    def log(self, level="info", message="", *args, **kwargs): return self.runtime.log(level, message, *args, **kwargs)

    @staticmethod
    def _safe_zip_members(archive, destination):
        destination = destination.resolve()
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            try:
                target.relative_to(destination)
            except ValueError:
                raise ValueError(f"Unsafe plugin archive path: {member.filename}")
        return True

    def _extract_zip(self, archive_path, destination):
        with zipfile.ZipFile(archive_path) as archive:
            if any(info.file_size > 256 * 1024 * 1024 for info in archive.infolist()):
                raise ValueError("Plugin archive contains a file larger than 256 MiB")
            self._safe_zip_members(archive, destination)
            archive.extractall(destination)

    def _validate_plugin_directory(self, root):
        root = Path(root)
        if not (root / "main.py").is_file():
            raise FileNotFoundError(f"Plugin entry point not found: {root / 'main.py'}")
        return root

    def install(self, source, *, name=None, overwrite=False):
        source = Path(source).expanduser().resolve()
        destination_root = self._directory()
        if source.is_dir():
            self._validate_plugin_directory(source)
            plugin_name = name or (Plugin(source).name() if (source / "info.json").is_file() else source.name)
            destination = destination_root / plugin_name
            if destination.exists():
                if not overwrite:
                    raise FileExistsError(f"Plugin already installed: {plugin_name}")
                shutil.rmtree(destination)
            shutil.copytree(source, destination)
        elif source.is_file() and source.suffix.lower() == ".zip":
            with tempfile.TemporaryDirectory() as temp:
                temp_root = Path(temp)
                self._extract_zip(source, temp_root)
                candidates = [p for p in temp_root.iterdir() if p.is_dir()]
                source_dir = candidates[0] if len(candidates) == 1 else temp_root
                self._validate_plugin_directory(source_dir)
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

    def uninstall(self, name, *, remove_cache=True, force=False):
        plugin = self.plugins.get(name)
        if plugin is None and not (self._directory() / name).exists():
            raise KeyError(f"Plugin is not installed: {name}")
        dependents = self.dependents(name) if plugin is not None else ()
        if dependents and not force:
            raise RuntimeError(f"Cannot uninstall {name}; loaded plugins depend on it: {', '.join(dependents)}")
        plugin = self.plugins.pop(name, None)
        if plugin is not None:
            plugin.uninstall(self.app)
        directory = self._directory() / name
        if directory.exists():
            shutil.rmtree(directory)
        if remove_cache:
            self.runtime.cache(name).clear()
        self.runtime.log("info", "Plugin uninstalled: %s", name)
        return plugin

    def reload(self, name):
        self.uninstall(name, remove_cache=False)
        directory = self._directory() / name
        if not directory.is_dir():
            raise FileNotFoundError(f"Installed plugin not found: {name}")
        result = self.load(directory)
        self.runtime.log("info", "Plugin reloaded: %s", name)
        return result

    def update(self, name, source=None, *, overwrite=True):
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
        for name in self.check_dependencies():
            plugin = self.plugins[name]
            result = plugin.startup(self.app)
            if hasattr(result, "__await__"):
                await result
            self.runtime.log("info", "Plugin started: %s", name)

    async def shutdown(self):
        for name in reversed(self.check_dependencies()):
            plugin = self.plugins[name]
            result = plugin.shutdown(self.app)
            if hasattr(result, "__await__"):
                await result
            self.runtime.log("info", "Plugin stopped: %s", name)
        self.runtime.close()

    def remove(self, name): return self.uninstall(name)
