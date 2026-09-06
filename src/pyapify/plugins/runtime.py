"""Runtime filesystem, logging, and cache services for PyAPIfy plugins."""
from __future__ import annotations
import functools, logging, os, pickle, shutil, time
from pathlib import Path


class PluginCache:
    """Persistent cache owned by one PyAPIfy plugin."""
    def __init__(self, root, plugin_name):
        safe = ''.join(c if c.isalnum() or c in '._-' else '_' for c in plugin_name) or 'plugin'
        self.root = Path(root).expanduser().resolve() / 'cache' / 'plugins_cache' / safe
        self.root.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger('pyapify.cache')
        self.logger.debug('Plugin cache initialized: %s', self.root)

    def _path(self, key):
        if not isinstance(key, str) or not key: raise TypeError('Cache key must be a non-empty string')
        filename = ''.join(c if c.isalnum() or c in '._-' else '_' for c in key)
        return self.root / (filename + '.cache')

    def set(self, key, value, *, ttl=None):
        if ttl is not None and (not isinstance(ttl, (int, float)) or ttl < 0): raise ValueError('ttl must be a non-negative number or None')
        payload = {'value': value, 'expires': None if ttl is None else time.time() + ttl}
        path, tmp = self._path(key), self._path(key).with_suffix('.tmp')
        with tmp.open('wb') as fh: pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(path)
        self.logger.debug('Cache set: %s', key)
        return value

    put = set

    def get(self, key, default=None):
        path = self._path(key)
        if not path.is_file():
            self.logger.debug('Cache miss: %s', key)
            return default
        try:
            with path.open('rb') as fh: payload = pickle.load(fh)
            expires = payload.get('expires')
            if expires is not None and time.time() >= expires:
                path.unlink(missing_ok=True); self.logger.debug('Cache expired: %s', key); return default
            self.logger.debug('Cache hit: %s', key)
            return payload.get('value', default)
        except (OSError, EOFError, pickle.PickleError, ValueError, TypeError, AttributeError):
            self.logger.warning('Invalid cache entry ignored: %s', key, exc_info=True)
            return default

    def has(self, key):
        marker = object(); return self.get(key, marker) is not marker
    contains = has

    def delete(self, key):
        path = self._path(key); existed = path.is_file(); path.unlink(missing_ok=True)
        self.logger.debug('Cache delete: %s existed=%s', key, existed)
        return existed
    remove = delete

    def clear(self):
        for path in self.root.glob('*.cache'): path.unlink(missing_ok=True)
        self.logger.info('Plugin cache cleared: %s', self.root)
        return self

    def keys(self): return [p.stem for p in self.root.glob('*.cache')]
    def path(self): return self.root
    def __contains__(self, key): return self.has(key)

    def __getitem__(self, key):
        marker = object(); value = self.get(key, marker)
        if value is marker: raise KeyError(key)
        return value

    def __setitem__(self, key, value): self.set(key, value)
    def __delitem__(self, key):
        if not self.delete(key): raise KeyError(key)

    def decorator(self, key=None, *, ttl=None):
        """Cache a function result using its arguments as part of the key."""
        def decorate(fn):
            prefix = key or fn.__name__
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                try: identity = pickle.dumps((prefix, args, sorted(kwargs.items())), protocol=4).hex()
                except (TypeError, pickle.PickleError): return fn(*args, **kwargs)
                marker = object(); value = self.get(identity, marker)
                if value is not marker: return value
                value = fn(*args, **kwargs); self.set(identity, value, ttl=ttl); return value
            return wrapper
        return decorate
    __call__ = decorator


class PyAPIfyRuntime:
    """Owns the project-local .pyapify runtime directory."""
    def __init__(self, root=None, *, max_logs=5):
        self.root = Path(root).expanduser().resolve() if root else Path.cwd().resolve() / '.pyapify'
        self.max_logs = max(2, int(max_logs))
        self.plugins_dir = self.root / 'plugins'; self.logs_dir = self.root / 'logs'; self.cache_dir = self.root / 'cache'
        self.plugins_cache_dir = self.cache_dir / 'plugins_cache'; self.pyapify_cache_dir = self.cache_dir / 'pyapify_cache'
        self.ensure(); self.log_file = self.logs_dir / 'latest_log.txt'; self.logger = self._create_logger()
        self.log('info', 'PyAPIfy runtime ready: %s', self.root)

    def ensure(self):
        for path in (self.plugins_dir, self.logs_dir, self.plugins_cache_dir, self.pyapify_cache_dir): path.mkdir(parents=True, exist_ok=True)
        return self

    def _rotate_logs(self):
        current = self.logs_dir / 'latest_log.txt'
        if not current.exists() or current.stat().st_size == 0: return
        oldest = self.logs_dir / f'latest_log_{self.max_logs}.txt'
        if oldest.exists(): oldest.unlink()
        for index in range(self.max_logs - 1, 1, -1):
            src, dst = self.logs_dir / f'latest_log_{index}.txt', self.logs_dir / f'latest_log_{index + 1}.txt'
            if src.exists(): src.replace(dst)
        current.replace(self.logs_dir / 'latest_log_2.txt')

    def _create_logger(self):
        self._rotate_logs(); logger = logging.getLogger('pyapify'); logger.setLevel(logging.DEBUG); logger.propagate = False
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            try: handler.close()
            except Exception: pass
        handler = logging.FileHandler(self.log_file, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s')); logger.addHandler(handler); return logger

    def cache(self, plugin_name='pyapify'): return PluginCache(self.root, plugin_name)
    def log(self, level, message, *args, **kwargs):
        method = getattr(self.logger, str(level).lower(), None)
        if method is None: raise ValueError(f'Unknown log level: {level}')
        method(message, *args, **kwargs)

    def close(self):
        for handler in list(self.logger.handlers): handler.flush(); handler.close(); self.logger.removeHandler(handler)

    def clear_cache(self):
        self.log('info', 'Clearing PyAPIfy runtime cache')
        if self.cache_dir.exists(): shutil.rmtree(self.cache_dir)
        self.ensure(); return self
