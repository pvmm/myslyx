# In-browser LSP (implemented: v1 completion + hover + signature help)

Companion to `lsp-local-only.md`. Where that note covers the
machine-installed bridge (`MYSLYX_LSP`, `myslyx/lsp.py`, the `local-lsp`
plugin — local runs only), this one covers the **online LSP that runs
directly in the browser** with no server binary, on every deployment
including shared ones.

## Implemented (v1)

A real `vscode-languageserver` server inside a Web Worker, served as the
`weblsp` plugin (`enabledByDefault`, `boot`, deliberately NOT `onlyLocal`):

- `tools/weblsp/` — build toolchain (`package.json`: `vscode-languageserver`
  + `esbuild`; `src/worker.js` bootstrap, `src/server.js` LSP handlers,
  `src/hintsmodel.js` pure hints logic, `build.mjs`). `npm run build`
  re-emits the committed `myslyx/static/plugins/weblsp/worker.bundle.js`
  (386 KB IIFE; wheels run without node). See `tools/weblsp/README.md`.
- `myslyx/static/plugins/weblsp/` — `plugin.json`, `weblsp.js` (factory:
  native source for C MSXgl + Pascal, custom `WBHintCompletions` provider
  for plain C, hover tooltip, `#wb-sighelp` signature box),
  `client.js` (hand-written JSON-RPC over `worker.postMessage`, full-text
  sync, `window.__wbWebLsp` marker), `worker.bundle.js` (committed).
- Knowledge base: the SAME generated hints dictionaries the sidebar and
  popups use (`static/hints/<key>.json` — `gen_msxgl_hints.py` untouched).
  The worker fetches the dictionary for the active `__wbHintKey`
  (`c`, `msxgl`, `pascal`); the page pushes `{label, hintKey, symbols}`
  with `$/setContext` on every `wb-active-editor` (localStorage is
  main-thread-only). The persisted store only knows top-level function
  definitions, so the worker additionally mines the synced document text
  itself on every completion (`parseDocumentSymbols` in `hintsmodel.js`):
  file-scope variables, function names, parameters and Pascal `var`-block
  names rank first, ahead of framework names. Covered by
  `weblsp/local-variables`.
- `myslyx/static/native-completions.js` — stands down for `msxgl`/`pascal`
  while `window.__wbWebLspReady` is set, so each label completes exactly
  once; clears on worker failure and the curated path resumes.
- Runner/tests — `tests/test_weblsp.py` (10 suites, default env + one
  `SPACE_ID=1` phase + one clangd phase; no binaries needed except the
  clangd-gated one): native/custom/pascal completions, locals, hover,
  signature help, exclusivity, remote-works, disabled-by-config.

## Deliberate limits

- No semantic C support: `vscode-languageserver` is protocol plumbing only
  (JSON-RPC + document sync + request routing; verified against
  `tools/weblsp/node_modules/` — no parser, no AST, no type system). Every
  scrap of C knowledge is ours: the regex-parsed hints dictionaries, the
  `parseDocumentSymbols` heuristics, the top-level scanner. So the worker
  offers no type-aware completion, no diagnostics, no go-to-definition, no
  include/macro resolution and no scope-correct shadowing — it is a fast
  offline text index, not a language engine. The only setup in Myslyx with a
  genuine C frontend stays `local-lsp` + clangd (which is why the local
  bridge wins completions when it is up).
- Menu exclusivity: `weblsp` and `local-lsp` both declare
  `"languageServer": true`, so enabling one from Settings > PLUGINS stops
  the other (the loser never boots after the reload). Covered by
  `weblsp/exclusive-toggle`.
- Runtime mutual exclusion with the machine-installed bridge: while `local-lsp`
  actually serves the current file (`window.__wbLocalLspWorking`, set by its
  ping), the worker stands down its *completion* sources so exactly one
  language server answers each popup. Hover and signature help stay with the
  worker, which the bridge does not provide. Covered by
  `weblsp/local-bridge-wins` (clangd phase).
- Member contexts (`.` / `->`) answer `null`: the client's curated struct
  machinery resolves in-file struct definitions the hints JSON cannot see.
- Signature help parses the rendered tip markdown (`hintsmodel.js`
  `parseTip`); free-form tips (c.json/pascal.json) yield no signature.
  Swap hook documented in `tools/weblsp/README.md`.
- No diagnostics: the worker has no compiler.
- `node_modules/` under `tools/weblsp/` is build-only and git-ignored; the
  bundle is the only committed artifact.
