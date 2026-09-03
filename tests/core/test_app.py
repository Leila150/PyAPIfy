from pyapify import PyAPIfy,HTTP,Request,Model

def test_routes_and_params():
    api=PyAPIfy()
    @api.get('/users/{id:int}')
    def user(id): return {'id':id}
    r=api.test().get('/users/42'); assert r.status==200; assert r.json()=={'id':42}

def test_post_json_and_status():
    api=PyAPIfy()
    @api.post('/users')
    def create(body): return HTTP.status_code(body,status=201)
    r=api.test().post('/users',json={'name':'A'}); assert r.status==201 and r.json()['name']=='A'

def test_auth():
    api=PyAPIfy()
    @api.get('/private',auth='secret')
    def private(): return {'ok':True}
    assert api.test().get('/private').status==401
    assert api.test().get('/private',headers={'X-API-Key':'secret'}).status==200

def test_http_helpers():
    r=api=PyAPIfy().test()
    # response helper is intentionally raisable as well as returnable
    x=HTTP.redirect('/new'); assert x.status==302 and x.headers['Location']=='/new'

def test_model():
    class User(Model):
        name:str
        age:int
    u=User(name='Leila',age='20'); assert u.age==20 and u.dict()['name']=='Leila'
