"""Minimal stdio LSP client for C / C MSXgl completions (local-only).

Turns the LSP binary named by the ``MYSLYX_LSP`` environment variable (e.g.
``clangd``) into a small request/response service the editor page reaches over
HTTP (the routes registered in ``app.py``). It is gated on the env var *and* a
local run (``myslyx.local.is_local``): nothing spawns when ``MYSLYX_LSP`` is
unset, the binary does not resolve, or the server looks like a shared
deployment. Every failure is contained — the bridge answers
``{enabled: false, items: []}`` and the editor keeps working with the curated
hints dictionary.

Each editor buffer becomes its own ephemeral workspace: a temp directory with
the buffer written as a real file plus a minimal ``compile_commands.json``, so
index-based servers like ``clangd`` treat it as a proper C translation unit
instead of an anonymous in-memory buffer. ``clangd`` gets a
``--compile-commands-dir`` flag; other servers just get the buffer.

The wire protocol is JSON-RPC 2.0 over stdio with ``Content-Length`` framing,
enough of LSP for initialize/didOpen/didChange/textDocument/completion.
Diagnostics and other push notifications are read and skipped.
"""

import json
import os
import select
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from myslyx.local import is_local

_TIMEOUT = 6.0
_STDERR_CAP = 200
_LANGUAGE_ID = 'c'
_DEFAULT_NAME = 'buffer.c'

# LSP CompletionItemKind -> stable client type hint.
_KIND_TO_TYPE = {
    1: 'text', 2: 'method', 3: 'function', 4: 'class', 5: 'module',
    6: 'type', 7: 'property', 8: 'field', 9: 'constructor', 10: 'enum',
    11: 'interface', 12: 'enum member', 13: 'struct', 14: 'event',
    15: 'operator', 16: 'type parameter', 17: 'variable', 18: 'constant',
    19: 'keyword', 20: 'snippet', 21: 'text',
}


class _LspError(Exception):
    """A wire/process failure talking to the LSP server (not an LSP error)."""


def _resolve(cmd: str) -> str | None:
    """Resolve ``cmd`` (a shell token list) to an executable, or None."""
    exe = shlex.split(cmd)[0]
    if os.sep in exe or (os.altsep and os.altsep in exe):
        return cmd if os.path.exists(exe) else None
    return cmd if shutil.which(exe) else None


def available() -> dict:
    """Server-side capability advert: {enabled, server, error}."""
    cmd = os.environ.get('MYSLYX_LSP', '').strip()
    if not cmd:
        return {'enabled': False, 'server': None, 'error': None}
    if not is_local():
        return {'enabled': False, 'server': cmd, 'error': 'LSP is local-only (remote run)'}
    if not _resolve(cmd):
        return {'enabled': False, 'server': cmd, 'error': f'LSP binary not found: {cmd}'}
    return {'enabled': True, 'server': cmd, 'error': None}


def _buffer_name(name: str | None) -> str:
    """A safe file name for the editor buffer (clangd keys off the extension
    to pick C vs C++, so a name without one gets a .c suffix)."""
    fname = (name or '').strip() or _DEFAULT_NAME
    fname = fname.replace('/', '_').replace('\\', '_')
    if not Path(fname).suffix:
        fname += '.c'
    return fname


def _map_items(items: list) -> list:
    """Map LSP CompletionItems to the client's {label, detail, apply, type}."""
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = item.get('label')
        if not isinstance(label, str) or not label:
            continue
        label = label.strip()
        if not label:
            continue
        entry: dict = {'label': label, 'type': _KIND_TO_TYPE.get(item.get('kind'), 'text')}
        detail = item.get('detail')
        if isinstance(detail, str) and detail:
            entry['detail'] = detail
        insert = item.get('insertText')
        if isinstance(insert, str) and insert and insert != label:
            entry['apply'] = insert
        out.append(entry)
    return out


def _extract_items(result) -> list:
    if not result:
        return []
    items = result.get('items') if isinstance(result, dict) else result
    return _map_items(items or [])


