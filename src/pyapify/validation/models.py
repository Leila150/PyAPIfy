"""Small, dependency-free typed model/validation layer."""
from __future__ import annotations
from typing import get_origin,get_args,Union
class ValidationError(ValueError): pass
class Model:
    def __init__(self,**data):
        hints=self.__annotations__ if hasattr(self,'__annotations__') else {}
        for name,typ in hints.items():
            if name in data: value=data[name]
            elif hasattr(self,name): value=getattr(self,name)
            else: raise ValidationError(f'Missing field: {name}')
            setattr(self,name,self._convert(name,value,typ))
        unknown=set(data)-set(hints)
        if unknown: raise ValidationError('Unexpected fields: '+', '.join(sorted(unknown)))
    @classmethod
    def _convert(cls,name,v,t):
        if v is None and type(None) in get_args(t): return None
        o=get_origin(t)
        if o is Union:
            for a in get_args(t):
                if a is type(None): continue
                try:return cls._convert(name,v,a)
                except (ValueError,TypeError,ValidationError): pass
            raise ValidationError(f'Invalid field: {name}')
        if isinstance(t,type) and issubclass(t,Model): return v if isinstance(v,t) else t(**v)
        if o in (list,tuple,set):
            a=get_args(t)[0] if get_args(t) else object; return o(cls._convert(name,x,a) for x in v)
        if o is dict:
            return dict(v)
        if t is bool and isinstance(v,str): return v.lower() in ('1','true','yes','on')
        if isinstance(t,type) and not isinstance(v,t):
            try:return t(v)
            except Exception as e: raise ValidationError(f'Invalid field: {name}') from e
        return v
    def dict(self): return {k:(v.dict() if isinstance(v,Model) else [x.dict() if isinstance(x,Model) else x for x in v] if isinstance(v,list) else v) for k,v in self.__dict__.items()}
    model_dump=dict
