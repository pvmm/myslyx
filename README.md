<p>
  <img src="static/favicon-pixelated.png" alt="Project Icon" width="128" height="96">
</p>

# Myslyx Text Editor

A in-browser code editor built with NiceGUI and CodeMirror. Intended for lightweight editing, demos, and agent onboarding within this repository.

Features
- Embedded CodeMirror editor with file dock
- Wrap around, code completion and code folding
- Undo/redo, rename, delete, save, download/upload, drag-and-drop import

Privacy & storage
- Your files persist in the browser's localStorage. To render the editor, the page mirrors the active pool into the running server session (memory only), but the server never stores your files — there is no database or on-disk backend.
- Running Myslyx yourself (see "Running" above) keeps everything on your own machine.

Requirements
- Python 3.10+

Install (as a package)
- The editor is packaged as `myslyx`. Install it locally with pip (use a virtual environment):

  python -m venv .venv
  source .venv/bin/activate
  pip install .

- For development, install it editable so code and static files live in your checkout:

  pip install -e .

- The install provides a `myslyx` console command and a `python -m myslyx` module. To uninstall later: `pip uninstall myslyx`.

Running
- Start the server (default port 8080) with any of:

  myslyx
  python -m myslyx
  python main.py            # from a source checkout - no install needed

- Specify a different port with `-p` / `--port` or with the `PORT` environment variable:

  myslyx --port 8081
  PORT=8081 myslyx

- Specify a different host/interface with `-H` / `--host` or with the `HOST` environment variable:

  myslyx --host 127.0.0.1 --port 8081
  HOST=127.0.0.1 PORT=8081 myslyx

- Open the editor in your browser at: http://localhost:8081/editor (adjust port as needed)

Local LSP completions (C / C MSXgl)
- Myslyx can feed completions from a local Language Server over the plugin
  system (the bundled `local-lsp` plugin). This is **local-only** by design: it is
  disabled in shared / multi-user deployments (e.g. a Hugging Face Space) and
  reads the file you are editing off your own disk — the server never stores it.
- On a Linux machine, install a C language server (clangd) and start Myslyx with
  `MYSLYX_LSP` set to the binary name (or an absolute path):

  Debian/Ubuntu:   sudo apt install clangd
  Fedora/RHEL:     sudo dnf install clang-tools-extra

  MYSLYX_LSP=clangd python main.py

- Open a `.c` file (plain C) or a C MSXgl file, type a few characters (e.g.
  `#include <string.h>` then `strl`) and the native/custom popup shows live
  suggestions from clangd, on top of the curated keyword dictionary.
- If the LSP cannot be reached the plugin auto-disables with a brief toast and
  the editor falls back to the built-in hints — nothing breaks.
- Set `MYSLYX_LOCAL=0` yourself to make Myslyx behave like a remote/shared run
  (useful to verify all local-only plugins stay off).

In-browser LSP (C / C MSXgl / Pascal)
- Myslyx also ships an LSP that runs entirely in your browser (the bundled
  `weblsp` plugin): a real `vscode-languageserver` server in a Web Worker
  serving completions, hover tips and signature help from the same generated
  hints dictionaries as the sidebar (`static/hints/*.json`), plus your own
  exported symbols. It needs no server binary and works on shared / remote
  deployments too.
- In a C MSXgl file, type `VDP_SetM` for worker-fed completions, hover a
  builtin for its tip, or type `VDP_SetMode(` for signature help. Plain C
  keeps the custom popup; Pascal completes through the native one.
- The worker bundle (`myslyx/static/plugins/weblsp/worker.bundle.js`) is
  committed so installs run without node. Rebuild it after editing the server
  sources or upgrading dependencies with:

  npm --prefix tools/weblsp install
  npm --prefix tools/weblsp run build

- Disable it in Settings > PLUGINS (`weblsp`); the curated dictionaries keep
  working as fallback.

Developer notes
- Auto-reload is on for development (uvicorn watches `*.py`, `*.css`, `*.js`). Disable it with `--no-reload` (or `WB_TESTING=1`) when you need a single quiet process.
- To quickly check Python syntax for pages, run:

  python -m py_compile myslyx/pages/editor_page.py

- Logs and debugging: see `myslyx/app.py` for middleware that logs HTTP requests and engineio/socketio logger settings.

Tests
- Browser acceptance tests live in `tests/`. They spawn their own app subprocess and run the same suites across Chromium and Firefox (WebKit is not a default: Playwright's prebuilt WebKit needs ICU 74 / libjpeg 8 / libbacktrace, which Fedora doesn't ship — run `-b webkit` only on a host that provides them).
- Install the test dependencies and browsers once:

  pip install -e .[dev]
  playwright install chromium firefox webkit

- Run the default browsers:

  python -m tests.runner

- Run specific browsers:

  python -m tests.runner -b chromium firefox

- Run one suite (or any subset) by name substring — repeat `-f` for several
  filters, or add `-b` to keep the run to a single browser:

  python -m tests.runner -f native/msxgl-member -b chromium
  python -m tests.runner -f hints -f multiedit

  Filters match case-insensitively against the registered suite names (e.g.
  `fold`, `lang-combo`, `native`). No server or browser is started until you
  actually run suites, so narrowing with `-f` is the fast way to iterate on a
  single test.

- List every registered suite name:

  python -m tests.runner -l

- Feature workflow: after completing a feature, run the suite you created for
  it first (`python -m tests.runner -f <suite>`); once it passes, run the
  complete set (`python -m tests.runner`) before finishing — never ship a
  feature on an untested suite or a skipped full run.

- Timeouts: approximate 25 seconds per test in a run — the single suite gets
  `timeout 25` (25 s), the complete 72-suite set (including the clangd-gated
  local-LSP suites) `timeout 1800` (30 min).

- Browsers that cannot launch (e.g. missing host libraries) are reported as SKIP rather than failing the run.

Contributing
- Make small, focused changes; run the app locally and test the editor UI after edits. Prefer client-side handlers in `myslyx/pages/editor_page.py` for frontend behavior.

© 2026 Pedro "pvm" Medeiros
