// Myslyx Text Editor - in-browser LSP completions for hinted languages.
//
// The "weblsp" plugin: a real vscode-languageserver server runs inside a Web
// Worker (the committed worker.bundle.js, built by tools/weblsp/) and serves
// completion + hover + signatureHelp from the SAME generated hints
// dictionaries (static/hints/<key>.json) that feed the sidebar and popups,
// plus the user's own exported symbols. It works on every deployment —
// including shared/remote ones where the machine-installed bridge behind the
// "local-lsp" plugin can never run.
//
// UI integration mirrors the local-lsp plugin:
//   - C MSXgl and Pascal complete through CodeMirror's NATIVE popup via a
//     completion source appended with EditorState.languageData
//     "autocomplete". While the worker is ready, native-completions.js stands
//     down for those keys (window.__wbWebLspReady) so each label completes
//     exactly once; if the worker fails it clears the flag and the curated
//     sources take over again.
//   - plain C keeps the CUSTOM .wb-autocomplete-popup through an async
//     WBHintCompletions provider (first-non-null wins; null defers to the
//     curated default path).
// Hover uses CM's hoverTooltip; signature help renders a small fixed retro
// box (#wb-sighelp) fed by the worker's textDocument/signatureHelp.
import { getClient, kindToType } from './client.js';

const MAX_ROWS = 200;

let customRegistered = false;

// The current language, resolved by the editor (window.WBLanguage, built in
// retro.js from the server-set __wbBaseLang/__wbHintKey attributes). Nothing
// here names a language: a family joins the worker simply by existing in
// WBLanguage's table, so plain C and C MSXgl are both served as base 'c'.
function lang() {
    return window.WBLanguage;
}

function served() {
    return !!lang().hasFamily();
}

// Mutual exclusion with the machine-installed bridge (local-lsp plugin):
// while it is actually serving the current file, the worker stands down its
// completion sources so exactly one language server answers each popup.
// Mirrors local-lsp's own gate (it drives clangd/SDCC, so it never claims
// Pascal) — and only completions stand down: hover and signature help stay
// with the worker, which the bridge does not provide.
function localBridgeServing() {
    return !!(window.__wbLocalLspWorking && lang().localLspServes());
}

