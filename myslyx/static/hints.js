// Myslyx Text Editor - hints sidebar, autocomplete popup and user-symbol scanner.
// Data comes from /static/hints/<key>.json (see WBHints.get in retro.js) and the
// current editor language key + active file id come from server-set globals
// window.__wbHintKey / window.__wbActiveFid.
(function() {
    'use strict';

    var HINTS_CONTENT_ID = 'hints-content';

    // ===== Markdown rendering =====

    function renderMarkdown(text) {
        if (!text) return '';
        try {
            // breaks:true keeps the previous single-newline -> line-break look
            // when migrating the plain-text tips that used '\n'.
            return window.marked.parse(text, { breaks: true });
        } catch(e) {
            return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                       .replace(/\n/g, '<br>');
        }
    }

    // ===== Editor view resolution =====

    var view = null;
    var scanTimer = null;
    var completeTimer = null;
    var panelToken = 0;

    function getActiveFid() {
        return window.__wbActiveFid || null;
    }

    function getHintKey() {
        return window.__wbHintKey || 'plaintext';
    }

    // ===== User symbol scanning (language-aware) =====

    // Maps the CodeMirror language name to a scanner key.
    function getScannerKey() {
        var lang = (window.__wbCurrentLang || '').toUpperCase();
        if (lang === 'PASCAL') return 'pascal';
        if (lang === 'C') return 'c';
        if (lang === 'Z80') return 'asm';
        return 'basic';
    }

    function lineNumberAt(text, index) {
        var line = 1;
        for (var i = 0; i < index; i++) { if (text[i] === '\n') line++; }
        return line;
    }

    function getWord(state, pos) {
        var line = state.doc.lineAt(pos);
        var lineText = line.text;
        var col = pos - line.from;
        var end = col;
        while (end < lineText.length && /[A-Za-z0-9_$%!&]/.test(lineText[end])) end++;
        var start = col;
        while (start > 0 && /[A-Za-z0-9_$%!&]/.test(lineText[start - 1])) start--;
        return { word: lineText.slice(start, end), start: start, line: line, lineText: lineText };
    }

    // ===== User symbol scanning (FUNCTION / SUB / DEF FN / PROCEDURE / labels) =====

    function scanSymbols(viewImpl, fid) {
        if (!fid) return [];
        var text = viewImpl.state.doc.toString();
        var key = getScannerKey();
        var found = [];
        var m;

        function add(name, kind, index) {
            found.push({ name: name.toUpperCase(), kind: kind, line: lineNumberAt(text, index), file: fid });
        }

        if (key === 'pascal') {
            // Pascal: FUNCTION name / PROCEDURE name
            var reP = /(?:FUNCTION|PROCEDURE)\s+([A-Za-z_][A-Za-z0-9_]*)/gi;
            while ((m = reP.exec(text)) !== null) {
                var pw = m[0].toUpperCase();
                add(m[1], pw.indexOf('FUNCTION') === 0 ? 'function' : 'procedure', m.index);
            }
        } else if (key === 'c') {
            // C: type name(args) {  (function/definition, not prototype/control keywords)
            var reC = /(?:^|[^A-Za-z0-9_])(?:(?:const|static|inline|extern|volatile|unsigned|signed|long|short|register)\s+)*(?:void|int|char|float|double|bool|size_t)\s+[*\s]*([A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*\{/g;
            while ((m = reC.exec(text)) !== null) {
                add(m[1], 'function', m.index + m[0].indexOf(m[1]));
            }
        } else if (key === 'asm') {
            // Assembly labels: a name at the start of a line ending with ':'
            var lines = text.split('\n');
            var offset = 0;
            for (var li = 0; li < lines.length; li++) {
                var lm = lines[li].match(/^\s*([A-Za-z_@][A-Za-z0-9_@?]*)\s*:/);
                if (lm && lm[1]) {
                    add(lm[1], 'label', offset + lines[li].indexOf(lm[1]));
                }
                offset += lines[li].length + 1;
            }
        } else {
            // Basic (HitBasic/VBScript): FUNCTION name / SUB name / DEF FN name
            var reB = /(?:FUNCTION|SUB|DEF\s+FN)\s+([A-Za-z][A-Za-z0-9_$%!&]*)/gi;
            while ((m = reB.exec(text)) !== null) {
                var kw = m[0].toUpperCase();
                var kind = kw.indexOf('FUNCTION') === 0 ? 'function'
                        : (kw.indexOf('SUB') === 0 ? 'sub' : 'fn');
                add(m[1], kind, m.index);
            }
        }

        var symbols = WBStorage.loadSymbols() || {};
        symbols[fid] = found;
        WBStorage.saveSymbols(symbols);
        return found;
    }

    function getAllSymbols() {
        var symbols = WBStorage.loadSymbols() || {};
        var files = WBStorage.loadFiles() || [];
        var namesById = {};
        var exportById = {};
        files.forEach(function(f) {
            namesById[f.id] = f.name;
            exportById[f.id] = f.export_symbols !== false;
        });
        var activeFid = getActiveFid();
        var out = [];
        Object.keys(symbols).forEach(function(fid) {
            // A file with global export disabled only makes its symbols
            // available while that file is the one being edited.
            if (exportById[fid] !== false) {
                (symbols[fid] || []).forEach(function(s) {
                    out.push({ name: s.name, kind: s.kind, line: s.line, file: namesById[fid] || fid });
                });
            } else if (fid === activeFid) {
                (symbols[fid] || []).forEach(function(s) {
                    out.push({ name: s.name, kind: s.kind, line: s.line, file: namesById[fid] || fid });
                });
            }
        });
        return out;
    }

    function findSymbol(word, symbols) {
        var upper = word.toUpperCase();
        var found = null;
        symbols.forEach(function(s) {
            if (s.name === upper && !found) found = s;
        });
        return found;
    }

    // ===== Hints sidebar =====

    function updateHintsPanel(force) {
        var hintsEl = document.getElementById(HINTS_CONTENT_ID);
        if (!hintsEl || !view) return;

        var state = view.state;
        var sel = state.selection.main;
        var wordInfo = getWord(state, sel.head);
        var word = wordInfo.word;
        var token = ++panelToken;

        if (!word) {
            // Keep the last hint visible instead of blanking the panel.
            return;
        }

        WBHints.get(getHintKey()).then(function(hints) {
            if (token !== panelToken) return; // a newer update superseded us
            renderPanel(hintsEl, word, hints);
        });
    }

    function renderPanel(hintsEl, word, hints) {
        var upper = word.toUpperCase();

        // 1. Curated tip (markdown). Match case-insensitively.
        var tip = null;
        if (hints.tips) {
            tip = hints.tips[upper];
            if (!tip) {
                var keys = Object.keys(hints.tips);
                for (var i = 0; i < keys.length; i++) {
                    if (keys[i].toUpperCase() === upper) { tip = hints.tips[keys[i]]; break; }
                }
            }
        }
        if (tip) {
            hintsEl.innerHTML =
                '<div class="hint-title">' + upper + '</div>' +
                '<div class="hint-text">' + renderMarkdown(tip) + '</div>';
            return;
        }

        // 2. User-defined function/subroutine.
        var symbol = findSymbol(word, getAllSymbols());
        if (symbol) {
            hintsEl.innerHTML =
                '<div class="hint-title">' + upper + '</div>' +
                '<div class="hint-text">You defined this here:<br>' +
                '&nbsp;&nbsp;<span class="hint-code">' + symbol.file + '</span> line ' + symbol.line +
                ' (<span class="hint-code">' + symbol.kind + '</span>)</div>';
            return;
        }

        // 3. Pattern-based tip.
        if (hints.patterns) {
            var state = view.state;
            var line = state.doc.lineAt(state.selection.main.head).text;
            for (var p = 0; p < hints.patterns.length; p++) {
                try {
                    var re = new RegExp(hints.patterns[p].re);
                    if (line.match(re)) {
                        hintsEl.innerHTML =
                            '<div class="hint-title">' + upper + '</div>' +
                            '<div class="hint-text">' + renderMarkdown(hints.patterns[p].tip) + '</div>';
                        return;
                    }
                } catch(e) {}
            }
        }

        // 4. Known keyword / builtin.
        var known = (hints.keywords || []).some(function(k) { return k.toUpperCase() === upper; });
        if (known) {
            hintsEl.innerHTML =
                '<div class="hint-title">' + upper + '</div>' +
                '<div class="hint-text">' + upper + ' is a language keyword.</div>';
            return;
        }
        var builtin = (hints.builtins || []).some(function(b) { return b.toUpperCase() === upper; });
        if (builtin) {
            hintsEl.innerHTML =
                '<div class="hint-title">' + upper + '</div>' +
                '<div class="hint-text">' + upper + ' is a builtin function/object.</div>';
            return;
        }

        // 5. No hint found — keep the last displayed hint unchanged.
    }

    // ===== Autocomplete popup =====

    var popup = null;
    var popupItems = [];
    var popupIndex = 0;

    function removePopup() {
        if (popup) { popup.remove(); popup = null; }
        popupItems = [];
        popupIndex = 0;
    }

    function isReadonly() {
        return !!window.__wbActiveReadonly;
    }

    function showPopup(matches, pos) {
        removePopup();
        if (matches.length === 0 || isReadonly()) return;

        popup = document.createElement('div');
        popup.className = 'wb-autocomplete-popup';
        popup.style.cssText =
            'position:fixed;z-index:10000;background:#fff;border:2px solid #000;' +
            'box-shadow:inset 1px 1px 0 #555,3px 3px 0 rgba(0,0,0,0.3);' +
            'font-family:"Press Start 2P",monospace;font-size:9px;max-height:180px;' +
            'overflow-y:auto;min-width:160px;';

        matches.forEach(function(m, i) {
            var item = document.createElement('div');
            item.style.cssText =
                'padding:5px 8px;cursor:pointer;display:flex;justify-content:space-between;gap:12px;';
            if (i === 0) { item.style.background = '#0055aa'; item.style.color = '#fff'; }
            var label = document.createElement('span');
            label.textContent = m.label;
            var kind = document.createElement('span');
            kind.textContent = m.detail || '';
            kind.style.opacity = '0.6';
            kind.style.fontSize = '7px';
            item.appendChild(label);
            item.appendChild(kind);
            item.addEventListener('mouseenter', function() {
                popupItems.forEach(function(p) { p.style.background = ''; p.style.color = ''; });
                item.style.background = '#0055aa';
                item.style.color = '#fff';
                popupIndex = i;
            });
            item.addEventListener('click', function() {
                insertCompletion(matches[i]);
            });
            popup.appendChild(item);
            popupItems.push(item);
        });

        document.body.appendChild(popup);
        var coords = view.coordsAtPos(pos);
        if (coords) {
            popup.style.left = coords.left + 'px';
            popup.style.top = (coords.bottom + 4) + 'px';
        }
        popupIndex = 0;
    }

    function insertCompletion(match) {
        if (isReadonly()) { removePopup(); return; }
        var state = view.state;
        var sel = state.selection.main;
        var wordInfo = getWord(state, sel.head);
        var from = wordInfo.line.from + wordInfo.start;
        var to = sel.head;
        view.dispatch({
            changes: { from: from, to: to, insert: match.label },
            selection: { anchor: from + match.label.length }
        });
        removePopup();
        view.focus();
    }

    function movePopup(dir) {
        if (popupItems.length === 0) return;
        popupItems[popupIndex].style.background = '';
        popupItems[popupIndex].style.color = '';
        popupIndex = (popupIndex + dir + popupItems.length) % popupItems.length;
        popupItems[popupIndex].style.background = '#0055aa';
        popupItems[popupIndex].style.color = '#fff';
        popupItems[popupIndex].scrollIntoView({ block: 'nearest' });
    }

    function getCompletions(word, hints) {
        if (!hints || !word) return [];
        var lower = word.toLowerCase();
        var seen = {};
        var out = [];
        function push(name, detail) {
            var up = name.toUpperCase();
            if (!(up in seen) && name.toLowerCase() !== lower) {
                seen[up] = true;
                out.push({ label: name, detail: detail });
            }
        }
        (hints.keywords || []).forEach(function(k) { push(k, 'keyword'); });
        (hints.builtins || []).forEach(function(b) { push(b, 'builtin'); });
        getAllSymbols().forEach(function(s) { push(s.name, s.kind); });
        return out.filter(function(m) {
            return m.label.toLowerCase().indexOf(lower) === 0;
        }).slice(0, 12);
    }

    function checkCompletions() {
        if (!view || isReadonly()) { removePopup(); return; }
        var state = view.state;
        var wordInfo = getWord(state, state.selection.main.head);
        var word = wordInfo.word;
        if (!word) { removePopup(); return; }

        WBHints.get(getHintKey()).then(function(hints) {
            if (!view) return;
            var matches = getCompletions(word, hints);
            if (matches.length > 0) {
                showPopup(matches, wordInfo.line.from + wordInfo.start);
            } else {
                removePopup();
            }
        });
    }

    // ===== Wiring =====

    function scheduleScan() {
        clearTimeout(scanTimer);
        scanTimer = setTimeout(function() {
            scanSymbols(view, getActiveFid());
            updateHintsPanel(true);
        }, 250);
    }

    function scheduleCompletions() {
        clearTimeout(completeTimer);
        completeTimer = setTimeout(checkCompletions, 80);
    }

    function activateView(v) {
        var active = v;
        view = active;
        if (!active._wbHintHooked) {
            active._wbHintHooked = true;

            import('nicegui-codemirror').then(function(CM) {
                if (!active) return;
                active.dispatch({
                    effects: CM.StateEffect.appendConfig.of([
                        CM.EditorView.updateListener.of(function(update) {
                            if (update.docChanged) {
                                scheduleScan();
                                scheduleCompletions();
                            }
                            if (update.selectionSet) {
                                updateHintsPanel(true);
                            }
                        })
                    ])
                });

                // Keyboard navigation for the popup, and close on blur.
                active.contentDOM.addEventListener('keydown', function(e) {
                    if (!popup) return;
                    if (e.key === 'ArrowDown') { e.preventDefault(); movePopup(1); }
                    else if (e.key === 'ArrowUp') { e.preventDefault(); movePopup(-1); }
                    else if (e.key === 'Enter' || e.key === 'Tab') {
                        if (popupItems.length > 0) { e.preventDefault(); insertCompletion(popupItems[popupIndex]); }
                    } else if (e.key === 'Escape') { removePopup(); }
                });
                active.contentDOM.addEventListener('blur', function() {
                    setTimeout(removePopup, 150);
                });
            });
        }
        // Re-scan + refresh the panel on every activation (the view's own
        // updateListener covers edits and cursor moves afterwards).
        scanSymbols(active, getActiveFid());
        updateHintsPanel(true);
    }

    function tryHook() {
        var elId = window.__wbEditorId;
        if (!elId) return false;
        var el = window.getElement ? window.getElement(elId) : null;
        if (!el || !el.editorPromise) return false;
        el.editorPromise.then(activateView);
        return true;
    }

    // Re-bind whenever the server activates a (possibly new) editor.
    window.addEventListener('wb-active-editor', function() {
        try {
            removePopup();
            tryHook();
        } catch(e) {}
    });

    // Fallback poll for the very first editor at load time.
    var attempts = 0;
    var iv = setInterval(function() {
        if (tryHook() || ++attempts > 100) clearInterval(iv);
    }, 200);
})();