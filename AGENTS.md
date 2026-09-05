# Agents onboarding

This file helps AI agents and new contributors quickly understand how to work on this repository.

Guidelines for agents
- Follow the project's coding conventions: keep changes small and focused.
- When editing UI code, prefer client-side handlers in `pages/editor_page.py`'s `_init()` and use `ui.run_javascript()` rather than inline attributes.
- For Python changes, run: `.venv/bin/python -m py_compile pages/editor_page.py` before pushing.
- When adding features that affect the frontend, include minimal manual test steps and a browser check (hard refresh).

Key files
- `pages/editor_page.py` — main NiceGUI page for the editor and toolbar.
- `static/retro.js` — client-side helpers and storage (`WBStorage`, `WBHints`).
- `static/hints/` — language hint dictionaries (JSON). To add/change keyword or builtin help texts, see `static/hints/README.md`.
- `static/hints.js` — hints sidebar, autocomplete popup and user-symbol scanner.
- `static/retro.css` — theme and editor gutter alignment.

If you need to persist agent notes, add them under `/docs/agents/` and reference this file.
