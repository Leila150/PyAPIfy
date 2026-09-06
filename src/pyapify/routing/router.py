"""Fast, dependency-free route registry."""
from .route import Route
from ..logging import get_logger

logger = get_logger("routing.router")


class Router:
    def __init__(self, prefix='', auth=None, tags=()):
        self.prefix = prefix.rstrip('/')
        self.auth = auth
        self.tags = tuple(tags)
        self.routes = []
        logger.debug("Router created: prefix=%r tags=%r", self.prefix, self.tags)

    def add(self, path, endpoint, methods=('GET',), name=None, auth=None, tags=(), websocket=False):
        full = (self.prefix + ('/' if not path.startswith('/') else '') + path) or '/'
        r = Route(full, endpoint, set(methods), name, self.auth if auth is None else auth, self.tags + tuple(tags), websocket)
        self.routes.append(r)
        logger.info("Route registered: %s %s -> %s", ','.join(sorted(r.methods)), full, r.name)
        return r

    def match(self, path, method):
        method = method.upper()
        for r in self.routes:
            params = r.match(path)
            if params is not None and method in r.methods:
                logger.debug("Route matched: %s %s -> %s", method, path, r.name)
                return r, params
        logger.debug("No route match: %s %s", method, path)
        return None, None

    def methods_for(self, path):
        methods = {m for r in self.routes if r.match(path) is not None for m in r.methods}
        logger.debug("Methods for %s: %s", path, ','.join(sorted(methods)) or '<none>')
        return methods
