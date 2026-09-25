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
const SERVED_KEYS = { c: 1, msxgl: 1, pascal: 1 };

let customRegistered = false;

function servedKey() {
    const k = window.__wbHintKey || 'c';
    return !!SERVED_KEYS[k];
}

// Mutual exclusion with the machine-installed bridge (local-lsp plugin):
// while it is actually serving the current file, the worker stands down its
// completion sources so exactly one language server answers each popup.
// Mirrors local-lsp's own gates — it serves plain C and C MSXgl, never
// Pascal — and only completions stand down: hover and signature help stay
// with the worker, which the bridge does not provide.
function localBridgeServing() {
    if (!window.__wbLocalLspWorking) return false;
    const lang = window.__wbCurrentLang || '';
    const key = window.__wbHintKey || 'c';
    return lang === 'C' || key === 'msxgl';
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

// ---- plain C: custom WBHintCompletions provider (async) --------------------
function customProvider(pctx) {
    const client = getClient();
    if (!client.isReady()) return null;
    if ((window.__wbCurrentLang || '') !== 'C') return null;
    if (localBridgeServing()) return null;
    const state = pctx.view.state;
    const pos = state.selection.main.head;
    // Member contexts stay with the c-struct-complete plugin (it owns the
    // custom popup's member path); the worker only feeds word completions
    // here. matchBefore cannot see receivers, so detect from the line.
    const line = state.doc.lineAt(pos);
    if (/(->|\.)\s*([A-Za-z_][A-Za-z0-9_]*)?$/.test(state.sliceDoc(line.from, pos))) return null;
    return client.complete(state, pos).then(function(items) {
        if (!items || !items.length) return null;
        const prefix = (pctx.word || '').toLowerCase();
        const rows = items
            .filter(function(it) {
                return !prefix || (it.label || '').toLowerCase().indexOf(prefix) === 0;
            })
            .slice(0, MAX_ROWS)
            .map(function(it) {
                return { label: it.label, detail: it.detail || '', type: kindToType(it.kind) };
            });
        return rows.length ? rows : null;
    }).catch(function() { return null; });
}

// ---- C MSXgl + Pascal: native CodeMirror completion source ----------------
function tidyOptions(items, prefix) {
    const lower = (prefix || '').toLowerCase();
    return items
        .filter(function(it) {
            return !lower || (it.label || '').toLowerCase().indexOf(lower) === 0;
        })
        .slice(0, MAX_ROWS)
        .map(function(it) {
            return { label: it.label, detail: it.detail || '', type: kindToType(it.kind) };
        });
}

async function weblspNativeSource(ctx) {
    try {
        const key = window.__wbHintKey || 'c';
        if (key !== 'msxgl' && key !== 'pascal') return null;
        if (key === 'msxgl' && localBridgeServing()) return null;
        const client = getClient();
        if (!client.isReady()) return null;
        const state = ctx.state;
        const pos = ctx.pos;
        // Member context (dangling "./->", possibly with a partial field
        // word): the worker resolves struct/union fields. matchBefore
        // cannot see the receiver, so detect it from the line prefix; the
        // server validates and filters. Pascal has no struct tables, so its
        // member queries always answer null server-side.
        const line = state.doc.lineAt(pos);
        const tail = state.sliceDoc(line.from, pos);
        const mm = /(->|\.)\s*([A-Za-z_][A-Za-z0-9_]*)?$/.exec(tail);
        if (mm) {
            const word = mm[2] || '';
            const items = await client.complete(state, pos);
            if (!items || !items.length) return null;
            const options = tidyOptions(items, word);
            return options.length ? { from: pos - word.length, options: options } : null;
        }
        const w = ctx.matchBefore(/[A-Za-z_][A-Za-z0-9_]*/);
        if (!w || (!ctx.explicit && !w.text)) return null;
        const items = await client.complete(state, pos);
        if (!items || !items.length) return null;
        const options = tidyOptions(items, w.text);
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
            if (!servedKey()) return null;
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
        if (!servedKey()) { hideSigBox(); return; }
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
