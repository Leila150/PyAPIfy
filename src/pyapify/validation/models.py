"""Dependency-free typed models, validation and JSON-schema generation."""
from __future__ import annotations
from typing import get_origin,get_args,get_type_hints,Union

class ValidationError(ValueError): pass
class Field:
    def __init__(self,default=...,*,min_length=None,max_length=None,ge=None,gt=None,le=None,lt=None,description=None): self.default=default; self.min_length=min_length; self.max_length=max_length; self.ge=ge; self.gt=gt; self.le=le; self.lt=lt; self.description=description

def _schema(t):
    o=get_origin(t); args=get_args(t)
    if o is Union:
        return {'anyOf':[_schema(a) for a in args if a is not type(None)]} | ({'nullable':True} if type(None) in args else {})
    if o in (list,tuple,set): return {'type':'array','items':_schema(args[0]) if args else {}}
    if o is dict:return {'type':'object'}
    return {'type':{str:'string',int:'integer',float:'number',bool:'boolean',bytes:'string'}.get(t,'object')}

class Model:
    __validators__={}
    def __init__(self,**data):
        hints=get_type_hints(self.__class__); unknown=set(data)-set(hints)
        if unknown: raise ValidationError('Unexpected fields: '+', '.join(sorted(unknown)))
        for name,typ in hints.items():
            class_default=getattr(self.__class__,name,...) ; value=data[name] if name in data else (class_default.default if isinstance(class_default,Field) else class_default)
            if value is ...:
                if type(None) in get_args(typ): value=None
                else: raise ValidationError(f'Missing field: {name}')
            if isinstance(class_default,Field): self._constraints(name,value,class_default)
            setattr(self,name,self._convert(name,value,typ))
        for name,validator in getattr(self.__class__,'__validators__',{}).items():
            if name in self.__dict__:
                result=validator(self.__dict__[name]); self.__dict__[name]=result if result is not None else self.__dict__[name]
    @staticmethod
    def _constraints(name,v,f):
        if v is not None and f.min_length is not None and len(v)<f.min_length: raise ValidationError(f'{name} is shorter than {f.min_length}')
        if v is not None and f.max_length is not None and len(v)>f.max_length: raise ValidationError(f'{name} is longer than {f.max_length}')
        for op,limit in ((lambda a,b:a>=b,f.ge),(lambda a,b:a>b,f.gt),(lambda a,b:a<=b,f.le),(lambda a,b:a<b,f.lt)):
            if limit is not None and not op(v,limit): raise ValidationError(f'Invalid value for {name}')
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
            a=get_args(t)[0] if get_args(t) else object; converted=[cls._convert(name,x,a) for x in v]; return o(converted)
        if o is dict:return dict(v)
        if t is bool and isinstance(v,str):
            if v.lower() not in ('1','true','yes','on','0','false','no','off'): raise ValidationError(f'Invalid field: {name}')
            return v.lower() in ('1','true','yes','on')
        if isinstance(t,type) and not isinstance(v,t):
            try:return t(v)
            except Exception as e: raise ValidationError(f'Invalid field: {name}') from e
        return v
    def dict(self):
        def dump(v):
            if isinstance(v,Model): return {k:dump(x) for k,x in v.__dict__.items()}
            if isinstance(v,(list,tuple,set)): return [dump(x) for x in v]
            if isinstance(v,dict): return {k:dump(x) for k,x in v.items()}
            return v
        return {k:dump(v) for k,v in self.__dict__.items()}
    model_dump=dict
    @classmethod
    def schema(cls):
        props={}; required=[]; hints=get_type_hints(cls)
        for name,t in hints.items():
            props[name]=_schema(t); default=getattr(cls,name,...)
            if isinstance(default,Field):
                if default.description: props[name]['description']=default.description
                default=default.default
            if default is ... and type(None) not in get_args(t): required.append(name)
            elif default is not ...: props[name]['default']=default
        result={'type':'object','title':cls.__name__,'properties':props}
        if required: result['required']=required
        return result
    model_json_schema=schema
