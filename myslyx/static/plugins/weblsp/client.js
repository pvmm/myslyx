// Myslyx in-browser LSP - main-thread JSON-RPC client (plain ES module).
//
// Speaks raw LSP JSON-RPC objects to the worker bundle over
// worker.postMessage / onmessage (the vscode-languageserver browser
// transport needs no Content-Length framing). One client per page
// (module singleton); document sync is full-text and race-free: the exact
// buffer a request was computed from is pushed (didOpen once per file,
// didChange when it differs) before the request goes out.
//
// Failure policy mirrors the local-lsp plugin: any transport/handshake
// failure hard-disables the client for the page session (clearing
// window.__wbWebLspReady so the curated sources take over) with one retro
// toast. Observed by the test suite via window.__wbWebLsp.
const BUNDLE_URL = new URL('./worker.bundle.js', import.meta.url).href;
const HANDSHAKE_TIMEOUT = 10000;
const REQUEST_TIMEOUT = 5000;
const MAX_ROWS = 200;

const KIND_TYPE = {
    3: 'function',
    14: 'keyword',
    17: 'file',
    22: 'type',
    21: 'constant',
    5: 'field',
    6: 'variable',
};

// User-discovered symbols (functions/subroutines). Mirrors
// native-completions.js::getAllSymbols: a file with global export disabled
// only contributes while it is the one being edited.
function getAllSymbols() {
    try {
        var symbols = window.WBStorage && window.WBStorage.loadSymbols
            ? window.WBStorage.loadSymbols() : {};
        var files = window.WBStorage && window.WBStorage.loadFiles
            ? window.WBStorage.loadFiles() : [];
        var exportById = {};
        files.forEach(function(f) { exportById[f.id] = f.export_symbols !== false; });
        var activeFid = window.__wbActiveFid || null;
        var out = [];
        Object.keys(symbols).forEach(function(fid) {
            if (exportById[fid] !== false || fid === activeFid) {
                (symbols[fid] || []).forEach(function(s) {
                    out.push({ name: s.name, kind: s.kind });
                });
            }
        });
        return out;
    } catch (e) {
        return [];
    }
}

let singleton = null;

export function getClient() {
    if (!singleton) singleton = createClient();
    return singleton;
}

export function kindToType(kind) {
    return KIND_TYPE[kind] || 'text';
}

