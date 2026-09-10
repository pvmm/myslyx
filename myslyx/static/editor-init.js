// Editor bootstrap and storage initialization.
// This script sets up the persistent file pool and drag-and-drop bindings.
(function() {
    function run() {
        (function() {
            // Shared map of file id -> CodeMirror element id, created before
            // any editor is registered by the server.
            window.__wbEditorIds = window.__wbEditorIds || {};
            try {
                const SCHEMA_KEY = 'wb_editor_schema_v';
                const SCHEMA_VERSION = '2';

                // If the URL contains ?reset=1, wipe storage and caches, then reload the whole app.
                try {
                    const params = new URLSearchParams(window.location.search || '');
                    if (params.get('reset') === '1') {
                        try {
                            ['wb_editor_files', 'wb_editor_active', 'wb_editor_schema_v',
                             'wb_editor_font', 'wb_editor_font_size']
                                .forEach(k => localStorage.removeItem(k));
                        } catch(e) {}
                        localStorage.setItem(SCHEMA_KEY, SCHEMA_VERSION);
                        var reloadNow = function() {
                            try {
                                const url = new URL(window.location.href);
                                url.searchParams.delete('reset');
                                url.searchParams.set('r', String(Date.now()));
                                window.history.replaceState({}, '', url.toString());
                            } catch(e) {}
                            window.location.reload();
                        };
                        try {
                            if (window.caches && window.caches.keys) {
                                window.caches.keys().then(function(names) {
                                    var deletes = names.map(function(n) {
                                        return window.caches.delete(n).catch(function() {});
                                    });
                                    Promise.all(deletes).then(reloadNow).catch(reloadNow);
                                }).catch(reloadNow);
                            } else {
                                reloadNow();
                            }
                        } catch(e) { reloadNow(); }
                        return;
                    }
                    try {
                        if (params.get('r')) {
                            const url = new URL(window.location.href);
                            url.searchParams.delete('r');
                            window.history.replaceState({}, '', url.toString());
                        }
                    } catch(e) {}
                } catch(e) {}

                // Ensure the schema marker is set, but do NOT pre-seed the
                // file pool here.  Empty storage is left alone: once the page
                // connects, the server pushes the pool back through the
                // storage sync bridge and installs the read-only STARTUP
                // starter when there are no files.  Pre-seeding here made
                // every reload (e.g. toggling a plugin in the Settings menu)
                // report the client defaults, and following that up by
                // overwriting the pool wiped the user's files with a starter.
                if (localStorage.getItem(SCHEMA_KEY) !== SCHEMA_VERSION) {
                    localStorage.setItem(SCHEMA_KEY, SCHEMA_VERSION);
                }
            } catch(e) {}

            // The file pool is synced to the server via the storage sync
            // bridge once the page connects.

            function importFile(file, content, lang) {
                try {
                    window.__wbPendingFile = { name: file.name, language: lang, content: content, export_symbols: true };
                    const br = document.getElementById('wb-open-bridge');
                    if (br) br.dispatchEvent(new CustomEvent('wb-open-file', { detail: {} }));
                } catch(e) { console.warn('importFile error', e); }
            }

            document.addEventListener('dragover', function(e){ try{ e.preventDefault(); }catch(e){} }, false);
            document.addEventListener('drop', function(e){
                try {
                    e.preventDefault();
                    const items = e.dataTransfer && e.dataTransfer.files ? e.dataTransfer.files : null;
                    if (!items || items.length === 0) return;
                    for (let i=0;i<items.length;i++) {
                        const f = items[i];
                        (function(file){
                            const reader = new FileReader();
                            reader.onload = function(ev) {
                                try {
                                    var lang = 'Text';
                                    var n = (file.name || '').toLowerCase();
                                    if (n.endsWith('.bas')) lang='HitBasic';
                                    else if (n.endsWith('.pas') || n.endsWith('.pp') || n.endsWith('.inc')) lang='Pascal';
                                    else if (n.endsWith('.c') || n.endsWith('.h')) lang='C';
                                    else if (n.endsWith('.asm') || n.endsWith('.s') || n.endsWith('.z80')) lang='Z80';
                                    importFile(file, ev.target.result, lang);
                                } catch(e) { console.error(e); }
                            };
                            reader.readAsText(file);
                        })(f);
                    }
                } catch(e) { console.warn('drop handler error', e); }
            }, false);
        })();
    }

    window.WBEditorBoot = { run: run };
    if (document.readyState !== 'loading') {
        run();
    } else {
        document.addEventListener('DOMContentLoaded', run, { once: true });
    }
})();
