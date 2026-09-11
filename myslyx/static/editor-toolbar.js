// Toolbar helpers: enable/disable buttons for read-only files and focus an
// input inside a dialog. Extracted from inline run_javascript snippets.
(function() {
    'use strict';

    window.WBSetReadonly = {
        // Disable rename/delete/undo/redo while a read-only file is shown.
        apply: function(readonly) {
            try {
                ['wb-rename-btn', 'wb-delete-btn', 'wb-undo-btn', 'wb-redo-btn']
                    .forEach(function(id) {
                        var b = document.getElementById(id);
                        if (b) b.disabled = readonly;
                    });
            } catch (e) {}
        }
    };

    window.WBFocusInput = {
        // Focus the first <input> of the element with the given id.
        focus: function(elId) {
            setTimeout(function() {
                try {
                    var el = document.getElementById(elId);
                    if (el) {
                        var inp = el.querySelector('input');
                        if (inp) inp.focus();
                    }
                } catch (e) {}
            }, 50);
        }
    };
})();