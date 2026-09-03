import base64
import asyncio
from pyapify import PyAPIfy, HTTP, Request, APIKeyAuth, Model, Field
from pyapify.middleware import RequestIDMiddleware, SecurityHeadersMiddleware


def test_docs_and_any():
    api=PyAPIfy()
    api.any('/x')(lambda: {'ok': True})
    assert api.openapi()['openapi']=='3.1.0'
    assert any(r.path=='/docs' for r in api.router.routes)
    assert api.test().get('/x').status_code==200


def test_auth_provider():
    api=PyAPIfy()
    api.get('/private',auth=APIKeyAuth('secret'))(lambda: {'ok':True})
    client=api.test()
    assert client.get('/private').status_code==401
    assert client.get('/private',headers={'X-API-Key':'secret'}).status_code==200


def test_model_field_schema():
    class User(Model):
        name: str = Field(min_length=2)
        age: int = 18
    user=User(name='Leila')
    assert user.age==18 and user.model_dump()['name']=='Leila'
    assert 'properties' in User.model_json_schema()


def test_middleware():
    api=PyAPIfy(docs=False)
    api.add_middleware(RequestIDMiddleware)
    api.add_middleware(SecurityHeadersMiddleware)
    api.get('/')(lambda: {'ok':True})
    response=api.test().get('/')
    assert response.status_code==200
    assert response.headers.get('X-Request-ID')
    assert response.headers.get('X-Content-Type-Options')=='nosniff'


def test_basic_request_helpers():
    encoded=base64.b64encode(b'a=b').decode()
    request=Request('POST','/x?a=1&a=2',{'Content-Type':'application/x-www-form-urlencoded','Cookie':'sid=abc'},b'a=b')
    assert request.params['a']==['1','2']
    assert request.form['a']=='b'
    assert request.cookies['sid']=='abc'
