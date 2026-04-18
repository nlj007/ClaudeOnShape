"""Geometric selection tools — resolve semantic face/edge descriptions to
deterministic IDs that can be plugged into feature JSON.

The core function is `find_faces`. It runs a FeatureScript lambda against the
part studio to enumerate faces along with their surface type, normal, origin,
area, and (for cylinders) radius + axis. Python then filters and ranks the
results by user criteria — e.g. "planar face pointing +Z with the highest z
coordinate owned by feature X".

Why do this client-side-ranking split?
- Onshape's FeatureScript is great at topological queries (qCreatedBy,
  qGeometry, qCapEntity) but expressing "sort by origin.z descending, take
  first" in a dynamic lambda is painful and makes the lambda hard to cache.
- Our agent needs to log/inspect intermediate candidates; having the full list
  in Python makes debugging tractable.
- Adds one tiny extra round-trip but zero material latency for typical 4-20
  face studios.

The returned FaceRef dicts are directly embeddable as deterministic IDs in
subsequent BTMIndividualQuery-138 entries (see SketchBuilder.plane_id,
ExtrudeBuilder.region_entity_ids, or fillet/chamfer builders later).

See the field survey for why this pattern was chosen:
- hedless hardcodes "Top"/"Front"/"Right" + filters bodydetails responses
- clarsbyte adds find_circular_edges with the same FS-lambda-via-REST pattern
- Nobody does auto-direction-from-normal yet — that's in features.py
"""
from ..fsvalue import decode

# FeatureScript lambda. Enumerates every face in the part studio matching a
# source query, evaluates its surface, and returns a list of records.
#
# Placeholders filled in at call time:
#   {source_query}  — FS expression producing a Query of FACE entities
#
# Per-face record: {id, surface_type, origin[3], normal[3], area, radius?, axis?[3]}
# Lengths are in meters (Onshape internal unit).
_FIND_FACES_FS = """
function(context is Context, queries) {
    var faceQ = {source_query};
    var faces = evaluateQuery(context, faceQ);
    var result = [];
    for (var f in faces) {
        var rec = {};
        // transientQueriesToStrings(Query) returns a STRING directly (not an
        // array). Don't index into it — that triggers "Attempt to dereference
        // non-container". If you need the array form, wrap input in [f].
        rec.id = transientQueriesToStrings(f);
        // try(expr) returns undefined on MODELING errors (e.g. non-planar
        // face passed to evPlane). Do NOT use `as number` casts — they fail
        // when the value is undefined.
        var plane = try(evPlane(context, {"face": f}));
        if (plane != undefined) {
            rec.surface_type = "PLANE";
            rec.origin = [plane.origin[0].value, plane.origin[1].value, plane.origin[2].value];
            rec.normal = [plane.normal[0], plane.normal[1], plane.normal[2]];
            result = append(result, rec);
            continue;
        }
        var sdef = try(evSurfaceDefinition(context, {"face": f}));
        if (sdef is Cylinder) {
            rec.surface_type = "CYLINDER";
            rec.radius = sdef.radius.value;
            rec.origin = [sdef.coordSystem.origin[0].value, sdef.coordSystem.origin[1].value, sdef.coordSystem.origin[2].value];
            rec.axis = [sdef.coordSystem.zAxis[0], sdef.coordSystem.zAxis[1], sdef.coordSystem.zAxis[2]];
            rec.normal = rec.axis;
            result = append(result, rec);
            continue;
        }
        rec.surface_type = "OTHER";
        result = append(result, rec);
    }
    return result;
}
"""


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(v):
    m = (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5
    return [v[0] / m, v[1] / m, v[2] / m] if m else v


import math


def _source_query(created_by_feature_id, include_construction):
    """Build the FS Query expression for the source set of faces.

    Defaults to all non-construction faces in the studio — construction planes
    (Top/Front/Right) are excluded because the agent almost never wants them
    once a body exists; use the SketchPlane enum for those.
    """
    if created_by_feature_id:
        # qCreatedBy filters to faces created by a specific feature. Faces
        # later consumed by a boolean/cut may not be present — use the full
        # studio query if the feature has since been modified.
        q = f'qCreatedBy(makeId("{created_by_feature_id}"), EntityType.FACE)'
    else:
        q = "qEverything(EntityType.FACE)"
    if not include_construction:
        q = f"qSubtraction({q}, qConstructionFilter({q}, ConstructionObject.YES))"
    return q


SCHEMAS = [
    {
        "name": "find_faces",
        "description": (
            "Resolve a semantic face description to deterministic IDs (the "
            "`id` field of the returned FaceRef dicts). Use the IDs as "
            "`plane_id` for create_circle_sketch or as region/target refs "
            "elsewhere.\n\n"
            "Filters are ANDed. Results are ranked by (1) distance from "
            "near_point ascending, then (2) the extremum axis, then (3) area "
            "descending. Use `limit` to cap how many are returned.\n\n"
            "Common recipes:\n"
            "- Top face of the only body:     normal_like=[0,0,1], extremum='max_z', surface_type='PLANE'\n"
            "- Top face of feature Extrude1:  created_by_feature_id='FJJM6...', normal_like=[0,0,1], surface_type='PLANE'\n"
            "- The 2-inch-Ø cylindrical hole: surface_type='CYLINDER', diameter=0.0508\n"
            "- Face nearest a point:          near_point=[0.01,0,0.05]"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "workspace_id": {"type": "string"},
                "element_id": {"type": "string"},
                "created_by_feature_id": {
                    "type": "string",
                    "description": "Restrict to faces created by this feature (uses qCreatedBy).",
                },
                "surface_type": {
                    "type": "string",
                    "enum": ["PLANE", "CYLINDER", "ANY"],
                    "default": "ANY",
                },
                "normal_like": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3, "maxItems": 3,
                    "description": "Target normal vector (in world coords). Matching faces have normal within normal_tolerance_deg.",
                },
                "normal_tolerance_deg": {"type": "number", "default": 15.0},
                "extremum": {
                    "type": "string",
                    "enum": ["max_x", "min_x", "max_y", "min_y", "max_z", "min_z"],
                    "description": "Keep the face whose origin extremizes this axis (after other filters).",
                },
                "diameter": {
                    "type": "number",
                    "description": "For CYLINDER: match cylinders with this diameter (meters) within tolerance.",
                },
                "diameter_tolerance": {"type": "number", "default": 1e-4},
                "near_point": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3, "maxItems": 3,
                    "description": "Sort results by distance from this point ascending (meters).",
                },
                "include_construction": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include origin Top/Front/Right construction planes.",
                },
                "limit": {"type": "integer", "default": 5, "minimum": 1},
            },
            "required": ["document_id", "workspace_id", "element_id"],
        },
    }
]


