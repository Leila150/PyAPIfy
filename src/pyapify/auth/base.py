"""Authentication primitives."""
from abc import ABC,abstractmethod
class AuthProvider(ABC):
    @abstractmethod
    def authenticate(self,request): ...
class APIKeyAuth(AuthProvider):
    def __init__(self,key,header='X-API-Key'): self.key=key; self.header=header
    def authenticate(self,request): return request.headers.get(self.header)==self.key
class BearerAuth(AuthProvider):
    def __init__(self,token): self.token=token
    def authenticate(self,request): return request.headers.get('Authorization','')==f'Bearer {self.token}'
class BasicAuth(AuthProvider):
    def __init__(self,username,password): self.username=username; self.password=password
    def authenticate(self,request):
        import base64
        try:u,p=base64.b64decode(request.headers.get('Authorization','').split(' ',1)[1]).decode().split(':',1); return u==self.username and p==self.password
        except Exception:return False
