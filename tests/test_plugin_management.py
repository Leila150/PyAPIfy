from pathlib import Path

from pyapify import PyAPIfy
from pyapify.plugins import Plugin


def make_plugin(root: Path, name: str):
    directory = root / name
    directory.mkdir()
    (directory / "info.json").write_text(
        '{"name": "%s", "version": "1.0.0", "dependencies": []}' % name,
        encoding="utf-8",
    )
    (directory / "main.py").write_text(
        "from PyAPIfy import Plugin\nplugin = Plugin()\n",
        encoding="utf-8",
    )
    return directory


def test_manager_installs_and_discovers(tmp_path, monkeypatch):
    plugin_root = tmp_path / "source"
    plugin_root.mkdir()
    source = make_plugin(plugin_root, "example")
    install_root = tmp_path / "installed"
    monkeypatch.setenv("PYAPIFY_PLUGIN_DIR", str(install_root))

    api = PyAPIfy(docs=False)
    destination = api.plugin_manager.install(source)
    assert destination == install_root / "example"
    loaded = api.plugin_manager.discover()
    assert loaded[0].name() == "example"
    assert api.plugin_manager.loaded("example")


def test_plugin_use_accepts_installed_name(tmp_path, monkeypatch):
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = make_plugin(source_root, "dependency")
    install_root = tmp_path / "installed"
    monkeypatch.setenv("PYAPIFY_PLUGIN_DIR", str(install_root))

    api = PyAPIfy(docs=False)
    api.plugin_manager.install(source)
    owner = Plugin(tmp_path / "owner")
    owner.root.mkdir()
    owner.bind(api)
    used = owner.use("dependency")
    assert used.name() == "dependency"
    assert used in owner.used_plugins()


def test_plugin_management_lifecycle(tmp_path, monkeypatch):
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = make_plugin(source_root, "lifecycle")
    install_root = tmp_path / "installed"
    monkeypatch.setenv("PYAPIFY_PLUGIN_DIR", str(install_root))

    api = PyAPIfy(docs=False)
    api.plugin_manager.install(source)
    plugin = api.plugin_manager.load(install_root / "lifecycle")
    assert plugin.exists()
    assert plugin.loaded()
    plugin.disable_plugin()
    assert not plugin.enabled()
    plugin.enable_plugin()
    assert plugin.enabled()
    plugin.uninstall()
    assert not (install_root / "lifecycle").exists()
