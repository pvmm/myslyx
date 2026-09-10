# CodeMirror / NiceGUI integration improvements

Scope: how Myslyx wires CodeMirror 6 (via NiceGUI's `ui.codemirror` component and
the shared `nicegui-codemirror` module) to the editor page, the settings menu and
the hints/folding/plugin layer.

Constraint honoured throughout: every proposal below is achievable with
**CodeMirror 6 official extension APIs** and **NiceGUI's documented component
surface** — no monkeypatching, no window-global state, and no data injected into
the DOM or into otherwise-private objects (`view`, `element`, `.cm-content`).

Current weaknesses are cited as `path:line` so each item can be mapped to code.

---

## 1. Own the editor lifecycle in one client controller module

Today the "active editor's view" is found by six independent retry loops and
seven window globals that the server sets via string-built `run_javascript`:

- Globals written from the server: `__wbEditorId`, `__wbEditorIds`,
  `__wbCurrentLang`, `__wbHintKey`, `__wbActiveFid`, `__wbActiveReadonly`,
  `__wbPendingFile`, `__wbPendingRoot` (`editor_page.py:474,552-557,594-598,652`).
- Retry loops that poll `window.__wbEditorId`/`getElement(...).editorPromise`
  with magic attempt counters: `plugins.js:96-101`, `folding.js:380-383`,
  `hints.js:520-527`, `editor_page.py:559-589` (focus), `editor_page.py:575-579`.

**Improvement:** a single ES module (`myslyx/static/wb/editor-controller.js`)
imported once that owns the EditorView lifecycle and exposes one promise
(`whenReady()`), plus plain functions. Every other script consumes that module
instead of polling globals / NiceGUI internals. The server reaches the client
through the module only (see also items 7–8). Result: deterministic sequencing —
"view exists" is a resolved promise, not a `setInterval` bounty.

## 2. Configure extensions at mount (Compartments/facets), never `appendConfig`

- `folding.js:290-312` dispatches `StateEffect.appendConfig.of([...])` and then
  re-applies on a 8-try/400 ms retry loop because "CodeMirror can rebuild the
  editor state shortly after mount, dropping appended config facets"
  (`folding.js:359-373`).
- `plugins.js:24,74-82` marks `view._wbPluginsApplied` (data injected into the
  view object) and appends plugin extensions at runtime.
- `hints.js:482-498` marks `active._wbHintHooked` and appends an updateListener
  the same way.

**Improvement:** folding (`foldService`, fold keymap, gutter refresh listener),
the hints update-listener and each plugin's extensions are passed to the view's
initial extension list at mount — through an `extensions` Compartment the
component already knows how to reconfigure (the `ui.codemirror` Vue component
already uses Compartments for language/theme/editable/line-wrapping/user-keymap,
see its `setupExtensions`/`mounted`). No underscore markers, no `appendConfig`,
no re-apply racing. Dynamic changes (e.g. plugin enablement) reconfigure the
Compartment via a prop, which is the mechanism the component ships with.

## 3. Enforce read-only with CM state, not DOM listeners

`editor_page.py:594-628` finds `.wb-edit-slot-<fid> .cm-editor .cm-content` and
attaches capture-phase `keydown`/`beforeinput` handlers (`el._wbReadOnlyHandler`,
stored on the DOM node) to block input. `editor-keyboard.js:12` additionally
blocks undo/redo at document level. This misses IME composition, drag-drop
inserts, programmatic transactions, menu paste, and stored the handler on a DOM
element.

**Improvement:** use CM6's `EditorState.readOnly` / `EditorView.editable`
through the component's existing `disable` prop (`setDisabled` already
reconfigures an `editableConfig` Compartment). This stops all edits through the
editor's own pipeline — including undo/redo — and needs no per-element handler.

## 4. Keystrokes via CM keymaps instead of DOM/window `keydown`

- `editor-keyboard.js:14-42` listens on `document` for Ctrl/Cmd-Z/Y and skips
  when `e.target.closest('.cm-editor')` (a DOM heuristic), then calls
  `getElement(id).editorPromise.then(... CM.undo/redo)`.
- `folding.js:328-349` intercepts Ctrl+Shift+[ / ] at `window` capture phase to
  work around CodeMirror's key normalization (Playwright fires `[` instead of
  `{`, mapping to Mod-[ / indentLess).

**Improvement:** declare these as first-class CM keymaps (`Mod-z`, `Mod-y`,
`Mod-Shift-z`, `Mod-[`, `Mod-]`) at the right precedence, using the component's
official `keymap` prop and `KeyBinding` wrapper (`map_key`/`unmap_key`,
`keybinding` event). CM6's own key binding machinery then resolves chords,
platforms and `preventDefault` — no document-level listener, no `closest()`
guessing, and the fold bindings behave identically for `[` and `{` because
keymap entries use `Key`-aware matching.

## 5. Language lives in CM state — drop the mirror globals

`__wbCurrentLang`, `__wbHintKey`, `__wbActiveFid` are re-set on every activation
and language change (`editor_page.py:552-557,680-681`) and read by hints/folding
(`hints.js:4,121-132`, `folding.js:103`). This parallel bookkeeping drifts from
the editor's real state.

