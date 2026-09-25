// Myslyx in-browser LSP - pure hints model (dependency-free).
//
// Shared by the worker server (tools/weblsp/src/server.js, bundled with
// esbuild) and runnable directly under node for unit checks. It mirrors the
// client-side semantics of static/native-completions.js so the worker serves
// the same prefix/case rules the popups already use:
//
//   - word completion merges hints keywords/builtins/types with the user's
//     own symbols, prefix-filtered (Pascal case-insensitive, C exact-case
//     boost), capped at MAX_ITEMS;
//   - member contexts (caret after "." / "->") return null on purpose: the
//     client keeps serving those from its curated struct machinery
//     (c-struct-complete / native-completions memberSource), which resolves
//     in-file struct definitions the hints JSON cannot see;
//   - tips are looked up case-insensitively (msxgl.json keys every tip by the
//     UPPER-CASE symbol name; c.json and pascal.json do the same);
//   - parseTip() recovers a structured {signature, params} from a rendered
//     tip markdown. The generator (tools/gen_msxgl_hints.py::tip_markdown)
//     always emits the signature as the first ```c block and the parameters
//     as a "**Parameters:**" list of "- `name` - desc" lines, so the parse is
//     deterministic. If the generator ever emits structured signatures,
//     swap this function out and keep the callers.

// LSP CompletionItemKind numbers we emit (kept numeric so the module stays
// free of the vscode-languageserver import; see server.js for the mapping).
export const Kind = {
    Function: 3,
    Field: 5,
    Variable: 6,
    Keyword: 14,
    Constant: 21,
    Struct: 22,
};

export const MAX_ITEMS = 200;

// A name that reads as an enum constant (mirrors looksLikeEnumConstant in
// native-completions.js): those complete as constants, other type names as
// struct-ish types.
export function isEnumConstant(name) {
    return /^[A-Z][A-Z0-9_]*$/.test(name) && name.indexOf('_') >= 0;
}

export function normalizeHints(json) {
    const h = json || {};
    return {
        keywords: (h.keywords || []).slice(),
        builtins: (h.builtins || []).slice(),
        types: (h.types || []).slice(),
        structs: h.structs || {},
        tips: h.tips || {},
    };
}

// The trailing [A-Za-z0-9_] run ending at offset (mirrors wordBefore in
// native-completions.js).
export function wordBefore(text, offset) {
    let start = Math.max(0, Math.min(offset, text.length));
    while (start > 0 && /[A-Za-z0-9_]/.test(text[start - 1])) start--;
    return { word: text.slice(start, offset), start };
}

// The identifier under offset (expands both directions).
export function wordAt(text, offset) {
    const pos = Math.max(0, Math.min(offset, text.length));
    let start = pos;
    let end = pos;
    while (start > 0 && /[A-Za-z0-9_]/.test(text[start - 1])) start--;
    while (end < text.length && /[A-Za-z0-9_]/.test(text[end])) end++;
    return { word: text.slice(start, end), start, end };
}

// Member-trigger detection on the caret's line, mirroring
// native-completions.js::memberContext's text fallback: strip the trailing
// identifier, then report whether the caret dangles after "." / "->".
export function memberTriggerInfo(text, offset) {
    const wb = wordBefore(text, offset);
    const lineStart = text.lastIndexOf('\n', offset - 1) + 1;
    const w = wb.word;
    let prefix = text.slice(lineStart, wb.start).replace(/[ \t]*$/, '');
    if (/(->|\.)$/.test(prefix)) return { isMember: true, word: w, from: wb.start };
    return { isMember: false, word: w, from: wb.start };
}

