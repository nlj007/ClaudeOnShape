"""Feature-creation & update tools. High-level wrappers over builders."""
from ..builders import (
    SketchBuilder, SketchPlane,
    ExtrudeBuilder, ExtrudeType, EndBound,
    ChamferBuilder, ChamferType,
)

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
        "name": "update_feature",
        "description": (
            "Update a feature's parameters. Call get_features first, modify parameter "
            "values in the returned feature object, then pass the full modified feature "
            "plus the sourceMicroversion from that same get_features call."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                **_DWE,
                "feature": {"type": "object", "description": "Full modified feature object."},
                "source_microversion": {"type": "string"},
            },
            "required": [*_DWE_REQ, "feature", "source_microversion"],
        },
    },
    {
        "name": "create_circle_sketch",
        "description": (
            "Create a new sketch containing one circle. Coords/radius in METERS. "
            "Pick ONE of:\n"
            "  - `plane`: 'TOP' | 'FRONT' | 'RIGHT' — sketch on an origin plane\n"
            "  - `plane_id`: deterministic ID from find_faces — sketch on a body face\n"
            "Use a body face when the circle must sit ON an existing body (e.g. "
            "a counterbore recess around an existing hole). The sketch's local "
            "2D coordinates (center_x, center_y) are in the face's own UV frame, "
            "NOT world XY. For a concentric feature on a face centered on world "
            "origin, use center_x=center_y=0."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                **_DWE,
                "name": {"type": "string"},
                "plane": {"type": "string", "enum": ["TOP", "FRONT", "RIGHT"]},
                "plane_id": {"type": "string", "description": "Deterministic ID of a body face (from find_faces)."},
                "center_x": {"type": "number"},
                "center_y": {"type": "number"},
                "radius": {"type": "number"},
            },
            "required": [*_DWE_REQ, "name", "center_x", "center_y", "radius"],
        },
    },
    {
        "name": "create_rectangle_sketch",
        "description": (
            "Create a new sketch containing one centered rectangle. Use this "
            "as the base sketch for rectangular blocks/plates. Dimensions in "
            "METERS. Same plane/plane_id semantics as create_circle_sketch."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                **_DWE,
                "name": {"type": "string"},
                "plane": {"type": "string", "enum": ["TOP", "FRONT", "RIGHT"]},
                "plane_id": {"type": "string"},
                "center_x": {"type": "number"},
                "center_y": {"type": "number"},
                "width": {"type": "number", "description": "Width along sketch U-axis (meters)."},
                "height": {"type": "number", "description": "Height along sketch V-axis (meters)."},
            },
            "required": [*_DWE_REQ, "name", "center_x", "center_y", "width", "height"],
        },
    },
    {
        "name": "create_extrude",
        "description": (
            "Extrude the regions of a sketch. Operation: NEW body, ADD (boss), "
            "REMOVE (cut), INTERSECT. End bound: BLIND (use depth like '25 mm' "
            "or '1 in'), THROUGH_ALL, UP_TO_NEXT.\n\n"
            "DIRECTION: extrude grows along the sketch plane's normal. If the "
            "sketch is on the TOP face of a body, the default direction is +Z "
            "(upward, OUT of the body). For a REMOVE that cuts INTO the body, "
            "set `opposite_direction=true`. Rule of thumb: when sketching on a "
            "body face and cutting into it, opposite_direction=true. When "
            "extruding up from a floor plane, leave it false.\n\n"
            "Set second_direction=true to extrude both ways (e.g. a hole "
            "through a body from a mid-plane sketch)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                **_DWE,
                "sketch_feature_id": {"type": "string"},
                "name": {"type": "string"},
                "operation": {"type": "string", "enum": ["NEW", "ADD", "REMOVE", "INTERSECT"]},
                "end_bound": {"type": "string", "enum": ["BLIND", "THROUGH_ALL", "UP_TO_NEXT"]},
                "depth": {"type": "string"},
                "opposite_direction": {"type": "boolean", "default": False,
                    "description": "Explicit flip. Wins over target_direction."},
                "target_direction": {
                    "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                    "description": "World-coord vector for desired extrude growth, e.g. [0,0,-1] for 'down'. Requires sketch_plane_normal.",
                },
                "sketch_plane_normal": {
                    "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                    "description": "Normal of the sketch plane (from find_faces). Combined with target_direction to set opposite_direction automatically.",
                },
                "second_direction": {"type": "boolean"},
                "second_end_bound": {"type": "string", "enum": ["BLIND", "THROUGH_ALL", "UP_TO_NEXT"]},
                "second_depth": {"type": "string"},
            },
            "required": [*_DWE_REQ, "sketch_feature_id", "name", "operation", "end_bound"],
        },
    },
    {
        "name": "create_chamfer",
        "description": (
            "Chamfer edges by deterministic ID. Get IDs from find_edges. "
            "chamfer_type=EQUAL_OFFSETS is the common case and only uses "
            "`width`. Width is a quantity expression like '2 mm' or '1/8 in'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                **_DWE,
                "name": {"type": "string"},
                "edge_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "chamfer_type": {"type": "string",
                    "enum": ["EQUAL_OFFSETS", "TWO_OFFSETS", "OFFSET_ANGLE"],
                    "default": "EQUAL_OFFSETS"},
                "width": {"type": "string"},
                "width2": {"type": "string"},
                "angle": {"type": "string"},
                "tangent_propagation": {"type": "boolean", "default": False},
            },
            "required": [*_DWE_REQ, "edge_ids", "width"],
        },
    },
    {
        "name": "delete_feature",
        "description": "Delete a feature by featureId.",
        "input_schema": {
            "type": "object",
            "properties": {**_DWE, "feature_id": {"type": "string"}},
            "required": [*_DWE_REQ, "feature_id"],
        },
    },
]


