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
// to a struct TYPE via the document model (struct definitions, declared
// variables, multi-declarators, pointers/const/arrays, function parameters)
// and that struct's fields become the completions, with the field type shown
// as detail. Member chains (a.b.c) are resolved recursively through structs
// whose definition is known: in-file definitions plus the "structs" map of
// the active hints JSON (myslyx/static/hints/<key>.json, e.g. msxgl.json).
// Pointer vs. value is deliberately not distinguished.
'use strict';

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

    function stripComment(line) {
        var i = line.indexOf('//');
        if (i >= 0) line = line.slice(0, i);
        i = line.indexOf('/*');
        if (i >= 0) line = line.slice(0, i);
        return line;
    }

    // Reduce a declared type to its base struct-name candidate: drop
    // qualifiers, the struct/union keyword, trailing pointer stars and the
    // members' array suffixes ("char name[8]" -> "char").
    function baseType(raw) {
        var t = (raw || '').trim()
            .replace(/^(const|static|volatile|register|inline|signed|unsigned|struct|union)\s+/i, '')
            .replace(/\s*\*+\s*$/, '')
            .replace(/\[[^\]]*\]/g, '')
            .trim();
        return t || null;
    }

    function parseModel(doc) {
        var lines = doc.split('\n');
        var structs = {};   // struct tag/alias -> [{name,type,raw},...]
        var i = 0;

        function extractFieldsFromText(text, fields) {
            var chunks = text.split(';');
            for (var c = 0; c < chunks.length; c++) {
                var fm = chunks[c].trim();
                if (!fm || fm.indexOf('{') >= 0 || fm.indexOf('}') >= 0 || fm.indexOf('(') >= 0) continue;
                var m = /^([A-Za-z_][\w\s\*.]*?)\s+([A-Za-z_]\w*)\s*(\[[^\]]*\])?\s*(:.*)?$/.exec(fm);
                if (!m) continue;
                var bt = baseType(m[1]);
                if (bt) fields.push({ name: m[2], type: bt, raw: m[1].trim() });
            }
        }

        function scanFields(openIdx) {
            var fields = [];
            var depth = 0;
            for (var j = openIdx; j < lines.length; j++) {
                var text = stripComment(lines[j]);
                var open = (text.match(/\{/g) || []).length;
                var close = (text.match(/\}/g) || []).length;
                var delta = open - close;
                if (j === openIdx) {
                    // Consume an inline body on the opener line ("typedef
                    // struct { u8 x; u8 y; } Point;") plus any following brace-
                    // balanced lines until the matching "};".
                    var inline = text.indexOf('{') >= 0 ? text.slice(text.indexOf('{') + 1) : '';
                    extractFieldsFromText(inline, fields);
                    depth = delta;
                    if (depth <= 0) break;
                    continue;
                }
                extractFieldsFromText(text, fields);
                depth += delta;
                if (depth <= 0) break;
            }
            return fields;
        }

        // Pass 1: struct definitions. Supports:
        //   typedef struct Tag { ... } Alias;   typedef struct { ... } Alias;
        //   struct Tag { ... };
        while (i < lines.length) {
            var line = stripComment(lines[i]).trim();
            if (/^typedef\s+struct\b/i.test(line) || /^struct\s+[A-Za-z_]\w*\s*\{/.test(line)) {
                var tag = null;
                var tm = /^typedef\s+struct\s+([A-Za-z_]\w*)/i.exec(line);
                if (tm) tag = tm[1];
                var openIdx = i;
                if (line.indexOf('{') < 0) {
                    for (var k = i + 1; k < Math.min(i + 6, lines.length); k++) {
                        if (stripComment(lines[k]).indexOf('{') >= 0) { openIdx = k; break; }
                    }
                }
                var fields = scanFields(openIdx);
                var alias = null;
                var endIdx = null;
                // The closing "} Alias;" may sit on the opener line itself
                // ("typedef struct { u8 x; } Point;") or on a later line.
                var lastClose = line.lastIndexOf('}');
                if (lastClose >= 0) {
                    var am = /^([A-Za-z_]\w*)$/.exec(
                        line.slice(lastClose + 1).replace(/;.*$/, '').trim());
                    if (am) { alias = am[1]; endIdx = i; }
                }
                for (var k2 = openIdx; endIdx === null && k2 < Math.min(openIdx + 500, lines.length); k2++) {
                    var closeLine = stripComment(lines[k2]).trim();
                    if (/^\};\s*$/.test(closeLine)) { endIdx = k2; break; }
                    var cm = /^\}\s*([A-Za-z_]\w*)\s*;?$/.exec(closeLine);
                    if (cm) { alias = cm[1]; endIdx = k2; break; }
                }
                var members = fields.map(function(f) {
                    return { name: f.name, type: f.type, raw: f.raw };
                });
                if (alias) structs[alias] = members;
                if (tag) structs[tag] = members;
                i = endIdx !== null ? endIdx + 1 : openIdx + 1;
            } else {
                i++;
            }
        }

        return structs;
    }

    // Collect variable/parameter declarations. Any "<known struct name>
    // <declarator>" maps the declarator to that struct. A name followed by
    // '(' is a function (return type), not a variable. Multi-declarators
    // ("Foo a, b, c;") and pointer declarators ("Foo *p, *q") are collected
    // from the rest of the statement. "structNames" is the merged set of
    // struct names known so far (in-file + framework hints data).
    function collectVars(doc, structNames) {
        var vars = {};
        if (!structNames.length) return vars;
        var esc = function(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); };
        function collect(chunk, out) {
            var stmt = stripComment(chunk);
            for (var s = 0; s < structNames.length; s++) {
                var tn = structNames[s];
                var re = new RegExp('(?:^|[^A-Za-z0-9_.>~])' + esc(tn) +
                    '\\s+(?:const\\s+)?(?:\\*\\s*)*([A-Za-z_][A-Za-z0-9_]*)\\b', 'g');
                var m;
                while ((m = re.exec(stmt)) !== null) {
                    var name = m[1];
                    var rest = stmt.slice(m.index + m[0].length);
                    if (/^\s*\(/.test(rest)) continue; // function definition
                    out[name] = tn;
                    // Declarators following commas inside this statement.
                    var decls = rest.split(',');
                    for (var d = 0; d < decls.length; d++) {
                        var part = decls[d]
                            .replace(/=.*$/, '')
                            .replace(/\[[^\]]*\]/g, '')
                            .replace(/^\s*\*+\s*/, '')
                            .trim();
                        var dm = /^([A-Za-z_][A-Za-z0-9_]*)/.exec(part);
                        if (dm) out[dm[1]] = tn;
                    }
                }
            }
        }

        var stmtRe = /[^;\n]+/g;
        var stm;
        while ((stm = stmtRe.exec(doc)) !== null) {
            var stmt = stm[0].trim();
            if (!stmt || stmt.charAt(0) === '#') continue;
            collect(stmt, vars);
        }
        // Parameter lists: "(Foo * p, Bar * q)" — each comma-separated chunk
        // carries its own type prefix, so run the collector on each.
        var pRe = /\(([^()]*)\)/g;
        var pm;
        while ((pm = pRe.exec(doc)) !== null) {
            var pbody = pm[1];
            if (/\{|\}/.test(pbody)) continue;
            pbody.split(',').forEach(function(chunk) {
                if (chunk.trim()) collect(chunk, vars);
            });
        }

        return vars;
    }

    function ensureModel(doc) {
        var fp = doc.length + '|' + (doc.match(/\n/g) || []).length;
        if (modelFingerprint !== fp) {
            modelFingerprint = fp;
            model = parseModel(doc);
        }
        return model;
    }

    function membersOf(allStructs, name) {
        return allStructs[name] || null;
    }

    function memberNamed(allStructs, structName, name) {
        var list = membersOf(allStructs, structName);
        if (!list) return null;
        for (var i = 0; i < list.length; i++) {
            if (list[i].name === name) return list[i];
        }
        return null;
    }

    function fieldsToShow(allStructs, structName, word) {
        var list = membersOf(allStructs, structName);
        if (!list || !list.length) return [];
        var lower = (word || '').toLowerCase();
        var out = [];
        for (var i = 0; i < list.length; i++) {
            var f = list[i];
            if (lower && f.name.toLowerCase().indexOf(lower) !== 0) continue;
            out.push({ label: f.name, detail: f.raw || f.type });
        }
        return out;
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