class _Session:
    """One LSP process, owned by one editor file (fid), with a temp workspace."""

    def __init__(self, command: str, buffer_name: str, language_id: str = _LANGUAGE_ID):
        self._command = command
        self._buffer_name = buffer_name
        self._language_id = language_id
        self._proc: subprocess.Popen | None = None
        self._workspace: Path | None = None
        self._buffer: Path | None = None
        self._uri: str = ''
        self._lock = threading.Lock()
        self._seq = 1
        self._open = False
        self._last_text: str | None = None
        self._doc_version = 1
        self._stderr: list[str] = []

    # ----- process + wire helpers -----------------------------------------

    def _spawn(self) -> None:
        # Ephemeral workspace: a real buffer file plus a minimal compilation
        # database so index-based servers parse the buffer as a C file.
        workspace = Path(tempfile.mkdtemp(prefix='myslyx-lsp-'))
        buffer_path = workspace / self._buffer_name
        (workspace / 'compile_commands.json').write_text(json.dumps([{
            'directory': str(workspace),
            'file': str(buffer_path),
            'command': 'clang -std=c99 ' + buffer_path.name,
        }]))
        command = self._command
        if os.path.basename(shlex.split(self._command)[0]).lower().endswith('clangd'):
            command = command + ' --compile-commands-dir=' + str(workspace)
        proc = subprocess.Popen(
            shlex.split(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        threading.Thread(target=self._drain_stderr, args=(proc,), daemon=True).start()
        self._workspace = workspace
        self._buffer = buffer_path
        self._uri = buffer_path.as_uri()
        self._proc = proc
        resp = self._request('initialize', {
            'processId': None,
            'rootUri': workspace.as_uri(),
            'workspaceFolders': [{'uri': workspace.as_uri(), 'name': 'myslyx'}],
            'capabilities': {},
        })
        if resp is not None and resp.get('error'):
            raise _LspError(f'LSP initialize failed: {resp["error"]}')
        self._notify('initialized', {})

    def _drain_stderr(self, proc: subprocess.Popen) -> None:
        try:
            for raw in iter(proc.stderr.readline, b''):
                line = raw[:400].decode('utf-8', 'replace').rstrip()
                if line:
                    self._stderr.append(line)
                    if len(self._stderr) > _STDERR_CAP:
                        del self._stderr[0]
        except Exception:
            pass

    def _write(self, payload: dict) -> None:
        data = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        self._proc.stdin.write(('Content-Length: %d\r\n\r\n' % len(data)).encode() + data)
        self._proc.stdin.flush()

    def _notify(self, method: str, params: dict) -> None:
        if self._proc is None:
            self._spawn()
        self._write({'jsonrpc': '2.0', 'method': method, 'params': params})

    def _request(self, method: str, params: dict) -> dict:
        if self._proc is None:
            self._spawn()
        req_id = self._seq
        self._seq += 1
        self._write({'jsonrpc': '2.0', 'id': req_id, 'method': method, 'params': params})
        deadline = time.monotonic() + _TIMEOUT
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _LspError('LSP response timed out')
            msg = self._read(remaining)
            if isinstance(msg, dict) and msg.get('id') == req_id:
                return msg

    def _read(self, timeout: float) -> dict:
        """Read one JSON-RPC message with Content-Length framing."""
        proc = self._proc
        deadline = time.monotonic() + timeout
        header = b''
        while b'\r\n\r\n' not in header:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _LspError('LSP read timed out')
            ready, _, _ = select.select([proc.stdout], [], [], min(remaining, 5.0))
            if not ready:
                continue
            chunk = proc.stdout.read1(4096)
            if not chunk:
                raise _LspError(f'LSP closed its stdout: {self._stderr[-3:]}')
            header += chunk
            if len(header) > 64 * 1024:
                raise _LspError('LSP header too large')
        head, _, rest = header.partition(b'\r\n\r\n')
        length = 0
        for line in head.split(b'\r\n'):
            if line.lower().startswith(b'content-length:'):
                try:
                    length = int(line.split(b':', 1)[1].strip())
                except ValueError as exc:
                    raise _LspError('LSP bad Content-Length') from exc
        body = rest
        while len(body) < length:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _LspError('LSP body read timed out')
            ready, _, _ = select.select([proc.stdout], [], [], min(remaining, 5.0))
            if not ready:
                continue
            chunk = proc.stdout.read1(4096)
            if not chunk:
                raise _LspError('LSP closed mid-message')
            body += chunk
        try:
            return json.loads(body[:length].decode('utf-8'))
        except (UnicodeDecodeError, ValueError) as exc:
            raise _LspError(f'LSP sent invalid JSON: {exc}') from exc

    # ----- LSP semantics ----------------------------------------------------

    def _ensure_open(self, text: str) -> None:
        if not self._open:
            self._spawn()
            self._buffer.write_text(text, encoding='utf-8')
            self._notify('textDocument/didOpen', {
                'textDocument': {
                    'uri': self._uri,
                    'languageId': self._language_id,
                    'version': 1,
                    'text': text,
                },
            })
            self._last_text = text
            self._open = True
        elif text != self._last_text:
            self._buffer.write_text(text, encoding='utf-8')
            self._notify('textDocument/didChange', {
                'textDocument': {'uri': self._uri, 'version': 2},
                'contentChanges': [{'text': text}],
            })
            self._last_text = text

    def completion(self, text: str, line: int, character: int) -> list:
        with self._lock:
            self._ensure_open(text)
            resp = self._request('textDocument/completion', {
                'textDocument': {'uri': self._uri},
                'position': {'line': line, 'character': character},
                'context': {'triggerKind': 1},
            })
            if resp is not None and resp.get('error'):
                return []
            return _extract_items(resp.get('result') if resp else None)

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except OSError:
                    pass
            except OSError:
                pass
        # Close the pipes up front so the GC never writes into a dead process's
        # stdin (it would surface as a noisy BrokenPipeError at finalization).
        # stderr is only closed after the process has exited, when the drain
        # thread has already read it to EOF.
        if proc:
            exited = proc.poll() is not None
            for stream in (proc.stdin, proc.stdout):
                try:
                    if stream:
                        stream.close()
                except OSError:
                    pass
            if exited:
                try:
                    if proc.stderr:
                        proc.stderr.close()
                except OSError:
                    pass
        workspace = self._workspace
        self._workspace = None
        if workspace:
            shutil.rmtree(workspace, ignore_errors=True)


# ----- registry (one session per editor file) ------------------------------

_REGISTRY: dict[str, _Session] = {}
_REGISTRY_LOCK = threading.Lock()


def _get_session(fid: str, command: str, buffer_name: str) -> _Session:
    with _REGISTRY_LOCK:
        session = _REGISTRY.get(fid)
        if session is None:
            session = _Session(command, buffer_name)
            _REGISTRY[fid] = session
        return session


def _close_session(fid: str) -> None:
    with _REGISTRY_LOCK:
        session = _REGISTRY.pop(fid, None)
    if session:
        session.close()


# ----- bridge API ----------------------------------------------------------

def ping() -> dict:
    """Spawn + initialize a throwaway session to prove the LSP is reachable."""
    info = available()
    if not info['enabled']:
        return info
    session = _Session(info['server'], _DEFAULT_NAME)
    try:
        with session._lock:
            session._spawn()
        session.close()
        return {'enabled': True, 'server': info['server'], 'error': None}
    except _LspError as exc:
        session.close()
        return {'enabled': False, 'server': info['server'], 'error': str(exc)}
    except OSError as exc:
        session.close()
        return {'enabled': False, 'server': info['server'], 'error': f'could not start LSP: {exc}'}


def complete(fid: str, language: str, name: str | None, content: str,
             line: int = 0, character: int = 0) -> dict:
    """One completion round trip for an editor buffer. Never raises."""
    info = available()
    if not info['enabled']:
        return {'enabled': False, 'items': [], 'error': info.get('error')}
    session = _get_session(fid, info['server'], _buffer_name(name))
    try:
        items = session.completion(content, int(line), int(character))
        return {'enabled': True, 'items': items, 'error': None}
    except (_LspError, OSError, ValueError) as exc:
        _close_session(fid)
        return {'enabled': False, 'items': [], 'error': str(exc)}


def close(fid: str) -> None:
    _close_session(fid)