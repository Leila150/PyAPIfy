import asyncio, base64, json, socket, struct
from pyapify import PyAPIfy, HTTP, Request, APIKeyAuth, JWTAuth, Model, Field
from pyapify.middleware import RequestIDMiddleware, SecurityHeadersMiddleware
from pyapify.websocket.websocket import WebSocket

def test_docs_and_any():
    api=PyAPIfy(); api.any('/x')(lambda: {'ok': True})
    assert api.openapi()['openapi']=='3.1.0'; assert any(r.path=='/docs' for r in api.router.routes); assert api.test().get('/x').status_code==200

def test_auth_provider():
    api=PyAPIfy(); api.get('/private',auth=APIKeyAuth('secret'))(lambda: {'ok':True}); client=api.test()
    assert client.get('/private').status_code==401; assert client.get('/private',headers={'X-API-Key':'secret'}).status_code==200

def test_jwt_provider():
    auth=JWTAuth('secret',issuer='test'); token=auth.encode({'sub':'123'},expires_in=60); api=PyAPIfy(docs=False); api.get('/private',auth=auth)(lambda: {'ok':True})
    response=api.test().get('/private',headers={'Authorization':'Bearer '+token}); assert response.status_code==200

def test_model_field_schema():
    class User(Model):
        name: str = Field(min_length=2); age: int = 18
    user=User(name='Leila'); assert user.age==18 and user.model_dump()['name']=='Leila'; assert 'properties' in User.model_json_schema()

def test_typed_query_and_openapi():
    api=PyAPIfy(docs=False)
    @api.get('/search')
    def search(limit:int=10, active:bool=False): return {'limit':limit,'active':active}
    response=api.test().get('/search?limit=5&active=true'); assert response.json()=={'limit':5,'active':True}
    assert api.openapi()['paths']['/search']['get']['parameters'][0]['schema']['type'] in ('integer','boolean')

def test_sse():
    response=HTTP.sse([{'event':'message','id':'1','data':'hello'},'world']); status,headers,body=response.serialize()
    assert status==200 and headers['Content-Type']=='text/event-stream' and b'event: message' in body and b'data: hello' in body

def test_middleware():
    api=PyAPIfy(docs=False); api.add_middleware(RequestIDMiddleware); api.add_middleware(SecurityHeadersMiddleware); api.get('/')(lambda: {'ok':True})
    response=api.test().get('/'); assert response.status_code==200; assert response.headers.get('X-Request-ID'); assert response.headers.get('X-Content-Type-Options')=='nosniff'

def test_basic_request_helpers():
    request=Request('POST','/x?a=1&a=2',{'Content-Type':'application/x-www-form-urlencoded','Cookie':'sid=abc'},b'a=b')
    assert request.params['a']==['1','2']; assert request.form['a']=='b'; assert request.cookies['sid']=='abc'

def test_websocket_frames():
    left,right=socket.socketpair(); ws=WebSocket(left); ws.send('hello'); frame=right.recv(64); assert frame[:2]==b'\x81\x05' and frame[2:]==b'hello'; right.sendall(b'\x81\x05world'); assert ws.receive()=='world'; left.close(); right.close()
