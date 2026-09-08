// Myslyx Text Editor - file-stats plugin module.
// Shows live character / word / line counts for the active file, stacked
// under its name in the top toolbar. Fully client-side: the counts are
// recomputed from the active CodeMirror document on every edit and whenever
// the active file changes (the server dispatches 'wb-active-editor' on
// switch/load/rename). The display slot is a plain-DOM column the module
// injects around the existing #wb-file-name label, so no page code changes.
//
// Counts follow plain-text conventions:
//   chars  -> length of the document text
//   words  -> whitespace-separated tokens in the (trimmed) text
//   lines  -> one per trailing-newline-terminated line (N+1 over '\n')

export default function fileStats(CM) {
    const { ViewPlugin } = CM;

    // Create (once) the toolbar slot: a flex column holding the existing
    // filename label on top and the counts node underneath.
    function ensureSlot() {
        const nameEl = document.getElementById('wb-file-name');
        if (!nameEl) return null;
        if (nameEl._wbFileStatsNode) return nameEl._wbFileStatsNode;

        const col = document.createElement('div');
        col.style.display = 'flex';
        col.style.flexDirection = 'column';
        col.style.justifyContent = 'center';
        col.style.gap = '4px';
        col.style.marginLeft = '12px';

        // The label keeps its own margin otherwise, misaligning the counts.
        nameEl.style.marginLeft = '0px';

        const counts = document.createElement('div');
        counts.id = 'wb-file-counts';
        counts.style.fontFamily = 'var(--wb-font, monospace)';
        counts.style.fontSize = '12px';
        counts.style.color = 'var(--wb-text, #888)';
        counts.textContent = '';

        nameEl.parentNode.insertBefore(col, nameEl);
        col.appendChild(nameEl);
        col.appendChild(counts);

        nameEl._wbFileStatsNode = counts;
        return counts;
    }

    function countText(text) {
        const chars = text.length;
        const words = text.trim() ? text.trim().split(/\s+/).length : 0;
        const lines = text ? text.split('\n').length : 0;
        return chars + ' chars \u00b7 ' + words + ' words \u00b7 ' + lines + ' lines';
    }

    function render(node, text) {
        node.textContent = text ? countText(text) : '';
    }

    // Global refresh: recompute from the ACTIVE editor's document. Reads the
    // view through the same editor-id bridge the runtime uses, so file
    // switches pick up that file's counts even before it is edited.
    if (!window._wbFileStatsRefresh) {
        window._wbFileStatsRefresh = function() {
            try {
                const node = ensureSlot();
                if (!node) return;
                const elId = window.__wbEditorId;
                if (!elId) {
                    render(node, '');
                    return;
                }
                const el = window.getElement ? window.getElement(elId) : null;
                if (!el || !el.editorPromise) return;
                el.editorPromise.then(function(view) {
                    try { render(node, view.state.doc.toString()); } catch(e) {}
                });
            } catch(e) {}
        };
        window.addEventListener('wb-active-editor', function() {
            try { window._wbFileStatsRefresh(); } catch(e) {}
        });
        // Cover the very first activation (fires before this module attaches).
        try { window._wbFileStatsRefresh(); } catch(e) {}
    }

    // Per-view listener: keep counts in sync while the user types.
    return ViewPlugin.fromClass(class {
        update(update) {
            if (!update.docChanged) return;
            try {
                const node = ensureSlot();
                if (node) render(node, update.state.doc.toString());
            } catch(e) {}
        }
    });
}
