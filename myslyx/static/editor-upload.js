// Browser-side file-picker flow for importing documents into the editor.
// Kept outside the Python page so the upload logic stays editable as plain JS.
(function() {
    function run() {
        (function() {
            const inp = document.createElement('input');
            inp.type = 'file';
            inp.accept = '*/*';
            inp.onchange = function(ev) {
                const f = ev.target.files[0];
                if (!f) return;
                const reader = new FileReader();
                reader.onload = function(e) {
                    try {
                        var lang = 'Text';
                        var n = (f.name || '').toLowerCase();
                        if (n.endsWith('.bas')) lang = 'HitBasic';
                        else if (n.endsWith('.pas') || n.endsWith('.pp') || n.endsWith('.inc')) lang = 'Pascal';
                        else if (n.endsWith('.c') || n.endsWith('.h')) lang = 'C';
                        else if (n.endsWith('.asm') || n.endsWith('.s') || n.endsWith('.z80')) lang = 'Z80';
                        window.__wbPendingFile = { name: f.name, language: lang, content: e.target.result, export_symbols: true };
                        const br = document.getElementById('wb-open-bridge');
                        if (br) br.dispatchEvent(new CustomEvent('wb-open-file', { detail: {} }));
                        try { alert('Imported: ' + f.name); } catch(_) { console.log('Imported', f.name); }
                    } catch(err) { console.error(err); }
                };
                reader.readAsText(f);
            };
            inp.click();
        })();
    }

    window.WBFileImport = { run: run };
})();
