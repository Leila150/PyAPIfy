"""Compiled route definitions and parameter conversion."""
from __future__ import annotations
import inspect, re
from dataclasses import dataclass

_CONVERTERS = {
    "str": str,
    "int": int,
    "float": float,
    "path": str,
    "bool": lambda x: x.lower() in ("1", "true", "yes", "on"),
}


def register_converter(name, converter):
    if not isinstance(name, str) or not name:
        raise TypeError("Converter name must be a non-empty string")
    if not callable(converter):
        raise TypeError("Converter must be callable")
    _CONVERTERS[name] = converter


def unregister_converter(name):
    if name in {"str", "int", "float", "path", "bool"}:
        raise ValueError(f"Cannot remove built-in converter: {name}")
    return _CONVERTERS.pop(name, None)


@dataclass
class Route:
    path: str
    endpoint: object
    methods: set[str]
    name: str | None = None
    auth: object = None
    tags: tuple = ()
    websocket: bool = False

    def __post_init__(self):
        self.methods = {m.upper() for m in self.methods}
        self.name = self.name or getattr(self.endpoint, "__name__", "route")
        pattern = self.path
        self.param_names = []

        def repl(match):
            name, typ = match.group(1), match.group(2) or "str"
            if typ not in _CONVERTERS:
                raise ValueError(f"Unknown path converter: {typ}")
            self.param_names.append((name, typ))
            expression = {
                "path": ".*",
                "int": r"-?\d+",
                "float": r"-?\d+(?:\.\d+)?",
                "bool": r"[^/]+",
            }.get(typ, r"[^/]+")
            return f"(?P<{name}>{expression})"

        pattern = re.sub(r"\{([A-Za-z_]\w*)(?::\s*([A-Za-z_]\w*))?\}", repl, pattern)
        self.regex = re.compile("^" + pattern.rstrip("/") + "/?$")

    def match(self, path):
        match = self.regex.match(path)
        if not match:
            return None
        return {name: _CONVERTERS[typ](match.group(name)) for name, typ in self.param_names}

    def signature(self):
        return inspect.signature(self.endpoint)