**Improvement:** extensions read the language from `view.state.facet(language)`
and react through an `updateListener`/`Prec`-positioned extension (already the
pattern in `folding.js:262-288`). The server keeps `ed.set_language(...)` (the
component's official API) as the single source of truth; global variables and
the `__wbHintKey` mapping go away. Folding's "language changed → refresh gutter"
listener becomes part of the statically-configured extensions from item 2.

## 6. Autocomplete through a real `CompletionSource`

`hints.js` builds a hand-rolled popup: completes on timeouts (`scheduleScan`
250 ms / `scheduleCompletions` 80 ms), inserts via `view.dispatch({changes})`
(`hints.js:400-413`), navigates with `ArrowDown/ArrowUp/Enter/Tab/Escape` via a
listener attached to `active.contentDOM` (`hints.js:501-508`), and is closed on
a `blur` timer.

**Improvement:** a `@codemirror/autocomplete` `autocompletion()` + custom
`CompletionSource` fed by the hint dictionaries and the symbol store. CodeMirror
owns popup rendering, key navigation, filtering, insertion and blur/dismiss —
no DOM listeners glued to the content element, no timers racing each other.

## 7. Stop interpolating runtime data into JS source strings

Most client calls are f-string-built `run_javascript` snippets. Most use
`{json.dumps(...)}` for data (`editor_page.py:749,352-359`) — but not all:
`editor_page.py:704` injects the font name directly into a JS string literal
(`localStorage.setItem('wb_editor_font', '{font}')`) and `:552-556` interpolate
language/fid inside quotes. A single quote or cosmetic glyph breaks or executes
the snippet.

**Improvement:** never splice runtime values into `run_javascript` source.
Values travel as element props/events (JSON-serialised) or through one typed
controller entry point; if a snippet is unavoidable it only reads already-safe
state. This removes a whole class of syntax errors and a (mild) injection
surface, and makes the few remaining snippets lint-clean.

## 8. Single, typed client↔server channel; retire bespoke bridges

Multiple ad-hoc channels exist: hidden DOM elements used as message buses
(`#wb-open-bridge`, `#wb-storage-sync-bridge` + `dispatchEvent(new CustomEvent(...))`
from `editor-init.js:73-75`, `editor_page.py:849-860`), a `window.__wbPyBridge`
object (`storage-bridge.js`), and broadcast `window.dispatchEvent(...CustomEvent('wb-active-editor'))`
coordinating scripts (`editor_page.py:649-655,683-689`).

**Improvement:** a coherent design where the *component's official events*
carry data: `update:value`, `keybinding`, `anchor-positions`, and `on_change`
for edits; props for state pushed *to* the editor. File-open and pool-sync
requests go through the single controller module (item 1) exposed as one
documented function, not bespoke DOM events per concern. Net effect: the editor
area no longer contains hidden bridge elements, and no payload is serialised
through the DOM event system.

## 9. Debounce persistence and stream ChangeSets

`_on_editor_change` receives the entire document per keystroke and
`_save_to_storage` re-sends the **whole pool** to localStorage on every edit
(`editor_page.py:352-359,657-662`). Under the hood the component already emits
`update:value` as a compact `ChangeSet` (the Vue component's `changeSender`).

**Improvement:** coalesce edits client-side (debounced snapshot in the
controller, e.g. 500 ms) and persist once; keep the server mirror updated via
the component's existing change events. This kills the full-pool-per-keystroke
`run_javascript` chatter and shrinks round trips dramatically on large files.

## 10. Pin and import `nicegui-codemirror` once

`editor-keyboard.js:18`, `folding.js:338,366`, `plugins.js:29` and
`hints.js:484` each do a dynamic `import('nicegui-codemirror')` and keep a
private `CM_NS` copy. The module resolves from NiceGUI's bundled `dist`, so any
lazy-load ordering/re-import jitter or a packaging change silently breaks parts
of the editor.

**Improvement:** `import('nicegui-codemirror')` exactly once in the controller
module and share the namespace through the module object (item 1). Confirms the
bundle is present at startup and gives one predictable dependency instead of a
race of dynamic imports.

## 11. Lean on the server-side per-file model; stop parallel client bookkeeping

Per-file state (id, language, readonly, content) already lives only server-side
in `client_state['files']` / `editors[fid]` and is the single source of truth.
The client mirrors it through globals (`__wbEditorIds`, `__wbCurrentLang`, …).

**Improvement:** the client needs exactly three things per visible editor —
content, language, read-only — all available as component props
(`value`, `language`, `disable`). Everything else stays server-side. Activating
a file becomes "set props on the right component", and scripts read per-editor
facts from CM state, never from a parallel global registry.

---

Suggested order (each step is shippable on its own):

1. Item 7 + Item 9 — stop string interpolation, debounce the full-pool writes (mechanical, low risk).
2. Item 3 — read-only via `disable`; deletes the quirkiest DOM hack.
3. Item 4 — move undo/redo/fold keystrokes into keymaps.
4. Item 1 + Item 10 — introduce the controller module and single import.
5. Item 2 — move folding/hints/plugins to mount-time extensions.
6. Item 5 + Item 6 + Item 8 — remove globals and bespoke bridges; native autocomplete.
7. Item 11 — final tidy-up of whatever globals remain.