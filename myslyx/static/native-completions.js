// Myslyx Text Editor - native CodeMirror autocomplete for C MSXgl source.
//
// C MSXgl (and only C MSXgl) replaces the custom .wb-autocomplete-popup with
// CodeMirror's built-in (native) autocompletion. NiceGUI's basicSetup already
// wires @codemirror/autocomplete into every editor, so no bundled module is
// needed here — we only REGISTER completion sources. autocompletion() reads
// its default sources from the "autocomplete" language-data field, which
// EditorState.languageData lets us provide from page JS (both are exported by
// nicegui-codemirror).
//
// The provider is appended to every view once (view.__wbNativeCmInstalled) and
// the SOURCE guards on window.__wbHintKey, so it stays invisible for other
// languages and also keeps working when the language combo switches a view
// between plain C and C MSXgl.
//
// Word completions reuse the same curated data as the custom popup: msxgl.json
// keywords (C + SDCC), builtins and types, plus the user's own discovered
// symbols. Member completions ("." / "->") are driven by the parse tree
// (FieldExpression nodes, with a text-based fallback) and resolve field types
// through the shared C struct document model in plugins/c-struct-complete/
// (the same tables the c-struct-complete plugin uses for plain C).
import * as CM from 'nicegui-codemirror';
import { parseModel, collectVars, membersOf, memberNamed, fieldsToShow }
    from './plugins/c-struct-complete/c-struct-model.js';

const MSXGL_HINT_KEY = 'msxgl';
const MAX_WORD_OPTIONS = 200;

const hintsCache = {};
const modelCache = new WeakMap();

function hintKey() {
    return window.__wbHintKey || 'c';
}

function isMsxgl() {
    return hintKey() === MSXGL_HINT_KEY;
}

function loadHints(key) {
    if (!hintsCache[key]) {
        const p = window.WBHints
            ? window.WBHints.get(key)
            : Promise.resolve({ keywords: [], builtins: [], types: [], structs: {} });
        hintsCache[key] = p.then(function(h) {
            // msxgl.json carries structs as NAME -> [[type, field, comment],
            // ...]; normalize to the rich member shape (same as the plugin).
            const structs = {};
            for (const n in ((h && h.structs) || {})) {
                structs[n] = (h.structs[n] || []).map(function(t) {
                    return { name: t[1], type: t[0], raw: t[0] };
                });
            }
            return {
                keywords: (h && h.keywords) || [],
                builtins: (h && h.builtins) || [],
                types: (h && h.types) || [],
                structs: structs,
            };
        });
    }
    return hintsCache[key];
}

// The trailing identifier (possibly empty) right before the caret.
function wordBefore(state, pos) {
    let start = pos;
    while (start > 0) {
        const ch = state.sliceDoc(start - 1, start);
        if (ch && /[A-Za-z0-9_]/.test(ch)) start--;
        else break;
    }
    return { word: state.sliceDoc(start, pos), start: start };
}

// The nearest FieldExpression whose field token sits at the caret. Field
// names are parsed as "FieldIdentifier" leaves covering ".name" / "->name",
// nested member access nests FieldExpressions ("spr.attr.y").
function findFieldExpression(tree, pos) {
    let node = tree.resolveInner(pos, -1);
    while (node) {
        if (node.type.name === 'FieldExpression') {
            const last = node.lastChild;
            if (last && last.type.name === 'FieldIdentifier' &&
                last.from <= pos && pos <= last.to + 1) {
                return node;
            }
        }
        node = node.parent;
    }
    return null;
}

