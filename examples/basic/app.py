from pyapify import PyAPIfy, HTTP
api=PyAPIfy(title='Example API',version='1.0.0',debug=True)
@api.get('/')
def home(): return {'message':'Hello from PyAPIfy'}
@api.get('/users/{id:int}')
def user(id):
    if id != 1: raise HTTP.status_code(status=HTTP.NOT_FOUND,detail='User does not exist')
    return {'id':id,'name':'Leila'}
@api.post('/users')
def create(body): return HTTP.status_code(body,status=HTTP.CREATED)
if __name__=='__main__': api.run()
