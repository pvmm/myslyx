# Creating and installing Myslyx plugins

A **Myslyx plugin** is a small, self-contained piece of client-side JavaScript
that extends the built-in CodeMirror 6 editor — for example with decoration
widgets (color swatches), hover tooltips, or extra key bindings. Plugins run in
the browser, never on the server, and are delivered as static files, so adding
one requires **no Python changes** and no rebuild of the package.

The reference implementation lives in `myslyx/static/plugins/color-swatches/`
and the full internal contract in `myslyx/static/plugins/README.md`.

---

## Normal CodeMirror extensions vs. Myslyx plugins

The text editor inside Myslyx *is* CodeMirror 6, so a Myslyx plugin is written
with the exact same API — `Decoration`, `StateField`, `WidgetType`, `keymap`,
`ViewPlugin`, and friends. The differences are about **how the module is
packaged and loaded**, not about the CodeMirror API itself.

| | Standalone CodeMirror extension | Myslyx plugin |
|---|---|---|
| Where the API comes from | `import { ... } from '@codemirror/view'`, `'@codemirror/state'`, ... | A `CM` namespace passed to your module by the plugin runtime |
| Module format | An ESM/CommonJS module in your own bundler | A single ES module in a self-contained directory |
| Browser setup needed | An import map or a bundling step (browsers can't resolve `@codemirror/...`) | None — `nicegui-codemirror` is pre-bundled by the page |
| Hosting | Whatever your app uses | Served as static files (bundled under `/static/plugins/<name>/` or installed under `/user-plugins/<name>/`) |
| Adding it | Recompile / rebuild your frontend | Drop one directory in, hard-refresh the page |
| Language awareness | None (global to the editor) | Can be scoped to specific languages |
| Enable/disable | At editor construction | Per-user shared config (`localStorage['wb_editor_config']`) |

The one rule that matters when porting: **never `import` from bare
`@codemirror/*` specifiers** in a Myslyx plugin. The page has no import map for
them, so those imports would fail at load time. Instead, destructure everything
you need from the `CM` argument.

```js
// Standalone CodeMirror extension — needs a bundler + import map:
import { EditorView } from '@codemirror/view';
import { StateField, Decoration } from '@codemirror/state';

// ... code using EditorView/StateField/Decoration ...

// Same logic as a Myslyx plugin — namespace comes from the runtime:
export default function myExtension(CM) {
    const { EditorView, StateField, Decoration } = CM;
    // ... the very same code ...
}
```

A Myslyx plugin is therefore a plain CodeMirror extension with two changes to
its module signature:

1. delete the `import { ... } from '@codemirror/...'` lines,
2. wrap the body in `export default function <name>(CM) { ... }` and take the
   symbols you need from `CM` at the top.

Classes that `extend WidgetType` must live *inside* the factory so their parent
is in scope. Everything else — widget code, regexes, `StateField.define`
bodies — is unchanged, which keeps the plugin portable: you can lift it back
out any time.

---

## Anatomy of a plugin

Each plugin lives in its own directory:

```
myslyx/static/plugins/<name>/
├── <name>.js          # required: ES module, default-exported factory
├── plugin.json        # optional: metadata (see below)
└── ...                # optional: CSS, images, helper modules
```

`<name>` is a single URL-safe token (letters, digits, hyphens) and also
determines the entry module file (`<name>.js`) and the served URL. A bundled
plugin is served at `/static/plugins/<name>/<name>.js`; a plugin installed in
the user configuration directory (below) is served at
`/user-plugins/<name>/<name>.js`.

### The factory

The module's default export is a function that receives the CodeMirror
namespace and returns **one extension or an array of extensions**:

```js
export default function myExtension(CM, ctx) {
    const { StateField, EditorView, Decoration, WidgetType, StateEffect, keymap } = CM;
    // return [ext1, ext2, ...];
}
```

`ctx` is the per-plugin config object merged from the user's settings (`{}` by
default) and can be used to read options that live in the shared client config.

### Optional `plugin.json`

```json
{
    "languages": ["C MSXgl"],
    "baseLang": ["c"],
    "enabledByDefault": false,
    "boot": true
}
```

- `languages` — a list of file-language ids (the `LANGUAGES` keys in
  `pages/editor_page.py`: `HitBasic`, `Pascal`, `C`, `C MSXgl`, `Z80`,
  `Text`; `"*"` = all). Present and empty means *all* languages.
- `baseLang` — a list of **base-language family** ids. The editor publishes
  `window.__wbBaseLang` alongside the current language: `HitBasic` -> `basic`,
  `Pascal` -> `pascal`, `C` and `C MSXgl` -> `c`, `Z80` -> `asm`, `Text` ->
  `text`. A generic plugin declares `"baseLang": ["c"]` and runs for **every**
  C-derived language — plain C, the MSXgl framework, and any future one —
  with no manifest updates. `languages` and `baseLang` are two independent
  scopes: when both are declared they must *both* match (AND); `"*"` / absent
  always matches. Internally this is `WBPlugins._langOk()`.
- `enabledByDefault` — whether the plugin is on until the user disables it.
  Default: `true`.
