# higher priority (one commit per entry, update this document when done)
- [x] Update LANG combo box according to the current visible file on the text editor.
- [x] The HINTS window display "Plain text" when a C or Pascal file is displayed in the text editor.
- [x] Pressing enter in the autocompletion context menu doesn't select that option and write it on the text editor component.
- [x] Pressing enter or right arrow when over the PLUGIN submenu in the favicon menu doesn't send the cursor to the submenu. The cursor still moves around in the same menu section.
- [x] Create a short cut for "EXPORT SYMBOLS ON/OFF" that doesn't collide with CodeMirror or the browser predefined short cuts. Add it to the short cuts window.
- [x] Create a short cut for the "RENAME" button that doesn't collide with CodeMirror or the browser predefined short cuts. Add it to the short cuts window.
- [x] Create a short cut for the "UPLOAD" button that doesn't collide with CodeMirror or the browser predefined short cuts. Add it to the short cuts window.
- [x] Create a short cut for the "DOWNLOAD" button that doesn't collide with CodeMirror or the browser predefined short cuts. Add it to the short cuts window.
- [x] Create a short cut for the "DELETE" button that doesn't collide with CodeMirror or the browser predefined short cuts. Add it to the short cuts window.
- [x] Create a short cut for the "+ NEW" button that doesn't collide with CodeMirror or the browser predefined short cuts. Add it to the short cuts window.
- [x] Create short cut to move around the open files in the file pool that doesn't collide with CodeMirror or the browser predefined short cuts. Add it to the short cuts window.
- [x] Move all inline javascript to their own files in the static subdirectory when they have 5+ lines and don't have string interpolation.

# Sensitive / flaky JS-in-Python spots to keep an eye on (check each when fixed):
- [ ] `window.__wbPyBridge` (editor_page.py:76-91) = unguarded global storage API; Python writes whole file pool via json.dumps into run_javascript (375-379). Any JS can call setFiles/setActive and bypass _open_file_request, dedupe, rename/conflict checks and the readonly STARTUP flag.
- [ ] Active-editor singletons `__wbEditorId`/`__wbEditorIds` (495, 577, 718, 927-934) + getElement(...).editorPromise races; helpers/plugins read these synchronously. Root cause of the old "Language not found" boot race and typing-before-mount drops.
- [ ] Settings rows (WRAP/LIGATURES) (1022-1200): fire-and-forget saveConfig + inline restyle, no ack; tests add fixed 400ms waits; querySelectorAll('.cm-editor .cm-content') restyles all editors.
- [ ] _load_file_into_editor (541-660): f-string values interpolated into run_javascript ({readonly}, {cm_lang}); a quote in any value breaks the JS; readonly STARTUP enforced client-side only.
- [ ] _on_editor_change trusts client value; tests read doc via view editorPromise (helpers.py:6-9) not the Python echo, so content is only ever validated client-side.
