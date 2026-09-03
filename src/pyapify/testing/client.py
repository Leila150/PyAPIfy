"""In-process synchronous test client."""
import asyncio,json
from urllib.parse import urlencode
from ..http.request import Request
class TestResponse:
    def __init__(self,status,headers,body): self.status=status; self.status_code=status; self.headers=headers; self.content=body; self.body=body
    @property
    def text(self): return self.body.decode('utf-8',errors='replace')
    def json(self): return json.loads(self.text)
    def __bool__(self): return 200<=self.status<400
class TestClient:
    def __init__(self,app): self.app=app
    def request(self,method,path,*,json=None,data=None,headers=None,params=None,cookies=None):
        headers=dict(headers or {}); body=b''
        if params: path += ('&' if '?' in path else '?')+urlencode(params,doseq=True)
        if json is not None: body=__import__('json').dumps(json).encode(); headers.setdefault('Content-Type','application/json')
        elif data is not None: body=data.encode() if isinstance(data,str) else bytes(data)
        if cookies: headers['Cookie']='; '.join(f'{k}={v}' for k,v in cookies.items())
        headers.setdefault('Content-Length',str(len(body))); r=Request(method,path,headers,body,('testclient',0)); res=asyncio.run(self.app.dispatch(r)); status,h,b=res.serialize(); return TestResponse(status,h,b)
    def __getattr__(self,name):
        if name.upper() in {'GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS','TRACE','CONNECT'}: return lambda path,**kw:self.request(name.upper(),path,**kw)
        raise AttributeError(name)
