"""FeatureScript escape hatch — arbitrary FS evaluation against a part studio."""

_DWE = {
    "document_id": {"type": "string"},
    "workspace_id": {"type": "string"},
    "element_id": {"type": "string"},
}
_DWE_REQ = ["document_id", "workspace_id", "element_id"]

FS_CHEATSHEET = """\
FeatureScript quick reference (for eval_featurescript `script`):

The script is the BODY of a function that takes `context is Context` and
`queries is map` and returns a value. Examples:

  # Count faces on the first part
  function(context is Context, queries) {
      return size(evaluateQuery(context, qEverything(EntityType.FACE)));
  }

  # Return the IDs of all part bodies
  function(context is Context, queries) {
      var ids = [];
      for (var p in evaluateQuery(context, qEverything(EntityType.BODY))) {
          ids = append(ids, transientQueriesToStrings(p));
      }
      return ids;
  }

The `queries` argument is populated from the `queries` list you pass alongside
the script — each entry is `{"key": "myQuery", "query": "<serialized query>"}`.
Use FeatureScript's standard library: qEverything, qOwnedByBody, qCreatedBy,
evaluateQuery, evBox3d, evPlane, evDistance, etc.
"""


SCHEMAS = [
    {
        "name": "eval_featurescript",
        "description": (
            "Evaluate arbitrary FeatureScript against the part studio. READ-ONLY: "
            "use for geometry queries, measurements, inspections, derived values. "
            "CANNOT create, modify, or delete features — FS eval runs in a sandboxed "
            "context with no persistent effect on the part studio. For creating "
            "features, use create_* tools (or ask the user if no tool fits). "
            "The script must be a full "
            "`function(context is Context, queries) { ... }` body that returns a value."
            f"\n\n{FS_CHEATSHEET}"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                **_DWE,
                "script": {"type": "string", "description": "FeatureScript function body."},
                "queries": {
                    "type": "array",
                    "description": "Optional list of named queries passed to the script.",
                    "items": {"type": "object"},
                },
            },
            "required": [*_DWE_REQ, "script"],
        },
    },
]


def _eval(t, c):
    return c.eval_featurescript(
        t["document_id"], t["workspace_id"], t["element_id"],
        t["script"], t.get("queries"),
    )


HANDLERS = {"eval_featurescript": _eval}
