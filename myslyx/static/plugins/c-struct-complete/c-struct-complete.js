// Myslyx Text Editor - C struct member completion plugin.
//
// A generic base-language plugin. It scopes on the base-language attribute
// window.__wbBaseLang === 'c', shared by plain C ("C"), the MSXgl C framework
// ("C MSXgl") and every future language whose base is 'c' — so it activates
// automatically, with no manifest edits, the moment a new C-derived language
// gets an entry in editor_page's BASE_LANG.
//
// It is a boot plugin: its module registers a completion provider once at
// page startup and returns no per-view CodeMirror extensions (plugin.json
// declares "boot": true, "baseLang": ["c"]).
//
// The provider intercepts the editor's autocomplete when the caret follows a
// "." or "->" member access ("player.pos."). The base expression is resolved
// to a struct TYPE via the document model in c-struct-model.js (shared with
// native-completions, which drives C MSXgl's native autocomplete) and that
// struct's fields become the completions, with the field type shown as
// detail. Member chains (a.b.c) are resolved recursively through structs
// whose definition is known: in-file definitions plus the "structs" map of
// the active hints JSON (myslyx/static/hints/<key>.json, e.g. msxgl.json).
// Pointer vs. value is deliberately not distinguished.
'use strict';

import { parseModel, collectVars, membersOf, memberNamed, fieldsToShow }
    from './c-struct-model.js';

function cStructComplete(CM) {
    var model = null;          // parsed doc model, rebuilt on doc change
    var modelFingerprint = null;
    var hintsState = { key: null, structs: {} };  // framework structs (async)
    var hintsCache = {};

    function isBaseC() {
        return window.__wbBaseLang === 'c';
    }

    function hintKey() {
        return window.__wbHintKey || 'c';
    }

    function loadHints(key) {
        if (!hintsCache[key]) {
            var p = window.WBHints
                ? window.WBHints.get(key)
                : Promise.resolve({ keywords: [], builtins: [], tips: {}, structs: {} });
            hintsCache[key] = p.then(function(h) {
                hintsState.key = key;
                // The hints JSON carries structs as NAME -> [[type, field,
                // comment], ...]; normalize to the rich member shape.
                var structs = {};
                for (var n in ((h && h.structs) || {})) {
                    structs[n] = (h.structs[n] || []).map(function(t) {
                        return { name: t[1], type: t[0], raw: t[0] };
                    });
                }
                hintsState.structs = structs;
                // The filled data may now unlock a completion check the caller
                // already gave up on (hints.js re-runs its popup check).
                try { window.dispatchEvent(new CustomEvent('wb-hints-ready')); } catch (e) {}
            });
        }
        return hintsCache[key];
    }

    function ensureModel(doc) {
        var fp = doc.length + '|' + (doc.match(/\n/g) || []).length;
        if (modelFingerprint !== fp) {
            modelFingerprint = fp;
            model = parseModel(doc);
        }
        return model;
    }

    // Returns the fields to complete for the caret's member-access context,
    // or null when this is not a member access (default completions apply).
    function runProvider(ctx) {
        if (!isBaseC()) return null;

        var prefix = ctx.line.slice(0, ctx.col);
        var trimmed = prefix.trim();
        var word = ctx.word || '';

        // Strip the partial identifier being typed, if any.
        if (word && /^[A-Za-z_][A-Za-z0-9_]*$/.test(word) &&
            trimmed.length >= word.length &&
            trimmed.slice(trimmed.length - word.length) === word) {
            trimmed = trimmed.slice(0, trimmed.length - word.length).trim();
        }
        if (!/(->|\.)$/.test(trimmed)) return null;

        // Struct data from the active hints JSON (async). When it isn't
        // loaded for the current key yet, fetch it. For an empty word the
        // best answer right now is "[]" (show nothing): it stops the default
        // keyword path from flashing its own popup that would then be
        // replaced by the member list once the hints data lands (the loaded
        // data fires "wb-hints-ready", which re-runs the completion check).
        if (hintsState.key !== hintKey()) {
            loadHints(hintKey());
            return word ? null : [];
        }

        var doc = ctx.view ? ctx.view.state.doc.toString() : '';
        var model = ensureModel(doc);
        var allStructs = {};
        var k;
        for (k in model) allStructs[k] = model[k];
        for (k in hintsState.structs) if (!(k in allStructs)) allStructs[k] = hintsState.structs[k];
        var allVars = collectVars(doc, Object.keys(allStructs));

        // Only the trailing member chain matters; earlier tokens on the line
        // ("foo = a.b.c.…") must not corrupt the base expression.
        var chainRe = /([A-Za-z_]\w*(?:\s*(?:->|\.)\s*[A-Za-z_]\w*)*)\s*(?:->|\.)\s*$/;
        var cm = chainRe.exec(trimmed);
        if (!cm) return null;
        var parts = cm[1].split(/(?:->|\.)/).map(function(p) { return p.trim(); });
        parts.push(''); // the dangling separator right at the caret
        var base = parts[0] || '';
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(base)) return [];

        // Base type: a declared variable/parameter, or the base itself when it
        // already names a struct.
        var cur = allVars[base];
        if (!cur) cur = (base in allStructs) ? base : null;
        if (!cur) return [];

        for (var i = 1; i < parts.length; i++) {
            var tok = parts[i];
            var isLast = (i === parts.length - 1);
            if (tok === '') return fieldsToShow(allStructs, cur, word);
            var mem = memberNamed(allStructs, cur, tok);
            if (!mem) return [];
            if (isLast) return fieldsToShow(allStructs, cur, word);
            // Intermediate hop: the member must itself be a struct.
            if (!membersOf(allStructs, mem.type)) return [];
            cur = mem.type;
        }
        return [];
    }

    if (window.WBHintCompletions) {
        window.WBHintCompletions.register('c-struct-complete', runProvider);
    }
    loadHints(hintKey());

    return [];
}

export default cStructComplete;