"""Fast, dependency-free route registry."""
from .route import Route

class Router:
    def __init__(self,prefix='',auth=None,tags=()): self.prefix=prefix.rstrip('/'); self.auth=auth; self.tags=tuple(tags); self.routes=[]
    def add(self,path,endpoint,methods=('GET',),name=None,auth=None,tags=()):
        full=(self.prefix+('/' if not path.startswith('/') else '')+path) or '/'
        r=Route(full,endpoint,set(methods),name, self.auth if auth is None else auth, self.tags+tuple(tags)); self.routes.append(r); return r
    def match(self,path,method):
        for r in self.routes:
            params=r.match(path)
            if params is not None: return r,params
        return None,None
    def methods_for(self,path):
        return {m for r in self.routes if r.match(path) is not None for m in r.methods}
