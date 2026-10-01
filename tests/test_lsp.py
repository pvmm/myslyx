"""Acceptance suite for the local-only LSP bridge (C / C MSXgl).

The server-side LSP session (myslyx/lsp.py) runs only when ``MYSLYX_LSP`` is
set on a local run. Each suite declares the server environment it needs (see
the ``env`` entry); tests/runner.py spawns one app server per distinct env and
marks a suite SKIP when its env cannot be provided (e.g. clangd missing).

Assertions are pipeline-level: they verify the client actually reaches
``/wb/lsp/ping`` and ``/wb/lsp/complete`` with the right payloads and handles
connection failures (auto-disable + toast) — not that a specific language
server suggests a specific symbol (clangd output is not deterministic).
"""

import asyncio
import json
import time

from tests import helpers as h

# (name, fn, env). env None -> the default server; a dict -> a dedicated
# server phase started with those extra environment variables. Note: entries
# are assembled at the bottom, after the suite functions are defined.


# ----- helpers -------------------------------------------------------------

def _watch(page):
    """Network capture for the LSP bridge endpoints (attached BEFORE reloads)."""
    state = {'ping': 0, 'complete': 0, 'complete_bodies': [], 'complete_responses': []}

    def on_request(req):
        if '/wb/lsp/ping' in req.url:
            state['ping'] += 1
        elif '/wb/lsp/complete' in req.url:
            state['complete'] += 1
            try:
                state['complete_bodies'].append(req.post_data or '')
            except Exception:
                pass

    async def on_response(resp):
        if '/wb/lsp/complete' in resp.url:
            try:
                state['complete_responses'].append(json.loads(await resp.text()))
            except Exception:
                pass

    page.on('request', on_request)
    page.on('response', on_response)
    return state


async def _wait_for(page, probe, timeout=15000, msg='condition not met'):
    """Poll a sync-or-async probe until it returns truthy (sync probes are allowed)."""
    deadline = time.monotonic() + timeout / 1000.0
    last_exc = None
    while True:
        try:
            result = probe()
            if asyncio.iscoroutine(result):
                result = await result
            if result:
                return
        except Exception as exc:
            last_exc = exc
        if time.monotonic() >= deadline:
            if last_exc is not None:
                raise TimeoutError(f'{msg} (last probe error: {type(last_exc).__name__}: {last_exc})')
            raise TimeoutError(msg)
        await asyncio.sleep(0.1)


async def _type_slow(page, text, pause=120):
    """Type per character with small pauses so clangd can index between keys.

    A newline first dismisses any open completion popup: Enter/Tab accept the
    highlighted item (see hints.js), so without the Escape the pending
    `#include` completion would swallow the line break and corrupt the buffer.
    """
    for i, ch in enumerate(text):
        if ch == '\n':
            await page.keyboard.press('Escape')
        await page.keyboard.type(ch)
        if i % 2 == 1:
            await page.wait_for_timeout(pause)
    await page.wait_for_timeout(600)


async def _reload_setup(page):
    """Reload so the LSP boot-time ping happens under the network watch."""
    await page.reload(wait_until='load')
    await page.wait_for_selector('.wb-file-tab', timeout=20000)


async def _native_labels(page):
    return await page.evaluate(
        "() => Array.from(document.querySelectorAll("
        "'.cm-tooltip-autocomplete .cm-completionLabel')).map(e => e.textContent)")


async def _custom_labels(page):
    return await page.evaluate(
        "() => Array.from(document.querySelectorAll("
        "'.wb-autocomplete-popup > div > span:first-child')).map(e => e.textContent)")


async def _labels_contain(page, labels_fn, needle):
    """Poll-friendly probe: true as soon as a popup label contains the needle."""
    try:
        labels = await labels_fn(page)
        return bool(labels) and any(needle in label for label in labels)
    except Exception:
        return False


async def _goto_new_file(page, language, hint_key):
    await h.new_file(page, 2)
    await h.set_language(page, language)
    if hint_key:
        await page.wait_for_function(f"window.__wbHintKey === '{hint_key}'")
    await h.focus_active_editor(page)


# ----- suites --------------------------------------------------------------

async def disabled_by_default(page, msgs):
    """No MYSLYX_LSP -> no advertising, no LSP traffic, curated works."""
    state = _watch(page)
    await _reload_setup(page)
    assert await page.evaluate('window.__wbLocal === true'), 'local run must report __wbLocal true'
    info = await page.evaluate('window.__wbLsp')
    assert info and info.get('enabled') is False, f'LSP must be off by default: {info}'
    await _goto_new_file(page, 'C', None)
    await page.keyboard.type('#include <string.h>\nint main() { ret')
    await page.wait_for_timeout(800)
    assert state['ping'] == 0, 'ping must not fire without MYSLYX_LSP'
    assert state['complete'] == 0, 'complete must not fire without MYSLYX_LSP'
    assert not msgs, f'console errors: {msgs}'


