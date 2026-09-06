from pathlib import Path

from pyapify import PyAPIfy
from pyapify.plugins import Plugin
from pyapify.plugins.runtime import PyAPIfyRuntime


def test_runtime_creates_pyapify_tree(tmp_path):
    runtime = PyAPIfyRuntime(tmp_path / '.pyapify')
    assert runtime.plugins_dir.is_dir()
    assert runtime.logs_dir.is_dir()
    assert runtime.plugins_cache_dir.is_dir()
    assert runtime.pyapify_cache_dir.is_dir()
    runtime.log('info', 'runtime test')
    runtime.close()
    assert (tmp_path / '.pyapify' / 'logs' / 'latest_log.txt').is_file()


def test_plugin_cache_persists(tmp_path):
    runtime = PyAPIfyRuntime(tmp_path / '.pyapify')
    cache = runtime.cache('example')
    cache.set('answer', 42)
    assert cache.get('answer') == 42
    assert cache.has('answer')
    cache.delete('answer')
    assert cache.get('answer') is None
    runtime.close()


def test_plugin_use_binds_used_plugin():
    base = Plugin()
    feature = Plugin()
    feature.use(base)
    api = PyAPIfy(docs=False)
    api.use(feature)
    assert base in api.plugins
    assert feature in api.plugins


def test_plugin_cache_and_log_use_project_runtime(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = Path('.pyapify/plugins/example')
    root.mkdir(parents=True)
    plugin = Plugin(root)
    plugin.cache().set('hello', {'value': 'world'})
    assert plugin.cache().get('hello') == {'value': 'world'}
    plugin.log('info', 'plugin runtime test')
    assert (tmp_path / '.pyapify' / 'cache' / 'plugins_cache' / 'example').is_dir()
    assert (tmp_path / '.pyapify' / 'logs' / 'latest_log.txt').is_file()
