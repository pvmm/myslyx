<p>
  <img src="static/favicon-pixelated.png" alt="Project Icon" width="128" height="96">
</p>

# Myslyx Text Editor

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

- Open the editor in your browser at: http://localhost:8081/editor (adjust port as needed)

Developer notes
- Auto-reload is on for development (uvicorn watches `*.py`, `*.css`, `*.js`). Disable it with `--no-reload` (or `WB_TESTING=1`) when you need a single quiet process.
- To quickly check Python syntax for pages, run:

  python -m py_compile pages/editor_page.py

- Logs and debugging: see `main.py` for middleware that logs HTTP requests and engineio/socketio logger settings.

Tests
- Browser acceptance tests live in `tests/`. They spawn their own app subprocess and run the same suites across Chromium and Firefox (WebKit is not a default: Playwright's prebuilt WebKit needs ICU 74 / libjpeg 8 / libbacktrace, which Fedora doesn't ship — run `-b webkit` only on a host that provides them).
- Install the test dependencies and browsers once:

  pip install -r dev-requirements.txt
  playwright install chromium firefox webkit

- Run the default browsers:

  python -m tests.runner

- Run specific browsers:

  python -m tests.runner -b chromium firefox

- Browsers that cannot launch (e.g. missing host libraries) are reported as SKIP rather than failing the run.

Contributing
- Make small, focused changes; run the app locally and test the editor UI after edits. Prefer client-side handlers in `pages/editor_page.py` for frontend behavior.

© 2026 Pedro "pvm" Medeiros
