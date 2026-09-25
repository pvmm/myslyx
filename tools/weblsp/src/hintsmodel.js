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
//   - member contexts (caret after "." / "->") resolve struct/union fields
//     from the hints `structs` tables merged with locally declared
//     aggregates (in-file definitions win), through receiver chains
//     ("spr.attr.") fed by the document's variable->type bindings. The
//     client stands its curated member sources down while the worker is
//     ready so each field completes exactly once;
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
    (symbols || []).forEach((s) => {
        if (!s || !s.name) return;
        if (s.kind === 'function') push(s.name, Kind.Function, 'function');
        else if (s.kind === 'type') push(s.name, Kind.Struct, 'type');
        else if (s.kind === 'constant') push(s.name, Kind.Constant, 'const');
        else push(s.name, Kind.Variable, s.kind || 'symbol');
    });

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

// ---------------------------------------------------------------------------
// Document-local declarations.
//
// The persisted symbol store (hints.js::scanSymbols, pushed in as `symbols`)
// only discovers top-level function definitions, so variables, parameters
// and file-scope names typed in the open buffer would never complete. The
// worker already holds the synced document text, so it mines declarations
// itself on every completion request (a few KB of regex scanning, well under
// a millisecond). Heuristic and over-approximating on purpose: a stray
// extra name in the popup beats a missing one.
//
// Returns [{name, kind}] with kind 'function' | 'variable' | 'param' (the
// same shape as the pushed symbols). C names keep their case; Pascal names
// are uppercased to match the scanner convention (case-insensitive).
// typeNames: extra known type names (the active hints' `types` list).

function stripCNoise(text) {
    return String(text)
        .replace(/\/\*[\s\S]*?\*\//g, ' ')
        .replace(/\/\/[^\n]*/g, ' ')
        .replace(/'(?:\\.|[^'\\\n])*'/g, "'c'")
        .replace(/"(?:\\.|[^"\\\n])*"/g, '"s"');
}

function stripPascalNoise(text) {
    return String(text)
        .replace(/\(\*[\s\S]*?\*\)/g, ' ')
        .replace(/\{[^}]*\}/g, ' ')
        .replace(/\/\/[^\n]*/g, ' ')
        .replace(/'(?:[^']|'')*'/g, "'s'");
}

// Mirrors the scanner's C type set (hints.js::scanSymbols), extended with
// common libc typedefs. struct/union/enum tags and the hints' own type
// names arrive via typeNames.
const C_TYPE_WORDS = [
    'void', 'char', 'short', 'int', 'long', 'float', 'double',
    'signed', 'unsigned', 'bool', 'size_t',
    'u8', 'u16', 'u32', 'u64', 's8', 's16', 's32', 's64',
    'f16', 'f32', 'fix16', 'fix32', 'fix16_16', 'f16_16', 'f32_32',
    'FILE', 'time_t', 'clock_t', 'ptrdiff_t', 'wchar_t',
];
const C_QUALIFIERS = ['const', 'static', 'extern', 'volatile', 'register', 'inline', 'struct', 'union', 'enum'];
// Control/keyword words that must never complete as variables.
const C_NOISE = new Set([
    'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'default',
    'return', 'sizeof', 'typedef', 'break', 'continue', 'goto',
]);

