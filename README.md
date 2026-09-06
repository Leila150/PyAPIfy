# PyAPIfy

**Simple outside. Powerful inside.**

PyAPIfy is a Python application/API framework designed around one idea: **building with Python should feel like writing Python, not configuring a framework.**

It provides routing, request/response handling, validation, middleware, authentication, WebSockets, SSE, testing, lifecycle tooling, a development server and a first-class extension system — while keeping its core runtime independent.

## Quick start

```python
from pyapify import PyAPIfy

api = PyAPIfy()

@api.get('/users/{id:int}')
def user(id: int):
    return {'id': id}

api.run()
```

## Plugin extensions

PyAPIfy plugins exist **only to extend PyAPIfy**. They are not a general-purpose Python plugin system.

```python
from pyapify import Plugin

plugin = Plugin()

@plugin.create_decorator(name='cache')
def cache(api, *args, **kwargs):
    def decorator(fn):
        return fn
    return decorator
```

After the plugin is registered with an application:

```python
api.use(plugin)

@api.cache()
def data():
    return {'ok': True}
```

The official extension API includes:

- decorators — `create_decorator`, `edit_decorator`, `delete_decorator`
- functions — `create_function`, `edit_function`, `delete_function`
- hooks — `create_hook`, `edit_hook`, `delete_hook`
- route types — `create_route_type`, `edit_route_type`, `delete_route_type`
- middleware — `create_middleware`, `edit_middleware`, `delete_middleware`
- CLI commands — `create_command`, `edit_command`, `delete_command`
- configuration — `create_config`, `edit_config`, `delete_config`
- tests — `create_test`, `edit_test`, `delete_test`
- custom run systems — `create_run`, `edit_run`, `delete_run`
- additional extension categories through the same PyAPIfy extension registry

## Plugin layout

Plugins are manually installed under the PyAPIfy runtime directory:

```text
.pyapify/
├── plugins/
│   └── example_plugin/
│       ├── main.py
│       ├── info.json
│       └── src/
│           ├── __init__.py
│           └── ...
├── logs/
│   ├── latest_log_5.txt
│   ├── latest_log_4.txt
│   ├── latest_log_3.txt
│   ├── latest_log_2.txt
│   └── latest_log.txt
└── cache/
    ├── plugins_cache/
    ├── pyapify_cache/
    └── ...
```

A plugin entry point can load files relative to its own directory:

```python
from pyapify import Plugin

plugin = Plugin()
example = plugin.load('src/__init__.py')
```

## Core features

- GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS, TRACE and CONNECT routes
- typed path converters and route names
- query, header, cookie, form and file handling
- typed request models and validation
- JSON, text, HTML, XML, bytes, files, streaming and redirects
- arbitrary HTTP status responses
- dependency injection
- middleware
- authentication primitives
- route groups/routers
- WebSockets and SSE
- lifecycle hooks
- background tasks and interval scheduling
- in-process testing
- OpenAPI generation and interactive docs
- development CLI
- dependency-free HTTP server with automatic HTTPS development defaults
- first-class PyAPIfy-only plugins

## Architecture

PyAPIfy owns its core runtime instead of wrapping another web framework. Plugins sit above the core through a defined extension registry so extensions can add PyAPIfy capabilities without requiring developers to modify framework internals.

## Website

The repository contains the PyAPIfy website in `docs/`, including documentation and the plugin registry. A GitHub Pages workflow is included for deployment.

## Status

PyAPIfy is under active development. Advanced areas continue to be expanded and tested, including richer plugin discovery, production server capabilities, richer OpenAPI generation, metrics/tracing and the future `.api` language.

## License

See [LICENSE](LICENSE).
