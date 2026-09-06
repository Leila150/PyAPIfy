"""Public API for building PyAPIfy-only extensions.

Plugins extend PyAPIfy itself; they are deliberately not a general-purpose
Python plugin system.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any


class Plugin:
    """Builder and lifecycle object for a PyAPIfy extension plugin."""

    # These are the extension points discussed for PyAPIfy.  Keeping the
    # catalogue explicit makes the public API discoverable while __getattr__
    # still permits future PyAPIfy extension points without a breaking API.
    EXTENSION_KINDS = (
        "decorator", "function", "hook", "route_type", "middleware",
        "command", "config", "test", "run",
        "request_handler", "response_type", "http_method", "status_code",
        "converter", "validator", "model_type", "dependency", "auth",
        "permission", "error_handler", "lifecycle", "task", "schedule",
        "openapi", "documentation", "websocket", "sse", "html", "css",
        "js", "gui", "group", "router", "storage", "cache", "server",
        "https", "log_handler", "environment", "plugin_extension",
    )

    def __init__(self, root: str | os.PathLike[str] | None = None):
        self.root = Path(root).resolve() if root else self._discover_root()
        self._registry: dict[str, dict[str, dict[str, Any]]] = {}
        self._app = None
        self._metadata: dict[str, Any] = {}
        self._loaded: dict[str, Any] = {}
        self._enabled = True
        self._registered = False
        self._read_metadata()

    def _discover_root(self) -> Path:
        for frame in inspect.stack()[1:]:
            filename = Path(frame.filename).resolve()
            if filename.name == "main.py":
                return filename.parent
        return Path.cwd().resolve()

    def _read_metadata(self) -> None:
        path = self.root / "info.json"
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._metadata = data
            except (OSError, ValueError):
                self._metadata = {}

    # ------------------------------------------------------------------
    # Loading / metadata
    # ------------------------------------------------------------------
    def load(self, path: str | os.PathLike[str]):
        """Load a Python file relative to the plugin root."""
        target = (self.root / path).resolve()
        if not target.is_file():
            raise FileNotFoundError(target)
        module_name = f"pyapify_plugin_{self.name()}_{len(self._loaded)}"
        spec = importlib.util.spec_from_file_location(module_name, target)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load plugin file: {target}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        self._loaded[str(target)] = module
        return module

    def info(self):
        return dict(self._metadata)

    def path(self):
        return self.root

    def name(self):
        return self._metadata.get("name", self.root.name)

    def version(self):
        return self._metadata.get("version", "0.0.0")

    def dependencies(self):
        value = self._metadata.get("dependencies", [])
        return list(value) if isinstance(value, (list, tuple, set)) else [value]

    def require(self, *dependencies):
        """Declare PyAPIfy plugin dependencies in this plugin's metadata."""
        current = self._metadata.setdefault("dependencies", [])
        if not isinstance(current, list):
            current = self._metadata["dependencies"] = list(current) if current else []
        for dependency in dependencies:
            if dependency not in current:
                current.append(dependency)
        return self

    # ------------------------------------------------------------------
    # Core registry
    # ------------------------------------------------------------------
    def _create(self, kind: str, name: str | None, value: Any, **meta):
        key = name or getattr(value, "__name__", None)
        if not key:
            raise ValueError(f"{kind} requires a name")
        bucket = self._registry.setdefault(kind, {})
        if key in bucket:
            raise ValueError(f"{kind} already exists: {key}")
        bucket[key] = {"value": value, **meta}
        self._attach(kind, key, value, bucket[key])
        return value

    def _edit(self, kind: str, name: str, value: Any = None, **meta):
        bucket = self._registry.setdefault(kind, {})
        if name not in bucket:
            raise KeyError(f"Unknown {kind}: {name}")
        if value is not None:
            bucket[name]["value"] = value
        bucket[name].update(meta)
        self._attach(kind, name, bucket[name]["value"], bucket[name])
        return bucket[name]["value"]

    def _delete(self, kind: str, name: str):
        bucket = self._registry.setdefault(kind, {})
        item = bucket.pop(name, None)
        if item is None:
            raise KeyError(f"Unknown {kind}: {name}")
        self._detach(kind, name)
        return item["value"]

    def _attach(self, kind: str, name: str, value: Any, meta: dict[str, Any]):
        if self._app is None or not self._enabled:
            return
        self._app._register_plugin_extension(kind, name, value, meta, self)

    def _detach(self, kind: str, name: str):
        if self._app is not None:
            self._app._unregister_plugin_extension(kind, name, self)

    def bind(self, app):
        self._app = app
        self._registered = True
        for kind, items in self._registry.items():
            for name, item in items.items():
                self._attach(kind, name, item["value"], item)
        return self

    def _decorator(self, kind: str, name: str | None = None, **meta):
        def register(value):
            return self._create(kind, name, value, **meta)
        return register

    # ------------------------------------------------------------------
    # Explicit public creation/edit/delete APIs
    # ------------------------------------------------------------------
    def create_decorator(self, name=None, **meta): return self._decorator("decorator", name, **meta)
    def edit_decorator(self, name, value=None, **meta): return self._edit("decorator", name, value, **meta)
    def delete_decorator(self, name): return self._delete("decorator", name)

    def create_function(self, name=None, **meta): return self._decorator("function", name, **meta)
    def edit_function(self, name, value=None, **meta): return self._edit("function", name, value, **meta)
    def delete_function(self, name): return self._delete("function", name)

    def create_hook(self, name=None, **meta): return self._decorator("hook", name, **meta)
    def edit_hook(self, name, value=None, **meta): return self._edit("hook", name, value, **meta)
    def delete_hook(self, name): return self._delete("hook", name)

    def create_route_type(self, name=None, **meta): return self._decorator("route_type", name, **meta)
    def edit_route_type(self, name, value=None, **meta): return self._edit("route_type", name, value, **meta)
    def delete_route_type(self, name): return self._delete("route_type", name)

    def create_middleware(self, name=None, **meta): return self._decorator("middleware", name, **meta)
    def edit_middleware(self, name, value=None, **meta): return self._edit("middleware", name, value, **meta)
    def delete_middleware(self, name): return self._delete("middleware", name)

    def create_command(self, name=None, **meta): return self._decorator("command", name, **meta)
    def edit_command(self, name, value=None, **meta): return self._edit("command", name, value, **meta)
    def delete_command(self, name): return self._delete("command", name)

    def create_config(self, name=None, **meta): return self._decorator("config", name, **meta)
    def edit_config(self, name, value=None, **meta): return self._edit("config", name, value, **meta)
    def delete_config(self, name): return self._delete("config", name)

    def create_test(self, name=None, **meta): return self._decorator("test", name, **meta)
    def edit_test(self, name, value=None, **meta): return self._edit("test", name, value, **meta)
    def delete_test(self, name): return self._delete("test", name)

    def create_run(self, name=None, **meta): return self._decorator("run", name, **meta)
    def edit_run(self, name, value=None, **meta): return self._edit("run", name, value, **meta)
    def delete_run(self, name): return self._delete("run", name)

    # Additional explicitly supported PyAPIfy extension points.
    def _simple_create(self, kind, name=None, **meta): return self._decorator(kind, name, **meta)
    def _simple_edit(self, kind, name, value=None, **meta): return self._edit(kind, name, value, **meta)
    def _simple_delete(self, kind, name): return self._delete(kind, name)

    # Generate real class methods rather than relying only on __getattr__, so
    # IDEs, dir(), documentation tools and static inspection can discover them.
    @classmethod
    def _install_extension_methods(cls):
        for kind in cls.EXTENSION_KINDS:
            if hasattr(cls, f"create_{kind}"):
                continue
            setattr(cls, f"create_{kind}", lambda self, name=None, _k=kind, **meta: self._simple_create(_k, name, **meta))
            setattr(cls, f"edit_{kind}", lambda self, name, value=None, _k=kind, **meta: self._simple_edit(_k, name, value, **meta))
            setattr(cls, f"delete_{kind}", lambda self, name, _k=kind: self._simple_delete(_k, name))

    def __getattr__(self, attr):
        if attr.startswith("create_"):
            return lambda name=None, **meta: self._simple_create(attr[7:], name, **meta)
        if attr.startswith("edit_"):
            return lambda name, value=None, **meta: self._simple_edit(attr[5:], name, value, **meta)
        if attr.startswith("delete_"):
            return lambda name: self._simple_delete(attr[7:], name)
        raise AttributeError(attr)

    # ------------------------------------------------------------------
    # Registration / lifecycle
    # ------------------------------------------------------------------
    def register(self):
        self._registered = True
        if self._app is not None:
            self.bind(self._app)
        return self

    def unregister(self):
        if self._app is not None:
            for kind, items in list(self._registry.items()):
                for name in list(items):
                    self._detach(kind, name)
        self._registered = False
        return self

    def enable(self):
        self._enabled = True
        if self._app:
            self.bind(self._app)
        return self

    def disable(self):
        if self._enabled:
            for kind, items in list(self._registry.items()):
                for name in list(items):
                    self._detach(kind, name)
        self._enabled = False
        return self

    def enabled(self): return self._enabled
    def is_registered(self): return self._registered

    def startup(self, app):
        hook = self._registry.get("hook", {}).get("startup")
        if hook:
            result = hook["value"](app)
            if inspect.isawaitable(result): return result
        return None

    def shutdown(self, app):
        hook = self._registry.get("hook", {}).get("shutdown")
        if hook:
            result = hook["value"](app)
            if inspect.isawaitable(result): return result
        return None

    def uninstall(self, app=None):
        target = app or self._app
        if target is not None:
            for kind, items in list(self._registry.items()):
                for name in list(items):
                    target._unregister_plugin_extension(kind, name, self)
        self._app = None
        self._registered = False
        return self

    def capabilities(self):
        return set(self._registry)


Plugin._install_extension_methods()
