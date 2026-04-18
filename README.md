# onshape-agent

LLM-driven agent for driving Onshape part studios. Tier-2 (single-intent) task
agent today; Tier-3 planner + local-model (Gemma/Qwen) adapter planned.

## Quick start

### 1. Get API keys

You need three keys. Sign up / create them at:

- **Anthropic API key** — https://console.anthropic.com/settings/keys
  (requires an Anthropic account with a credit balance)
- **Onshape access key + secret key** — https://dev-portal.onshape.com/keys
  (click "Create new API key"; copy both the access key and the secret key
  — the secret is shown only once)

### 2. Clone and install

```bash
git clone https://github.com/nlj007/ClaudeOnShape.git
cd ClaudeOnShape
python3 -m venv .venv            # or: uv venv --python 3.12 .venv
.venv/bin/pip install -r requirements.txt
```

### 3. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` and paste your three keys:

```
ONSHAPE_ACCESS_KEY=...
ONSHAPE_SECRET_KEY=...
ANTHROPIC_API_KEY=...
```

`.env` is gitignored — it never leaves your machine. (For a more secure
setup, macOS users can store keys in Keychain and export them via
`~/.zshrc` instead; see "Optional: Keychain-based secrets" below.)

### 4. Point the agent at an Onshape Part Studio

Open any Part Studio in Onshape. The URL looks like:

```
https://cad.onshape.com/documents/<did>/w/<wid>/e/<eid>
```

Copy the three IDs out of the URL. Then run:

```bash
.venv/bin/python agent.py <did> <wid> <eid>                 # interactive
.venv/bin/python agent.py <did> <wid> <eid> "your prompt"   # one-shot
```

Try a prompt like: `"Create a 3x3x3 inch cube centered on the origin."`

### Optional: Keychain-based secrets (macOS)

If you'd rather not keep keys in a `.env` file, store them in macOS
Keychain and export them from your shell:

```bash
security add-generic-password -a "$USER" -s anthropic-api-key -w
security add-generic-password -a "$USER" -s onshape-access-key -w
security add-generic-password -a "$USER" -s onshape-secret-key -w
```

Then add to `~/.zshrc`:

```bash
export ANTHROPIC_API_KEY="$(security find-generic-password -s anthropic-api-key -w 2>/dev/null)"
export ONSHAPE_ACCESS_KEY="$(security find-generic-password -s onshape-access-key -w 2>/dev/null)"
export ONSHAPE_SECRET_KEY="$(security find-generic-password -s onshape-secret-key -w 2>/dev/null)"
```

Open a new terminal, click "Always Allow" on the Keychain prompts, and
delete `.env` — the agent reads env vars first.

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