- `boot` — load the module and run its factory once at page startup (global
  side effects before any editor exists). The factory must be idempotent; the
  per-view install re-runs it for actual extensions.

> Legacy id: a plugin whose `languages` says `"VBScript"` (the pre-rename
> BASIC id) also runs on `HitBasic` files.

### Contributing autocomplete suggestions

The editor's autocomplete popup normally serves keywords/builtins from the
hints JSON. Plugins can add their own suggestions by registering a provider
on `window.WBHintCompletions` (boot plugins do this once at startup):

```js
window.WBHintCompletions.register('my-completions', function(ctx) {
    // ctx: { view, word, line, col, start }
    //   null  -> let the default keyword/builtin path handle this keystroke;
    //   []    -> show nothing;
    //   [{ label, detail?, apply? }] -> show a popup.
});
```

`static/hints.js` consults providers first; the first non-null array wins.
`apply` is an optional string that replaces the typed word (for example a
complete `cmd.length` inserted over `cmd.`). Hint data can load asynchronously
(`window.WBHints.get(key)`): once loaded, dispatch `wb-hints-ready` on
`window` and hints.js re-runs the completion check automatically. The bundled
`c-struct-complete` plugin is the reference implementation.

---

## Creating a plugin step by step

1. Create the directory `myslyx/static/plugins/<name>/` and the module
   `<name>.js` (or drop it straight into your user plugins directory — see
   "Installing a plugin" below).
2. Write your extension as a plain CodeMirror 6 extension, using only the `CM`
   namespace (see the porting notes above).
3. Add a `plugin.json` only if you need language scoping or a non-default
   enabled state.
4. Validate:

   ```bash
   node --check myslyx/static/plugins/<name>/<name>.js
   ```

5. Hard-refresh `/editor` and check **Settings > PLUGINS** — the plugin is
   picked up automatically, with no Python edits and no server restart.

Good practice:

- **Prefer the injected-extension pattern.** Return CodeMirror extensions over
  mutating the DOM yourself; CodeMirror recomputes decorations on every edit.
- **Match the retro theme.** Reuse existing popup/spacing conventions
  (`wb-autocomplete-popup`, `--wb-font`, `--wb-white`, hard borders) so the
  plugin looks native.
- **Keep assets in the plugin directory.** Files under
  `myslyx/static/plugins/<name>/` are served at `/static/plugins/<name>/...`,
  and files under your user plugins directory at `/user-plugins/<name>/...` —
  nothing leaks between plugins.
- **Wrap failures.** The runtime catches load errors and factory throws, logs a
  warning, and skips the plugin without breaking the editor.

---

## Installing a plugin

A plugin is installed the moment its directory exists on disk. At page load
Myslyx scans two locations and merges the manifests: bundled plugins first,
then plugins in the user configuration directory. A plugin installed by the
user **shadows** a bundled plugin with the same name.

### From a source checkout or editable install

Drop the plugin directory into `myslyx/static/plugins/` and hard-refresh:

```bash
cp -r my-plugin myslyx/static/plugins/
```

### From an installed package

Plugins can be installed in either of two places. Both are discovered
automatically; neither requires editing the package or restarting the server.

**Preferred — the user configuration directory.** This works for any install
method (regular `pip install`, virtualenv, system install) and survives package
upgrades. Myslyx creates it on first launch and serves it at
`/user-plugins/`. The location depends on the operating system:

| OS      | Plugins directory |
|---------|-------------------|
| Windows | `%APPDATA%\myslyx\plugins` |
| macOS   | `~/Library/Application Support/myslyx/plugins` |
| Linux   | `$XDG_CONFIG_HOME/myslyx/plugins` (default `~/.config/myslyx/plugins`) |

```bash
# example on Linux
mkdir -p ~/.config/myslyx/plugins
cp -r my-plugin ~/.config/myslyx/plugins/
```

**Alternative — inside the package.** With a regular (non-editable)
`pip install`, the bundled static files live in your Python's
`site-packages/myslyx/static/plugins/`. Find the path with:

```bash
python -c "import myslyx; from pathlib import Path; print(Path(myslyx.__file__).parent / 'static' / 'plugins')"
```

Then copy your plugin directory there. This is only useful for development
machines — package upgrades overwrite it. If you are *distributing* a plugin
bundled with Myslyx, add it to the source tree and rebuild the wheel;
`MANIFEST.in` bundles `myslyx/static/**` automatically.

### Enable / disable

Enabled state lives in the shared client config (`localStorage['wb_editor_config']`):

```json
{ "plugins": { "my-plugin": false } }
```

A plugin is enabled by default unless the config sets `plugins.<name> = false`
or `plugin.json` declares `enabledByDefault: false`. Config changes apply on
the next page load — there is no runtime toggle yet.

---

## Validating end to end

1. `node --check` the module (see "Creating a plugin step by step").
2. Hard-refresh `/editor` and open **Settings > PLUGINS** — the plugin must
   appear.
3. Exercise it on a real file. For the included `color-swatches` example, type
   a hex token such as `#ff00ff` and a small color box should render next to it
   on every edit.
4. Re-run the browser acceptance suite if available:

   ```bash
   .venv/bin/python -m tests.runner
   ```