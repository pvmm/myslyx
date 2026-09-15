// Myslyx Text Editor - shared C struct document model.
//
// The structural model behind C member completion: struct definitions,
// declared variable/function-parameter bindings and the base-type reducer.
// Both the c-struct-complete plugin (custom popup for plain C) and
// native-completions (native autocomplete for C MSXgl) import this module so
// they always resolve rows like "pos.x" through the same tables.
//
// Caveat: pointer vs. value is deliberately not distinguished; a declared
// "Foo *p" and a plain "Foo p" both resolve to the same struct fields.

export function stripComment(line) {
    var i = line.indexOf('//');
    if (i >= 0) line = line.slice(0, i);
    i = line.indexOf('/*');
    if (i >= 0) line = line.slice(0, i);
    return line;
}

// Reduce a declared type to its base struct-name candidate: drop
// qualifiers, the struct/union keyword, trailing pointer stars and the
// members' array suffixes ("char name[8]" -> "char").
export function baseType(raw) {
    var t = (raw || '').trim()
        .replace(/^(const|static|volatile|register|inline|signed|unsigned|struct|union)\s+/i, '')
        .replace(/\s*\*+\s*$/, '')
        .replace(/\[[^\]]*\]/g, '')
        .trim();
    return t || null;
}

export function parseModel(doc) {
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
export function collectVars(doc, structNames) {
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

export function membersOf(allStructs, name) {
    return allStructs[name] || null;
}

export function memberNamed(allStructs, structName, name) {
    var list = membersOf(allStructs, structName);
    if (!list) return null;
    for (var i = 0; i < list.length; i++) {
        if (list[i].name === name) return list[i];
    }
    return null;
}

export function fieldsToShow(allStructs, structName, word) {
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