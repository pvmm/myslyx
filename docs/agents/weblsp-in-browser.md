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
  (401 KB IIFE; wheels run without node). See `tools/weblsp/README.md`.
- `myslyx/static/plugins/weblsp/` — `plugin.json` (no language filter on
  purpose, see "Deliberate limits"), `weblsp.js` (factory: native source for
  the dictionary-backed languages, custom `WBHintCompletions` provider for the
  rest, hover tooltip, `#wb-sighelp` signature box),
  `client.js` (hand-written JSON-RPC over `worker.postMessage`, full-text
  sync, `window.__wbWebLsp` marker), `worker.bundle.js` (committed).
- Knowledge base: the SAME generated hints dictionaries the sidebar and
  popups use (`static/hints/<key>.json` — `gen_msxgl_hints.py` untouched).
  The worker fetches the dictionary for the active `__wbHintKey`;
  the page pushes `{label, hintKey, base, symbols}`
  with `$/setContext` on every `wb-active-editor` (localStorage is
  main-thread-only). The persisted store only knows top-level function
  definitions, so the worker additionally mines the synced document text
  itself on every completion (`parseDocumentSymbols` in `hintsmodel.js`):
  file-scope variables, function names, parameters and Pascal `var`-block
  names rank first, ahead of framework names. Local struct/union/enum
  declarations are found the same way (`parseLocalTypes`, brace-depth
  scanned): the type names and enum constants complete, and they join the
  known-type set so declarators using them (`MySprite player;`) parse as
  variables — while struct *fields* never leak as file-scope names (struct
  bodies are masked for the declarator pass). Covered by
  `weblsp/local-variables` and `weblsp/local-types`.
- Member completion (`textDocument/completion` on `.` / `->`): framework
  `structs` tables merged with locally declared aggregates (in-file wins
  whole-struct), resolved through receiver chains
  (`memberChainBefore`/`resolveMemberItems` in `hintsmodel.js`) fed by the
  document's variable->type bindings (pointer vs. value not distinguished,
  mirroring the curated model). While the worker is ready the curated
  member sources stand down so each field completes exactly once; plain C
  keeps its `c-struct-complete` member path and the local bridge keeps
  clangd members when it serves. Covered by `weblsp/member-complete`.
- `#include` file completion (`includeContext`/`buildIncludeItems` in
  `hintsmodel.js`): `<...>` offers the dictionary `headers` (standard C
  set, plus engine modules for MSXgl); `"..."` offers the project's own
  `.h` files (pushed with `$/setContext`) plus the engine `modules` for
  MSXgl. Quoted standard includes are intentionally not offered; closed
  includes answer null. Accepting a header appends its closing bracket
  (custom popup via string `apply`, honored by `insertCompletion`; native
  popup via a per-option apply function that also swallows an already-typed
  filename suffix and never duplicates a present closer). Covered by
  `weblsp/include-c-std`, `weblsp/include-msxgl-modules`,
  `weblsp/include-local` and `weblsp/include-closers`
  (plus `local-lsp/include-closers` for clangd).
- `myslyx/static/native-completions.js` — stands down for `msxgl`/`pascal`
  while `window.__wbWebLspReady` is set, so each label completes exactly
  once; clears on worker failure and the curated path resumes.
- Runner/tests — `tests/test_weblsp.py` (20 suites, default env + one
  `SPACE_ID=1` phase + one clangd phase; no binaries needed except the
  clangd-gated one): native/custom/pascal completions, locals, types,
  members, includes, closers, substring, hover, signature help,
  exclusivity, remote-works, disabled-by-config.

## Deliberate limits

- Matching is substring everywhere (words, members, headers), ranked
  exact-case prefix, case-insensitive prefix, substring by position
  (`matchScore`/`tierBoost` in `hintsmodel.js`, mirrored in
  `native-completions.js`, `hints.js` and `c-struct-model.js` so the curated
  fallbacks behave identically). Clients pass worker/clangd results through
  with their boosts and set `filter: false` so CodeMirror reproduces the
  server ranking instead of hiding substring hits. Covered by the
  `weblsp/substring-*` suites.

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
- Language scoping is **runtime, not manifest**. `weblsp/plugin.json`
  declares no `languages` and no `baseLang` filter, and that is deliberate:
  `WBPlugins.install()` runs once per view and evaluates `_langOk` at that
  moment only (plugins.js:84), so a language filter on a `boot` plugin would
  freeze its scope at load time and the LANG combo could never widen it. The
  manifest stays generic (any language may load the plugin) and the plugin
  decides per query, through `window.WBLanguage`:
  - `baseLang` is the right scope for a *non-boot* plugin (see
    `c-struct-complete`, which scopes `["c"]` and covers plain C and C MSXgl
    with one entry).
  - a boot language server must self-gate: `weblsp.js` `served()` (family
    known) and `lang().usesNativePopup()` (this language renders in the
    native tooltip) at completion time, hover time and signature time.
- `window.WBLanguage` (retro.js) is the single language constant for the
  whole client: it answers from the attributes the server publishes per file
  (`__wbBaseLang` for the family, `__wbHintKey` for the dictionary) which
  popup applies, the LSP `languageId`, whether the family has `#include`
  headers, and whether the machine bridge may serve it. `hints.js`,
  `native-completions.js`, `weblsp.js`, `local-lsp.js` and `client.js` all
  read it and **name no language**, so a new C-derived dialect is a data
  change: its `hints/<key>.json` plus rows in editor_page.py's
  `HINT_KEYS`/`BASE_LANG` (no plugin edits). The worker mirrors this — the
  page sends `base` in `$/setContext` and the server picks a parser family,
  so only a genuinely new *parser* family (a new `DOCUMENT_PARSERS` entry in
  `hintsmodel.js`) is a code change.
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
- Unresolvable member chains (unknown struct, call-result receivers like
  `f(x).y` that need a syntax tree) answer `null`: the curated tree path
  resumes automatically whenever the worker is down or the local bridge
  serves, so silence here never loses a completion the old path had.
- Signature help parses the rendered tip markdown (`hintsmodel.js`
  `parseTip`); free-form tips (c.json/pascal.json) yield no signature.
  Swap hook documented in `tools/weblsp/README.md`.
- No diagnostics: the worker has no compiler.
- `node_modules/` under `tools/weblsp/` is build-only and git-ignored; the
  bundle is the only committed artifact.