def _update_feature(t, c):
    return c.update_features(*_ids(t), [t["feature"]], t["source_microversion"])


def _create_circle_sketch(t, c):
    # plane_id (deterministic ID of a body face) overrides the default plane.
    # If neither is given, fall back to TOP. Validated at the builder level.
    sb = SketchBuilder(
        name=t["name"],
        plane=SketchPlane[t.get("plane", "TOP")],
        plane_id=t.get("plane_id"),
    )
    sb.add_circle(t["center_x"], t["center_y"], t["radius"])
    return c.add_feature(*_ids(t), sb.build())


def _create_extrude(t, c):
    # Auto-resolve opposite_direction from target_direction + sketch_plane_normal.
    # Rule: extrude grows along (sketch_normal) by default; flipping grows along
    # (-sketch_normal). If the user's intended world direction opposes the
    # sketch normal (dot < 0), we must flip. Explicit opposite_direction wins.
    opp = t.get("opposite_direction", False)
    if not opp and "target_direction" in t and "sketch_plane_normal" in t:
        n = t["sketch_plane_normal"]
        d = t["target_direction"]
        dot = sum(n[i] * d[i] for i in range(3))
        opp = dot < 0
    eb = ExtrudeBuilder(
        sketch_feature_id=t["sketch_feature_id"],
        name=t["name"],
        operation=ExtrudeType[t["operation"]],
        end_bound=EndBound[t["end_bound"]],
        depth=t.get("depth", "25 mm"),
        opposite_direction=opp,
        second_direction=t.get("second_direction", False),
        second_end_bound=EndBound[t.get("second_end_bound", "BLIND")],
        second_depth=t.get("second_depth", "25 mm"),
    )
    return c.add_feature(*_ids(t), eb.build())


def _delete_feature(t, c):
    return c.delete_feature(*_ids(t), t["feature_id"])


def _create_chamfer(t, c):
    cb = ChamferBuilder(
        edge_ids=t["edge_ids"],
        name=t.get("name", "Chamfer"),
        chamfer_type=ChamferType[t.get("chamfer_type", "EQUAL_OFFSETS")],
        width=t["width"],
        width2=t.get("width2", "2 mm"),
        angle=t.get("angle", "45 deg"),
        tangent_propagation=t.get("tangent_propagation", False),
    )
    return c.add_feature(*_ids(t), cb.build())


def _create_rectangle_sketch(t, c):
    sb = SketchBuilder(
        name=t["name"],
        plane=SketchPlane[t.get("plane", "TOP")],
        plane_id=t.get("plane_id"),
    )
    sb.add_rectangle(t["center_x"], t["center_y"], t["width"], t["height"])
    return c.add_feature(*_ids(t), sb.build())


HANDLERS = {
    "update_feature": _update_feature,
    "create_circle_sketch": _create_circle_sketch,
    "create_rectangle_sketch": _create_rectangle_sketch,
    "create_extrude": _create_extrude,
    "create_chamfer": _create_chamfer,
    "delete_feature": _delete_feature,
}
