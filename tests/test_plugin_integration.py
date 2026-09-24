import asyncio
import pytest
from pyapify import HTTP, PyAPIfy, Plugin, http


def test_plugin_extensions_wire_into_runtime_registries():
    api = PyAPIfy(docs=False)
    plugin = Plugin()

    @plugin.create_converter(name='uuidish')
    def uuidish(value):
        return value.lower()

    @plugin.create_validator(name='positive')
    def positive(value):
        return value > 0

    @plugin.create_dependency(name='dependency')
    def dependency():
        return 'ok'

    @plugin.create_auth(name='auth_provider')
    def auth_provider(request):
        return True

    @plugin.create_permission(name='admin')
    def admin(request):
        return True

    @plugin.create_error_handler(name='custom_error')
    def custom_error(exc):
        return HTTP.text('handled', status=418)

    @plugin.create_route_type(name='custom')
    def custom_route(value):
        return value

    @plugin.create_http_method(name='PURGE')
    def purge():
        return None

    @plugin.create_status_code(name='CUSTOM', value=299)
    def status_code():
        return 299

    @plugin.create_request_handler(name='handler')
    def handler(request):
        return request

    @plugin.create_response_type(name='response')
    def response(value):
        return HTTP.text(value)

    @plugin.create_task(name='task')
    def task():
        return None

    @plugin.create_schedule(name='schedule')
    def schedule():
        return None

    @plugin.create_openapi(name='openapi_extension')
    def openapi_extension(document, app):
        document.setdefault('x-plugin', True)
        return document

    @plugin.create_documentation(name='docs')
    def docs():
        return 'docs'

    @plugin.create_websocket(name='socket')
    def socket():
        return None

    @plugin.create_sse(name='events')
    def events():
        return None

    @plugin.create_html(name='html')
    def html():
        return None

    @plugin.create_css(name='css')
    def css():
        return None

    @plugin.create_js(name='js')
    def js():
        return None

    @plugin.create_gui(name='gui')
    def gui():
        return None

    @plugin.create_storage(name='storage')
    def storage():
        return None

    @plugin.create_cache(name='cache')
    def cache():
        return None

    @plugin.create_server(name='server')
    def server():
        return None

    @plugin.create_https(name='https')
    def https():
        return None

    @plugin.create_log_handler(name='logger')
    def logger():
        return None

    @plugin.create_environment(name='env')
    def env():
        return None

    @plugin.create_plugin_extension(name='extension')
    def extension():
        return None

    @plugin.create_command(name='hello')
    def hello():
        return None

    @plugin.create_test(name='plugin_test')
    def plugin_test():
        return True

    api.use(plugin)

    assert api.validators['positive'] is positive
    assert api.model_types == {}
    assert api.dependencies['dependency'] is dependency
    assert api.auth_providers['auth_provider'] is auth_provider
    assert api.permissions['admin'] is admin
    assert api.route_types['custom'] is custom_route
    assert 'PURGE' in api.http_methods
    assert api.status_codes['CUSTOM'] == 299
    assert HTTP.CUSTOM == 299
    assert HTTP.custom(detail='custom').status == 299
    assert api.request_handlers['handler'] is handler
    assert api.response_types['response'] is response
    assert api.tasks['task'] is task
    assert api.schedules['schedule'] is schedule
    assert api.websocket_extensions['socket'] is socket
    assert api.sse_extensions['events'] is events
    assert api.html_extensions['html'] is html
    assert api.css_extensions['css'] is css
    assert api.js_extensions['js'] is js
    assert api.gui_extensions['gui'] is gui
    assert api.storage_extensions['storage'] is storage
    assert api.cache_extensions['cache'] is cache
    assert api.server_extensions['server'] is server
    assert api.https_extensions['https'] is https
    assert api.log_handlers['logger'] is logger
    assert api.environments['env'] is env
    assert api.plugin_extensions_registry['extension'] is extension
    assert api.commands['hello'] is hello
    assert api.tests['plugin_test'] is plugin_test
    assert api.openapi()['x-plugin'] is True
    assert http.status_code(code=200, detail='OK').status == 200


def test_plugin_converter_is_live_in_router():
    api = PyAPIfy(docs=False)
    plugin = Plugin()

    @plugin.create_converter(name='lower')
    def lower(value):
        return value.lower()

    api.use(plugin)

    @api.get('/items/{name: lower}')
    def item(name):
        return name

    response = api.test().get('/items/HELLO')
    assert response.status == 200
    assert response.data == 'hello'

    plugin.disable()
    assert 'lower' not in api.plugin_extensions('converter')


