"""Tier 2 task agent — tool-use loop over the Chat abstraction.

Handles single intents like "rename part X", "change sketch d1 to 25 mm",
"create a 2in hole on the top plane". Keep it simple: loop until end_turn
or max_turns, logging each step.
"""
from ..llm import Chat, ToolCall, TextBlock
from ..tools import all_schemas, dispatch


DEFAULT_SYSTEM = """\
You are an Onshape CAD assistant. You operate on a single Part Studio via tools.

UNITS: all lengths in METERS at the API boundary. 1 in = 0.0254 m, 1 mm = 0.001 m.
Depth expressions in extrude/chamfer accept unit strings like '0.25 in', '5 mm'.

WORKFLOW for NEW bodies:
  1. create_circle_sketch / etc. on a default plane (TOP/FRONT/RIGHT).
  2. create_extrude with operation='NEW' and an end_bound.

WORKFLOW for CUTTING into an existing body (e.g. holes, counterbores):
  1. find_faces(normal_like=..., extremum=..., surface_type='PLANE') to get
     the deterministic ID of the target face. SAVE the face's `normal` vector.
  2. create_circle_sketch with `plane_id=<face id>` (NOT `plane`). The circle
     center (center_x, center_y) is in the FACE's local 2D frame; for a
     circle centered on a face that sits on the world origin, use 0,0.
  3. create_extrude with operation='REMOVE', end_bound='THROUGH_ALL' or
     'BLIND', AND pass `target_direction` + `sketch_plane_normal`. Use the
     world vector that points INTO the body (e.g. [0,0,-1] if cutting down
     from a top face). The tool will flip direction automatically.

WORKFLOW for CHAMFERING / FILLETING:
  1. find_edges(edge_type='LINE' or 'CIRCLE', body_id=..., adjacent_to_face_id=...)
     to get edge IDs. For "all edges of the part", use no filter.
  2. create_chamfer(edge_ids=[...], width='1 mm').

EDGE-FILTER HEURISTICS (saves tool calls — use these before asking):
  - "original outer edges of the body, no holes/cuts" →
    created_by_feature_id=<the base extrude feature id>. This is the CLEANEST
    selector: it returns exactly the edges produced by that feature and is
    immune to later cuts (which only add edges, never remove them from the
    base extrude's created set). Prefer this over edge_type filters.
  - "just the hole rims" → edge_type='CIRCLE' (+ optionally
    created_by_feature_id=<the cut extrude>).
  - "edges around one specific face" → adjacent_to_face_id=<face id from find_faces>.
  - AVOID relying on edge_type='LINE' alone to mean "block edges" — cuts can
    introduce line-edge seams too (e.g. where a cylindrical hole wall meets
    a planar face at a tangent). Use created_by_feature_id instead.

IDS GO STALE AFTER DELETES. If you delete a feature and then want to operate
on edges/faces of what's left, RE-QUERY — don't reuse IDs from before the
delete. Deterministic IDs are stable across regens of the SAME feature tree,
not across edits to it.

UPDATING a feature (change a dimension, rename, etc.):
  1. get_features — returns features + sourceMicroversion.
  2. Modify the feature object in place.
  3. update_feature(feature=<modified>, source_microversion=<from step 1>).

After a cut or boolean, an existing face's deterministic ID usually CHANGES.
If you need the same face again, re-run find_faces; don't reuse the old ID.

If no canned tool fits, use eval_featurescript as an escape hatch (FS body:
`function(context is Context, queries) { ... return something; }`).

Be concise: report what you did, don't echo parameters back to the user.
"""


class TaskAgent:
    def __init__(self, chat: Chat, client, system: str = DEFAULT_SYSTEM,
                 max_turns: int = 15, verbose: bool = True):
        self.chat = chat
        self.client = client
        self.system = system
        self.max_turns = max_turns
        self.verbose = verbose
        self.tools = all_schemas()

    def _log(self, *args):
        if self.verbose:
            print(*args)

    def run(self, prompt: str) -> str:
        messages = [{"role": "user", "content": prompt}]
        for turn in range(self.max_turns):
            resp = self.chat.complete(self.system, messages, self.tools)
            messages.append(self.chat.format_assistant_turn(resp))

            tool_results = []
            final_text = []
            for block in resp.blocks:
                if isinstance(block, TextBlock):
                    final_text.append(block.text)
                    self._log(f"[assistant] {block.text}")
                elif isinstance(block, ToolCall):
                    self._log(f"[tool_call] {block.name}({_preview(block.input)})")
                    result = dispatch(block.name, block.input, self.client)
                    self._log(f"[tool_result] {result[:200]}{'...' if len(result) > 200 else ''}")
                    tool_results.append(self.chat.format_tool_result(block.id, result))

            if resp.stop_reason != "tool_use":
                return "\n".join(final_text)

            messages.append({"role": "user", "content": tool_results})

        return "[max turns reached]"


def _preview(d: dict, limit: int = 120) -> str:
    s = ", ".join(f"{k}={v!r}" for k, v in d.items() if k not in
                  ("document_id", "workspace_id", "element_id", "script", "feature"))
    return s[:limit] + ("..." if len(s) > limit else "")