// Locally declared struct/union/enum types, enum constants and aggregate
// trailing declarators.
//
// Two jobs: the type names themselves must complete (`MySprite`), and they
// must join the known-type set so declarators using them (`MySprite player`)
// parse as variables (second pass in parseCDocumentSymbols). Finds typedef
// aggregates (`typedef struct [Tag] { ... } [Alias, ...];`), plain tags
// (`struct Tag { ... };`, `struct Tag;`) and enum bodies (whose members are
// globally-scoped constants). Brace-depth scanning survives nested
// definitions; bodies recurse for nested tags. A trailing declarator list
// after `}` is a type alias list only under `typedef`; in a plain definition
// at depth 0 it is file-scope variables (`struct S { ... } myVar;`), nested
// ones are fields. Returns {types, consts, vars}.
function parseLocalTypes(text) {
    const types = [];
    const consts = [];
    const vars = [];
    const members = {};
    const clean = stripCNoise(text);
    const seenT = new Set();
    const seenC = new Set();
    const seenV = new Set();
    const addT = (n) => { if (n && !seenT.has(n)) { seenT.add(n); types.push(n); } };
    const addC = (n) => { if (n && !seenC.has(n)) { seenC.add(n); consts.push(n); } };
    const addV = (n, ofType) => {
        if (n && !seenV.has(n)) { seenV.add(n); vars.push({ name: n, ofType }); }
    };

    function scanConsts(body) {
        for (const part of body.split(',')) {
            const cm = /^\s*([A-Za-z_]\w*)/.exec(part);
            if (cm) addC(cm[1]);
        }
    }

    // Field list of one struct/union body as [[type, name, '']] triples (the
    // hints `structs` shape, minus comments). Segments holding nested
    // aggregates are skipped (their tags resolve through recursion); the
    // curated member path owns nothing here — these tables feed the
    // worker-side receiver resolver below.
    function parseFields(body) {
        const fields = [];
        for (const seg of body.split(';')) {
            if (!seg || /[{}}]/.test(seg) || seg.indexOf('(') >= 0) continue;
            const fm = /^\s*(.+?)\s+([A-Za-z_]\w*(?:\s*\[[^\]]*\])?(?:\s*:\s*\d+)?)\s*$/.exec(seg);
            if (!fm) continue;
            const ftype = fm[1].trim();
            const fname = fm[2].trim();
            if (!ftype || !fname || /^(extern|typedef)$/.test(ftype)) continue;
            fields.push([ftype, fname, '']);
        }
        return fields;
    }

    function scanRange(from, to, depth) {
        const re = /(typedef\s+)?\b(struct|union|enum)\b\s*([A-Za-z_]\w*)?/g;
        re.lastIndex = from;
        let m;
        while ((m = re.exec(clean)) !== null && m.index < to) {
            const isTypedef = !!m[1];
            const kind = m[2];
            const tag = m[3] || null;
            let i = m.index + m[0].length;
            const skipWs = () => { while (i < to && /\s/.test(clean[i])) i++; };
            skipWs();
            if (clean[i] === '{') {
                let braceDepth = 0;
                const start = i;
                while (i < to) {
                    if (clean[i] === '{') braceDepth++;
                    else if (clean[i] === '}') {
                        braceDepth--;
                        if (braceDepth === 0) break;
                    }
                    i++;
                }
                const body = clean.slice(start + 1, i);
                i++; // past '}'
                if (tag) addT(tag);
                let fieldList = null;
                if (kind === 'enum') scanConsts(body);
                else {
                    scanRange(start + 1, i - 1, depth + 1); // nested tags
                    fieldList = parseFields(body);
                    if (tag && fieldList.length) members[tag] = fieldList;
                }
                skipWs();
                const lm = /^(\*?\s*[A-Za-z_]\w*(?:\s*,\s*\*?\s*[A-Za-z_]\w*)*)\s*;/.exec(clean.slice(i, to));
                if (lm) {
                    for (const nm of lm[1].split(',')) {
                        const w = nm.replace(/\*/g, '').trim();
                        if (!w) continue;
                        if (isTypedef) {
                            addT(w);
                            if (fieldList && fieldList.length) members[w] = fieldList;
                        } else if (depth === 0) addV(w);
                    }
                    i += lm[0].length;
                }
                re.lastIndex = i;
                continue;
            }
            // "struct Tag;" forward declaration — or "struct Tag ..." used
            // as a type (the declarator itself is the var parser's job).
            if (tag) addT(tag);
        }
    }

    scanRange(0, clean.length, 0);
    return { types, consts, vars, members };
}

