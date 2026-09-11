// Global toolbar/file-pool shortcuts handled at the document level.
// All use Ctrl+Alt (or Cmd+Alt) combos chosen to not collide with CodeMirror
// or the browser: EXPORT SYMBOLS, RENAME, UPLOAD, DOWNLOAD, DELETE, + NEW and
// cycling through the open files in the file pool.
(function() {
    'use strict';

    var installed = false;

    function install() {
        if (installed) return;
        installed = true;

        document.addEventListener('keydown', function(e) {
            var mod = e.ctrlKey || e.metaKey;
            if (!mod || !e.altKey) return;
            var key = e.key.toLowerCase();

            // Toolbar actions dispatch a real click on the corresponding
            // button so the server-side handlers (and their read-only guards)
            // keep working unchanged.
            var byKey = {
                'e': '#wb-export-btn',
                'r': '#wb-rename-btn',
                'u': '#wb-upload-btn',
                'd': '#wb-download-btn',
                'x': '#wb-delete-btn',
                'n': '#wb-new-file-btn'
            };
            if (byKey[key]) {
                e.preventDefault();
                clickSel(byKey[key]);
                return;
            }
            if (key === '[' || key === ']') {
                e.preventDefault();
                movePool(key === ']' ? 1 : -1);
            }
        });
    }

    function clickSel(sel) {
        var el = document.querySelector(sel);
        if (el && !el.disabled && el.click) el.click();
    }

    // Move to the previous([) / next(]) open file in the dock.
    function movePool(delta) {
        var tabs = document.querySelectorAll('.wb-file-tab');
        if (!tabs.length) return;
        var active = document.querySelector('.wb-file-tab.active');
        var idx = Array.prototype.indexOf.call(tabs, active);
        var start = idx < 0 ? (delta > 0 ? -1 : 0) : idx;
        var next = (((start + delta) % tabs.length) + tabs.length) % tabs.length;
        var tab = tabs[next];
        if (tab && tab.click) tab.click();
    }

    window.WBShortcuts = { install: install };
    if (document.readyState !== 'loading') {
        install();
    } else {
        document.addEventListener('DOMContentLoaded', install, { once: true });
    }
})();