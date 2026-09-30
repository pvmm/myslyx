// Myslyx Text Editor - local-only LSP completions for C / C MSXgl
// (the "local-lsp" plugin; machine-installed LSP servers via myslyx/lsp.py).
//
// When the server has an LSP configured and this is a local run
// (window.__wbLsp.enabled && window.__wbLocal), completions come from the
// server-side LSP session (myslyx/lsp.py) over the HTTP bridge:
//
//     POST /wb/lsp/ping      capability + connectivity check
//     POST /wb/lsp/complete  buffer round trip -> CompletionItems
//
// The plugin joins both editor popups:
//   - C MSXgl completes through CodeMirror's NATIVE popup via a completion
//     source appended with EditorState.languageData "autocomplete" (the same
//     mechanism native-completions.js uses); LSP results augment the curated
//     msxgl hints automatically.
//   - plain C keeps the CUSTOM .wb-autocomplete-popup through a
//     WBHintCompletions provider, which is allowed to return a Promise (see
//     hints.js).
//
// It is a "boot" + "onlyLocal" plugin (plugin.json): it only activates on a
// local machine. If the LSP cannot be reached (binary fails to start, the
// handshake breaks, the network errors) the plugin disables itself for the
// page session, shows one retro toast, and lets the editor fall back to the
// curated hints dictionaries.
const MAX_ROWS = 200;

// Shared, page-level bridge state (the module is imported exactly once).
let bridge = {
    ready: false,    // the ping has settled
    working: false,  // the ping proved the LSP is reachable
    disabled: false, // hard-disable for this page session
    toasted: false,  // the toast is shown at most once
};

function api() {
    return window.__wbLsp;
}

function available() {
    return !!(api() && api().enabled && window.__wbLocal !== false);
}

function disable(msg) {
    if (bridge.disabled) return;
    bridge.disabled = true;
    // Observed by the test suite; re-enabled only on the next page load.
    window.__wbLspAutodisabled = true;
    // The in-browser LSP plugin (weblsp) reads this to decide whether the
    // local bridge is serving the current file: while it is true, weblsp
    // stands down its completion sources so exactly one language server
    // answers each popup (hover/signature stay with the worker, which the
    // bridge does not provide).
    window.__wbLocalLspWorking = false;
    toast('LSP unavailable: ' + msg);
}

function toast(msg) {
    if (bridge.toasted) return;
    bridge.toasted = true;
    const el = document.createElement('div');
    el.id = 'wb-lsp-toast';
    el.textContent = msg;
    Object.assign(el.style, {
        position: 'fixed',
        left: '16px',
        bottom: '16px',
        zIndex: '10000',
        fontFamily: 'var(--wb-font, monospace)',
        fontSize: '12px',
        color: '#fff',
        background: '#aa0000',
        border: '2px solid #fff',
        padding: '8px 14px',
        maxWidth: '60vw',
        cursor: 'pointer',
    });
    document.body.appendChild(el);
    const dismiss = function() { el.remove(); };
    el.addEventListener('click', dismiss);
    setTimeout(dismiss, 4000);
}

// Page-level flag read by the weblsp plugin for completion mutual
// exclusion (see disable()). False until the ping proves the bridge works.
window.__wbLocalLspWorking = false;

// One connectivity probe per page load. A failure disables the bridge before
// the user ever types, so the curated hints keep working immediately.
function startBridge() {
    if (bridge.ready) return;
    bridge.ready = true;
    fetch('/wb/lsp/ping', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
    })
        .then(function(r) {
            return r.json().catch(function() {
                return { enabled: false, error: 'bad LSP ping response' };
            });
        })
        .then(function(j) {
            if (j && j.enabled === true) {
                bridge.working = true;
                window.__wbLocalLspWorking = true;
                return;
            }
            disable((j && j.error) || 'LSP not reachable');
        })
        .catch(function() {
            disable('cannot reach the LSP bridge');
        });
}

// One completion round trip. Resolves to the mapped items; on any failure it
// disables the bridge and resolves to null so curated sources take over.
function completeRequest(params) {
    if (bridge.disabled || !bridge.working) return Promise.resolve(null);
    return fetch('/wb/lsp/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
    })
        .then(function(r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        })
        .then(function(j) {
            if (!j || j.enabled === false) {
                throw new Error((j && j.error) || 'LSP disabled by the server');
            }
            return j.items || [];
        })
        .catch(function(err) {
            disable((err && err.message) || 'completion failed');
            return null;
        });
}

