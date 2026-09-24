"""First-class PyAPIfy extension system."""

from .api import Plugin
from .manager import PluginManager
from . import management as _management

__all__ = ["Plugin", "PluginManager"]
