"""Read-only tools: features, sketches, parts, metadata."""

_DWE = {
    "document_id": {"type": "string"},
    "workspace_id": {"type": "string"},
    "element_id": {"type": "string"},
}
_DWE_REQ = ["document_id", "workspace_id", "element_id"]


def _ids(t):
    return t["document_id"], t["workspace_id"], t["element_id"]


SCHEMAS = [
    {
        "name": "get_features",
        "description": "List all features in a part studio with full parameter definitions. Returns sourceMicroversion needed for updates.",
        "input_schema": {"type": "object", "properties": _DWE, "required": _DWE_REQ},
    },
    {
        "name": "get_sketches",
        "description": "Get all sketches with their entities (curves, constraints, dimensions).",
        "input_schema": {"type": "object", "properties": _DWE, "required": _DWE_REQ},
    },
    {
        "name": "get_parts",
        "description": "List all parts in a part studio with IDs, names, and basic metadata.",
        "input_schema": {"type": "object", "properties": _DWE, "required": _DWE_REQ},
    },
    {
        "name": "get_part_metadata",
        "description": "Get full metadata for a specific part (name, appearance, material, custom props).",
        "input_schema": {
            "type": "object",
            "properties": {**_DWE, "part_id": {"type": "string"}},
            "required": [*_DWE_REQ, "part_id"],
        },
    },
]

HANDLERS = {
    "get_features": lambda t, c: c.get_features(*_ids(t)),
    "get_sketches": lambda t, c: c.get_sketches(*_ids(t)),
    "get_parts": lambda t, c: c.get_parts(*_ids(t)),
    "get_part_metadata": lambda t, c: c.get_part_metadata(*_ids(t), t["part_id"]),
}
