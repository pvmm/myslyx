# Agents onboarding

This file helps AI agents and new contributors quickly understand how to work on this repository.

Guidelines for agents
- Follow the project's coding conventions: keep changes small and focused.
- When editing UI code, prefer client-side handlers in `myslyx/pages/editor_page.py`'s `_init()` and use `ui.run_javascript()` rather than inline attributes.
- For Python changes, run: `.venv/bin/python -m py_compile myslyx/pages/editor_page.py` before pushing.
- When adding features that affect the frontend, include minimal manual test steps and a browser check (hard refresh).
- Always clean up after yourself: every server (e.g. `python main.py`, test-run myslyx instances) started for a session must be killed before the task is finished — they accumulate and hog machine resources. Close stray Playwright/`firefox 127.0.0.1` tabs left pointing at dead test ports too.

Project layout
- Myslyx is an installable Python package (`pyproject.toml`). Install it for local use with `.venv/bin/pip install .` (or `-e .` for editable/development installs). It provides the `myslyx` console command and `python -m myslyx`.
- `main.py` at the repo root is a thin shim (`from myslyx.app import run; run()`) kept for the Hugging Face Space entrypoint and for running straight from a checkout without installing.

Key files
- `myslyx/app.py` — app server: static file serving, CLI parsing (`-p/-H/--no-reload`, `PORT`/`HOST`/`WB_TESTING`), logging, `ui.run()`. The `run()` entry point must stay import-safe (no server start at import time).
- `myslyx/pages/editor_page.py` — main NiceGUI page for the editor and toolbar.
- `myslyx/static/retro.js` — client-side helpers and storage (`WBStorage`, `WBHints`).
- `myslyx/static/hints/` — language hint dictionaries (JSON). To add/change keyword or builtin help texts, see `myslyx/static/hints/README.md`.
- `myslyx/static/hints.js` — hints sidebar, autocomplete popup and user-symbol scanner.
- `myslyx/static/retro.css` — theme and editor gutter alignment.

Building / verifying the package
- Syntax check: `.venv/bin/python -m py_compile myslyx/app.py myslyx/pages/editor_page.py`
- Editable install: `.venv/bin/pip install -e .`
- Build artifacts: `.venv/bin/python -m pip wheel . -w /tmp/opencode/wheels` (wheel includes `myslyx/static/**` and `myslyx/STARTUP.txt` via MANIFEST.in + include-package-data).
- Verify a clean (non-editable) install in a throwaway venv before shipping — confirms data files actually shipped.

If you need to persist agent notes, add them under `/docs/agents/` and reference this file.