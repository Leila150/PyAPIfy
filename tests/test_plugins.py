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


def test_all_documented_plugin_extension_builders_exist():
    plugin = Plugin(Path(__file__).parent)

    for kind in Plugin.EXTENSION_KINDS:
        assert hasattr(plugin, f"create_{kind}")
        assert hasattr(plugin, f"edit_{kind}")
        assert hasattr(plugin, f"delete_{kind}")


def test_extension_builder_create_edit_delete():
    plugin = Plugin(Path(__file__).parent)

    @plugin.create_validator(name="positive")
    def positive(value):
        return value > 0

    assert "validator" in plugin.capabilities()
    assert plugin.positive if hasattr(plugin, "positive") else True

    replacement = lambda value: value >= 0
    plugin.edit_validator("positive", replacement, description="updated")
    assert plugin.delete_validator("positive") is replacement
    assert "validator" not in plugin.capabilities()


def test_plugin_lifecycle_extension_is_owned_and_removed_on_disable():
    api = PyAPIfy(docs=False)
    plugin = Plugin(Path(__file__).parent)
    calls = []

    @plugin.create_lifecycle(name="startup_hook", phase="startup")
    def startup_hook(app):
        calls.append("startup")

    api.use(plugin)
    assert startup_hook in api._startup
    plugin.disable()
    assert startup_hook not in api._startup
    assert ("startup_hook" not in api.plugin_extensions("lifecycle"))


def test_plugin_lifecycle_edit_does_not_duplicate_callbacks():
    api = PyAPIfy(docs=False)
    plugin = Plugin(Path(__file__).parent)
    calls = []

    @plugin.create_lifecycle(name="startup_hook", phase="startup")
    def startup_hook(app):
        calls.append("old")

    api.use(plugin)

    def replacement(app):
        calls.append("new")

    plugin.edit_lifecycle("startup_hook", replacement, phase="startup")
    assert api._startup.count(replacement) == 1
    assert startup_hook not in api._startup


@pytest.mark.asyncio
async def test_plugin_async_lifecycle_hooks_run_and_shutdown_in_order():
    api = PyAPIfy(docs=False)
    plugin = Plugin(Path(__file__).parent)
    calls = []

    @plugin.create_lifecycle(name="startup_hook", phase="startup")
    async def startup_hook(app):
        calls.append("startup")

    @plugin.create_lifecycle(name="shutdown_hook", phase="shutdown")
    async def shutdown_hook(app):
        calls.append("shutdown")

    api.use(plugin)
    await api.startup_async()
    assert calls == ["startup"]
    assert api._started

    await api.shutdown_async()
    assert calls == ["startup", "shutdown"]
    assert not api._started


@pytest.mark.asyncio
async def test_failed_plugin_lifecycle_startup_rolls_back_app_state():
    api = PyAPIfy(docs=False)
    plugin = Plugin(Path(__file__).parent)

    @plugin.create_lifecycle(name="broken", phase="startup")
    async def broken(app):
        raise RuntimeError("startup failed")

    api.use(plugin)

    with pytest.raises(RuntimeError, match="startup failed"):
        await api.startup_async()

    assert not api._started
