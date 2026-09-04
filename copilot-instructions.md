# Copilot / Assistant Instructions

Short guidance for automated assistants working in this repo.

Work style
- Be concise and surgical: prefer minimal, focused edits addressing the user's request.
- Use `apply_patch` to modify files and run `python -m py_compile` on modified Python files.
- Avoid changing external dependencies unless requested.

Testing and verification
- Run the local server using the project's virtualenv: `.venv/bin/python main.py`.
- After frontend JS/CSS edits, ask the user to hard-refresh the browser (Ctrl+Shift+R).

Local conventions
- Prefix CSS variables with `--wb-` and classes with `wb-`.
- Put client-side behavior in `static/retro.js` where appropriate.

When in doubt, ask the user for clarification before making larger changes.