function createClient() {
    const c = {
        worker: null,
        nextId: 1,
        pending: new Map(),
        ready: false,
        initialized: false,
        disabled: false,
        toasted: false,
        opened: {},
        version: 0,
        initPromise: null,
        ctxTimer: 0,
    };

    function mark(info) {
        try {
            window.__wbWebLsp = Object.assign(window.__wbWebLsp || {}, info);
        } catch (e) {}
    }

    function setReadyFlag(on) {
        try {
            window.__wbWebLspReady = !!on;
        } catch (e) {}
    }

    function toast(msg) {
        if (c.toasted) return;
        c.toasted = true;
        try {
            const el = document.createElement('div');
            el.id = 'wb-weblsp-toast';
            el.textContent = msg;
            el.style.position = 'fixed';
            el.style.left = '16px';
            el.style.bottom = '16px';
            el.style.zIndex = '10000';
            el.style.background = 'var(--wb-black, #000)';
            el.style.color = 'var(--wb-white, #fff)';
            el.style.border = '2px solid var(--wb-white, #fff)';
            el.style.padding = '8px 10px';
            el.style.fontFamily = 'var(--wb-font, monospace)';
            el.style.fontSize = '9px';
            document.body.appendChild(el);
            setTimeout(function() { try { el.remove(); } catch (e) {} }, 5000);
        } catch (e) {}
    }

    function disable(msg) {
        if (c.disabled) return;
        c.disabled = true;
        c.ready = false;
        setReadyFlag(false);
        mark({ ready: false, error: msg || 'disabled' });
        try {
            c.pending.forEach(function(p) {
                try { p.reject(new Error(msg || 'disabled')); } catch (e) {}
            });
            c.pending.clear();
        } catch (e) {}
        toast('In-browser LSP unavailable: ' + (msg || 'worker failed'));
    }

    function onMessage(ev) {
        const m = ev && ev.data;
        if (!m || typeof m !== 'object') return;
        if (m.id !== undefined && m.id !== null && c.pending.has(m.id)) {
            const p = c.pending.get(m.id);
            c.pending.delete(m.id);
            try { clearTimeout(p.timer); } catch (e) {}
            if (m.error) p.reject(new Error((m.error && m.error.message) || 'LSP error'));
            else p.resolve(m.result);
            return;
        }
        if (m.id !== undefined && m.id !== null && c.worker) {
            // Unknown server->client request: answer MethodNotFound so the
            // server never hangs (our server sends none, this is defensive).
            try {
                c.worker.postMessage({
                    jsonrpc: '2.0', id: m.id,
                    error: { code: -32601, message: 'Method not found' },
                });
            } catch (e) {}
        }
        // Server notifications (e.g. window/logMessage) are ignored.
    }

    function notify(method, params) {
        if (!c.worker || c.disabled) return;
        try {
            c.worker.postMessage({ jsonrpc: '2.0', method: method, params: params || {} });
        } catch (e) {
            disable('worker post failed');
        }
    }

    function request(method, params) {
        if (c.disabled) return Promise.reject(new Error('disabled'));
        if (!c.worker) return Promise.reject(new Error('no worker'));
        const id = c.nextId++;
        return new Promise(function(resolve, reject) {
            const timer = setTimeout(function() {
                if (c.pending.has(id)) {
                    c.pending.delete(id);
                    disable('request timed out: ' + method);
                    reject(new Error('timeout'));
                }
            }, REQUEST_TIMEOUT);
            c.pending.set(id, { resolve: resolve, reject: reject, timer: timer });
            try {
                c.worker.postMessage({ jsonrpc: '2.0', id: id, method: method, params: params || {} });
            } catch (e) {
                try { clearTimeout(timer); } catch (ignored) {}
                c.pending.delete(id);
                disable('worker post failed');
                reject(e);
            }
        });
    }

    function pushContext() {
        if (!c.initialized || c.disabled) return;
        var headers = [];
        try {
            var files = window.WBStorage && window.WBStorage.loadFiles
                ? window.WBStorage.loadFiles() : [];
            files.forEach(function(f) {
                if (f && typeof f.name === 'string' && /\.h$/i.test(f.name)) {
                    headers.push(f.name);
                }
            });
        } catch (e) {}
        notify('$/setContext', {
            label: window.__wbCurrentLang || '',
            hintKey: window.__wbHintKey || 'c',
            symbols: getAllSymbols(),
            headers: headers,
        });
    }

    function scheduleContext() {
        if (!c.initialized || c.disabled) return;
        try { clearTimeout(c.ctxTimer); } catch (e) {}
        c.ctxTimer = setTimeout(pushContext, 500);
    }

    function ensureWorker() {
        if (c.initPromise) return c.initPromise;
        if (c.disabled) return Promise.resolve(false);
        try {
            c.worker = new Worker(BUNDLE_URL);
        } catch (e) {
            disable('cannot start worker');
            c.initPromise = Promise.resolve(false);
            return c.initPromise;
        }
        c.worker.onmessage = onMessage;
        c.worker.onerror = function() { disable('worker error'); };
        mark({ ready: false, worker: 'starting', error: '' });
        c.initPromise = new Promise(function(resolve) {
            const timer = setTimeout(function() {
                disable('handshake timed out');
                resolve(false);
            }, HANDSHAKE_TIMEOUT);
            request('initialize', {
                processId: null, rootUri: null, capabilities: {}, workspaceFolders: null,
            }).then(function() {
                try { clearTimeout(timer); } catch (e) {}
                notify('initialized', {});
                c.initialized = true;
                c.ready = true;
                setReadyFlag(true);
                mark({ ready: true, worker: 'up', error: '' });
                pushContext();
                resolve(true);
            }).catch(function() {
                try { clearTimeout(timer); } catch (e) {}
                resolve(false); // disable() already ran inside request()
            });
        });
        return c.initPromise;
    }

    function uriFor(fid) {
        return 'inmemory://weblsp/' + (fid || 'untitled');
    }

    function languageId() {
        return (window.__wbHintKey === 'pascal') ? 'pascal' : 'c';
    }

    function syncDoc(state, pos) {
        if (!c.initialized || c.disabled) return null;
        const fid = window.__wbActiveFid || 'untitled';
        const uri = uriFor(fid);
        const text = state.doc.toString();
        const e = c.opened[uri];
        try {
            if (!e) {
                c.version++;
                notify('textDocument/didOpen', {
                    textDocument: { uri: uri, languageId: languageId(), version: c.version, text: text },
                });
                c.opened[uri] = { text: text, version: c.version };
            } else if (e.text !== text) {
                c.version++;
                notify('textDocument/didChange', {
                    textDocument: { uri: uri, version: c.version },
                    contentChanges: [{ text: text }],
                });
                e.text = text;
                e.version = c.version;
            }
        } catch (err) {
            disable('sync failed');
            return null;
        }
        const line = state.doc.lineAt(pos);
        return { uri: uri, line: line.number - 1, character: pos - line.from };
    }

    async function roundTrip(method, state, pos) {
        await ensureWorker();
        if (!c.ready) return null;
        const s = syncDoc(state, pos);
        if (!s) return null;
        try {
            return await request(method, {
                textDocument: { uri: s.uri },
                position: { line: s.line, character: s.character },
            });
        } catch (e) {
            return null;
        }
    }

    async function complete(state, pos) {
        const res = await roundTrip('textDocument/completion', state, pos);
        if (!res) return null;
        const items = Array.isArray(res) ? res : (res.items || []);
        if (!items.length) return null;
        // Observed by the test suite (mutual exclusion with the local bridge).
        try {
            const prev = (window.__wbWebLsp && window.__wbWebLsp.completedRequests) || 0;
            mark({ completedRequests: prev + 1 });
        } catch (e) {}
        return items.slice(0, MAX_ROWS);
    }

    async function hover(state, pos) {
        const res = await roundTrip('textDocument/hover', state, pos);
        if (!res || !res.contents) return null;
        const md = typeof res.contents === 'string' ? res.contents : (res.contents.value || '');
        return md ? { markdown: md } : null;
    }

    async function signature(state, pos) {
        const res = await roundTrip('textDocument/signatureHelp', state, pos);
        if (!res || !res.signatures || !res.signatures.length) return null;
        return res;
    }

    // Fresh context on every file activation / language switch (the page
    // dispatches wb-active-editor for both). User symbols may also change as
    // other files are edited; views re-push debounced via scheduleContext().
    window.addEventListener('wb-active-editor', function() {
        try {
            ensureWorker();
            pushContext();
            scheduleContext();
        } catch (e) {}
    });

    return {
        ensureWorker: ensureWorker,
        isReady: function() { return c.ready && !c.disabled; },
        isDisabled: function() { return c.disabled; },
        complete: complete,
        hover: hover,
        signature: signature,
        pushContext: pushContext,
        scheduleContext: scheduleContext,
    };
}
