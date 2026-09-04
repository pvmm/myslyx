# HITBASIC Editor

A small in-browser code editor built with NiceGUI and CodeMirror. Intended for lightweight editing, demos, and agent onboarding within this repository.

Features
- Embedded CodeMirror editor with file dock
- Starter `README.md` and sample Python file on first open
- Undo/redo, rename, delete, save, download/upload, drag-and-drop import
- Read-only support for selected files

Requirements
- Python 3.10+
- Create and activate a virtual environment (recommended):

  python -m venv .venv
  source .venv/bin/activate

- Install dependencies:

  pip install -r requirements.txt

Running
- Start the server (default port 8080):

  python main.py

- Specify a different port with `--port` / `-p` or with the `PORT` environment variable:

  python main.py --port 8081
  PORT=8081 python main.py

- Specify a different host/interface with `--host` / `-H` or with the `HOST` environment variable:

  python main.py --host 127.0.0.1 --port 8081
  HOST=127.0.0.1 PORT=8081 python main.py

- Open the editor in your browser at: http://localhost:8080/editor (adjust port as needed)

Developer notes
- Auto-reload is disabled by default to avoid multi-process engineio/socketio ASGI issues while debugging. Re-enable `reload=True` in `main.py` only when you understand the reloader behavior.
- To quickly check Python syntax for pages, run:

  python -m py_compile pages/editor_page.py

- Logs and debugging: see `main.py` for middleware that logs HTTP requests and engineio/socketio logger settings.

Known issues
- Investigating occasional engineio KeyError 'REQUEST_METHOD' when using the reloader. Use `PORT`/`--port` and run without reload for stable testing.

Contributing
- Make small, focused changes; run the app locally and test the editor UI after edits. Prefer client-side handlers in `pages/editor_page.py` for frontend behavior.

License
- MIT-style (no license file included)
