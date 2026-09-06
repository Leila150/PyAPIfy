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
    assert api.status_codes['CUSTOM'] is status_code
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
