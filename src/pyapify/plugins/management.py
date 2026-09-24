"""High-level management helpers for PyAPIfy plugins.

These helpers deliberately manage PyAPIfy extensions only; they are not a
replacement for Python's package manager.
"""
from __future__ import annotations

from pathlib import Path
from .api import Plugin


def _manager(plugin: Plugin):
    if plugin._app is None or not hasattr(plugin._app, "plugin_manager"):
        raise RuntimeError("Plugin management requires the plugin to be bound to a PyAPIfy app")
    return plugin._app.plugin_manager


def use(self: Plugin, target):
    """Use another installed/loaded PyAPIfy plugin."""
    if isinstance(target, Plugin):
        if target is self:
            raise ValueError("A plugin cannot use itself")
        if target not in self._used_plugins:
            self._used_plugins.append(target)
        if self._app is not None and target not in self._app.plugins:
            self._app.use(target)
        return target

    manager = _manager(self)
    if isinstance(target, Path):
        other = manager.load(target)
    elif isinstance(target, str):
        if target in manager.plugins:
            other = manager.plugins[target]
        else:
            installed = manager.default_directory() / target
            other = manager.load(installed) if installed.is_dir() else manager.load(target)
    else:
        raise TypeError("plugin.use() expects a Plugin, plugin name, directory, or module target")

    if other is self:
        raise ValueError("A plugin cannot use itself")
    if other not in self._used_plugins:
        self._used_plugins.append(other)
    return other


def install(self: Plugin, source, *, name=None, overwrite=False):
    return _manager(self).install(source, name=name, overwrite=overwrite)


def uninstall(self: Plugin, name=None, *, remove_cache=True):
    return _manager(self).uninstall(name or self.name(), remove_cache=remove_cache)


def update(self: Plugin, name=None, source=None, *, overwrite=True):
    return _manager(self).update(name or self.name(), source, overwrite=overwrite)


def reload(self: Plugin, name=None):
    return _manager(self).reload(name or self.name())


def exists(self: Plugin, name=None):
    return _manager(self).exists(name or self.name())


def loaded(self: Plugin, name=None):
    return _manager(self).loaded(name or self.name())


def enable(self: Plugin, name=None):
    return _manager(self).enable(name or self.name())


def disable(self: Plugin, name=None):
    return _manager(self).disable(name or self.name())


def plugins(self: Plugin):
    return _manager(self).list()


def require_plugin(self: Plugin, name):
    return _manager(self).require(name)


def dependency_status(self: Plugin, name=None):
    return _manager(self).dependency_status(name or self.name())


def dependency_tree(self: Plugin, name=None):
    return _manager(self).dependency_tree(name or self.name())


Plugin.use = use
Plugin.install = install
Plugin.uninstall = uninstall
Plugin.update = update
Plugin.reload = reload
Plugin.exists = exists
Plugin.loaded = loaded
Plugin.enable_plugin = enable
Plugin.disable_plugin = disable
Plugin.plugins = plugins
Plugin.require_plugin = require_plugin
Plugin.dependency_status = dependency_status
Plugin.dependency_tree = dependency_tree
