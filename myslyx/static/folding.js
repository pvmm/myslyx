// Myslyx Text Editor - keyword-based code folding.
//
// The bundled stream parsers (HitBasic, Pascal, C, Z80) produce no Lezer
// tree, so CodeMirror's tree-based folding never finds anything to fold.
// This module registers a foldService provider that recognises block
// keywords per language and returns native fold ranges, which the regular
// fold gutter and fold keys then act on. Z80 and plain text have no block
// structure and stay unfoldable.
//
// The provider answers two kinds of queries:
//  - the line itself opens a block          -> scan forward for the closer
//  - the line sits inside a block           -> scan backward for the
//    innermost enclosing opener, then forward for its closer (this is what
//    lets the Ctrl-Shift-[ / ] fold keys work from anywhere in a body,
//    exactly like tree-based folding does).
//
// Folding is obligatory: this provider is installed into every editor view
// like static/plugins.js does, but it is not itself a plugin and cannot be
// disabled from Settings > PLUGINS.
(function() {
    'use strict';

    var CM_NS = null;
    var MAX_SCAN_LINES = 2000;

    // --- HitBasic (VBScript-style) block keywords ---------------------------

    var HB_OPEN = ['IF', 'FOR', 'DO', 'WHILE', 'SELECT', 'SUB', 'FUNCTION', 'CLASS', 'PROPERTY', 'WITH'];
    var HB_MIDDLE = ['ELSE', 'ELSEIF', 'CASE', 'UNTIL'];
    var HB_END_FAMILY = ['IF', 'SUB', 'FUNCTION', 'CLASS', 'SELECT', 'PROPERTY', 'WITH', 'TYPE'];
    var HB_NAME_RE = /[ \t]*(?:[0-9]+[ \t]*)?([A-Za-z][A-Za-z0-9]*)/;

    function hbToken(lineText) {
        var m = HB_NAME_RE.exec(lineText);
        if (!m) return null;
        var w1 = m[1].toUpperCase();
        var word = lineText.slice(m[0].length);
        var m2 = /[ \t]*([A-Za-z][A-Za-z0-9]*)/.exec(word);
        var w2 = m2 ? m2[1].toUpperCase() : null;
        if (HB_MIDDLE.indexOf(w1) >= 0) return { middle: true };
        if (HB_OPEN.indexOf(w1) >= 0) return { open: w1 };
        if (w1 === 'NEXT') return { close: 'FOR' };
        if (w1 === 'LOOP') return { close: 'DO' };
        if (w1 === 'WEND') return { close: 'WHILE' };
        if (w1 === 'ENDIF') return { close: 'IF' };
        if (w1 === 'END' && w2 && HB_END_FAMILY.indexOf(w2) >= 0) return { close: w2 };
        return null;
    }

    // --- Pascal ---------------------------------------------------------------

    var PA_RE = /[ \t]*([A-Za-z][A-Za-z0-9]*)/;

    function paToken(lineText) {
        var m = PA_RE.exec(lineText);
        if (!m) return null;
        var w = m[1].toUpperCase();
        if (w === 'BEGIN') return { open: 'BEGIN' };
        if (w === 'END') return { close: 'BEGIN' };
        return null;
    }

    // --- C-like brace counting -------------------------------------------------

    function braceDelta(lineText) {
        var d = 0;
        for (var i = 0; i < lineText.length; i++) {
            var ch = lineText.charAt(i);
            if (ch === '{') d++;
            else if (ch === '}') d--;
        }
        return d;
    }

    function isCCommentLine(lineText) {
        var t = lineText.trim();
        return t.length === 0 || t.charAt(0) === '/' || t.charAt(0) === '*';
    }

    // --- foldService provider ---------------------------------------------------

    // Absolute document position just after the block keyword that opens a
    // line (past any leading spaces or line number). Folds start here so the
    // opener line itself stays visible: its gutter marker remains clickable
    // and the Ctrl-Shift-] fold key works from that line, like tree folding.
    function keywordRange(line, re) {
        var m = re.exec(line.text);
        return line.from + (m ? m.index + m[0].length : 0);
    }

    function languageKey(state) {
        var name = null;
        try {
            var lang = state.facet(CM_NS.language);
            if (lang && lang.name) name = lang.name;
        } catch (e) {}
        if (!name) {
            try {
                var data = state.languageDataAt('name', 0);
                if (data && data.length && data[0] != null) name = data[0];
            } catch (e) {}
        }
        // No global-language fallback here: window.__wbCurrentLang is updated
        // by the server after the editor language actually changes, so relying
        // on it during a gutter rebuild would classify the new (plain text)
        // language as the stale previous one, leaving misleading markers.
        name = String(name).toLowerCase();
        if (name.indexOf('hitbasic') >= 0 || name.indexOf('basic') >= 0 || name === 'vbscript') return 'hitbasic';
        if (name.indexOf('pascal') >= 0) return 'pascal';
        if (name === 'c' || name === 'cpp' || name === 'clike' || name === 'c++') return 'c';
        return null;
    }

    // Forward scan for the closer of a keyword block opened on this line.
    function matchingKeywordBlock(state, lineStart, lineEnd, classify, block) {
        var doc = state.doc;
        var openLine = doc.lineAt(lineStart);
        var first = classify(openLine.text);
        if (!first || !first.open) return null;
        var stack = [first.open];
        var from = keywordRange(openLine, block);
        var last = Math.min(doc.lines, openLine.number + MAX_SCAN_LINES);
        for (var n = openLine.number + 1; n <= last; n++) {
            var line = doc.line(n);
            var tok = classify(line.text);
            if (!tok || tok.middle) continue;
            if (tok.open) {
                stack.push(tok.open);
                continue;
            }
            if (tok.close) {
                var idx = stack.lastIndexOf(tok.close);
                if (idx < 0) continue;
                stack = stack.slice(0, idx);
                if (stack.length === 0) return { from: from, to: line.from };
            }
        }
        return null;
    }

    // Backward scan: find the innermost keyword block enclosing this line, then
    // scan forward for its closer. Lets the fold keys work from a body line.
    function enclosingKeywordBlock(state, lineStart, lineEnd, classify, block) {
        var doc = state.doc;
        var cur = doc.lineAt(lineStart);
        var stack = [];

        function processFrom(n) {
            var tok = classify(doc.line(n).text);
            if (!tok || tok.middle) return;
            if (tok.open) {
                stack.push({ type: tok.open, from: keywordRange(doc.line(n), block) });
            } else if (tok.close) {
                var i = stack.length - 1;
                while (i >= 0 && stack[i].type !== tok.close) i--;
                if (i >= 0) stack = stack.slice(0, i);
            }
        }

        var firstNum = Math.max(1, cur.number - MAX_SCAN_LINES);
        for (var n = firstNum; n <= cur.number; n++) processFrom(n);
        if (stack.length === 0) return null;
        var top = stack[stack.length - 1];
        var last = Math.min(doc.lines, cur.number + MAX_SCAN_LINES);
        for (var m = cur.number + 1; m <= last; m++) {
            var tok = classify(doc.line(m).text);
            if (!tok || tok.middle) continue;
            if (tok.open) {
                stack.push({ type: tok.open, from: keywordRange(doc.line(m), block) });
                continue;
            }
            if (tok.close) {
                var i = stack.length - 1;
                while (i >= 0 && stack[i].type !== tok.close) i--;
                if (i < 0) continue;
                var popped = stack[i];
                stack = stack.slice(0, i);
                if (popped === top) return { from: top.from, to: doc.line(m).from };
            }
        }
        return null;
    }

    // Forward scan for the closer brace of a '{' on this line.
    function matchingBraceBlock(state, lineStart, lineEnd) {
        var doc = state.doc;
        var openLine = doc.lineAt(lineStart);
        if (isCCommentLine(openLine.text)) return null;
        var total = braceDelta(openLine.text);
        if (total <= 0) return null;
        var from = openLine.from + openLine.text.indexOf('{') + 1;
        var last = Math.min(doc.lines, openLine.number + MAX_SCAN_LINES);
        for (var n = openLine.number + 1; n <= last; n++) {
            var line = doc.line(n);
            if (isCCommentLine(line.text)) continue;
            total += braceDelta(line.text);
            if (total <= 0) return { from: from, to: line.from };
        }
        return null;
    }

    // Backward scan for a brace block enclosing this line.
    function enclosingBraceBlock(state, lineStart, lineEnd) {
        var doc = state.doc;
        var cur = doc.lineAt(lineStart);
        var opens = [];
        var firstNum = Math.max(1, cur.number - MAX_SCAN_LINES);

        function processLine(line) {
            if (isCCommentLine(line.text)) return;
            var text = line.text;
            for (var i = 0; i < text.length; i++) {
                var ch = text.charAt(i);
                if (ch === '{') opens.push({ pos: line.from + i + 1 });
                else if (ch === '}' && opens.length) opens.pop();
            }
        }

        for (var n = firstNum; n <= cur.number; n++) processLine(doc.line(n));
        if (opens.length === 0) return null;
        var top = opens[opens.length - 1];
        var last = Math.min(doc.lines, cur.number + MAX_SCAN_LINES);
        for (var m = cur.number + 1; m <= last; m++) {
            processLine(doc.line(m));
            if (opens.indexOf(top) < 0) return { from: top.pos, to: doc.line(m).from };
        }
        return null;
    }

    function foldProvider(state, lineStart, lineEnd) {
        var key = languageKey(state);
        if (key === 'hitbasic') {
            var cur = state.doc.lineAt(lineStart);
            var first = hbToken(cur.text);
            if (first && first.open) return matchingKeywordBlock(state, lineStart, lineEnd, hbToken, HB_NAME_RE);
            return enclosingKeywordBlock(state, lineStart, lineEnd, hbToken, HB_NAME_RE);
        }
        if (key === 'pascal') {
            var curP = state.doc.lineAt(lineStart);
            var firstP = paToken(curP.text);
            if (firstP && firstP.open) return matchingKeywordBlock(state, lineStart, lineEnd, paToken, PA_RE);
            return enclosingKeywordBlock(state, lineStart, lineEnd, paToken, PA_RE);
        }
        if (key === 'c') {
            var curC = state.doc.lineAt(lineStart);
            if (!isCCommentLine(curC.text) && braceDelta(curC.text) > 0) {
                return matchingBraceBlock(state, lineStart, lineEnd);
            }
            return enclosingBraceBlock(state, lineStart, lineEnd);
        }
        return null;
    }

    // --- install machinery (mirrors static/plugins.js) -------------------------

    var RETRY_MS = 400;
    var MAX_RETRIES = 8;

    // The fold gutter only rebuilds its markers when the document, viewport,
    // syntax tree, fold state or foldService facet change. Reconfiguring the
    // editor's language is none of those for the stream-parser languages, so
    // markers computed under the old language linger after a switch. Watch for
    // language changes: clearing then re-adding a fold range churns the fold
    // state (which triggers a gutter rebuild) without touching the document.
    function languageRefreshListener(CM, view) {
        var lastLangName = null;
        try {
            var lf0 = view.state && view.state.facet(CM.language);
            if (lf0 && lf0.name) lastLangName = lf0.name;
        } catch (e) {}
        return CM.EditorView.updateListener.of(function(update) {
            if (update.docChanged) return; // rebuilds the gutter anyway
            var name = null;
            try {
                var lf = update.state.facet(CM.language);
                if (lf && lf.name) name = lf.name;
            } catch (e) {}
            if (name === lastLangName) return;
            lastLangName = name;
            if (update.state.doc.length < 1) return;
            var one = { from: 0, to: 1 };
            setTimeout(function() {
                try {
                    update.view.dispatch({ effects: CM.foldEffect.of(one) });
                    update.view.dispatch({ effects: CM.unfoldEffect.of(one) });
                } catch (e) {
                    console.warn('WBFold: language refresh failed', e);
                }
            }, 0);
        });
    }

    function ensureFoldService(view, CM) {
        if (!view || !view.state) return false;
        var st = view.state;
        var have = false;
        try {
            have = (st.facet(CM.foldService) || []).some(function(f) { return f === foldProvider; });
        } catch (e) {
            return false;
        }
        if (have) return true;
        var ext = [CM.foldService.of(foldProvider), languageRefreshListener(CM, view)];
        // Show the useful detail of a folded opener line (a SUB's name, an IF's
        // test condition) instead of a bare ellipsis. Fold ranges for keyword
        // blocks start right after the block keyword, so the hidden part still
        // holds that detail; render it before the '…'. preparePlaceholder hands
        // the placeholder DOM the fold start (the default passes null).
        if (CM.codeFolding) ext.push(CM.codeFolding({
            placeholderDOM: foldPlaceholderDOM,
            preparePlaceholder: function(state, range) { return range.from; }
        }));
        if (CM.foldKeymap && !(st.facet(CM.keymap) || []).some(function(k) {
            return k && k['Shift-Ctrl-['];
        })) {
            ext.push(CM.keymap.of(CM.foldKeymap));
        }
        try {
            view.dispatch({ effects: CM.StateEffect.appendConfig.of(ext) });
        } catch (e) {
            console.warn('WBFold: install failed', e);
        }
        return false;
    }

    // Replaces the range a fold hides with the remainder of the opener line
    // (from the fold start to the end of that line) plus an ellipsis, so a
    // folded HitBasic block reads e.g. "SUB GREET(NAME) …END SUB" rather than
    // "SUB …END SUB". Falls back to the plain ellipsis when no opener text is
    // left (brace blocks, folds that start at a line start).
    function foldPlaceholderDOM(view, onClick, pos) {
        var span = document.createElement('span');
        span.className = 'cm-foldPlaceholder';
        var label = '…';
        if (pos != null) {
            try {
                var line = view.state.doc.lineAt(pos);
                var rest = line.text.slice(pos - line.from).trim();
                if (rest) label = rest + ' …';
            } catch (e) {}
        }
        span.textContent = label;
        span.setAttribute('aria-label', 'folded code');
        span.title = 'unfold';
        span.onclick = onClick;
        return span;
    }

    function currentView() {
        var elId = window.__wbEditorId;
        if (!elId) return null;
        var el = window.getElement ? window.getElement(elId) : null;
        return (el && el.editorPromise) ? el.editorPromise : null;
    }

    // CodeMirror's own capture keydown handler tries the unshifted variant
    // of a character key first, so a Gesture produced as Ctrl+Shift+[ with
    // key='[' (as Playwright does) resolves to Mod-[ (indentLess) and the
    // fold binding never fires. Real keyboards emit key='{' and CodeMirror
    // folds fine. Intercept the gesture on the window in the capture phase
    // (which runs before CodeMirror's content-DOM handler) and fold/unfold
    // explicitly, so both cases behave identically.
    var foldKeysBound = false;
    function bindFoldKeys() {
        if (foldKeysBound) return;
        foldKeysBound = true;
        window.addEventListener('keydown', function(e) {
            if (!((e.ctrlKey || e.metaKey) && e.shiftKey)) return;
            if (e.code !== 'BracketLeft' && e.code !== 'BracketRight') return;
            var p = currentView();
            if (p) {
                p.then(function(view) {
                    import('nicegui-codemirror').then(function(CM) {
                        CM_NS = CM_NS || CM;
                        if (!view || !view.state) return;
                        if (e.code === 'BracketLeft') CM.foldCode(view);
                        else CM.unfoldCode(view);
                    });
                });
            }
            e.preventDefault();
            e.stopImmediatePropagation();
        }, true);
    }

    function install() {
        var p = currentView();
        if (!p) return;
        bindFoldKeys();
        p.then(function(view) {
            import('nicegui-codemirror').then(function(CM) {
                CM_NS = CM_NS || CM;
                if (ensureFoldService(view, CM)) return;
                // CodeMirror can rebuild the editor state shortly after mount,
                // dropping appended config facets; keep reapplying until it sticks.
                var n = 0;
                var iv = setInterval(function() {
                    var p2 = currentView();
                    if (p2) {
                        p2.then(function(v) {
                            import('nicegui-codemirror').then(function(CM2) {
                                CM_NS = CM_NS || CM2;
                                if (ensureFoldService(v, CM2)) clearInterval(iv);
                            });
                        });
                    }
                    if (++n > MAX_RETRIES) clearInterval(iv);
                }, RETRY_MS);
            });
        });
    }

    window.WBFold = { install: install };

    var attempts = 0;
    var iv = setInterval(function() {
        if (window.__wbEditorId || ++attempts > 50) clearInterval(iv);
    }, 100);
    install();

    // Re-bind whenever the server activates a (possibly new) editor; installs
    // are idempotent per view + fold-service presence.
    window.addEventListener('wb-active-editor', function() {
        try { install(); } catch (e) {}
    });
})();