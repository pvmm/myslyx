Commit individually each entry when fixed:
- [x] add support for vscode-languageserver as an online LSP for Myslyx (directly in the browser) instead of relying on SDCC or clangd server in the machine. The support for in-browser LSP should be defined as a plugin for Myslyx. Don't delete lsp.py and lsp.js that already exist, they serve a different purpose (machine-installed LSP servers). Rename the old plugin to something like "local-lsp"
- [x] add ability to autocomplete #include with local .h filename or a .h file included in the module list of the MSXgl.
- [x] Fix local-lsp/completions-c-custom (TimeoutError: strlen never rendered in the custom popup)
- [ ] extract language constant from weblsp.js and worker.bundle.js (replace hardcoded "msxgl" references with base language attribute) but make sure it still works as before
- [ ] add test suite for language-agnostic plugin behavior (C vs MSXgl+C completion round trips)
- [ ] verify weblsp.js plugin.json base language attribute is generic (not language-specific)
- [ ] update worker.bundle.js to respect the editor's language setting instead of fixed binding