async def completions_msxgl_native(page, msgs):
    """C MSXgl uses the native popup fed by live LSP results."""
    state = _watch(page)
    await _reload_setup(page)
    info = await page.evaluate('window.__wbLsp')
    assert info and info.get('enabled'), f'LSP must be advertised: {info}'
    await _goto_new_file(page, 'C+MSXgl', 'msxgl')
    await _type_slow(page, '#include <string.h>\nint main() { size_t n = strl')

    await _wait_for(page, lambda: state['complete'] >= 3, timeout=25000,
                    msg='no LSP completion round trips for C MSXgl')
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, 'strlen'),
                    timeout=25000, msg='strlen never rendered in the native popup')
    labels = await _native_labels(page)
    assert any('strlen' in s for s in labels), f'strlen missing from native popup: {labels}'

    assert state['complete'] >= 3, f'expected LSP round trips, got {state["complete"]}'
    last = state['complete_responses'][-1]
    assert last and last.get('enabled') is True, f'last complete response: {last}'
    assert not msgs, f'console errors: {msgs}'


async def completions_c_custom(page, msgs):
    """Plain C keeps the custom popup, fed by the async LSP provider."""
    state = _watch(page)
    await _reload_setup(page)
    info = await page.evaluate('window.__wbLsp')
    assert info and info.get('enabled'), f'LSP must be advertised: {info}'
    await _goto_new_file(page, 'C', None)
    await _type_slow(page, '#include <string.h>\nint main() { size_t n = strl')

    await _wait_for(page, lambda: _labels_contain(page, _custom_labels, 'strlen'),
                    timeout=25000, msg='strlen never rendered in the custom popup')
    labels = await _custom_labels(page)
    assert any('strlen' in s for s in labels), f'strlen missing from custom popup: {labels}'

    assert state['complete'] >= 3, f'expected LSP round trips, got {state["complete"]}'
    last = state['complete_responses'][-1]
    assert last and last.get('enabled') is True, f'last complete response: {last}'
    assert not msgs, f'console errors: {msgs}'


async def local_gate(page, msgs):
    """A "remote" (SPACE_ID=1) run must keep the onlyLocal plugin inert."""
    state = _watch(page)
    await _reload_setup(page)
    assert await page.evaluate('window.__wbLocal === false'), 'SPACE_ID run must report remote'
    info = await page.evaluate('window.__wbLsp')
    assert info and info.get('enabled') is False, f'LSP must not advertise remotely: {info}'
    await _goto_new_file(page, 'C', None)
    await page.keyboard.type('char')
    await page.wait_for_timeout(800)
    assert state['ping'] == 0, 'no ping on a shared deployment'
    assert state['complete'] == 0, 'no LSP round trips on a shared deployment'
    assert not msgs, f'console errors: {msgs}'


async def autodisable_on_failure(page, msgs):
    """A broken LSP (advertised but unreachable) disables the plugin with a toast."""
    state = _watch(page)
    await _reload_setup(page)
    info = await page.evaluate('window.__wbLsp')
    assert info and info.get('enabled'), f'LSP must be advertised before the failure: {info}'

    await _wait_for(page, lambda: state['ping'] >= 1,
                    timeout=15000, msg='the boot-time ping never fired')
    await _wait_for(page, lambda: page.evaluate('window.__wbLspAutodisabled === true'),
                    timeout=15000, msg='plugin never autodisabled')
    assert state['complete'] == 0, 'no completion requests after the failed ping'

    await page.wait_for_selector('#wb-lsp-toast', timeout=5000)
    toast_gone = await page.wait_for_function(
        "() => !document.getElementById('wb-lsp-toast')", timeout=8000)
    assert toast_gone, 'toast never dismissed'

    # The editor still works with the curated dictionary after the disable.
    await _goto_new_file(page, 'C', None)
    await page.keyboard.type('int')
    await page.wait_for_timeout(600)
    assert state['complete'] == 0, 'plugin must stay disabled for the session'
    assert not msgs, f'console errors: {msgs}'


async def include_closers(page, msgs):
    """Accepting a clangd-fed #include completion closes its bracket."""
    state = _watch(page)
    await _reload_setup(page)
    info = await page.evaluate('window.__wbLsp')
    assert info and info.get('enabled'), f'LSP must be advertised: {info}'
    await _goto_new_file(page, 'C+MSXgl', 'msxgl')
    await _type_slow(page, '#include <stdi')
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, '.h'),
                    timeout=25000, msg='no header completion from the bridge')
    await page.keyboard.press('Enter')
    # Whatever header clangd offered, exactly one closing bracket lands.
    await page.wait_for_function(
        "() => window.WBEditorActive.current(3000).then(v => "
        "!!v && /^#include <[^>\\n]*\\.h>$/.test(v.state.doc.toString()))",
        timeout=10000)
    assert state['complete'] >= 1, 'expected LSP round trips'
    assert not msgs, f'console errors: {msgs}'


DEFAULT_SUITES = [
    ('local-lsp/disabled-by-default', disabled_by_default, None),
]

ENABLED_SUITES = [
    ('local-lsp/completions-msxgl-native', completions_msxgl_native, {'MYSLYX_LSP': 'clangd'}),
    ('local-lsp/completions-c-custom', completions_c_custom, {'MYSLYX_LSP': 'clangd'}),
    ('local-lsp/include-closers', include_closers, {'MYSLYX_LSP': 'clangd'}),
    # Same binary as the positive phase, but the server looks like a shared
    # Hugging Face Space: the local-only gates must keep everything inert.
    ('local-lsp/local-gate', local_gate, {'MYSLYX_LSP': 'clangd', 'SPACE_ID': '1'}),
    # Executable but not an LSP server: resolves, then fails at ping time.
    ('local-lsp/autodisable-on-failure', autodisable_on_failure, {'MYSLYX_LSP': '/bin/false'}),
]

LSP_SUITES = DEFAULT_SUITES + ENABLED_SUITES