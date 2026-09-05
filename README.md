# PyAPIfy

**Simple outside. Powerful inside.**

PyAPIfy is a Python API framework designed around one idea: **building an API should feel like writing Python, not configuring a framework.**

It takes the best developer ideas from lightweight web frameworks and modern typed API frameworks, while keeping PyAPIfy’s routing, request/response handling, server, validation and dispatch system independent.

## The goal

A great API package should give you:

- **Tiny everyday code** — routes should take one decorator and one function.
- **Python-native typing** — use `int`, `str`, `bool`, models and normal function signatures.
- **Power when you need it** — middleware, dependency injection, authentication, streaming, WebSockets, SSE, files and lifecycle hooks are available without changing the basic programming model.
- **Excellent defaults** — JSON responses, errors, OpenAPI, testing and development tooling should work with little configuration.
- **No framework maze** — the common path should be obvious, while advanced features remain discoverable.
- **Independent internals** — PyAPIfy does not wrap Starlette or another web framework.

## Hello API

```python
from pyapify import PyAPIfy

api = PyAPIfy()

@api.get('/')
def home():
    return {'message': 'Hello!'}

@api.get('/users/{id:int}')
def user(id: int):
    return {'id': id}

api.run()
```

That's the normal PyAPIfy experience.

## Request models

```python
from pyapify import Model

class User(Model):
    username: str
    age: int

@api.post('/users')
def create_user(user: User):
    return user.model_dump()
```

The function signature describes what the endpoint needs. PyAPIfy handles request extraction and validation.

## Responses without ceremony

Returning normal Python data is enough:

```python
@api.get('/hello')
def hello():
    return {'message': 'hello'}
```

When you need control, use the same small `HTTP` object everywhere:

```python
from pyapify import HTTP

@api.post('/users')
def create_user(user: User):
    return HTTP.created(user.model_dump())

@api.get('/users/{id:int}')
def get_user(id: int):
    if id != 1:
        raise HTTP.not_found(detail='User does not exist')
    return {'id': id}
```

Available response tools include JSON, text, HTML, XML, bytes, files, streaming, SSE, redirects, cookies, headers and arbitrary HTTP status codes.

## Dependencies

Shared application logic stays clean:

```python
from pyapify import depends


def current_user(request):
    return authenticate(request)

@api.get('/me')
def me(user=depends(current_user)):
    return user
```

Dependencies can be nested, synchronous or asynchronous, and can be cached per request.

## Authentication

Authentication is explicit and composable:

```python
API_KEY = 'secret'

@api.get('/admin', auth=API_KEY)
def admin():
    return {'ok': True}
```

Built-in authentication primitives include API keys, bearer tokens, basic authentication and JWT.

## Middleware

```python
@api.middleware
async def logger(request, next):
    print(request.method, request.path)
    return await next(request)
```

Built-in middleware covers common API needs such as CORS, security headers, request IDs, timing and rate limiting.

## WebSockets and SSE

```python
@api.websocket('/chat')
async def chat(socket):
    while True:
        message = await socket.receive()
        await socket.send(message)
```

```python
@api.sse('/events')
async def events():
    yield {'message': 'hello'}
```

## Testing

```python
client = api.test()

response = client.get('/')
assert response.status_code == 200
assert response.json()['message'] == 'Hello!'
```

No real server is required for basic endpoint tests.

## Automatic API documentation

PyAPIfy generates OpenAPI and exposes interactive documentation:

- `/openapi.json`
- `/docs`
- `/redoc`

Routes, typed parameters and models can contribute to the generated schema.

## Development server

```python
api.run()
```

The development server is designed to be convenient: it binds to the local network, uses HTTPS by default with an automatically generated development certificate, and accepts your own certificate when needed.

```python
api.run(certfile='certificate.pem', keyfile='private-key.pem')
```

Plain HTTP is still explicit:

```python
api.run(https=False)
```

## CLI

PyAPIfy also provides a development CLI for inspecting routes, validating projects, generating OpenAPI, running tests and other framework tasks.

```bash
pyapify dev app.py
pyapify routes app.py
pyapify openapi app.py
pyapify test
pyapify doctor
```

## What makes PyAPIfy different?

The target is **not** to make developers learn 100 features before writing their first route.

The target is:

> **5 lines for a simple API. Serious infrastructure when the API grows.**

A beginner can start with decorators and dictionaries. An experienced developer can progressively add models, dependencies, authentication, middleware, routers, streaming, WebSockets, plugins and production-oriented controls without replacing the programming model.

## Architecture

PyAPIfy owns its core runtime:

- routing
- HTTP request parsing
- HTTP response handling
- dispatch
- validation/models
- dependency injection
- middleware
- authentication primitives
- development server
- testing client
- OpenAPI generation
- WebSocket transport
- SSE
- CLI

Optional integrations can be layered on top without turning the core into a dependency-heavy framework.

## Status

PyAPIfy is under active development. The core developer experience is implemented, while advanced areas such as HTTP/2, richer OpenAPI generation, reload supervision, plugin discovery, metrics/tracing, additional authentication flows, database integrations and the `.api` language continue to be developed and tested.

## License

See [LICENSE](LICENSE).
