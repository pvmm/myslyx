# high priority (one commit each)
- [ ] if changing the LANG of a file creates a name clash with another file, ask the user to rename the filename until the new name no longer clashes.
- [ ] add button to download all files in the file pool ("DOWNLOAD\nALL") as a zipped single file. Put it left of "RESET FILE POOL", unstacked.
- [ ] the sub folding in HitBasic displays "sub...end sub" when folded, but I would like it to display the name of the subroutine too, like the way the folding in the C language displays the name of the function even when the function is folded. The same thing happens to "function...end function" in HitBasic. Can you fix it to display the name of the function/sub even when folded?
- [ ] the if/end if folding in HitBasic displays "if...end if" when folded, but I would like it to display the test condition of the condition too, like the way the folding of conditions work in the C language. Can you fix it?
- [ ] when user presses Ctrl+, to display the favicon menu, the top item of the menu should be activated instead of no item being activated, forcing the user to move the arrow keys to figure out where the cursor is.
- [ ] mark code with sleep antipattern in the "Sensitive / flaky code" list below.
- [ ] create an example of a link in the HINTS documentation. For instance: the for keyword in the C language root page is now a link pointing to the "FOR Loop" hint. Make the link appear like a dashed line below the text of the link.

# Sensitive / flaky code to keep an eye on (check each when fixed):
- [ ] `window.__wbPyBridge` (editor_page.py:76-91) = unguarded global storage API; Python writes whole file pool via json.dumps into run_javascript (375-379). Any JS can call setFiles/setActive and bypass _open_file_request, dedupe, rename/conflict checks and the readonly STARTUP flag.
- [ ] Active-editor singletons `__wbEditorId`/`__wbEditorIds` (495, 577, 718, 927-934) + getElement(...).editorPromise races; helpers/plugins read these synchronously. Root cause of the old "Language not found" boot race and typing-before-mount drops.
- [ ] Settings rows (WRAP/LIGATURES) (1022-1200): fire-and-forget saveConfig + inline restyle, no ack; tests add fixed 400ms waits; querySelectorAll('.cm-editor .cm-content') restyles all editors.
- [ ] _load_file_into_editor (541-660): f-string values interpolated into run_javascript ({readonly}, {cm_lang}); a quote in any value breaks the JS; readonly STARTUP enforced client-side only.
- [ ] _on_editor_change trusts client value; tests read doc via view editorPromise (helpers.py:6-9) not the Python echo, so content is only ever validated client-side.
