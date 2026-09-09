// Myslyx Text Editor - localStorage persistence & editor helpers
(function() {
    'use strict';

    const STORAGE_KEY = 'wb_editor_files';
    const ACTIVE_KEY = 'wb_editor_active';

    // ===== File Pool Management via localStorage =====

    window.WBStorage = {
        loadFiles: function() {
            try {
                const raw = localStorage.getItem(STORAGE_KEY);
                if (raw) return JSON.parse(raw);
            } catch(e) {
                console.warn('WBStorage: failed to load files', e);
            }
            return null;
        },

        saveFiles: function(files) {
            try {
                localStorage.setItem(STORAGE_KEY, JSON.stringify(files));
            } catch(e) {
                console.warn('WBStorage: failed to save files', e);
            }
        },

        loadActive: function() {
            return localStorage.getItem(ACTIVE_KEY) || null;
        },

        saveActive: function(id) {
            localStorage.setItem(ACTIVE_KEY, id);
        },

        clear: function() {
            localStorage.removeItem(STORAGE_KEY);
            localStorage.removeItem(ACTIVE_KEY);
        },

        generateId: function() {
            return 'file_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
        }
    };

    // ===== Default starter files =====

    window.WBDefaults = {
        createStarterFiles: function() {
            return [
                {
                    id: WBStorage.generateId(),
                    name: 'hello.bas',
                    language: 'HitBasic',
                    content: [
                        '10 REM Welcome to Myslyx Text Editor',
                        '20 CLS',
                        '30 INPUT "What is your name? "; N$',
                        '40 PRINT "Hello, "; N$',
                        '50 PRINT "Welcome to Myslyx Text."',
                        '60 FOR I = 1 TO 3',
                        '70   SOUND 1, (9 - I) * 100 + 440',
                        '80   FOR J = 1 TO 1000: NEXT J',
                        '90 NEXT I',
                        '100 END'
                    ].join('\n')
                },
                {
                    id: WBStorage.generateId(),
                    name: 'notes.txt',
                    language: 'Text',
                    content: [
                        '=== Myslyx Text Editor ===',
                        '',
                        'Features:',
                        '  - Multiple files in memory',
                        '  - BASIC syntax highlighting',
                        '  - Autocomplete hints',
                        '  - Context tips panel',
                        '',
                        'Files persist in browser localStorage.',
                        'Switch files using the dock at the bottom.',
                    ].join('\n')
                }
            ];
        }
    };

    // ===== Language-specific hint data =====
    // ===== Language-specific hint data (loaded from /static/hints/*.json) =====

    window.WBHints = {
        _cache: {},

        // Fetch a hint dictionary once and cache it. Unknown languages fall
        // back to an empty plain-text structure.
        get: function(key) {
            key = key || 'plaintext';
            if (this._cache[key]) return Promise.resolve(this._cache[key]);
            var self = this;
            return fetch('/static/hints/' + key + '.json', { cache: 'no-cache' })
                .then(function(r) {
                    if (!r.ok) return { keywords: [], builtins: [], tips: {}, patterns: [] };
                    return r.json();
                })
                .then(function(data) {
                    self._cache[key] = data;
                    return data;
                })
                .catch(function() {
                    return { keywords: [], builtins: [], tips: {}, patterns: [] };
                });
        }
    };

    // ===== User-defined symbol persistence (discovered functions/subroutines) =====

    var SYMBOLS_KEY = 'wb_editor_symbols';

    window.WBStorage.loadSymbols = function() {
        try {
            var raw = localStorage.getItem(SYMBOLS_KEY);
            return raw ? JSON.parse(raw) : {};
        } catch(e) {
            console.warn('WBStorage: failed to load symbols', e);
            return {};
        }
    };

    window.WBStorage.saveSymbols = function(map) {
        try {
            localStorage.setItem(SYMBOLS_KEY, JSON.stringify(map));
        } catch(e) {
            console.warn('WBStorage: failed to save symbols', e);
        }
    };

    // Remove persisted symbols for a given file id.
    window.__wbPruneSymbols = function(fid) {
        if (!fid) return;
        try {
            var symbols = WBStorage.loadSymbols();
            if (symbols[fid]) {
                delete symbols[fid];
                WBStorage.saveSymbols(symbols);
            }
        } catch(e) {}
    };

    // ===== Common configuration (UI preferences stored together) =====

    var CONFIG_KEY = 'wb_editor_config';

    window.WBStorage.loadConfig = function() {
        try {
            return JSON.parse(localStorage.getItem(CONFIG_KEY) || '{}');
        } catch(e) {
            console.warn('WBStorage: failed to load config', e);
            return {};
        }
    };

    window.WBStorage.saveConfig = function(cfg) {
        try {
            localStorage.setItem(CONFIG_KEY, JSON.stringify(cfg));
        } catch(e) {
            console.warn('WBStorage: failed to save config', e);
        }
    };

    // ===== Resizable hints sidebar =====

    function setupHintsResizer() {
        var resizer = document.getElementById('wb-hints-resizer');
        var sidebar = document.querySelector('.wb-hints-sidebar');
        var main = document.querySelector('.wb-main-area');
        if (!resizer || !sidebar || !main) return false;

        // Restore a previously saved width (the editor flexes to fill the rest).
        var cfg = WBStorage.loadConfig();
        var saved = parseInt(cfg.hints_width, 10);
        if (saved && saved >= 120) sidebar.style.width = saved + 'px';

        var startX = 0;
        var startW = 0;
        resizer.addEventListener('mousedown', function(e) {
            e.preventDefault();
            startX = e.clientX;
            startW = sidebar.getBoundingClientRect().width;
            document.body.classList.add('wb-resizing');
            window.addEventListener('mousemove', onMove);
            window.addEventListener('mouseup', onUp);
        });

        function onMove(ev) {
            var dw = startX - ev.clientX; // dragging left shrinks the sidebar
            var rect = main.getBoundingClientRect();
            var w = Math.max(120, Math.min(Math.round(rect.width * 0.75), Math.round(startW + dw)));
            sidebar.style.width = w + 'px';
        }

        function onUp() {
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
            document.body.classList.remove('wb-resizing');
            var cfg = WBStorage.loadConfig();
            cfg.hints_width = Math.round(sidebar.getBoundingClientRect().width);
            WBStorage.saveConfig(cfg);
        }

        resizer._wbResizer = true;
        return true;
    }

    function attachResizerWithRetry() {
        var attempts = 0;
        var iv = setInterval(function() {
            if (setupHintsResizer() || ++attempts > 50) clearInterval(iv);
        }, 200);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', attachResizerWithRetry);
    } else {
        attachResizerWithRetry();
    }

})();
