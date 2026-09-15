# Local-only LSP follow-up (not implemented)

This note records the agreed design for wiring a Language Server Protocol
server into Myslyx. It is intentionally **local-only**: it is meant for a
developer running the editor on their own machine against their own files, not
for the shared / multi-user / Hugging Face Space deployment. Nothing here is
implemented yet.

## Idea
Let a locally installed LSP (e.g. `clangd`) provide completions (and later
diagnostics / definitions) for C / C MSXgl files. Because a browser page cannot
spawn a child process or reach a Unix socket, the flow is:

- The app server (or a sidecar process) spawns the LSP for the file being
  edited.
- The page talks to the server over a bridge (the existing
  `__wbPyBridge`-style channel) to send the current buffer content and receive
  completion lists.
- Completions are injected into the editor as a `CompletionSource` registered
  through the same `EditorState.languageData.at("autocomplete")` mechanism that
  `myslyx/static/native-completions.js` uses.

## Env gate (default off)
New environment variable `MYSLYX_LSP` (e.g. `clangd`). The LSP machinery only
starts when it is set; otherwise behavior is identical to today. This keeps the
shared/HF Space deployment untouched and avoids installing/probing for LSP
binaries on every `ui.run()`.

## Why native autocomplete integrates cleanly
`native-completions.js` registers the C MSXgl completion source purely through
the "autocomplete" language-data field, which CodeMirror's `autocompletion()`
reads for its default sources. The LSP source would be appended the same way
(`StateEffect.appendConfig` + `EditorState.languageData.of(...)`), gated on
`window.__wbHintKey === 'msxgl'` (or `'c'` when LSP is enabled), and would
replace/augment the curated JSON word source with the live LSP results.

## Out of scope
- No shared/server-side LSP for remote users.
- No auto-install of LSP binaries.
- No persistence of LSP state across sessions beyond the buffer round trip.