def test_plugin_route_type_is_live():
    api = PyAPIfy(docs=False)
    plugin = Plugin()

    @plugin.create_route_type(name='api_prefix')
    def api_prefix(path):
        return '/api' + (path if path.startswith('/') else '/' + path)

    api.use(plugin)

    @api.get('/items', route_type='api_prefix')
    def items():
        return 'ok'

    response = api.test().get('/api/items')
    assert response.status == 200
    assert response.data == 'ok'

    missing = api.test().get('/items')
    assert missing.status == 404


@pytest.mark.asyncio
async def test_plugin_schedule_runs_and_stops():
    api = PyAPIfy(docs=False)
    plugin = Plugin()
    calls = []

    @plugin.create_schedule(name='heartbeat', seconds=0)
    async def heartbeat():
        calls.append(1)
        if len(calls) >= 2:
            api._schedule_tasks['heartbeat'].cancel()

    api.use(plugin)
    await api.startup_async()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(calls) >= 2
    await api.shutdown_async()
    assert not api._schedule_tasks


@pytest.mark.asyncio
async def test_plugin_sse_extension_transforms_response():
    api = PyAPIfy(docs=False)
    plugin = Plugin()

    @plugin.create_sse(name='sse_wrapper')
    async def sse_wrapper(response, request):
        response.headers['X-SSE-Plugin'] = 'enabled'
        return response

    api.use(plugin)

    @api.get('/events')
    async def events():
        return HTTP.sse('hello')

    response = await api.dispatch(__import__('pyapify').Request('GET', '/events', {}, b'', ('127.0.0.1', 1), 'http'))
    assert response.status == 200
    assert response.headers['X-SSE-Plugin'] == 'enabled'


def test_plugin_websocket_extension_is_registered_for_transport():
    api = PyAPIfy(docs=False)
    plugin = Plugin()

    def websocket_extension(ws, request, route, params):
        return ws

    plugin.create_websocket(name='transport_hook')(websocket_extension)
    api.use(plugin)
    assert api.websocket_extensions['transport_hook'] is websocket_extension


@pytest.mark.asyncio
async def test_plugin_html_css_js_gui_extensions_transform_matching_responses():
    api = PyAPIfy(docs=False)
    plugin = Plugin()

    @plugin.create_html(name='html_extension')
    def html_extension(response, request):
        response.headers['X-HTML-Plugin'] = 'enabled'
        return response

    @plugin.create_css(name='css_extension')
    def css_extension(response, request):
        response.headers['X-CSS-Plugin'] = 'enabled'
        return response

    @plugin.create_js(name='js_extension')
    def js_extension(response, request):
        response.headers['X-JS-Plugin'] = 'enabled'
        return response

    @plugin.create_gui(name='gui_extension')
    def gui_extension(response, request):
        response.headers['X-GUI-Plugin'] = 'enabled'
        return response

    api.use(plugin)

    @api.html('/page')
    def page(): return '<h1>Hello</h1>'

    @api.css('/style.css')
    def style(): return 'body { margin: 0; }'

    @api.js('/app.js')
    def script(): return 'console.log(1);'

    @api.gui('/gui')
    def gui_page(): return 'gui'

    client = api.test()
    assert client.get('/page').headers['X-HTML-Plugin'] == 'enabled'
    assert client.get('/style.css').headers['X-CSS-Plugin'] == 'enabled'
    assert client.get('/app.js').headers['X-JS-Plugin'] == 'enabled'
    assert client.get('/gui').headers['X-GUI-Plugin'] == 'enabled'


@pytest.mark.asyncio
async def test_response_extension_type_error_is_not_retried():
    api = PyAPIfy(docs=False)
    plugin = Plugin()
    calls = []

    @plugin.create_html(name='broken_html')
    def broken_html(response, request):
        calls.append(1)
        raise TypeError('intentional extension failure')

    api.use(plugin)

    @api.html('/broken')
    def broken():
        return 'hello'

    response = await api.dispatch(
        __import__('pyapify').Request(
            'GET', '/broken', {}, b'', ('127.0.0.1', 1), 'http'
        )
    )

    assert response.status == 500
    assert calls == [1]
    assert 'TypeError' in response.data['error']
