# Editor plugins (`static/plugins/`)

Plugins extend the CodeMirror editor with client-side behaviour — decoration
widgets (e.g. color swatches), extra keymaps, hover popups — without touching
`pages/editor_page.py`. They run as plain scripts loaded in the page head.

The runtime is `static/plugins.js`. It registers plugins, checks whether each
one is enabled, and appends their CodeMirror 6 extensions to the editor once
the view exists (same editor-id polling strategy as `static/hints.js`).

## How a plugin is loaded

1. Drop a file `static/plugins/<name>.js` that calls `window.WBPlugins.register(...)`.
2. Load it from the page head in `pages/editor_page.py`, right after
   `plugins.js`:
   ```python
   ui.add_head_html('<script src="/static/plugins/<name>.js"></script>')
   ```

Script order matters: `plugins.js` (the runtime) must load before any plugin.

## Plugin contract

```js
window.WBPlugins.register({
    name: 'color-swatches',          // unique id, also the config key
    languages: ['*'],                // ['*'] for all, or ['VBScript','C',...]
    enabledByDefault: true,
    extensions: function(view, CM, ctx) {
        // Return an array of CodeMirror 6 extensions (ViewPlugin, StateField,
        // keymap, ...). CM is the 'nicegui-codemirror' namespace, lazily
        // imported (it re-exports the whole CodeMirror API: Decoration,
        // ViewPlugin, StateEffect, MatchDecorator, ...). ctx.config holds the
        // plugin's saved config object ({} if none).
        return [/* CM extension(s) */];
    }
});
```

### Good neighbours

- **Use the injected-extension pattern.** Prefer returning CM extensions over
  mutating the DOM yourself; CM recomputes decorations automatically on every
  edit.
- **Match the retro theme.** Reuse the existing popup/spacing conventions
  (`wb-autocomplete-popup`, `--wb-font`, `--wb-white`, hard borders) so plugins
  look native.
- **Guard your wiring.** Both `hints.js` and the plugin runtime hook the view
  with `view._wbXxxApplied` flags so they never double-install. Keep that
  convention if you add your own view-level state.
- **Wrap failures.** Throw inside `extensions` — the runtime catches it, logs a
  warning, and skips the plugin without breaking the editor.

## Enabling / disabling

Enabled state lives in the shared client config (`localStorage['wb_editor_config']`,
the same object as the hints width and WRAP prefs):

```json
{ "plugins": { "color-swatches": false } }
```

A plugin is enabled by default unless:
- the config sets `plugins.<name> = false`, or
- `enabledByDefault` is `false` in the plugin definition.

Config changes apply on the next page load (hard refresh) — there is no
runtime toggle yet.

## Included example: `color-swatches`

Scans the document for `#rrggbb`-style hex tokens and renders a small color box
right after each one. It is the minimal proof-of-concept (no popup yet) showing
the full pipeline: load script -> register -> hook view -> `MatchDecorator` ->
`Decoration.widget`. The swatch styles are injected by the plugin itself so
`static/retro.css` stays untouched.

## Validation

```bash
node --check static/plugins.js
node --check static/plugins/<name>.js
.venv/bin/python -m py_compile pages/editor_page.py
```

Then **hard-refresh** the browser and test with e.g. `#ff00ff` in an open file.