function bufferParams(state, pos) {
    const line = state.doc.lineAt(pos);
    return {
        fid: window.__wbActiveFid || '',
        language: window.__wbCurrentLang || 'C',
        name: '',
        content: state.doc.toString(),
        line: line.number - 1,
        character: pos - line.from,
    };
}

function tidyRow(it) {
    const row = { label: it.label, detail: it.detail, type: it.type };
    if (it.apply) row.apply = it.apply;
    if (typeof it.boost === 'number') row.boost = it.boost;
    return row;
}

// Partial `#include` file name on the caret's line: {delimiter, prefix} or
// null (open delimiter required; mirrors the weblsp plugin + worker).
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
// an already-typed filename suffix) and appends the closing bracket unless
// it is already there; caret lands after the closer.
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

// ---- plain C: custom WBHintCompletions provider (async) ----------------
function customProvider(pctx) {
    if (bridge.disabled) return null;
    if (!bridge.ready || !bridge.working) return null;
    if ((window.__wbCurrentLang || '') !== 'C') return null;
    const state = pctx.view.state;
    const pos = state.selection.main.head;
    // Inside an include line, string-apply the closing bracket (unless it
    // is already there); insertCompletion honors `apply`.
    const inc = includePrefix(state, pos);
    const closer = inc !== null ? includeCloser(inc.delimiter) : null;
    const afterWord = closer !== null ? pctx.line.slice(pctx.col, pctx.col + 1) : '';
    return completeRequest(bufferParams(state, pos)).then(function(items) {
        if (!items || !items.length) return [];
        // No client-side filtering: clangd scored and ranked these (its
        // fuzzy matches included); re-filtering here would strip them.
        return items
            .slice(0, MAX_ROWS)
            .map(function(it) {
                const row = tidyRow(it);
                if (closer !== null && /\.h$/i.test(it.label || '') && afterWord !== closer) {
                    row.apply = it.label + closer;
                }
                return row;
            });
    });
}

if (window.WBHintCompletions) {
    window.WBHintCompletions.register('local-lsp', customProvider);
}

// ---- C MSXgl: native CodeMirror completion source ----------------------
export default function localLspPlugin(CM) {
    if (!available()) return [];
    startBridge();

    const localLspNativeSource = async function(ctx) {
        try {
            if (bridge.disabled) return null;
            if (!bridge.ready || !bridge.working) return null;
            if ((window.__wbHintKey || 'c') !== 'msxgl') return null;
            const state = ctx.state;
            const pos = ctx.pos;
            // `#include` file completion closes its bracket on accept;
            // clangd mixes words and headers, so only header-looking labels
            // get the closer treatment.
            const inc = includePrefix(state, pos);
            if (inc !== null) {
                const closer = includeCloser(inc.delimiter);
                const items = await completeRequest(bufferParams(state, pos));
                if (!items || !items.length) return null;
                const options = items
                    .slice(0, MAX_ROWS)
                    .map(function(it) {
                        const row = tidyRow(it);
                        if (typeof row.boost !== 'number') row.boost = 0;
                        if (/\.h$/i.test(it.label || '')) row.apply = makeIncludeApply(closer);
                        return row;
                    });
                if (!options.length) return null;
                const suffix = (/[A-Za-z0-9_./\\]*/.exec(state.sliceDoc(pos)) || [''])[0].length;
                return { from: pos - inc.prefix.length, to: pos + suffix, options: options };
            }
            const w = ctx.matchBefore(/[A-Za-z_][A-Za-z0-9_]*/);
            if (!w || (!ctx.explicit && !w.text)) return null;
            const items = await completeRequest(bufferParams(ctx.state, ctx.pos));
            if (!items || !items.length) return null;
            const options = items
                .slice(0, MAX_ROWS)
                .map(function(it) {
                    const row = tidyRow(it);
                    if (typeof row.boost !== 'number') row.boost = 0;
                    return row;
                });
            return options.length ? { from: w.from, options: options } : null;
        } catch (e) {
            disable('completion failed');
            return null;
        }
    };

    const config = CM.EditorState.languageData.of(function() {
        return [{ autocomplete: localLspNativeSource }];
    });
    return [config];
}