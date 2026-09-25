# In-browser LSP worker toolchain (`tools/weblsp/`)

Builds the committed worker bundle that powers the `weblsp` plugin
(`myslyx/static/plugins/weblsp/`): a real `vscode-languageserver` server
running inside a Web Worker, serving completion + hover + signatureHelp from
the generated hints dictionaries (`myslyx/static/hints/<key>.json`) plus the
user symbols the page pushes in.

## Layout

- `package.json` — `vscode-languageserver` (+ textdocument) and `esbuild`.
  `node_modules/` here is build-only: it lives outside `myslyx/static/` so it
  can never ship in the wheel (MANIFEST.in includes `myslyx/static/**`).
- `src/worker.js` — bundle root: `BrowserMessageReader/Writer` on `self`,
  `createConnection`, `attach()`, `listen()`.
- `src/server.js` — LSP feature handlers (`initialize`, full-sync
  `textDocumentSync`, `completion`, `hover`, `signatureHelp`, plus the custom
  `$/setContext` notification carrying `{label, hintKey, symbols}`).
- `src/hintsmodel.js` — pure, dependency-free hints logic (prefix rules,
  member-trigger detection, tip lookup, signature/params recovery from the
  rendered tip markdown, enclosing-call scan). Importable directly under node
  for unit checks; shared by the bundle.
- `build.mjs` — esbuild bundle (browser platform, classic-worker IIFE) into
  `myslyx/static/plugins/weblsp/worker.bundle.js`.

## Rebuild

```bash
npm --prefix tools/weblsp install   # once (or after dependency bumps)
npm --prefix tools/weblsp run build # re-emit the committed bundle
```

Re-run the build after editing `src/*.js` or upgrading dependencies, and
commit the resulting `worker.bundle.js`: wheels and checkouts run WITHOUT
node. Quick model check without a browser:

```bash
node -e "import('./tools/weblsp/src/hintsmodel.js').then(async (m) => {
  const fs = await import('node:fs');
  const msxgl = m.normalizeHints(JSON.parse(
    fs.readFileSync('myslyx/static/hints/msxgl.json', 'utf8')));
  console.log(m.buildWordItems(msxgl, [], 'VDP_SetM', false).map((i) => i.label));
})"
```

## Signature data: the markdown-parse swap hook

`msxgl.json` (and its siblings) flatten each function's structured
`signature`/`params` into the rendered `tips` markdown, so `hintsmodel.js`
recovers them by parsing the generator's deterministic format (first
```` ```c ```` block + `**Parameters:**` list). If `tools/gen_msxgl_hints.py`
ever emits structured signatures, swap `parseTip()` (and `detailFor()` in
`server.js`) to read them directly — the callers already speak
`{signature, params: [{name, desc}]}`.

## Protocol notes

- The worker talks raw LSP JSON-RPC objects over `postMessage`/`onmessage`
  (the browser transport needs no `Content-Length` framing); the main-thread
  client is hand-written in `myslyx/static/plugins/weblsp/client.js`.
- Member contexts (caret after `.` / `->`) resolve struct/union fields from
  the hints `structs` tables merged with locally declared aggregates
  (`parseLocalTypes` members, in-file wins), through receiver chains fed by
  the document's variable->type bindings (`memberChainBefore` /
  `resolveMemberItems`). Unresolvable chains answer `null`.