// Merge hints + user symbols into LSP completion items for a word prefix.
// symbols: [{name, kind}] where kind is 'function' or anything else.
// caseInsensitive: true for Pascal (boost compares case-indifferently).
// detailFor: optional (label) -> detail-column string for builtins (the
// server passes a constant 'builtin' to mirror the curated popup contract).
export function buildWordItems(model, symbols, prefix, caseInsensitive, detailFor) {
    const lower = (prefix || '').toLowerCase();
    const upper = (prefix || '').toUpperCase();
    const seen = new Set();
    const out = [];

    function push(label, kind, detail) {
        const up = String(label).toUpperCase();
        if (!label || seen.has(up)) return;
        seen.add(up);
        out.push({ label: String(label), kind, detail: detail || '', _boost: 0 });
    }

    (model.keywords || []).forEach((k) => push(k, Kind.Keyword, 'keyword'));
    (model.builtins || []).forEach((b) => push(
        b, Kind.Function, (detailFor && detailFor(b)) || 'function'));
    (model.types || []).forEach((t) => push(
        t, isEnumConstant(t) ? Kind.Constant : Kind.Struct,
        isEnumConstant(t) ? 'const' : 'type'));
    (symbols || []).forEach((s) => push(
        s.name, s.kind === 'function' ? Kind.Function : Kind.Variable,
        s.kind || 'symbol'));

    const matched = out.filter((m) => !lower || m.label.toLowerCase().indexOf(lower) === 0);
    matched.forEach((m) => {
        if (lower && (caseInsensitive
            ? m.label.substring(0, prefix.length).toUpperCase() === upper
            : m.label.indexOf(prefix) === 0)) m._boost = 20;
    });
    matched.sort((a, b) => (b._boost - a._boost) ||
        (a.label < b.label ? -1 : a.label > b.label ? 1 : 0));
    return matched.slice(0, MAX_ITEMS).map((m) => ({
        label: m.label, kind: m.kind, detail: m.detail,
    }));
}

// Case-insensitive tip lookup (tips are keyed UPPER-CASE).
export function lookupTip(model, name) {
    if (!name) return null;
    const tips = model.tips || {};
    return tips[name.toUpperCase()] || null;
}

// Recover {signature, params} from a rendered tip markdown. Only the
// generator-shaped functions carry both; free-form tips (c.json/pascal.json)
// yield {signature: null, params: []}.
export function parseTip(tip) {
    if (!tip) return { signature: null, params: [] };
    let signature = null;
    const m = /```c\n([\s\S]*?)\n```/.exec(tip);
    if (m) {
        const first = m[1].split('\n')[0].trim();
        // Multi-line bodies (enum/struct type tips) are not signatures.
        if (first && m[1].indexOf('\n') < 0) signature = first;
    }
    const params = [];
    const lines = tip.split('\n');
    let inParams = false;
    for (const ln of lines) {
        const t = ln.trim();
        if (/^\*\*Parameters:\*\*/.test(t)) { inParams = true; continue; }
        if (inParams) {
            if (/^\*\*\S/.test(t)) break;
            const pm = /^-\s*`([^`]+)`\s*-?\s*(.*)$/.exec(t);
            if (pm) params.push({ name: pm[1].trim(), desc: (pm[2] || '').trim() });
            else if (t && params.length) break;
        }
    }
    return { signature, params };
}

// Enclosing call at offset: {name, argIndex} or null. Scans backwards for
// the unmatched '(' (stops at ';' / '{' / '}' at depth 0, or after a budget);
// argIndex counts top-level commas between '(' and the caret.
export function callInfo(text, offset) {
    const pos = Math.max(0, Math.min(offset, text.length));
    let depth = 0;
    let budget = 2000;
    for (let i = pos - 1; i >= 0 && budget-- > 0; i--) {
        const ch = text[i];
        if (ch === ')') { depth++; continue; }
        if (ch === '(') {
            if (depth === 0) {
                let j = i - 1;
                while (j >= 0 && (text[j] === ' ' || text[j] === '\t' || text[j] === '\n')) j--;
                let end = j + 1;
                while (j >= 0 && /[A-Za-z0-9_]/.test(text[j])) j--;
                const name = text.slice(j + 1, end);
                if (!name) return null;
                let argIndex = 0;
                let d2 = 0;
                for (let k = i + 1; k < pos; k++) {
                    const c = text[k];
                    if (c === '(') d2++;
                    else if (c === ')') { if (d2 > 0) d2--; }
                    else if (c === ',' && d2 === 0) argIndex++;
                }
                return { name, argIndex };
            }
            depth--;
            continue;
        }
        if (depth === 0 && (ch === ';' || ch === '{' || ch === '}')) return null;
    }
    return null;
}