// Resolve the receiver chain for the caret. Returns {parts, word, from} when
// the caret follows a "." / "->", else null.
async function memberContext(state, pos, wordInfo) {
    const line = state.doc.lineAt(pos);
    let prefix = line.text.slice(0, pos - line.from).trim();
    const word = wordInfo.word;
    if (word && /^[A-Za-z_][A-Za-z0-9_]*$/.test(word) &&
        prefix.length >= word.length &&
        prefix.slice(prefix.length - word.length) === word) {
        prefix = prefix.slice(0, prefix.length - word.length).trim();
    }
    const dangling = /(->|\.)$/.test(prefix);

    // Preferred: the syntax tree's FieldExpression chain.
    try {
        const tree = await CM.ensureSyntaxTree(state, pos, 4000);
        if (tree && tree.length > 0) {
            const fe = findFieldExpression(tree, pos);
            if (fe && fe.firstChild) {
                const parts = state.sliceDoc(fe.firstChild.from, fe.firstChild.to)
                    .trim().split(/(?:->|\.)/)
                    .map(function(s) { return s.trim(); })
                    .filter(function(s) { return s.length > 0; });
                if (parts.length) {
                    return { parts: parts, word: word, from: wordInfo.start };
                }
            }
        }
    } catch (e) {
        // fall through to the text heuristic
    }

    if (!dangling) return null;
    const cm = /([A-Za-z_]\w*(?:\s*(?:->|\.)\s*[A-Za-z_]\w*)*)\s*(?:->|\.)\s*$/.exec(prefix);
    if (!cm) return null;
    const parts = cm[1].split(/(?:->|\.)/).map(function(s) { return s.trim(); });
    if (!parts.length) return null;
    return { parts: parts, word: word, from: wordInfo.start };
}

// Resolve "parts" (receiver chain) to a struct's fields, filtered by "word".
// Mirrors the c-struct-complete provider: pointer vs. value is not
// distinguished, intermediate hops must themselves be structs, and a dangling
// separator ('' tail) means the caret sits right after the operator.
function resolveChain(allStructs, allVars, parts, word) {
    parts = parts.concat();
    if (parts[parts.length - 1] !== '') parts.push('');
    var base = parts[0] || '';
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(base)) return [];
    var cur = allVars[base];
    if (!cur) cur = (base in allStructs) ? base : null;
    if (!cur) return [];

    for (var i = 1; i < parts.length; i++) {
        var tok = parts[i];
        if (tok === '') return fieldsToShow(allStructs, cur, word);
        var mem = memberNamed(allStructs, cur, tok);
        if (!mem) return [];
        if (!membersOf(allStructs, mem.type)) return [];
        cur = mem.type;
    }
    return fieldsToShow(allStructs, cur, word);
}

function ensureModel(view) {
    const doc = view.state.doc.toString();
    const fp = doc.length + '|' + (doc.match(/\n/g) || []).length +
        '|' + doc.slice(0, 48) + '|' + doc.slice(-24);
    const e = modelCache.get(view);
    if (!e || e.fp !== fp) {
        const fresh = { fp: fp, model: parseModel(doc) };
        modelCache.set(view, fresh);
        return fresh.model;
    }
    return e.model;
}

async function memberSource(ctx, wordInfo, hints) {
    const state = ctx.state;
    const mc = await memberContext(state, ctx.pos, wordInfo);
    if (!mc) return null;
    const view = ctx.view;
    const doc = view ? view.state.doc.toString() : state.doc.toString();
    const model = view ? ensureModel(view) : parseModel(doc);

    // In-file definitions win over the framework's structs; the hints' structs
    // fill in whatever the file does not define (same merge as the plugin).
    const allStructs = {};
    let k;
    for (k in model) allStructs[k] = model[k];
    for (k in hints.structs) if (!(k in allStructs)) allStructs[k] = hints.structs[k];
    const allVars = collectVars(doc, Object.keys(allStructs));

    const options = resolveChain(allStructs, allVars, mc.parts, mc.word);
    if (!options.length) return null;
    return { from: mc.from, options: options };
}

// User-discovered symbols (functions/subroutines) that may be completed too.
// Mirrors hints.js getAllSymbols: a file with global export disabled only
// contributes while it is the one being edited.
function getAllSymbols() {
    var symbols = window.WBStorage && window.WBStorage.loadSymbols ? window.WBStorage.loadSymbols() : {};
    var files = window.WBStorage && window.WBStorage.loadFiles ? window.WBStorage.loadFiles() : [];
    var namesById = {};
    var exportById = {};
    files.forEach(function(f) {
        namesById[f.id] = f.name;
        exportById[f.id] = f.export_symbols !== false;
    });
    var activeFid = window.__wbActiveFid || null;
    var out = [];
    Object.keys(symbols).forEach(function(fid) {
        if (exportById[fid] !== false || fid === activeFid) {
            (symbols[fid] || []).forEach(function(s) {
                out.push({ name: s.name, kind: s.kind, line: s.line, file: namesById[fid] || fid });
            });
        }
    });
    return out;
}

