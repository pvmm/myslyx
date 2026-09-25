// Myslyx in-browser LSP - worker entry (esbuild bundle root).
//
// Runs inside a dedicated Web Worker. The main thread talks to it with raw
// LSP JSON-RPC objects over worker.postMessage / onmessage (the browser
// transport of vscode-languageserver needs no Content-Length framing).
import {
    createConnection,
    BrowserMessageReader,
    BrowserMessageWriter,
} from 'vscode-languageserver/browser';
import { attach } from './server.js';

const reader = new BrowserMessageReader(self);
const writer = new BrowserMessageWriter(self);
const connection = createConnection(reader, writer);
attach(connection);
connection.listen();