def _find_faces(t, c):
    script = _FIND_FACES_FS.replace(
        "{source_query}",
        _source_query(t.get("created_by_feature_id"), t.get("include_construction", False)),
    )
    raw = c.eval_featurescript(t["document_id"], t["workspace_id"], t["element_id"], script)
    faces = decode(raw)
    # Expect a list. Defensive: if FS returned empty or non-list, just bail.
    if not isinstance(faces, list):
        return {"faces": [], "note": "FS returned non-list", "raw": faces}

    surface_type = t.get("surface_type", "ANY")
    if surface_type != "ANY":
        faces = [f for f in faces if f.get("surface_type") == surface_type]

    if "normal_like" in t:
        target = _norm(t["normal_like"])
        cos_thresh = math.cos(math.radians(t.get("normal_tolerance_deg", 15.0)))
        faces = [
            f for f in faces
            if "normal" in f and _dot(_norm(f["normal"]), target) >= cos_thresh
        ]

    if "diameter" in t:
        d = t["diameter"]
        tol = t.get("diameter_tolerance", 1e-4)
        faces = [
            f for f in faces
            if f.get("surface_type") == "CYLINDER"
            and abs(2 * f.get("radius", 0) - d) < tol
        ]

    # Sort. Keys applied in reverse order (stable sort, last key wins primacy).
    # Primacy desired: near_point > extremum > area.
    if faces:
        faces.sort(key=lambda f: -float(f.get("area") or 0))
        if "extremum" in t:
            axis = {"x": 0, "y": 1, "z": 2}[t["extremum"][-1]]
            sign = 1 if t["extremum"].startswith("max") else -1
            faces.sort(key=lambda f: sign * (f.get("origin") or [0, 0, 0])[axis], reverse=True)
        if "near_point" in t:
            p = t["near_point"]
            def dist(f):
                o = f.get("origin") or [0, 0, 0]
                return sum((o[i] - p[i]) ** 2 for i in range(3))
            faces.sort(key=dist)

    limit = int(t.get("limit", 5))
    return {"faces": faces[:limit], "total_matched": len(faces)}


# ----------------------------------------------------------------------------
# find_edges — narrow version for fillet/chamfer targeting.
#
# Filters supported:
#   - edge_type:         "LINE" | "CIRCLE" | "ANY"
#   - created_by_feature_id: qCreatedBy filter
#   - body_id:           deterministic ID of a body; returns ONLY edges on it
#   - adjacent_to_face_id: deterministic ID of a face; returns edges that
#                          touch that face (useful for "edges around the hole")
#
# Returns, per edge: {id, edge_type, length, vertices: [[x,y,z], [x,y,z]]}
# (vertices are start/end for lines, or arbitrary points on the loop for
# circles — the agent shouldn't rely on vertex identity for circles).
# ----------------------------------------------------------------------------

