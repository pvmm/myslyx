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
   { "languages": ["VBScript"], "enabledByDefault": false }
   ```

   Defaults: `languages: ["*"]` (all languages), `enabledByDefault: true`.
   `name`, `dir` and `entry` (the module file) come from the directory name:
   `static/plugins/<name>/<name>.js`.

3. Hard-refresh the page. The plugin appears in the plugins menu and its
   extensions are appended the next time the editor view is created.

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

## Included example: `color-swatches`

Lives in `static/plugins/color-swatches/`. Scans the document for
`#rrggbb`-style hex tokens and renders a small color box right after each one.
It is the minimal proof-of-concept showing the full pipeline: manifest ->
load module -> register -> hook view -> `Decoration.widget` on a `StateField`.
It is a near-copy of the standalone version (see "Porting a standalone CM
extension" above).

## Validation

```bash
node --check static/plugins.js
node --check static/plugins/lifecycle.js
node --check static/plugins/<name>/<name>.js
.venv/bin/python -m py_compile pages/editor_page.py
```

Then **hard-refresh** the browser and test with e.g. `#ff00ff` in an open file.