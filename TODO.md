# Sensitive / flaky JS-in-Python spots to keep an eye on (check each when fixed):
- [ ] `window.__wbPyBridge` (editor_page.py:76-91) = unguarded global storage API; Python writes whole file pool via json.dumps into run_javascript (375-379). Any JS can call setFiles/setActive and bypass _open_file_request, dedupe, rename/conflict checks and the readonly STARTUP flag.
- [ ] Active-editor singletons `__wbEditorId`/`__wbEditorIds` (495, 577, 718, 927-934) + getElement(...).editorPromise races; helpers/plugins read these synchronously. Root cause of the old "Language not found" boot race and typing-before-mount drops.
- [ ] Settings rows (WRAP/LIGATURES) (1022-1200): fire-and-forget saveConfig + inline restyle, no ack; tests add fixed 400ms waits; querySelectorAll('.cm-editor .cm-content') restyles all editors.
- [ ] _load_file_into_editor (541-660): f-string values interpolated into run_javascript ({readonly}, {cm_lang}); a quote in any value breaks the JS; readonly STARTUP enforced client-side only.
- [ ] _on_editor_change trusts client value; tests read doc via view editorPromise (helpers.py:6-9) not the Python echo, so content is only ever validated client-side.
