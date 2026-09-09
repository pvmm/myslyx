// Keyboard and editor-view helpers for the active CodeMirror instance.
(function() {
    function install() {
        (function() {
            const f = localStorage.getItem('wb_editor_font') || 'Press Start 2P';
            document.documentElement.style.setProperty('--wb-editor-font', "'" + f + "', monospace");
            const fs = localStorage.getItem('wb_editor_font_size') || '13';
            document.documentElement.style.setProperty('--wb-editor-font-size', fs + 'px');
            window.__wbEditorIds = window.__wbEditorIds || {};

            function wbCmDo(action) {
                if (window.__wbActiveReadonly) return;
                var elId = window.__wbEditorId;
                if (!elId) return;
                getElement(elId).editorPromise.then(function(p) {
                    try {
                        import('nicegui-codemirror').then(function(CM) {
                            try {
                                if (action === 'undo') CM.undo(p); else CM.redo(p);
                            } catch(e) {}
                            try { p.focus(); } catch(e) {}
                        });
                    } catch(e) {}
                });
            }

            window.__wbUndo = function() { wbCmDo('undo'); };
            window.__wbRedo = function() { wbCmDo('redo'); };
            document.addEventListener('keydown', function(e) {
                var mod = e.ctrlKey || e.metaKey;
                if (!mod) return;
                if (e.key === 'z' && !e.shiftKey) {
                    if (e.target && e.target.closest && e.target.closest('.cm-editor')) return;
                    e.preventDefault();
                    window.__wbUndo();
                } else if (e.key === 'y' || (e.key === 'z' && e.shiftKey)) {
                    if (e.target && e.target.closest && e.target.closest('.cm-editor')) return;
                    e.preventDefault();
                    window.__wbRedo();
                }
            });
        })();
    }

    window.WBEditorKeyboard = { install: install };
    if (document.readyState !== 'loading') {
        install();
    } else {
        document.addEventListener('DOMContentLoaded', install, { once: true });
    }
})();
