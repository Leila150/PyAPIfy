"""Compiled route definitions and parameter conversion."""
from __future__ import annotations
import inspect,re
from dataclasses import dataclass

_CONVERTERS={'str':str,'int':int,'float':float,'path':str,'bool':lambda x:x.lower() in ('1','true','yes','on')}

@dataclass
class Route:
    path:str; endpoint:object; methods:set[str]; name:str|None=None; auth:object=None; tags:tuple=(); websocket:bool=False
    def __post_init__(self):
        self.methods={m.upper() for m in self.methods}; self.name=self.name or getattr(self.endpoint,'__name__','route')
        pattern=self.path; self.param_names=[]
        def repl(m):
            name,typ=m.group(1),m.group(2) or 'str'; self.param_names.append((name,typ)); return '(?P<%s>%s)'%(name,'.*' if typ=='path' else {'int':r'-?\d+','float':r'-?\d+(?:\.\d+)?','bool':r'[^/]+'}.get(typ,r'[^/]+'))
        pattern=re.sub(r'\{([A-Za-z_]\w*)(?::([A-Za-z_]\w*))?\}',repl,pattern); self.regex=re.compile('^'+pattern.rstrip('/')+'/?$')
    def match(self,path):
        m=self.regex.match(path); return None if not m else {n:_CONVERTERS[t](v) for n,t in self.param_names for v in [m.group(n)]}
    def signature(self): return inspect.signature(self.endpoint)
