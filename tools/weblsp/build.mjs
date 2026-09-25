// Build the committed in-browser LSP worker bundle.
//
//   npm run build   (or: node build.mjs)
//
// Bundles tools/weblsp/src/worker.js (vscode-languageserver/browser + the
// hints-driven server) into a single classic-worker script at
// myslyx/static/plugins/weblsp/worker.bundle.js. Re-run after editing
// src/*.js or upgrading dependencies, and commit the bundle: wheels and
// checkouts run WITHOUT node (MANIFEST.in ships myslyx/static/**).
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.join(here, '..', '..', 'myslyx', 'static', 'plugins', 'weblsp', 'worker.bundle.js');

await build({
    entryPoints: [path.join(here, 'src', 'worker.js')],
    bundle: true,
    outfile: out,
    platform: 'browser',
    format: 'iife',
    target: 'es2020',
    minify: false,
    sourcemap: false,
    logLevel: 'info',
});
console.log('wrote ' + out);
