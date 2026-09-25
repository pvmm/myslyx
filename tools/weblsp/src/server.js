// Myslyx in-browser LSP - vscode-languageserver feature handlers.
//
// attach(connection) registers initialize + textDocumentSync (full) +
// completion/hover/signatureHelp, all served from the generated hints
// dictionaries (static/hints/<key>.json, fetched same-origin by the worker)
// plus the user symbols the main thread pushes with $/setContext.
//
// Member contexts (caret after "." / "->") intentionally return null: the
// client keeps serving those from its curated struct machinery
// (c-struct-complete / native-completions memberSource), which resolves
// in-file struct definitions the hints JSON cannot see.
import {
    TextDocuments,
    TextDocumentSyncKind,
} from 'vscode-languageserver/browser';
import { TextDocument } from 'vscode-languageserver-textdocument';
import {
    normalizeHints,
    memberTriggerInfo,
    buildWordItems,
    lookupTip,
    wordAt,
    parseTip,
    callInfo,
    parseDocumentSymbols,
} from './hintsmodel.js';

const EMPTY = normalizeHints(null);
const HINT_KEY_RE = /^[a-z0-9]+$/;

export function attach(connection) {
    const documents = new TextDocuments(TextDocument);
    const ctx = { label: '', hintKey: 'c', symbols: [] };
    const cache = {}; // hintKey -> {model} once fetched

    function symbols() {
        return Array.isArray(ctx.symbols) ? ctx.symbols : [];
    }

    function modelFor(key) {
        const entry = cache[key];
        return entry ? entry.model : EMPTY;
    }

    // Fetch (and cache) a hints dictionary. Awaits in-flight fetches so the
    // first completion right after a language switch still has data.
    async function ensureHints(key) {
        if (!HINT_KEY_RE.test(key || '')) return EMPTY;
        if (cache[key]) return cache[key].model;
        if (!cache[key + '#pending']) {
            cache[key + '#pending'] = fetch('/static/hints/' + key + '.json')
                .then((r) => {
                    if (!r.ok) throw new Error('HTTP ' + r.status);
                    return r.json();
                })
                .then((j) => normalizeHints(j))
                .catch(() => EMPTY)
                .then((model) => { cache[key] = { model }; return model; });
        }
        return cache[key + '#pending'];
    }

    // Completion detail column mirrors the curated popup contract
    // (native-completions.js): keywords 'keyword', builtins 'builtin',
    // types 'type'/'const' (see hintsmodel), user symbols their kind — so a
    // worker-fed popup reads exactly like a curated one.
    function builtinDetail() {
        return 'builtin';
    }

    connection.onInitialize(() => ({
        capabilities: {
            textDocumentSync: TextDocumentSyncKind.Full,
            completionProvider: {
                resolveProvider: false,
                triggerCharacters: ['.', '>', '(', '#'],
            },
            hoverProvider: true,
            signatureHelpProvider: { triggerCharacters: ['('] },
        },
        serverInfo: { name: 'myslyx-weblsp', version: '1.0.0' },
    }));

    connection.onInitialized(() => {
        // Eagerly warm the default dictionary so the first keystroke is fast.
        ensureHints(ctx.hintKey || 'c').catch(() => {});
    });

    // Main-thread context: active file label, hints key (__wbHintKey), and
    // the exported user symbols (localStorage lives on the main thread).
    connection.onNotification('$/setContext', (params) => {
        const p = params || {};
        ctx.label = String(p.label || '');
        if (typeof p.hintKey === 'string' && p.hintKey) ctx.hintKey = p.hintKey;
        ctx.symbols = Array.isArray(p.symbols) ? p.symbols : [];
        ensureHints(ctx.hintKey).catch(() => {});
    });

    connection.onCompletion(async (params) => {
        const doc = documents.get(params.textDocument.uri);
        if (!doc) return null;
        const model = await ensureHints(ctx.hintKey);
        const text = doc.getText();
        let offset;
        try {
            offset = doc.offsetAt(params.position);
        } catch (e) {
            return null;
        }
        const mt = memberTriggerInfo(text, offset);
        if (mt.isMember) return null;
        const caseInsensitive = ctx.hintKey === 'pascal';
        // In-file declarations first (they win over framework names on a
        // clash), then the persisted cross-file symbols, then the hints.
        // The persisted store only knows top-level function definitions, so
        // the live parse is what completes locals, params and file-scope
        // variables typed in this buffer.
        const docSyms = parseDocumentSymbols(text, ctx.hintKey, model.types);
        const items = buildWordItems(model, docSyms.concat(symbols()), mt.word || '',
            caseInsensitive, builtinDetail);
        if (!items.length) return null;
        return { isIncomplete: false, items };
    });

    connection.onHover(async (params) => {
        const doc = documents.get(params.textDocument.uri);
        if (!doc) return null;
        const model = await ensureHints(ctx.hintKey);
        const text = doc.getText();
        let offset;
        try {
            offset = doc.offsetAt(params.position);
        } catch (e) {
            return null;
        }
        const w = wordAt(text, offset);
        if (!w.word) return null;
        const tip = lookupTip(model, w.word);
        if (!tip) return null;
        return { contents: { kind: 'markdown', value: tip } };
    });

    connection.onSignatureHelp(async (params) => {
        const doc = documents.get(params.textDocument.uri);
        if (!doc) return null;
        const model = await ensureHints(ctx.hintKey);
        const text = doc.getText();
        let offset;
        try {
            offset = doc.offsetAt(params.position);
        } catch (e) {
            return null;
        }
        const call = callInfo(text, offset);
        if (!call) return null;
        const tip = lookupTip(model, call.name);
        if (!tip) return null;
        const parsed = parseTip(tip);
        if (!parsed.signature) return null;
        const parameters = parsed.params.map((p) => ({
            label: p.name,
            documentation: p.desc || undefined,
        }));
        return {
            signatures: [{
                label: parsed.signature,
                documentation: { kind: 'markdown', value: tip },
                parameters,
            }],
            activeSignature: 0,
            activeParameter: parameters.length
                ? Math.min(call.argIndex, parameters.length - 1)
                : 0,
        };
    });

    documents.listen(connection);
    return { documents };
}
