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
| Hosting | Whatever your app uses | Served as a static file under `/static/plugins/<name>/` |
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
determines the entry module file (`<name>.js`) and the served URL
(`/static/plugins/<name>/<name>.js`).

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
    "languages": ["VBScript"],
    "enabledByDefault": false
}
```

- `languages` — restrict the plugin to specific file languages (values from the
  language dropdown: `VBScript`, `Pascal`, `C`, `Z80`, `Text`). Default: all.
- `enabledByDefault` — whether the plugin is on until the user disables it.
  Default: `true`.

---

## Creating a plugin step by step

1. Create the directory `myslyx/static/plugins/<name>/` and the module
   `<name>.js`.
2. Write your extension as a plain CodeMirror 6 extension, using only the `CM`
   namespace (see the porting notes above).
3. Add a `plugin.json` only if you need language scoping or a non-default
   enabled state.
4. Validate:

   ```bash
   node --check myslyx/static/plugins/<name>/<name>.js
   ```

5. Hard-refresh `/editor` and check the plugins menu — the plugin is picked up
   automatically, with no Python edits and no server restart.

Good practice:

- **Prefer the injected-extension pattern.** Return CodeMirror extensions over
  mutating the DOM yourself; CodeMirror recomputes decorations on every edit.
- **Match the retro theme.** Reuse existing popup/spacing conventions
  (`wb-autocomplete-popup`, `--wb-font`, `--wb-white`, hard borders) so the
  plugin looks native.
- **Keep assets in the plugin directory.** Files under
  `myslyx/static/plugins/<name>/` are served at `/static/plugins/<name>/...`
  and stay isolated from other plugins.
- **Wrap failures.** The runtime catches load errors and factory throws, logs a
  warning, and skips the plugin without breaking the editor.

---

## Installing a plugin

A plugin is installed the moment its directory exists on disk; the page
discovers plugins at load time by scanning `myslyx/static/plugins/`.

### From a source checkout or editable install

Drop the plugin directory into `myslyx/static/plugins/` and hard-refresh:

```bash
cp -r my-plugin myslyx/static/plugins/
```

### From an installed package

With a regular (non-editable) `pip install`, the static files live in your
Python's `site-packages/myslyx/static/plugins/`. Find the package with:

```bash
python -c "import myslyx; from pathlib import Path; print(Path(myslyx.__file__).parent / 'static' / 'plugins')"
```

Then copy your plugin directory there (or — if you are distributing a plugin —
add it to the source tree and rebuild the wheel; `MANIFEST.in` bundles
`myslyx/static/**` automatically).

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
2. Hard-refresh `/editor` and open the plugins menu — the plugin must appear.
3. Exercise it on a real file. For the included `color-swatches` example, type
   a hex token such as `#ff00ff` and a small color box should render next to it
   on every edit.
4. Re-run the browser acceptance suite if available:

   ```bash
   .venv/bin/python -m tests.runner
   ```