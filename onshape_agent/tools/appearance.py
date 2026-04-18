"""Part appearance & naming tools."""

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
        "name": "rename_part",
        "description": "Rename a part.",
        "input_schema": {
            "type": "object",
            "properties": {
                **_DWE,
                "part_id": {"type": "string"},
                "new_name": {"type": "string"},
            },
            "required": [*_DWE_REQ, "part_id", "new_name"],
        },
    },
    {
        "name": "set_part_color",
        "description": "Set a part's display color. RGB components are 0-255 integers.",
        "input_schema": {
            "type": "object",
            "properties": {
                **_DWE,
                "part_id": {"type": "string"},
                "red": {"type": "integer", "minimum": 0, "maximum": 255},
                "green": {"type": "integer", "minimum": 0, "maximum": 255},
                "blue": {"type": "integer", "minimum": 0, "maximum": 255},
                "opacity": {"type": "integer", "minimum": 0, "maximum": 255, "default": 255},
            },
            "required": [*_DWE_REQ, "part_id", "red", "green", "blue"],
        },
    },
]


def _rename(t, c):
    return c.update_part_metadata(*_ids(t), t["part_id"], {"name": t["new_name"]})


def _color(t, c):
    appearance = {
        "isGenerated": False,
        "color": {
            "red": t["red"],
            "green": t["green"],
            "blue": t["blue"],
        },
        "opacity": t.get("opacity", 255),
    }
    return c.update_part_metadata(*_ids(t), t["part_id"], {"appearance": appearance})


HANDLERS = {
    "rename_part": _rename,
    "set_part_color": _color,
}
