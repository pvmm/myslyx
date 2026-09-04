# Open bugs (from bugs.txt)

- Editor focus on startup — ensure editor receives focus when a file is loaded.
- Font switching issues — ensure editor font updates when users change theme or font.
- Save button behavior — verify saved files appear in the file pool below the editor.
- Undo/Redo buttons — ensure click and keyboard shortcuts both trigger native CodeMirror history.
- Hints/autocomplete — verify the hints window shows language-appropriate suggestions.
- Drag-and-drop upload — feature not implemented yet; add DnD handlers.

Testing tips
- Hard-refresh browser after modifying `static/` files to avoid caching issues.
- Capture browser console logs if a feature fails.
