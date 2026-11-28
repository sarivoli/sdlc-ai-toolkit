# Agent UI panel (A2UI MCP App)

Source of `scripts/ui/sdlc-ui.html`, the single HTML file that the `sdlc-ui`
MCP server (`scripts/sdlc_ui_mcp.py`) serves as `ui://sdlc/app`. Editors with
MCP Apps support load it in a sandboxed iframe; it renders the A2UI v1.0
messages that the `sdlc_ui_*` tools return.

```bash
cd ui
npm ci
npm run build     # writes ../scripts/ui/sdlc-ui.html and sdlc-ui.json (versions + sha256)
```

Commit both files under `scripts/ui/`: users install the prebuilt file and need
no Node.js. `node_modules/` and `dist/` are not committed.

- `src/main.ts`: A2UI `MessageProcessor` + `<a2ui-surface>`, MCP Apps `App`
  (handshake, tool results, theme). Button actions: `sdlc.chat` sends a reply
  into the chat, `sdlc.open` opens a link, anything else calls a server tool.
- `src/theme.css`: toolkit look on top of the A2UI basic catalog tokens,
  light and dark.
- `copy-bundle.mjs`: copies the build and writes `sdlc-ui.json`.