_FIND_EDGES_FS = """
function(context is Context, queries) {
    // Helper: resolve a deterministic ID (e.g. "JHD") to a Query by scanning
    // all entities of the given type and matching transientQueriesToStrings.
    // qTransient / makeId don't produce a valid Query for deterministic IDs
    // — this lookup is the workable pattern.
    // Deterministic IDs of bodies and faces to resolve (empty string = skip):
    var bodyDetId = "{body_id}";
    var faceDetId = "{face_id}";
    var bodyQ = undefined;
    if (bodyDetId != "") {
        for (var b in evaluateQuery(context, qEverything(EntityType.BODY))) {
            if (transientQueriesToStrings(b) == bodyDetId) { bodyQ = b; break; }
        }
    }
    var faceQ = undefined;
    if (faceDetId != "") {
        for (var f in evaluateQuery(context, qEverything(EntityType.FACE))) {
            if (transientQueriesToStrings(f) == faceDetId) { faceQ = f; break; }
        }
    }
    var edgeQ = {source_query};
    var edges = evaluateQuery(context, edgeQ);
    var result = [];
    for (var e in edges) {
        var rec = {};
        rec.id = transientQueriesToStrings(e);
        var curveType = try(evCurveDefinition(context, {"edge": e}));
        if (curveType is Line) {
            rec.edge_type = "LINE";
        } else if (curveType is Circle) {
            rec.edge_type = "CIRCLE";
            rec.radius = curveType.radius.value;
        } else {
            rec.edge_type = "OTHER";
        }
        var len = try(evLength(context, {"entities": e}));
        if (len != undefined) rec.length = len.value;
        result = append(result, rec);
    }
    return result;
}
"""


def _edge_source_query(t):
    """Build the FS source-query expression for edges.

    body_id and adjacent_to_face_id resolve to `bodyQ` / `faceQ` variables
    that the enclosing lambda populates by ID lookup (see _FIND_EDGES_FS).
    """
    parts = []
    if t.get("created_by_feature_id"):
        parts.append(f'qCreatedBy(makeId("{t["created_by_feature_id"]}"), EntityType.EDGE)')
    if t.get("body_id"):
        parts.append("qOwnedByBody(bodyQ, EntityType.EDGE)")
    if t.get("adjacent_to_face_id"):
        parts.append("qEdgeAdjacent(faceQ, EntityType.EDGE)")
    if not parts:
        parts.append("qEverything(EntityType.EDGE)")
    return parts[0] if len(parts) == 1 else f"qIntersection([{', '.join(parts)}])"


SCHEMAS.append({
    "name": "find_edges",
    "description": (
        "Resolve edges to deterministic IDs for fillet/chamfer targeting. "
        "Filters are ANDed. Use `body_id` for 'all edges of the part', "
        "`adjacent_to_face_id` for 'edges bordering this face' (e.g. the "
        "edges around a hole's cap face), or `created_by_feature_id` for "
        "'edges created by Hole Cut'. Returns {id, edge_type, length[, radius]}."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "document_id": {"type": "string"},
            "workspace_id": {"type": "string"},
            "element_id": {"type": "string"},
            "edge_type": {"type": "string", "enum": ["LINE", "CIRCLE", "ANY"], "default": "ANY"},
            "created_by_feature_id": {"type": "string"},
            "body_id": {"type": "string",
                "description": "Deterministic ID of a body (from qBodyType or get_parts)"},
            "adjacent_to_face_id": {"type": "string"},
            "min_length": {"type": "number"},
            "limit": {"type": "integer", "default": 50},
        },
        "required": ["document_id", "workspace_id", "element_id"],
    },
})


def _find_edges(t, c):
    script = (
        _FIND_EDGES_FS
        .replace("{body_id}", t.get("body_id") or "")
        .replace("{face_id}", t.get("adjacent_to_face_id") or "")
        .replace("{source_query}", _edge_source_query(t))
    )
    raw = c.eval_featurescript(t["document_id"], t["workspace_id"], t["element_id"], script)
    edges = decode(raw)
    if not isinstance(edges, list):
        return {"edges": [], "note": "FS returned non-list", "raw": edges}

    etype = t.get("edge_type", "ANY")
    if etype != "ANY":
        edges = [e for e in edges if e.get("edge_type") == etype]
    if "min_length" in t:
        edges = [e for e in edges if (e.get("length") or 0) >= t["min_length"]]

    limit = int(t.get("limit", 50))
    return {"edges": edges[:limit], "total_matched": len(edges)}


HANDLERS = {"find_faces": _find_faces, "find_edges": _find_edges}
