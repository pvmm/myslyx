# Project overview

NiceGUI-based in-browser editor using CodeMirror.

Structure
- `main.py` — app entrypoint.
- `pages/` — NiceGUI page modules (`editor_page.py`, `home_page.py`).
- `static/` — CSS and JS (`retro.css`, `retro.js`).

Features
- File pool with save/rename/delete, undo/redo, download/upload.
- Client-side persistent storage via `WBStorage` in `static/retro.js`.

Useful commands
```
.venv/bin/python -m py_compile pages/editor_page.py
.venv/bin/python main.py
```

Known work to continue
- Improve drag-and-drop upload.
- Finalize undo/redo across all browsers and button clicks.

Current status (summary)
- **Working:**
	- Editor page loads and is served by `main.py` on port 8080.
	- File pool (save/new/rename/delete) persists to browser localStorage via `WBStorage`.
	- `DELETE` dialog and handler fixed; delete action removes file from pool.
	- Undo/Redo: keyboard shortcuts (Ctrl/Cmd+Z/Y) work; undo/redo buttons dispatch native key events and are wired.
	- Upload (file picker) and Download implemented.
	- Drag-and-drop: implemented — dropping text files creates new entries in the file pool and opens them (page reload after drop).
	- Hints/autocomplete overlay present and wired to `WBHints`.
	- Editor font and font-size settings applied via CSS variables and persisted in `localStorage`.

- **Missing / To improve:**
	- Drag-and-drop currently reloads the page after files are added; consider live insertion to avoid full reload.
	- Repeated WatchFiles reload churn observed during edits — investigate to reduce spurious reloads.
	- Intermittent ASGI/engineio error in logs: KeyError `'REQUEST_METHOD'` (needs investigation when certain requests arrive).
	- Browser favicon requests produce 404s (non-critical).
	- Cross-browser acceptance testing (Firefox, Chrome) to confirm undo/redo button behavior and DnD UX.