// Blank "{...}" bodies of struct/union definitions (NOT enums: their bodies
// cannot match the declarator regexes) so struct FIELDS never parse as
// file-scope variables. Heads ("typedef struct Tag") and tails ("} Alias;")
// survive, so declarators still parse. Members stay completable through the
// curated member path (the worker answers member contexts with null).
function maskStructUnionBodies(clean) {
    const spans = [];
    const re = /(typedef\s+)?\b(struct|union)\b\s*([A-Za-z_]\w*)?\s*\{/g;
    let m;
    while ((m = re.exec(clean)) !== null) {
        let depth = 0;
        let i = m.index + m[0].length - 1; // at '{'
        while (i < clean.length) {
            if (clean[i] === '{') depth++;
            else if (clean[i] === '}') {
                depth--;
                if (depth === 0) break;
            }
            i++;
        }
        spans.push([m.index + m[0].length, i]); // inside the braces only
    }
    const chars = clean.split('');
    for (const [a, b] of spans) {
        for (let k = a; k < b && k < chars.length; k++) chars[k] = ' ';
    }
    return chars.join('');
}

// Declared type of one comma part of a parameter list ("const u8 *p" ->
// "u8", "struct S *p" -> "S", "x" -> undefined). Pointer vs. value is not
// distinguished, mirroring the curated struct model.
function paramType(part) {
    const toks = part.trim().replace(/\[[^\]]*\]/g, '').trim().split(/[\s*]+/).filter(Boolean);
    if (toks.length < 2) return undefined;
    const stop = new Set(['*'].concat(C_QUALIFIERS));
    let k = toks.length - 2;
    while (k >= 0 && stop.has(toks[k])) k--;
    return k >= 0 ? toks[k] : undefined;
}

