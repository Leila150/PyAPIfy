"""First-class plugin contract."""
from __future__ import annotations
class Plugin:
    name='plugin'; version='0.0.0'; requires=()
    def install(self,app): pass
    def uninstall(self,app): pass
    async def startup(self,app): pass
    async def shutdown(self,app): pass
    def configure(self,config): return config
    def commands(self): return []
    def capabilities(self): return set()
