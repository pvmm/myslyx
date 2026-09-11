// Toolbar helpers: enable/disable buttons for read-only files and focus an
// input inside a dialog. Extracted from inline run_javascript snippets.
(function() {
    'use strict';

    window.WBSetReadonly = {
        // Disable rename/delete/undo/redo (and lock the LANG combo) while a
        // read-only file is shown.
        apply: function(readonly) {
            try {
                ['wb-rename-btn', 'wb-delete-btn', 'wb-undo-btn', 'wb-redo-btn']
                    .forEach(function(id) {
                        var b = document.getElementById(id);
                        if (b) b.disabled = readonly;
                    });
                // The LANG combo must not change a read-only file's language. A CSS
                // pointer-events: none rule on the whole field (WBSetReadonly
                // adds .wb-locked to the .wb-select root) blocks the mouse —
                // Quasar's control forces pointer-events: auto, hence the
                // !important in retro.css — and a capture keydown handler
                // blocks the keyboard (Enter/Arrows/Space all open the
                // selection popup in Quasar).
                // Note: props('id=wb-lang-select') lands on the inner
                // .q-field__native, so the .wb-locked class must go on that
                // native AND its .wb-select field root.
                var native = document.getElementById('wb-lang-select');
                var sel = native ? native.closest('.wb-select') : null;
                if (sel) {
                    if (readonly) {
                        sel.classList.add('wb-locked');
                        if (native) native.classList.add('wb-locked');
                        if (!sel._wbLangLockKey) {
                            sel._wbLangLockKey = function(e) {
                                if (e.key === 'Enter' || e.key === 'ArrowDown' ||
                                    e.key === 'ArrowUp' || e.key === ' ') {
                                    e.preventDefault();
                                    e.stopPropagation();
                                }
                            };
                            sel.addEventListener('keydown', sel._wbLangLockKey, true);
                        }
                    } else {
                        sel.classList.remove('wb-locked');
                        if (native) native.classList.remove('wb-locked');
                        if (sel._wbLangLockKey) {
                            sel.removeEventListener('keydown', sel._wbLangLockKey, true);
                            sel._wbLangLockKey = null;
                        }
                    }
                }
            } catch (e) {}
        }
    };

    window.WBFocusInput = {
        // Focus the first <input> of the element with the given id.
        // Quasar consumes an 'id' prop on QInput as the datalist id
        // (list="<id>-datalist"), so the id itself is never an element:
        // fall back to the <input> that references that datalist.
        focus: function(elId) {
            setTimeout(function() {
                try {
                    var el = document.getElementById(elId);
                    var inp = el ? el.querySelector('input') : null;
                    if (!inp) inp = document.querySelector('[list="' + elId + '-datalist"]');
                    if (inp) inp.focus();
                } catch (e) {}
            }, 50);
        }
    };
})();