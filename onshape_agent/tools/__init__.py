"""Tool registry — aggregates neutral tool schemas and dispatch across domains.

Each domain module exposes:
    SCHEMAS: list[dict]  — neutral JSON schemas {name, description, input_schema}
    HANDLERS: dict[str, callable(input: dict, client) -> dict|list|str]
"""
import json
from . import reads, features, appearance, featurescript, geometry

_MODULES = [reads, features, appearance, featurescript, geometry]


def all_schemas() -> list:
    out = []
    for m in _MODULES:
        out.extend(m.SCHEMAS)
    return out


def _handlers() -> dict:
    out = {}
    for m in _MODULES:
        out.update(m.HANDLERS)
    return out


def dispatch(tool_name: str, tool_input: dict, client) -> str:
    handlers = _handlers()
    if tool_name not in handlers:
        return f"Unknown tool: {tool_name}"
    try:
        result = handlers[tool_name](tool_input, client)
    except Exception as e:
        return f"Error calling {tool_name}: {type(e).__name__}: {e}"
    if isinstance(result, (dict, list)):
        return json.dumps(result, indent=2, default=str)
    return str(result)
