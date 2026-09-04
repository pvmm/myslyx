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
