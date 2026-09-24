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
    """Use another installed/loaded PyAPIfy plugin.

    Accepts a Plugin instance, an installed plugin name, a plugin directory,
    or a Python module target understood by PluginManager.load().
    """
    if isinstance(target, Plugin):
        return Plugin.use(self, target)
    manager = _manager(self)
    if isinstance(target, (str, Path)):
        path = Path(target).expanduser()
        if path.is_dir():
            other = manager.load(path)
        elif manager.loaded(str(target)):
            other = manager.get(str(target))
        else:
            installed = manager.default_directory() / str(target)
            other = manager.load(installed) if installed.is_dir() else manager.load(str(target))
        if other is self:
            raise ValueError("A plugin cannot use itself")
        if other not in self._used_plugins:
            self._used_plugins.append(other)
        return other
    raise TypeError("plugin.use() expects a Plugin, plugin name, directory, or module target")


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
