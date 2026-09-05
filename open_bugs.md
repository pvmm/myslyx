# Open bugs (from bugs.txt)

- Editor focus on startup — ensure editor receives focus when a file is loaded.
- Font switching issues — ensure editor font updates when users change theme or font.
- Save button behavior — verify saved files appear in the file pool below the editor.
- Undo/Redo buttons — ensure click and keyboard shortcuts both trigger native CodeMirror history.
- Hints/autocomplete — verify the hints window shows language-appropriate suggestions.
- Drag-and-drop upload — feature not implemented yet; add DnD handlers.

Status updates
- Editor focus: implemented (focus polling added in `_load_file_into_editor`).
- Font switching: implemented via CSS variable and `localStorage` restore.
- Save behavior: implemented; files persist to the dock and to `WBStorage`.
- Undo/Redo: keyboard works; buttons are wired to dispatch native events (verify in each browser).
- Hints/autocomplete: popup and hints panel wired via a native CM6 update listener (`static/hints.js`); hint data is pluggable — edit `/static/hints/<key>.json` (markdown `tips`/`patterns`) without touching code. User-defined `FUNCTION`/`SUB`/`DEF FN` names are discovered from all pool files and persisted per file id in localStorage (`wb_editor_symbols`).
- Drag-and-drop upload: implemented; dropped files are read as text and saved to `WBStorage` then the page reloads to show them.

Remaining / follow-ups
- Convert DnD flow to live-insert (avoid page reload after drop) for smoother UX.
- Reduce WatchFiles reload churn when editing `pages/*.py` (investigate tooling or file-watching globs).
- Investigate ASGI/engineio KeyError `'REQUEST_METHOD'` seen in server logs under some requests.
- Add browser acceptance tests and note any browser-specific quirks.

Added by user:
- Set short cuts for Ctrl-+/Ctrl-- to grow/shrink font size.
- Add keyboards in shortcuts table
- Add internationalization support?


Testing tips
- Hard-refresh browser after modifying `static/` files to avoid caching issues.
- Capture browser console logs if a feature fails.
