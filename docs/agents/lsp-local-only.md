# Local-only LSP (implemented: v1 completions)

This note records the agreed design for wiring a Language Server Protocol
server into Myslyx, and the state of the implementation. It is intentionally
**local-only**: it is meant for a developer running the editor on their own
machine against their own files, not for the shared / multi-user / Hugging
Face Space deployment.

## Implemented (v1)

Completions from a locally installed LSP (e.g. `clangd`) for C / C MSXgl
files, delivered through the plugin system:

- `myslyx/local.py` — `is_local()` decides local vs. shared deployment
  (`MYSLYX_LOCAL` override; otherwise remote when `SPACE_ID` / `HF_SPACE_ID` /
  `SPACE_HOST` are set). Injected into the page as `window.__wbLocal`.
- `myslyx/lsp.py` — minimal stdio LSP client: JSON-RPC 2.0 with
  `Content-Length` framing, `available()`, `ping()`, `complete()`, `close()`.
  Sessions are keyed by file id and get a temp workspace with a real buffer
  file and a minimal `compile_commands.json` (clangd runs with
  `--compile-commands-dir`). Only serves when `MYSLYX_LSP` is set AND
  `is_local()` is true.
- `myslyx/app.py` — `POST /wb/lsp/ping`, `/wb/lsp/complete`, `/wb/lsp/close`
  (pydantic payloads).
- `myslyx/pages/editor_page.py` — injects `window.__wbLocal` and
  `window.__wbLsp = {enabled, server, error}`; the plugin manifest picks up
  `onlyLocal`.
- `myslyx/static/plugins/local-lsp/` — the client plugin (`plugin.json` with
  `"onlyLocal": true`, `"boot": true`; `local-lsp.js` bridge). Pings once at page
  load, feeds C MSXgl through the **native** autocomplete popup
  (`EditorState.languageData.at("autocomplete")`, the same mechanism as
  `native-completions.js`) and plain C through a **custom** popup via a
  `WBHintCompletions` async provider (hints.js `checkCompletions` now accepts
  Promises). On a failed ping the plugin auto-disables for the session
  (`window.__wbLspAutodisabled`) and shows a retro toast.
- Runner/tests — LSP suites are gated on real binaries (`clangd` via
  `shutil.which`, absolute paths via `os.path.exists`); sits SKIP when the
  environment cannot provide the binary. `tests/runner.py` starts one app
  server per distinct suite environment.

Double gate: the plugin is `onlyLocal` (client-side `__wbLocal`) *and* the
server advertises `enabled:false` on shared runs — either alone is enough for
a shared deployment to stay inert.

## Env gate (default off)

Environment variable `MYSLYX_LSP` (e.g. `clangd`, or an absolute path to the
LSP binary). The LSP machinery only starts when it is set; otherwise behavior
is identical to today.

## Out of scope / future

- Diagnostics and go-to-definition (only `textDocument/completion` is wired).
- No shared/server-side LSP for remote users.
- No auto-install of LSP binaries.
- No persistence of LSP state across sessions beyond the buffer round trip.