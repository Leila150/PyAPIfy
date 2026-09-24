"""Dependency parsing and resolution for PyAPIfy plugins."""
from __future__ import annotations
import re

_VERSION = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?.*$")


def version_tuple(value):
    match = _VERSION.match(str(value or "0.0.0"))
    return tuple(int(x or 0) for x in match.groups()) if match else (0, 0, 0)


def satisfies(version, requirement):
    if not requirement:
        return True
    match = re.match(r"^(>=|<=|==|!=|>|<)?\s*(.+)$", str(requirement).strip())
    if not match:
        return False
    op, wanted = match.groups()
    if not op:
        return True
    current, target = version_tuple(version), version_tuple(wanted)
    return {">=": current >= target, "<=": current <= target, "==": current == target,
            "!=": current != target, ">": current > target, "<": current < target}[op]


def dependency_parts(dependency):
    if isinstance(dependency, dict):
        return str(dependency.get("name", "")), str(dependency.get("version", ""))
    value = str(dependency).strip()
    match = re.match(r"^([A-Za-z0-9_.-]+)\s*(>=|<=|==|!=|>|<)?\s*(.*)$", value)
    return match.group(1), ((match.group(2) or "") + (match.group(3) or "")).strip()


def resolve(manager):
    graph = {}
    for name, plugin in manager.plugins.items():
        graph[name] = []
        for dep in plugin.dependencies():
            dep_name, requirement = dependency_parts(dep)
            if not dep_name:
                continue
            graph[name].append((dep_name, requirement))
            found = manager.plugins.get(dep_name)
            if found is None:
                raise RuntimeError(f"Missing plugin dependency: {dep_name} required by {name}")
            if requirement and not satisfies(found.version(), requirement):
                raise RuntimeError(f"Plugin {name} requires {dep_name}{requirement}, found {found.version()}")
    order, visiting, visited = [], set(), set()
    def visit(name):
        if name in visiting:
            raise RuntimeError(f"Circular plugin dependency detected at: {name}")
        if name in visited:
            return
        visiting.add(name)
        for dep, _ in graph.get(name, []):
            visit(dep)
        visiting.remove(name)
        visited.add(name)
        order.append(name)
    for name in graph:
        visit(name)
    return order
