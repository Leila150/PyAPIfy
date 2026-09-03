# PyAPIfy

**Simple outside. Powerful inside.** A dependency-light Python API framework built around a clean developer experience.

## Quick start

```python
from pyapify import PyAPIfy, HTTP

api = PyAPIfy(title='My API', version='1.0.0')

@api.get('/')
def home():
    return {'message': 'Hello, PyAPIfy!'}

@api.get('/users/{id:int}')
def user(id):
    if id != 1:
        raise HTTP.status_code(status=HTTP.NOT_FOUND, detail='User does not exist')
    return HTTP.status_code({'id': id}, status=HTTP.OK)

@api.post('/users')
def create(body):
    return HTTP.status_code(body, status=HTTP.CREATED)

api.run()
```

## Included foundation

- GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS, TRACE and CONNECT routes
- Custom routes and typed path converters (`{id:int}`, `{price:float}`, `{path:path}`)
- JSON, text, raw bytes, form, cookie, header and query parsing
- Rich response builders, redirects, cookies and arbitrary HTTP status codes
- Responses that can also be raised as HTTP errors
- Sync and async endpoint support
- Dependency injection with `Depends`
- Middleware pipeline
- Route-level API-key, bearer, basic and custom authentication primitives
- Typed `Model` validation and nested serialization
- In-process test client
- OpenAPI 3.1 generation
- Background tasks
- SSE helpers
- Dependency-free development server
- CLI entry point

## Design

PyAPIfy does not wrap Starlette or another web framework. The routing, request/response model, dispatch layer and developer-facing API are owned by PyAPIfy. Optional integrations can be layered on later.

## Status

The repository is under active development. The core runtime is implemented; advanced production features such as HTTP/2, WebSockets, multipart streaming, TLS automation, full OpenAPI schemas, reload supervision, plugin discovery, metrics/tracing and the `.api` language are being implemented incrementally and must be tested before production use.
