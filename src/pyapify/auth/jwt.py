"""Minimal standards-oriented JWT HS256 authentication provider."""
from __future__ import annotations
import base64, hashlib, hmac, json, time
from .base import AuthProvider

def _b64(data): return base64.urlsafe_b64encode(data).rstrip(b'=').decode()
def _unb64(value): return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))

class JWTAuth(AuthProvider):
    def __init__(self, secret, *, algorithms=('HS256',), issuer=None, audience=None, leeway=0):
        self.secret=secret.encode() if isinstance(secret,str) else secret; self.algorithms=tuple(algorithms); self.issuer=issuer; self.audience=audience; self.leeway=leeway
        if 'HS256' not in self.algorithms: raise ValueError('JWTAuth currently supports HS256 only')
    def encode(self,payload,*,expires_in=None):
        claims=dict(payload)
        if expires_in is not None: claims['exp']=int(time.time())+int(expires_in)
        if self.issuer is not None: claims.setdefault('iss',self.issuer)
        if self.audience is not None: claims.setdefault('aud',self.audience)
        header={'alg':'HS256','typ':'JWT'}; a=_b64(json.dumps(header,separators=(',',':')).encode()); b=_b64(json.dumps(claims,separators=(',',':'),default=str).encode()); sig=hmac.new(self.secret,f'{a}.{b}'.encode(),hashlib.sha256).digest(); return f'{a}.{b}.{_b64(sig)}'
    def decode(self,token):
        try:a,b,s=token.split('.'); expected=_b64(hmac.new(self.secret,f'{a}.{b}'.encode(),hashlib.sha256).digest())
        except Exception as exc: raise ValueError('Malformed JWT') from exc
        if not hmac.compare_digest(s,expected): raise ValueError('Invalid JWT signature')
        header=json.loads(_unb64(a)); payload=json.loads(_unb64(b))
        if header.get('alg')!='HS256': raise ValueError('Unsupported JWT algorithm')
        now=time.time()
        if 'exp' in payload and now>float(payload['exp'])+self.leeway: raise ValueError('JWT expired')
        if 'nbf' in payload and now+self.leeway<float(payload['nbf']): raise ValueError('JWT not active')
        if self.issuer is not None and payload.get('iss')!=self.issuer: raise ValueError('Invalid JWT issuer')
        if self.audience is not None:
            aud=payload.get('aud'); valid=self.audience in aud if isinstance(aud,list) else aud==self.audience
            if not valid: raise ValueError('Invalid JWT audience')
        return payload
    def authenticate(self,request):
        value=request.headers.get('Authorization','')
        if not value.lower().startswith('bearer '): return False
        try: request.auth=self.decode(value[7:].strip()); return True
        except ValueError: return False