function esc(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function mdToHtml(md) {
    try {
        if (window.marked && typeof window.marked.parse === 'function') {
            return window.marked.parse(md);
        }
    } catch (e) {}
    return '<pre>' + esc(md) + '</pre>';
}

function wordRange(state, pos) {
    let s = Math.max(0, Math.min(pos, state.doc.length));
    let e = s;
    while (s > 0 && /[A-Za-z0-9_]/.test(state.sliceDoc(s - 1, s))) s--;
    while (e < state.doc.length && /[A-Za-z0-9_]/.test(state.sliceDoc(e, e + 1))) e++;
    return { from: s, to: e };
}

// Partial `#include` file name on the caret's line: {delimiter, prefix} or
// null. Mirrors the worker's includeContext (open delimiter required: a
// closed include must never query, otherwise an empty word would fetch the
// whole dictionary).
function includePrefix(state, pos) {
    const line = state.doc.lineAt(pos);
    const tail = state.sliceDoc(line.from, pos);
    const m = /#\s*include\s*([<"])([^>"]*)$/.exec(tail);
    if (!m) return null;
    if (m[2] === '') {
        const opens = (tail.match(m[1] === '"' ? /"/g : /</g) || []).length;
        if (opens % 2 === 0) return null;
    }
    return { delimiter: m[1], prefix: m[2] || '' };
}

function includeCloser(delimiter) {
    return delimiter === '<' ? '>' : '"';
}

// Native-popup apply for include options: replaces the partial name (plus
// any already-typed suffix like `.h`) and appends the closing bracket,
// unless it is already there. Caret lands after the closer.
function makeIncludeApply(closer) {
    return function(view, completion, from, to) {
        let insert = completion.label;
        if (view.state.sliceDoc(to, to + 1) !== closer) insert += closer;
        view.dispatch({
            changes: { from: from, to: to, insert: insert },
            selection: { anchor: from + insert.length },
            scrollIntoView: true,
        });
    };
}

// ---- custom .wb-autocomplete-popup provider (async) ------------------------
// Languages the editor renders in the retro popup. The worker's member path
// stays out: that context belongs to the c-struct-complete plugin, which owns
// the popup's member completion.
function customProvider(pctx) {
    const client = getClient();
    if (!client.isReady()) return null;
    if (!served()) return null;
    if (lang().usesNativePopup()) return null;
    if (localBridgeServing()) return null;
    const state = pctx.view.state;
    const pos = state.selection.main.head;
    // Member contexts stay with the c-struct-complete plugin (it owns the
    // custom popup's member path); the worker only feeds word completions
    // here. matchBefore cannot see receivers, so detect from the line.
    const line = state.doc.lineAt(pos);
    if (/(->|\.)\s*([A-Za-z_][A-Za-z0-9_]*)?$/.test(state.sliceDoc(line.from, pos))) return null;
    // Empty word: only answer open `#include <|"` contexts (full header
    // list); anything else (e.g. `;`, closed includes) stays silent instead
    // of fetching the whole dictionary.
    const inc = includePrefix(state, pos);
    if (!pctx.word && inc === null) return null;
    // Inside an include line, string-apply the closing bracket (unless it
    // is already there); insertCompletion honors `apply`.
    const closer = inc !== null ? includeCloser(inc.delimiter) : null;
    const afterWord = closer !== null ? pctx.line.slice(pctx.col, pctx.col + 1) : '';
    return client.complete(state, pos).then(function(items) {
        if (!items || !items.length) return null;
        // No client-side filtering: the server scored, sorted and capped
        // these (substring tiers included); re-filtering here would strip
        // substring matches. Order is the server's ranking.
        const rows = items
            .slice(0, MAX_ROWS)
            .map(function(it) {
                const row = { label: it.label, detail: it.detail || '', type: kindToType(it.kind) };
                if (closer !== null && /\.h$/i.test(it.label || '') && afterWord !== closer) {
                    row.apply = it.label + closer;
                }
                return row;
            });
        return rows.length ? rows : null;
    }).catch(function() { return null; });
}

// ---- C MSXgl + Pascal: native CodeMirror completion source ----------------
// The server scored, sorted and capped these (substring tiers included);
// the client passes them through with their boosts. CodeMirror adds its own
// fuzzy score on top, but the tier gaps (10000/5000/1000) dwarf its spread,
// so the server ranking survives exactly — including substring hits, which
// CodeMirror's default fuzzy filter passes natively (and highlights).
function tidyOptions(items) {
    return items
        .slice(0, MAX_ROWS)
        .map(function(it) {
            return {
                label: it.label,
                detail: it.detail || '',
                type: kindToType(it.kind),
                boost: (it.boost != null ? it.boost : 0),
            };
        });
}

async function weblspNativeSource(ctx) {
    try {
        if (!served()) return null;
        if (!lang().usesNativePopup()) return null;
        if (localBridgeServing()) return null;
        const client = getClient();
        if (!client.isReady()) return null;
        const state = ctx.state;
        const pos = ctx.pos;
        // `#include` file completion: the worker knows the header lists
        // (standard C, engine modules) and the project's own .h files.
        // matchBefore cannot see past the delimiter, so detect from the
        // line prefix; the server re-validates (closed includes answer
        // null) and families without headers (Pascal) never match.
        const inc = includePrefix(state, pos);
        if (inc !== null) {
            const closer = includeCloser(inc.delimiter);
            const items = await client.complete(state, pos);
            if (!items || !items.length) return null;
            const options = tidyOptions(items).map(function(o) {
                o.apply = makeIncludeApply(closer);
                return o;
            });
            // Extend through an already-typed filename suffix (e.g. the
            // `.h` in `"mydefs|.h"`) so accepting replaces it instead of
            // duplicating it; the apply step still skips a present closer.
            const suffix = (/[A-Za-z0-9_./\\]*/.exec(state.sliceDoc(pos)) || [''])[0].length;
            const from = pos - inc.prefix.length;
            return options.length
                ? { from: from, to: pos + suffix, options: options } : null;
        }
        // Member context (dangling ./->, possibly with a partial field
        // word): the worker resolves struct/union fields. matchBefore
        // cannot see the receiver, so detect it from the line prefix instead.
        const lineTail = state.sliceDoc(state.doc.lineAt(pos).from, pos);
        const mm = /(->|\.)\s*([A-Za-z_][A-Za-z0-9_]*)?$/.exec(lineTail);
        if (mm) {
            const word = mm[2] || '';
            const items = await client.complete(state, pos);
            if (!items || !items.length) return null;
            const options = tidyOptions(items);
            return options.length ? { from: pos - word.length, options: options } : null;
        }
        const w = ctx.matchBefore(/[A-Za-z_][A-Za-z0-9_]*/);
        if (!w || (!ctx.explicit && !w.text)) return null;
        const items = await client.complete(state, pos);
        if (!items || !items.length) return null;
        const options = tidyOptions(items);
        return options.length ? { from: w.from, options: options } : null;
    } catch (e) {
        return null;
    }
}

// ---- hover ----------------------------------------------------------------
function hoverExtension(CM) {
    if (!CM.hoverTooltip) return [];
    return CM.hoverTooltip(async function(view, pos) {
        try {
            if (!served()) return null;
            const client = getClient();
            if (!client.isReady()) return null;
            const h = await client.hover(view.state, pos);
            if (!h || !h.markdown) return null;
            const r = wordRange(view.state, pos);
            if (r.from >= r.to) return null;
            return {
                pos: r.from,
                end: r.to,
                create: function() {
                    const dom = document.createElement('div');
                    dom.className = 'wb-weblsp-hover';
                    dom.style.maxWidth = '420px';
                    dom.style.fontFamily = 'var(--wb-font, monospace)';
                    dom.style.fontSize = '9px';
                    dom.innerHTML = mdToHtml(h.markdown);
                    return { dom: dom };
                },
            };
        } catch (e) {
            return null;
        }
    });
}

// ---- signature help (fixed retro box) -------------------------------------
function sigBox() {
    let el = document.getElementById('wb-sighelp');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'wb-sighelp';
    el.style.display = 'none';
    el.style.position = 'fixed';
    el.style.left = '16px';
    el.style.bottom = '16px';
    el.style.zIndex = '10000';
    el.style.maxWidth = 'min(640px, 90vw)';
    el.style.background = 'var(--wb-black, #000)';
    el.style.color = 'var(--wb-white, #fff)';
    el.style.border = '2px solid var(--wb-white, #fff)';
    el.style.padding = '8px 10px';
    el.style.fontFamily = 'var(--wb-font, monospace)';
    el.style.fontSize = '9px';
    el.style.whiteSpace = 'pre-wrap';
    document.body.appendChild(el);
    return el;
}

function hideSigBox() {
    try {
        const el = document.getElementById('wb-sighelp');
        if (el) el.style.display = 'none';
    } catch (e) {}
}

function showSigBox(res) {
    try {
        const sig = res.signatures[0];
        const active = Math.min(res.activeParameter || 0, (sig.parameters || []).length - 1);
        const param = (sig.parameters || [])[active];
        const el = sigBox();
        let html = '<div><code>' + esc(sig.label) + '</code></div>';
        if (param) {
            html += '<div style="margin-top:6px;opacity:0.9">`' + esc(param.label) + '`' +
                (param.documentation ? ' — ' + esc(
                    typeof param.documentation === 'string'
                        ? param.documentation : (param.documentation.value || '')) : '') +
                '</div>';
        }
        el.innerHTML = html;
        el.style.display = 'block';
    } catch (e) {
        hideSigBox();
    }
}

let sigTimer = 0;

function scheduleSigCheck(view, client) {
    try { clearTimeout(sigTimer); } catch (e) {}
    sigTimer = setTimeout(function() { checkSig(view, client); }, 150);
}

async function checkSig(view, client) {
    try {
        if (!served()) { hideSigBox(); return; }
        if (!client.isReady()) { hideSigBox(); return; }
        const state = view.state;
        const pos = state.selection.main.head;
        // Cheap pre-check: the caret sits inside a call's parens on the
        // recent text (stops at statement/block boundaries).
        const behind = state.sliceDoc(Math.max(0, pos - 300), pos);
        if (!/[\(,]\s*[^;{}()]*$/.test(behind)) { hideSigBox(); return; }
        const res = await client.signature(state, pos);
        if (!res || !res.signatures || !res.signatures.length) { hideSigBox(); return; }
        // Stale response (the caret moved while the worker answered)?
        if (view.state.selection.main.head !== pos) return;
        showSigBox(res);
    } catch (e) {
        hideSigBox();
    }
}

function signatureExtension(CM) {
    if (!CM.ViewPlugin) return [];
    const client = getClient();
    return CM.ViewPlugin.fromClass(class {
        update(update) {
            if (update.docChanged || update.selectionSet) {
                try { client.scheduleContext(); } catch (e) {}
                scheduleSigCheck(update.view, client);
            }
        }
        destroy() {
            try { clearTimeout(sigTimer); } catch (e) {}
        }
    });
}

export default function weblspPlugin(CM) {
    const client = getClient();
    // Spawn + handshake at boot so the worker is warm for the first keystroke.
    // Idempotent: the module is imported exactly once per page.
    client.ensureWorker();
    if (!customRegistered && window.WBHintCompletions) {
        customRegistered = true;
        window.WBHintCompletions.register('weblsp', customProvider);
    }
    const nativeConfig = CM.EditorState.languageData.of(function() {
        return [{ autocomplete: weblspNativeSource }];
    });
    return [nativeConfig].concat(hoverExtension(CM), signatureExtension(CM));
}
