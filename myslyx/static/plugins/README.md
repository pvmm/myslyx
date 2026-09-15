# Editor plugins (`static/plugins/`)

Plugins extend the CodeMirror editor with client-side behaviour — decoration
widgets (e.g. color swatches), extra keymaps, hover popups — without touching
`pages/editor_page.py`.

Each plugin lives in its own directory, `static/plugins/<name>/`, fully
isolated from every other plugin. The directory holds the plugin's ES module
(`<name>.js`, a plain CodeMirror 6 extension) plus any extra files it needs
(images, CSS, helper modules). `lifecycle.js` reads a manifest of those plugin
directories and binds each module to the editor through the runtime in
`static/plugins.js`.

## Runtime pieces

- `static/plugins.js` — the plugin runtime. Registers plugin definitions,
  checks enablement and language, and appends each plugin's CodeMirror 6
  extensions to the editor once its view exists.
- `static/plugins/lifecycle.js` — the glue. Loads each plugin's module and
  registers it with the runtime (see "Contract" below).
- `pages/editor_page.py` — builds the manifest (the list of plugin
  directories) into `window.WB_PLUGIN_MANIFEST` and injects it before
  `lifecycle.js`. Adding a plugin requires no Python changes.

## Adding a plugin

1. Create `static/plugins/<name>/<name>.js` — an ES module exporting a default
   factory:

   ```js
   export default function myExtension(CM) {
       const { EditorView, Decoration, WidgetType, StateField } = CM;
       // ...return one CodeMirror 6 extension (or an array of them)...
   }
   ```

2. (Optional) Add `static/plugins/<name>/plugin.json` to override defaults:

   ```json
   {
     "languages": ["C MSXgl"],
     "baseLang": ["c"],
     "enabledByDefault": false
   }
   ```

   Defaults: `languages: ["*"]` (all languages), `enabledByDefault: true`.
   `name`, `dir` and `entry` (the module file) come from the directory name:
   `static/plugins/<name>/<name>.js`.

   Set `"boot": true` when the plugin has global side effects that must be
   in place before any editor exists — the canonical example is registering a
   language in the CodeMirror catalog (see `hitbasic`). A boot plugin's module
   is loaded and its factory run once at page startup; per-view `install()`
   re-runs the same idempotent factory for the actual extensions:

3. Hard-refresh the page. The plugin appears in Settings > PLUGINS and its
   extensions are appended the next time the editor view is created.

### Language scoping

A plugin declares which languages it cares about on two orthogonal axes:

- `languages` scopes to the exact stored language ids — the `LANGUAGES` keys in
  `pages/editor_page.py` (`HitBasic`, `Pascal`, `C`, `C MSXgl`, `Z80`,
  `Text`). A stored id that matches is enough on its own.
- `baseLang` scopes to a *base* language family shared by several ids. The
  runtime publishes `window.__wbBaseLang` (HitBasic -> `basic`, Pascal ->
  `pascal`, C and C MSXgl -> `c`, Z80 -> `asm`, Text -> `text`), so a generic
  plugin declares `"baseLang": ["c"]` and automatically lights up for plain C,
  the C MSXgl framework, and any future C-derived language — no per-language
  manifest updates.
- `"*"` (default) matches everything. When both filters are declared, they
  both must pass (AND). An absent filter always passes.

The check lives in `static/plugins.js` (`_langOk`); `lifecycle.js` forwards
`baseLang` from the manifest. For compatibility, a plugin whose `languages`
says `"VBScript"` (the pre-rename BASIC id) also runs on `HitBasic` files.

### User plugins directory

When Myslyx runs from an *installed* package, plugins can also be installed in
a per-OS user configuration directory (created on first launch, served at
`/user-plugins/`, and scanned at page load):

- Windows: `%APPDATA%\myslyx\plugins`
- macOS: `~/Library/Application Support/myslyx/plugins`
- Linux: `$XDG_CONFIG_HOME/myslyx/plugins` (default `~/.config/myslyx/plugins`)

The resolution lives in `myslyx/paths.py` (`user_plugins_dir()`). The manifest
merges bundled plugins first and user plugins second, so a user plugin shadows
a bundled one with the same name. User plugins carry `base: '/user-plugins/'`
in the manifest, which `lifecycle.js` uses to pick the module URL.

## Contract

- The module's default factory receives the `nicegui-codemirror` namespace
  (`CM`) — the full CodeMirror 6 API (`Decoration`, `WidgetType`, `StateField`,
  `StateEffect`, `EditorView`, `ViewPlugin`, `keymap`, ...) — plus the
  per-plugin config object as its second argument. It returns a single
  extension or an array of extensions.
- Plugins must resolve all CodeMirror symbols from `CM`. Do not import from
  bare specifiers like `@codemirror/view` / `@codemirror/state`: the Myslyx
  page has no import map for them.
