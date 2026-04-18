# onshape-agent

LLM-driven agent for driving Onshape part studios. Tier-2 (single-intent) task
agent today; Tier-3 planner + local-model (Gemma/Qwen) adapter planned.

## Quick start

```bash
python3 -m venv .venv           # or: uv venv --python 3.12 .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # fill in ANTHROPIC_API_KEY + Onshape HMAC keys
.venv/bin/python agent.py <did> <wid> <eid>                 # interactive
.venv/bin/python agent.py <did> <wid> <eid> "your prompt"   # one-shot
```

The three IDs come from any Onshape Part Studio URL:
`cad.onshape.com/documents/<did>/w/<wid>/e/<eid>`.

## Layout

```
onshape-agent/
├── agent.py                    thin CLI → TaskAgent
├── requirements.txt
├── .env / .env.example         Anthropic + Onshape credentials
└── onshape_agent/
    ├── client.py               HMAC-signed REST + FS-eval client
    ├── llm.py                  Chat protocol + AnthropicChat adapter
    ├── fsvalue.py              Decode BTFSValue* envelopes → Python
    ├── agents/
    │   └── task.py             Tier-2 tool-use loop + system prompt
    ├── builders/               Feature-JSON builders (vendored from hedless)
    │   ├── sketch.py           SketchBuilder (circle, rectangle)
    │   ├── features.py         ExtrudeBuilder, ChamferBuilder (+ enums)
    │   └── README.md           MIT attribution
    └── tools/                  Tool schemas + handlers (exposed to the LLM)
        ├── reads.py            get_features, get_parts, get_part_studio
        ├── features.py         create_*_sketch, create_extrude,
        │                       create_chamfer, update_feature, delete_feature
        ├── geometry.py         find_faces, find_edges (deterministic IDs)
        ├── appearance.py       set_part_color, set_part_name
        └── featurescript.py    eval_featurescript (READ-ONLY escape hatch)
```

## Architecture

Three-tier plan (see `.claude/plans/come-up-with-a-modular-hearth.md`):

- **Tier 1 — Tools.** Deterministic Python wrappers over Onshape REST + FS.
  Grouped by domain in `onshape_agent/tools/`. Each module exports
  `SCHEMAS` (LLM-visible) and `HANDLERS` (dispatch map).
- **Tier 2 — Task agent.** [onshape_agent/agents/task.py](onshape_agent/agents/task.py) —
  tool-use loop over the `Chat` protocol. Handles atomic intents ("create a
  3×4×5 block with a through-hole and chamfered edges"). Shipped.
- **Tier 3 — Planner.** Not built yet. Will decompose multi-step workflows
  and delegate to Tier 2.

The `Chat` protocol in [onshape_agent/llm.py](onshape_agent/llm.py) abstracts
the LLM call. Swap `AnthropicChat` for an `OllamaChat` adapter to run Tier 2
on Gemma/Qwen locally — agent code does not change.

## What the agent can do today

End-to-end verified (single prompt → completed part):

- Create a rectangular block (via `create_rectangle_sketch` + `create_extrude`).
- Cut a through-hole on a named face (via `find_faces` → `create_circle_sketch`
  with `plane_id` → `create_extrude` with auto-direction resolution).
- Cut a counterbore recess + coaxial through-hole on a different face.
- Chamfer a filtered set of edges (via `find_edges` — filter by edge type,
  body, adjacent face, or `created_by_feature_id`).
- Update dimensions on existing features (`get_features` → mutate →
  `update_feature` with `sourceMicroversion`).
- Rename / recolor parts.
- Fallback: `eval_featurescript` for arbitrary read-only FS queries.

## Hard-won knowledge

Captured as inline comments — check these files before re-deriving:

- **Default-plane IDs** `JDC/JCC/JEC` (TOP/FRONT/RIGHT). Earlier `JHD/JFD/JGD`
  turned out to be Extrude-1 face IDs — trap documented in
  [onshape_agent/builders/sketch.py](onshape_agent/builders/sketch.py).
- **Circle sketching = two semicircular arcs.** Single-circle encoding
  produces broken regions. [onshape_agent/builders/sketch.py](onshape_agent/builders/sketch.py).
- **Extrude region selection requires** `filterInnerLoops:true` +
  `defaultScope:true`. [onshape_agent/builders/features.py](onshape_agent/builders/features.py).
- **Extrude direction auto-resolves** from `target_direction` +
  `sketch_plane_normal` via dot-product flip. [onshape_agent/tools/features.py](onshape_agent/tools/features.py).
- **`qTransient(makeId(...))` does NOT work** for deterministic IDs. Resolve
  by iterating entities + matching `transientQueriesToStrings` inside the FS
  lambda. [onshape_agent/tools/geometry.py](onshape_agent/tools/geometry.py).
- **`transientQueriesToStrings(singleQuery)` returns a string**, not an array.
  Don't index into it.
- **`eval_featurescript` queries param** must be `{}` not `[]` (Jackson
  requires a map). [onshape_agent/client.py](onshape_agent/client.py).
- **Deterministic IDs go stale after a delete** — re-query. System prompt
  calls this out: [onshape_agent/agents/task.py](onshape_agent/agents/task.py).
- **dotenv fallback in `AnthropicChat`** — shells that export empty
  `ANTHROPIC_API_KEY` block dotenv's normal load; we read `.env` directly.
  [onshape_agent/llm.py](onshape_agent/llm.py).

## Not yet built

- Tier 3 planner (multi-step decomposition).
- Intent router (classify Tier 2 vs Tier 3).
- Local-model adapter (`OllamaChat` for Gemma/Qwen on M4).
- Fillet builder (chamfer exists; fillet is the obvious next feature).
- Assembly / mate operations, drawings, exports.
- Fixing `find_edges(body_id=...)` edge-count expectations: chamfer-induced
  seams inflate the LINE count. Prefer `created_by_feature_id=<base extrude>`
  for "original body edges".