function looksLikeEnumConstant(name) {
    return /^[A-Z][A-Z0-9_]*$/.test(name) && name.indexOf('_') >= 0;
}

function buildWordOptions(hints, word) {
    var lower = (word || '').toLowerCase();
    var seen = {};
    var out = [];

    function push(label, detail, type) {
        var up = label.toUpperCase();
        if (up in seen) return;
        seen[up] = 1;
        out.push({ label: label, detail: detail, type: type });
    }

    (hints.keywords || []).forEach(function(k) { push(k, 'keyword', 'keyword'); });
    (hints.builtins || []).forEach(function(b) { push(b, 'builtin', 'function'); });

    var structNames = {};
    var s;
    for (s in hints.structs) structNames[s] = 1;
    (hints.types || []).forEach(function(t) {
        var isStruct = !!structNames[t];
        push(t, isStruct ? 'type' : 'const', isStruct ? 'type' : (looksLikeEnumConstant(t) ? 'constant' : 'type'));
    });
    getAllSymbols().forEach(function(x) {
        push(x.name, x.kind || 'symbol', x.kind === 'function' ? 'function' : 'variable');
    });

    var matched = out.filter(function(m) {
        return !lower || m.label.toLowerCase().indexOf(lower) === 0;
    });
    matched.forEach(function(m) {
        // Exact-case prefix (the normal C convention) ranks first; the native
        // popup otherwise falls back to its own label sort.
        if (lower && m.label.indexOf(word) === 0) m.boost = 20;
    });
    matched.sort(function(a, b) {
        return (b.boost || 0) - (a.boost || 0) || (a.label < b.label ? -1 : a.label > b.label ? 1 : 0);
    });
    return matched.slice(0, MAX_WORD_OPTIONS);
}

function wordSource(ctx, wordInfo, hints) {
    var w = ctx.matchBefore(/[A-Za-z_][A-Za-z0-9_]*/);
    if (!w) return null;
    if (!ctx.explicit && !w.text) return null;
    return { from: w.from, options: buildWordOptions(hints, w.text) };
}

async function msxglSource(ctx) {
    try {
        if (!isMsxgl()) return null;
        var hints = await loadHints(MSXGL_HINT_KEY);
        if (!hints) return null;
        var state = ctx.state;
        var pos = ctx.pos;
        var wordInfo = wordBefore(state, pos);
        var member = await memberContext(state, pos, wordInfo);
        if (member) {
            return await memberSource(ctx, wordInfo, hints);
        }
        return wordSource(ctx, wordInfo, hints);
    } catch (e) {
        return null;
    }
}

// The "autocomplete" language-data entry is autocompletion()'s default source
// mechanism: it is read through languageDataAt for every completion query, and
// merges with (and de-duplicates against) the language's own sources.
var nativeConfig = CM.EditorState.languageData.of(function() {
    return [{ autocomplete: msxglSource }];
});

function installOnView(view) {
    if (!view || view.__wbNativeCmInstalled) return;
    view.__wbNativeCmInstalled = true;
    try {
        view.dispatch({ effects: CM.StateEffect.appendConfig.of([nativeConfig]) });
    } catch (e) {}
}

function tryHook() {
    window.WBEditorActive.withView(function(v) {
        if (v) installOnView(v);
    });
    return true;
}

// Install on every view as it activates, and once at startup for the first
// editor (same race-tolerant pattern as hints.js / plugins.js).
window.addEventListener('wb-active-editor', function() {
    try { tryHook(); } catch (e) {}
});
var attempts = 0;
var iv = setInterval(function() {
    if (tryHook() || ++attempts > 100) clearInterval(iv);
}, 200);