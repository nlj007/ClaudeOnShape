# Builders — Attribution

Feature-JSON builders in this directory are adapted from:

- **hedless/onshape-mcp** — https://github.com/hedless/onshape-mcp (MIT License)
- **clarsbyte/onshape-mcp** (fork) — edge-query helpers for fillets

We vendor rather than depend: only the JSON shapes and the undocumented-quirk
knowledge (e.g. `filterInnerLoops`, `defaultScope`, two-semicircular-arc circle
encoding) are reused. The MCP transport and tool surface are not imported.

MIT License text is preserved in `LICENSE-hedless`.
