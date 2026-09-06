from pathlib import Path

from pyapify import Plugin, PyAPIfy


def test_plugin_registers_function_decorator_and_run():
    api = PyAPIfy(docs=False)
    plugin = Plugin(Path(__file__).parent)

    @plugin.create_function(name="hello_plugin")
    def hello(app, name="world"):
        return f"hello {name}"

    @plugin.create_run(name="custom_run")
    def custom_run(app, value):
        return value * 2

    @plugin.create_decorator(name="marker")
    def marker(app, value="ok"):
        def decorate(fn):
            fn.plugin_marker = value
            return fn
        return decorate

    api.use(plugin)

    assert api.hello_plugin("PyAPIfy") == "hello PyAPIfy"
    assert api.custom_run(21) == 42

    @api.marker("works")
    def endpoint():
        return True

    assert endpoint.plugin_marker == "works"
    assert plugin.is_registered()
    assert plugin.enabled()


def test_plugin_disable_removes_extensions():
    api = PyAPIfy(docs=False)
    plugin = Plugin(Path(__file__).parent)

    @plugin.create_function(name="temporary_extension")
    def temporary_extension(app):
        return True

    api.use(plugin)
    assert api.temporary_extension() is True

    plugin.disable()
    assert not plugin.enabled()
    assert not hasattr(api, "temporary_extension")