function parseCDocumentSymbols(text, typeNames) {
    const out = [];
    // First pass: local type names join the known set so the second pass
    // recognizes declarators using them (`MySprite player;`).
    const local = parseLocalTypes(text);
    const known = new Set(C_TYPE_WORDS.concat(typeNames || [], local.types));
    // Struct fields must not parse as variables: the declarator pass runs
    // on text with struct/union bodies blanked (enum bodies are harmless).
    const clean = maskStructUnionBodies(stripCNoise(text));

    for (const t of local.types) out.push({ name: t, kind: 'type' });
    for (const cn of local.consts) out.push({ name: cn, kind: 'constant' });

    // Function definitions (and prototypes): TYPE [+]name(...) [+{]
    const reFn = /(?:^|[^A-Za-z0-9_])((?:(?:const|static|inline|extern|volatile|unsigned|signed|long|short|register)\s+)*)([A-Za-z_]\w*)\s*(\*(?:\s*\*)*)?\s*([A-Za-z_]\w*)\s*\(([^;{}]*)\)\s*(\{?)/g;
    let m;
    while ((m = reFn.exec(clean)) !== null) {
        const type = m[2];
        const name = m[4];
        if (!known.has(type) || C_NOISE.has(name)) continue;
        out.push({ name, kind: 'function', ofType: type, params: m[5] || '' });
    }

    // Parameters of the functions just found: last identifier of each
    // top-level comma part ("const u8 *p", "char buf[16]" -> p, buf),
    // carrying its declared type for receiver resolution.
    for (const fn of out) {
        if (fn.kind !== 'function' || !fn.params) continue;
        for (const part of fn.params.split(',')) {
            const pm = /([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*$/.exec(part.trim());
            if (pm && pm[1] && !known.has(pm[1]) && !C_NOISE.has(pm[1]) &&
                pm[1] !== 'void' && !C_QUALIFIERS.includes(pm[1])) {
                out.push({ name: pm[1], kind: 'param', ofType: paramType(part) });
            }
        }
        delete fn.params;
    }

    // Variable declarations: [qualifiers] TYPE [*] name [,;=\[)\s].
    // The type-set check keeps calls (`foo(bar)`), keywords (`if (x)`)
    // and member access out; the lookahead keeps definitions and
    // prototypes (`int f(`) out.
    const reVar = /(?:^|[;{}()\s,])((?:(?:const|static|extern|volatile|register|inline|unsigned|signed|long|short|struct|union|enum)\s+)*)([A-Za-z_]\w*)(\s*\*(?:\s*\*)*)?\s*([A-Za-z_]\w*)(?=[\s,;=)\[])/g;
    while ((m = reVar.exec(clean)) !== null) {
        const type = m[2];
        const name = m[4];
        if (!known.has(type) || C_NOISE.has(name) || known.has(name)) continue;
        out.push({ name, kind: 'variable', ofType: type });
        // Comma continuations: "TYPE a, b = 1, c;" — initializers without
        // commas/parens are skipped over; anything fancier ends the run.
        const cont = /^(?:\s*=\s*[^,;()]+)?((?:\s*,\s*[A-Za-z_]\w*(?:\s*=\s*[^,;()]+)?)+)(?=\s*;)/.exec(
            clean.slice(reVar.lastIndex));
        if (cont) {
            for (const cm of cont[1].matchAll(/[A-Za-z_]\w*/g)) {
                if (!known.has(cm[0]) && !C_NOISE.has(cm[0])) {
                    out.push({ name: cm[0], kind: 'variable', ofType: type });
                }
            }
        }
    }
    // Plain typedef aliases ("typedef int myint;", "typedef MySprite S2;",
    // "typedef struct S *PS;") introduce usable type names too. Runs on the
    // masked text, so braced aggregates never reach it (their aliases come
    // from parseLocalTypes; duplicates are deduped downstream).
    const reAlias = /typedef\s+([A-Za-z_][\w\s*]*?)\s+([A-Za-z_]\w*)\s*;/g;
    while ((m = reAlias.exec(clean)) !== null) {
        if (!C_NOISE.has(m[2])) out.push({ name: m[2], kind: 'type' });
    }
    // Trailing declarators of plain (non-typedef) aggregates at file scope
    // (`struct S { ... } myVar;`) are genuine file-scope variables.
    for (const v of local.vars) out.push({ name: v.name, kind: 'variable', ofType: v.ofType });
    // Variable -> declared-type bindings for receiver resolution (first
    // declaration wins; shadowing across scopes is not modeled).
    const typeOf = new Map();
    for (const s of out) {
        if (s.ofType && !typeOf.has(s.name)) typeOf.set(s.name, s.ofType);
    }
    return { symbols: out, members: local.members, typeOf };
}

function parsePascalDocumentSymbols(text) {
    const out = [];
    const clean = stripPascalNoise(text);
    let m;

    // FUNCTION / PROCEDURE names (fresher than the persisted scan).
    const reSub = /\b(?:function|procedure)\s+([A-Za-z_]\w*)\s*(?:\(([^)]*)\))?/gi;
    while ((m = reSub.exec(clean)) !== null) {
        out.push({ name: m[1].toUpperCase(), kind: 'function' });
        // Params: groups split by ';', names before ':' split by ','.
        const groups = (m[2] || '').split(';');
        for (const g of groups) {
            const cm = /^([^:]*):/.exec(g);
            if (!cm) continue;
            for (const nm of cm[1].split(',')) {
                const w = nm.trim();
                if (/^[A-Za-z_]\w*$/.test(w)) out.push({ name: w.toUpperCase(), kind: 'param' });
            }
        }
    }

    // var-block style declarations: name[, name...]: Type;
    const reVar = /\b([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*:\s*[A-Za-z_]\w*\s*;/gi;
    while ((m = reVar.exec(clean)) !== null) {
        for (const nm of m[1].split(',')) {
            const w = nm.trim();
            if (/^[A-Za-z_]\w*$/.test(w)) out.push({ name: w.toUpperCase(), kind: 'variable' });
        }
    }
    return out;
}

export function parseDocumentSymbols(text, hintKey, typeNames) {
    return parseDocumentModel(text, hintKey, typeNames).symbols;
}

// Full document model for the server: word symbols plus the struct member
// tables and variable->type bindings that receiver resolution needs.
export function parseDocumentModel(text, hintKey, typeNames) {
    const empty = { symbols: [], members: {}, typeOf: new Map() };
    try {
        if (hintKey === 'pascal') {
            return { symbols: parsePascalDocumentSymbols(text), members: {}, typeOf: new Map() };
        }
        if (hintKey === 'c' || hintKey === 'msxgl') {
            return parseCDocumentSymbols(text, typeNames);
        }
        return empty;
    } catch (e) {
        return empty;
    }
}

// Receiver chain before the caret, mirroring native-completions.js'
// text fallback: strip the trailing word, require a dangling "." / "->",
// then capture the identifier chain ("spr.attr." -> ["spr","attr"]).
// Returns {parts, word, from} or null.
export function memberChainBefore(text, offset) {
    const pos = Math.max(0, Math.min(offset, text.length));
    const lineStart = text.lastIndexOf('\n', pos - 1) + 1;
    const prefix = text.slice(lineStart, pos);
    const wm = /[A-Za-z_][A-Za-z0-9_]*$/.exec(prefix);
    const word = wm ? wm[0] : '';
    const stem = (word ? prefix.slice(0, -word.length) : prefix).replace(/[ \t]*$/, '');
    if (!/(->|\.)$/.test(stem)) return null;
    const cm = /([A-Za-z_]\w*(?:\s*(?:->|\.)\s*[A-Za-z_]\w*)*)\s*(?:->|\.)\s*$/.exec(stem);
    if (!cm) return null;
    const parts = cm[1].split(/(?:->|\.)/).map((s) => s.trim()).filter((s) => s.length > 0);
    if (!parts.length) return null;
    return { parts, word, from: pos - word.length };
}

function stripTypeName(t) {
    return String(t || '').replace(/\*/g, '').replace(/\[[^\]]*\]/g, '').trim();
}

function fieldsOf(structs, name) {
    const s = structs[stripTypeName(name)];
    return Array.isArray(s) ? s : null;
}

function memberFieldType(structs, structName, field) {
    const fields = fieldsOf(structs, structName);
    if (!fields) return null;
    const hit = fields.find((f) => f && f[1] === field);
    return hit ? hit[0] : null;
}

// Resolve a receiver chain to a struct's fields, filtered by the trailing
// word. Mirrors the curated resolver: the base is a declared variable (via
// typeOf) or a struct name itself, intermediate hops must themselves be
// structs, pointer vs. value is not distinguished. Returns LSP items
// (kind Field, detail = declared field type) or [].
export function resolveMemberItems(structs, typeOf, parts, word) {
    if (!parts || !parts.length) return [];
    const base = parts[0];
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(base)) return [];
    let cur = (typeOf && typeOf.has(base)) ? typeOf.get(base)
        : ((base in structs) ? base : null);
    if (!cur) return [];
    for (let i = 1; i < parts.length; i++) {
        const tok = parts[i];
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(tok)) return [];
        const nt = memberFieldType(structs, cur, tok);
        if (!nt || !(stripTypeName(nt) in structs)) return [];
        cur = stripTypeName(nt);
    }
    const fields = fieldsOf(structs, cur);
    if (!fields) return [];
    const lower = (word || '').toLowerCase();
    const seen = new Set();
    const out = [];
    for (const f of fields) {
        if (!f || !f[1] || seen.has(f[1])) continue;
        seen.add(f[1]);
        if (lower && f[1].toLowerCase().indexOf(lower) !== 0) continue;
        out.push({ label: f[1], kind: 5, detail: (f[0] || '').trim(), _boost: 0 });
    }
    out.forEach((m) => {
        if (lower && m.label.indexOf(word) === 0) m._boost = 20;
    });
    out.sort((a, b) => (b._boost - a._boost) ||
        (a.label < b.label ? -1 : a.label > b.label ? 1 : 0));
    return out.slice(0, MAX_ITEMS).map((m) => ({
        label: m.label, kind: m.kind, detail: m.detail,
    }));
}