- Runtime ordering is preserved: `static/plugins.js` must load before
  `lifecycle.js` (it does — both are in the page head in that order).

### Porting a standalone CM extension

Take your vanilla extension (e.g. the standalone `color-swatches.js` example)
and change only its module signature:

- delete the `import { ... } from "@codemirror/..."` lines,
- wrap the body in `export default function <name>(CM) { ... }`,
- at the top of the factory, `const { Decoration, WidgetType, StateField, EditorView } = CM;`.

Classes that `extend WidgetType` must sit inside the factory so the parent is
in scope. Everything else — widgets, regexes, `StateField.define` bodies — is
unchanged, so the plugin stays a plain, portable CodeMirror extension.

### Good neighbours

- **Use the injected-extension pattern.** Prefer returning CM extensions over
  mutating the DOM yourself; CM recomputes decorations automatically on every
  edit.
- **Match the retro theme.** Reuse the existing popup/spacing conventions
  (`wb-autocomplete-popup`, `--wb-font`, `--wb-white`, hard borders) so plugins
  look native.
- **Keep assets in the plugin dir.** CSS/images/helpers go under
  `static/plugins/<name>/` and are served at
  `/static/plugins/<name>/<file>` — nothing leaks between plugins.
- **Wrap failures.** If the factory throws, or its module fails to load, the
  runtime logs a warning and skips the plugin without breaking the editor.

## Enabling / disabling

Enabled state lives in the shared client config (`localStorage['wb_editor_config']`,
the same object as the hints width and WRAP prefs):

```json
{ "plugins": { "color-swatches": false } }
```

A plugin is enabled by default unless:
- the config sets `plugins.<name> = false`, or
- `enabledByDefault` is `false` in the plugin's `plugin.json`.

Config changes apply on the next page load (hard refresh) — there is no
runtime toggle yet.

## Included examples

- `static/plugins/color-swatches/` — scans the document for `#rrggbb`-style hex
  tokens and renders a small color box right after each one. It is the minimal
  proof-of-concept showing the full pipeline: manifest -> load module ->
  register -> hook view -> `Decoration.widget` on a `StateField`. It is a
  near-copy of the standalone version (see "Porting a standalone CM
  extension" above).
- `static/plugins/file-stats/` — shows live character / word / line counts for
  the active file, stacked under its name in the top toolbar. It demonstrates
  a plugin that reaches outside the editor view: it injects the display slot
  as plain DOM around the existing `#wb-file-name` label and recomputes the
  counts from the active view's document on every edit and on
  `wb-active-editor` events.
- `static/plugins/hitbasic/` — publishes the *HitBasic* language to the
  CodeMirror catalog (the "nicegui-codemirror" `CM.languages` list used by
  `ui.codemirror`'s `setLanguage()`). Its factory returns no per-view
  extensions; instead it registers a language entry built from the VBScript
  highlighter plus `languageData.commentTokens` (`"'"`), which makes the
  built-in **Ctrl-/** comment toggle work in BASIC. Because the editor that
  triggers the module's first install may have mounted before the entry
  existed, the factory also re-applies the language to the active editor.
  Disabling this plugin removes HitBasic from the catalog (no highlighting,
  no Ctrl-/ toggle).
- `static/plugins/c-struct-complete/` — autocompletes C `struct` member names
  after `.` / `->` (a Boot plugin, `baseLang: ["c"]`). It parses struct
  declarations and typed variables from the document, merges in framework
  structs shipped with the active hints JSON (see
  `static/hints/README.md`, the `structs` key), and feeds the editor's
  autocomplete popup through a completion provider registered with
  `WBHintCompletions` (see `static/hints.js`). With no Python changes it
  covers plain C, the C MSXgl framework, and any future base-`c` language.

### Completions providers

Autocomplete is normally driven by keyword/builtin data from the hints JSON.
Plugins can contribute their own suggestions by registering a provider:

```js
window.WBHintCompletions.register('my-completions', function(ctx) {
    // ctx: { view, word, line, col, start }
    //  - return null to let the default keyword/builtin path handle it;
    //  - return [] to show nothing;
    //  - return [{ label, detail, apply }] to show a popup.
});
```

`static/hints.js` runs the providers first; the first non-null result wins.
`apply` is optional (a string replaces the typed word). Because hints data can
arrive asynchronously, a provider may load it and then dispatch
`wb-hints-ready` on `window`; hints.js re-runs the completion check for you.
See `c-struct-complete` for the full pattern.

## Validation

```bash
node --check static/plugins.js
node --check static/plugins/lifecycle.js
node --check static/plugins/<name>/<name>.js
.venv/bin/python -m py_compile pages/editor_page.py
```

Then **hard-refresh** the browser and test with e.g. `#ff00ff` in an open file.