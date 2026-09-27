"""Acceptance suite for the in-browser LSP plugin (C / C MSXgl / Pascal).

A real vscode-languageserver server runs in a Web Worker (bundled from
tools/weblsp/) and serves completion + hover + signatureHelp from the SAME
generated hints dictionaries (static/hints/<key>.json) that feed the sidebar
and popups, plus the user's exported symbols. Unlike the machine-installed
bridge behind the "local-lsp" plugin, this needs no server binary and works
on shared/remote runs too.

Assertions are pipeline-level: they verify the worker actually boots
(window.__wbWebLsp.ready), the popups/tooltips render worker-fed content,
and nothing ever touches /wb/lsp/* (independence from the local bridge).
"""

import json
import time

from tests import helpers as h
from tests.test_lsp import (
    _custom_labels,
    _goto_new_file,
    _labels_contain,
    _native_labels,
    _type_slow,
    _wait_for,
)

# (name, fn, env). env None -> the default server; a dict -> a dedicated
# server phase started with those extra environment variables.


# ----- helpers -------------------------------------------------------------

def _watch_lsp_bridge(page):
    """Count local-bridge round trips (must stay zero: the worker is local)."""
    state = {'ping': 0, 'complete': 0}

    def on_request(req):
        if '/wb/lsp/ping' in req.url:
            state['ping'] += 1
        elif '/wb/lsp/complete' in req.url:
            state['complete'] += 1

    page.on('request', on_request)
    return state


async def _reset_config(page):
    """Clear persisted plugin overrides and reload for a deterministic page."""
    await page.evaluate("""() => {
        const cfg = window.WBStorage.loadConfig();
        cfg.plugins = {};
        window.WBStorage.saveConfig(cfg);
    }""")
    await page.reload(wait_until='load')
    await page.wait_for_selector('.wb-file-tab', timeout=20000)


async def _wait_ready(page, timeout=20000):
    """Wait until the worker handshake settles as ready."""
    await _wait_for(
        page,
        lambda: page.evaluate(
            "window.__wbWebLspReady === true && !!(window.__wbWebLsp && window.__wbWebLsp.ready)"),
        timeout=timeout, msg='in-browser LSP worker never became ready')


async def _hover_token(page, token):
    """Move the mouse over the first occurrence of ``token`` in the doc."""
    pos = await page.evaluate("""(tok) => window.WBEditorActive.current(3000).then(v => {
        if (!v) return null;
        const idx = v.state.doc.toString().indexOf(tok);
        if (idx < 0) return null;
        const c = v.coordsAtPos(idx + 1);
        return c ? { x: c.left, y: c.top + 2 } : null;
    })""", token)
    assert pos, f'token {token!r} not found or not measurable'
    await page.mouse.move(pos['x'], pos['y'])


def _plugin_row(page, name):
    return page.locator('.wb-plugin-row', has=page.locator('.wb-plugin-name', has_text=name)).first


async def _row_checked(page, name):
    return await _plugin_row(page, name).locator('.wb-plugin-check').is_checked()


async def _open_plugins_submenu(page):
    await h.open_settings(page)
    await page.click('#wb-settings-plugins')
    await page.wait_for_selector('#wb-plugins-menu .wb-plugin-row', timeout=10000)


async def _close_menu_and_wait_reload(page):
    """Close the settings menu (applies plugin changes via reload) and wait
    for the reloaded page: tabs vanish with the old DOM, then come back."""
    await page.click('#wb-settings-btn')
    await page.wait_for_function("!document.querySelector('.wb-file-tab')", timeout=15000)
    await page.wait_for_selector('.wb-file-tab', timeout=20000)


# ----- suites --------------------------------------------------------------

async def completions_msxgl_native(page, msgs):
    """C MSXgl native popup is fed by the worker (no local bridge)."""
    bridge = _watch_lsp_bridge(page)
    await _reset_config(page)
    await _goto_new_file(page, 'C+MSXgl', 'msxgl')
    await _wait_ready(page)
    await h.focus_active_editor(page)
    await _type_slow(page, 'VDP_SetM', pause=60)
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, 'VDP_SetMode'),
                    timeout=20000, msg='VDP_SetMode never rendered in the native popup')
    labels = await _native_labels(page)
    assert any('VDP_SetMode' in s for s in labels), f'VDP_SetMode missing: {labels}'
    assert bridge['ping'] == 0, 'no local-bridge ping expected'
    assert bridge['complete'] == 0, 'no local-bridge round trips expected'
    assert not msgs, f'console errors: {msgs}'


async def completions_c_custom(page, msgs):
    """Plain C custom popup is fed by the worker (no local bridge)."""
    bridge = _watch_lsp_bridge(page)
    await _reset_config(page)
    await _goto_new_file(page, 'C', None)
    await _wait_ready(page)
    await h.focus_active_editor(page)
    await _type_slow(page, '#include <string.h>\nstrl', pause=60)
    await _wait_for(page, lambda: _labels_contain(page, _custom_labels, 'strlen'),
                    timeout=20000, msg='strlen never rendered in the custom popup')
    labels = await _custom_labels(page)
    assert any('strlen' in s for s in labels), f'strlen missing: {labels}'
    assert bridge['ping'] == 0, 'no local-bridge ping expected'
    assert bridge['complete'] == 0, 'no local-bridge round trips expected'
    assert not msgs, f'console errors: {msgs}'


async def completions_pascal_native(page, msgs):
    """Pascal native popup is fed by the worker (pascal.json)."""
    bridge = _watch_lsp_bridge(page)
    await _reset_config(page)
    await _goto_new_file(page, 'Pascal', 'pascal')
    await _wait_ready(page)
    await h.focus_active_editor(page)
    await _type_slow(page, 'writ', pause=60)
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, 'writeln'),
                    timeout=20000, msg='writeln never rendered in the native popup')
    labels = await _native_labels(page)
    assert any('writeln' in s for s in labels), f'writeln missing: {labels}'
    assert bridge['ping'] == 0, 'no local-bridge ping expected'
    assert bridge['complete'] == 0, 'no local-bridge round trips expected'
    assert not msgs, f'console errors: {msgs}'


async def hover_tip(page, msgs):
    """Hovering a builtin shows its generated tip markdown."""
    bridge = _watch_lsp_bridge(page)
    await _reset_config(page)
    await _goto_new_file(page, 'C+MSXgl', 'msxgl')
    await _wait_ready(page)
    await h.focus_active_editor(page)
    await _type_slow(page, 'VDP_SetMode(0);', pause=60)
    await _hover_token(page, 'VDP_SetMode')
    await page.wait_for_selector('.wb-weblsp-hover', timeout=10000)
    text = await page.text_content('.wb-weblsp-hover')
    assert 'Set screen mode' in (text or ''), f'tip text missing: {text!r}'
    assert bridge['ping'] == 0, 'no local-bridge ping expected'
    assert bridge['complete'] == 0, 'no local-bridge round trips expected'
    assert not msgs, f'console errors: {msgs}'


async def signature_help(page, msgs):
    """Typing an opening paren shows the worker's signature help."""
    bridge = _watch_lsp_bridge(page)
    await _reset_config(page)
    await _goto_new_file(page, 'C+MSXgl', 'msxgl')
    await _wait_ready(page)
    await h.focus_active_editor(page)
    await _type_slow(page, 'VDP_SetMode(', pause=60)
    await page.wait_for_selector('#wb-sighelp', timeout=10000)
    await page.wait_for_function(
        "() => { const el = document.getElementById('wb-sighelp');"
        " return !!el && el.style.display !== 'none' && el.textContent.includes('VDP_SetMode'); }",
        timeout=10000)
    text = await page.text_content('#wb-sighelp')
    assert 'void VDP_SetMode' in (text or ''), f'signature missing: {text!r}'
    assert 'mode' in (text or ''), f'active param missing: {text!r}'
    assert bridge['ping'] == 0, 'no local-bridge ping expected'
    assert bridge['complete'] == 0, 'no local-bridge round trips expected'
    assert not msgs, f'console errors: {msgs}'


async def remote_works(page, msgs):
    """A shared/remote run still gets worker-fed completions (local bridge off)."""
    bridge = _watch_lsp_bridge(page)
    await _reset_config(page)
    assert await page.evaluate('window.__wbLocal === false'), 'SPACE_ID run must report remote'
    info = await page.evaluate('window.__wbLsp')
    assert info and info.get('enabled') is False, f'local bridge must stay off: {info}'
    await _goto_new_file(page, 'C+MSXgl', 'msxgl')
    await _wait_ready(page)
    await h.focus_active_editor(page)
    await _type_slow(page, 'VDP_SetM', pause=60)
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, 'VDP_SetMode'),
                    timeout=20000, msg='worker completions missing on a remote run')
    labels = await _native_labels(page)
    assert any('VDP_SetMode' in s for s in labels), f'VDP_SetMode missing: {labels}'
    assert bridge['ping'] == 0, 'no local-bridge ping on a shared deployment'
    assert bridge['complete'] == 0, 'no local-bridge round trips on a shared deployment'
    assert not msgs, f'console errors: {msgs}'


async def disabled_by_config(page, msgs):
    """Opting out keeps the worker down; the curated dictionaries still work."""
    await page.evaluate("""() => {
        const cfg = window.WBStorage.loadConfig();
        cfg.plugins = { weblsp: false };
        window.WBStorage.saveConfig(cfg);
    }""")
    await page.reload(wait_until='load')
    await page.wait_for_selector('.wb-file-tab', timeout=20000)
    await _goto_new_file(page, 'C+MSXgl', 'msxgl')
    await h.focus_active_editor(page)
    await _type_slow(page, 'VDP_SetM', pause=60)
    # Curated fallback (native-completions.js never stood down: no flag).
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, 'VDP_SetMode'),
                    timeout=20000, msg='curated fallback missing with weblsp off')
    labels = await _native_labels(page)
    assert any('VDP_SetMode' in s for s in labels), f'VDP_SetMode missing: {labels}'
    ready = await page.evaluate("!!(window.__wbWebLsp && window.__wbWebLsp.ready)")
    assert not ready, 'worker must not boot while the plugin is disabled'
    assert await page.evaluate("window.__wbWebLspReady !== true"), 'stand-down flag must stay off'
    assert not msgs, f'console errors: {msgs}'
    # Hygiene for later suites sharing this browser session.
    await page.evaluate("""() => {
        const cfg = window.WBStorage.loadConfig();
        cfg.plugins = {};
        window.WBStorage.saveConfig(cfg);
    }""")


async def local_bridge_wins(page, msgs):
    """With MYSLYX_LSP set, the local bridge serves; the worker stands down.

    Both servers are up, but exactly one may answer each popup: completions
    come from the clangd round trip while the worker's served-completion
    counter stays flat (hover/signature intentionally stay with the worker).
    """
    bridge = _watch_lsp_bridge(page)
    await _reset_config(page)
    info = await page.evaluate('window.__wbLsp')
    assert info and info.get('enabled'), f'local bridge must be advertised: {info}'
    await _goto_new_file(page, 'C+MSXgl', 'msxgl')
    await _wait_ready(page)
    await _wait_for(page, lambda: page.evaluate('window.__wbLocalLspWorking === true'),
                    timeout=20000, msg='local bridge never proved working')
    before = await page.evaluate("(window.__wbWebLsp && window.__wbWebLsp.completedRequests) || 0")
    await h.focus_active_editor(page)
    await _type_slow(page, '#include <string.h>\nint main() { size_t n = strl', pause=120)
    await _wait_for(page, lambda: bridge['complete'] >= 1,
                    timeout=25000, msg='no local-bridge completion round trips')
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, 'strlen'),
                    timeout=25000, msg='strlen never rendered in the native popup')
    labels = await _native_labels(page)
    assert any('strlen' in s for s in labels), f'strlen missing: {labels}'
    after = await page.evaluate("(window.__wbWebLsp && window.__wbWebLsp.completedRequests) || 0")
    assert after == before, f'worker served {after - before} completions while the bridge was up'
    assert not msgs, f'console errors: {msgs}'


async def exclusive_toggle(page, msgs):
    """Enabling a language server from the plugin menu stops the others."""
    await _reset_config(page)
    # Both server plugins are on by default; switch weblsp off first so the
    # enable below exercises the exclusivity handler.
    await _open_plugins_submenu(page)
    assert await _row_checked(page, 'weblsp'), 'weblsp must start enabled by default'
    assert await _row_checked(page, 'local-lsp'), 'local-lsp must start enabled by default'
    await _plugin_row(page, 'weblsp').locator('.wb-plugin-check').click()
    assert not await _row_checked(page, 'weblsp'), 'weblsp must uncheck'
    await _close_menu_and_wait_reload(page)
    # Re-enable weblsp: local-lsp must drop immediately (menu + config).
    await _open_plugins_submenu(page)
    await _plugin_row(page, 'weblsp').locator('.wb-plugin-check').click()
    assert await _row_checked(page, 'weblsp'), 'weblsp must be checked after enabling'
    assert not await _row_checked(page, 'local-lsp'), 'enabling weblsp must uncheck local-lsp'
    cfg = await page.evaluate("window.WBStorage.loadConfig().plugins || {}")
    assert cfg.get('weblsp') is True, f'config must keep weblsp on: {cfg}'
    assert cfg.get('local-lsp') is False, f'config must switch local-lsp off: {cfg}'
    await _close_menu_and_wait_reload(page)
    # After the reload only weblsp boots: worker ready, local bridge never up.
    await _wait_ready(page)
    assert await page.evaluate("window.__wbLocalLspWorking !== true"), \
        'local-lsp must not boot once stopped'
    # Symmetric direction (menu + config asserts need no further reload).
    await _open_plugins_submenu(page)
    await _plugin_row(page, 'local-lsp').locator('.wb-plugin-check').click()
    assert await _row_checked(page, 'local-lsp'), 'local-lsp must be checked after enabling'
    assert not await _row_checked(page, 'weblsp'), 'enabling local-lsp must uncheck weblsp'
    cfg = await page.evaluate("window.WBStorage.loadConfig().plugins || {}")
    assert cfg.get('local-lsp') is True and cfg.get('weblsp') is False, \
        f'exclusivity not persisted: {cfg}'
    assert not msgs, f'console errors: {msgs}'


async def local_variables(page, msgs):
    """Names declared in the open buffer complete: globals, params, locals.

    The persisted symbol store only knows top-level function definitions, so
    the worker mines the synced document text itself on every request.
    """
    bridge = _watch_lsp_bridge(page)
    await _reset_config(page)
    await _goto_new_file(page, 'C+MSXgl', 'msxgl')
    await _wait_ready(page)
    await h.focus_active_editor(page)
    await _type_slow(
        page,
        'int myCounter = 0;\n'
        'int helper(int myParam) {\n'
        'int myLocal = myParam + myCounter;\n'
        'my',
        pause=60)
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, 'myCounter'),
                    timeout=20000, msg='file-scope variable never completed')
    labels = await _native_labels(page)
    for needle in ('myCounter', 'myLocal', 'myParam'):
        assert any(needle in s for s in labels), f'{needle} missing from popup: {labels}'

    # Pascal: var-block names and routine params complete too.
    await h.new_file(page, 3)
    await h.set_language(page, 'Pascal')
    await page.wait_for_function("window.__wbHintKey === 'pascal'")
    await h.focus_active_editor(page)
    await _type_slow(page, 'var myTotal: Integer;\nbegin\nmyT', pause=60)
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, 'MYTOTAL'),
                    timeout=20000, msg='pascal var-block name never completed')
    assert bridge['ping'] == 0, 'no local-bridge ping expected'
    assert bridge['complete'] == 0, 'no local-bridge round trips expected'
    assert not msgs, f'console errors: {msgs}'


async def local_types(page, msgs):
    """Struct/union/enum names declared locally complete — and so do
    variables declared with those local types, plus members of a local
    struct through the native popup (curated path; the worker yields)."""
    bridge = _watch_lsp_bridge(page)
    await _reset_config(page)
    await _goto_new_file(page, 'C+MSXgl', 'msxgl')
    await _wait_ready(page)
    await h.focus_active_editor(page)
    await _type_slow(
        page,
        'typedef struct { u8 x; u8 y; } MySprite;\n'
        'typedef union { u16 w; u8 b[2]; } MyWord;\n'
        'enum MyMode { MY_IDLE, MY_RUN };\n'
        'MySprite player;\n'
        'My',
        pause=60)
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, 'MySprite'),
                    timeout=20000, msg='local struct name never completed')
    labels = await _native_labels(page)
    for needle in ('MySprite', 'MyWord', 'MyMode', 'MY_IDLE', 'MY_RUN'):
        assert any(needle in s for s in labels), f'{needle} missing from popup: {labels}'
    details = await page.evaluate(
        "() => Array.from(document.querySelectorAll("
        "'.cm-tooltip-autocomplete .cm-completionDetail')).map(e => e.textContent)")
    assert any('type' in (d or '') for d in details), f'type tag missing: {details}'

    # A variable declared with the local type completes too (two-pass parse).
    await page.keyboard.press('Escape')
    await page.keyboard.press('Enter')
    await page.keyboard.type('play')
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, 'player'),
                    timeout=20000, msg='variable of local struct type never completed')

    # Members of the local struct resolve natively (curated member path).
    await page.keyboard.press('Escape')
    await page.keyboard.press('Enter')
    await page.keyboard.type('player.')
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, 'x'),
                    timeout=20000, msg='local struct members never completed')
    member_labels = await _native_labels(page)
    assert 'x' in member_labels and 'y' in member_labels, \
        f'local struct members missing: {member_labels}'
    assert bridge['ping'] == 0, 'no local-bridge ping expected'
    assert bridge['complete'] == 0, 'no local-bridge round trips expected'
    assert not msgs, f'console errors: {msgs}'


async def member_complete(page, msgs):
    """Struct/union members after ./-> come from the worker (local struct
    and framework struct alike); each field completes exactly once."""
    bridge = _watch_lsp_bridge(page)
    await _reset_config(page)
    await _goto_new_file(page, 'C+MSXgl', 'msxgl')
    await _wait_ready(page)
    await h.focus_active_editor(page)
    snippet = ('typedef struct { u8 x; u8 y; } MySprite;\n'
               'MySprite player;\n'
               'VDP_Sprite spr;\n')
    await page.evaluate("""(text) => window.WBEditorActive.current(3000).then(v => {
        v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: text } });
        return true;
    })""", snippet)
    await h.doc_equals(page, snippet)
    before = await page.evaluate("(window.__wbWebLsp && window.__wbWebLsp.completedRequests) || 0")
    await page.keyboard.press('Control+End')
    await page.keyboard.type('player.')
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, 'x'),
                    timeout=20000, msg='local struct members never completed')
    labels = await _native_labels(page)
    assert 'x' in labels and 'y' in labels, f'local struct members missing: {labels}'
    assert len(labels) == len(set(labels)), f'duplicate member labels: {labels}'
    after = await page.evaluate("(window.__wbWebLsp && window.__wbWebLsp.completedRequests) || 0")
    assert after > before, 'worker must serve completions in this file'

    # Framework struct members resolve through the worker too.
    await page.keyboard.press('Escape')
    await page.keyboard.press('Enter')
    await page.keyboard.type('spr.')
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, 'X'),
                    timeout=20000, msg='framework struct members never completed')
    fw_labels = await _native_labels(page)
    assert 'X' in fw_labels and 'Y' in fw_labels, f'framework members missing: {fw_labels}'
    assert len(fw_labels) == len(set(fw_labels)), f'duplicate member labels: {fw_labels}'
    assert bridge['ping'] == 0, 'no local-bridge ping expected'
    assert bridge['complete'] == 0, 'no local-bridge round trips expected'
    assert not msgs, f'console errors: {msgs}'


async def include_c_std(page, msgs):
    """Plain C `#include <...>` completes standard headers from the worker."""
    bridge = _watch_lsp_bridge(page)
    await _reset_config(page)
    await _goto_new_file(page, 'C', None)
    await _wait_ready(page)
    await h.focus_active_editor(page)
    await _type_slow(page, '#include <stdi', pause=60)
    await _wait_for(page, lambda: _labels_contain(page, _custom_labels, 'stdio.h'),
                    timeout=20000, msg='stdio.h never rendered in the custom popup')
    labels = await _custom_labels(page)
    for needle in ('stdio.h', 'stdint.h'):
        assert any(needle in s for s in labels), f'{needle} missing: {labels}'
    details = await page.evaluate(
        "() => Array.from(document.querySelectorAll("
        "'.wb-autocomplete-popup > div')).map(e => e.lastChild ? e.lastChild.textContent : '')")
    assert any('header' in (d or '') for d in details), f'header tag missing: {details}'

    # Bare delimiter lists every standard header.
    await page.keyboard.press('Escape')
    await page.keyboard.press('Enter')
    await page.keyboard.type('#include <')
    await _wait_for(page, lambda: _labels_contain(page, _custom_labels, 'string.h'),
                    timeout=20000, msg='full header list never rendered')
    assert bridge['ping'] == 0, 'no local-bridge ping expected'
    assert bridge['complete'] == 0, 'no local-bridge round trips expected'
    assert not msgs, f'console errors: {msgs}'


async def include_msxgl_modules(page, msgs):
    """C MSXgl `#include "..."` completes the engine modules natively."""
    bridge = _watch_lsp_bridge(page)
    await _reset_config(page)
    await _goto_new_file(page, 'C+MSXgl', 'msxgl')
    await _wait_ready(page)
    await h.focus_active_editor(page)
    await _type_slow(page, '#include "msxg', pause=60)
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, 'msxgl.h'),
                    timeout=20000, msg='msxgl.h never rendered in the native popup')
    labels = await _native_labels(page)
    assert any('msxgl.h' in s for s in labels), f'msxgl.h missing: {labels}'

    # Bracket includes reach the engine headers too.
    await page.keyboard.press('Escape')
    await page.keyboard.press('Enter')
    await page.keyboard.type('#include <vd')
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, 'vdp.h'),
                    timeout=20000, msg='vdp.h never rendered for bracket includes')
    assert bridge['ping'] == 0, 'no local-bridge ping expected'
    assert bridge['complete'] == 0, 'no local-bridge round trips expected'
    assert not msgs, f'console errors: {msgs}'


async def include_local_headers(page, msgs):
    """Both languages complete the project's own .h files (quoted only)."""
    bridge = _watch_lsp_bridge(page)
    await _reset_config(page)
    # Import a project header through the upload drop path.
    before = await page.evaluate("document.querySelectorAll('.wb-file-tab').length")
    await page.evaluate("""() => {
        const dt = new DataTransfer();
        dt.items.add(new File(['#pragma once\\nint shared_value;\\n'], 'mydefs.h', {type: 'text/plain'}));
        const ev = new Event('drop', {bubbles: true, cancelable: true});
        try { Object.defineProperty(ev, 'dataTransfer', {value: dt}); } catch(e) { ev.dataTransfer = dt; }
        document.dispatchEvent(ev);
    }""")
    await page.wait_for_function(
        f"document.querySelectorAll('.wb-file-tab').length > {before}", timeout=15000)
    n = await page.evaluate("document.querySelectorAll('.wb-file-tab').length")
    await h.new_file(page, n + 1)
    await h.set_language(page, 'C')
    await _wait_ready(page)
    await h.focus_active_editor(page)
    await _type_slow(page, '#include "myd', pause=60)
    await _wait_for(page, lambda: _labels_contain(page, _custom_labels, 'mydefs.h'),
                    timeout=20000, msg='project header never rendered')
    labels = await _custom_labels(page)
    assert any('mydefs.h' in s for s in labels), f'mydefs.h missing: {labels}'

    # Bracket includes never offer project headers.
    await page.keyboard.press('Escape')
    await page.keyboard.press('Enter')
    await page.keyboard.type('#include <myd')
    await page.wait_for_timeout(1200)
    assert not await page.evaluate("!!document.querySelector('.wb-autocomplete-popup')"), \
        'project headers must not complete inside <...>'
    assert bridge['ping'] == 0, 'no local-bridge ping expected'
    assert bridge['complete'] == 0, 'no local-bridge round trips expected'
    assert not msgs, f'console errors: {msgs}'


async def include_closers(page, msgs):
    """Accepting an #include completion inserts its closing bracket."""
    bridge = _watch_lsp_bridge(page)
    await _reset_config(page)
    await _goto_new_file(page, 'C', None)
    await _wait_ready(page)
    await h.focus_active_editor(page)
    await _type_slow(page, '#include <stdi', pause=60)
    await _wait_for(page, lambda: _labels_contain(page, _custom_labels, 'stdint.h'),
                    timeout=20000, msg='stdint.h never rendered')
    await page.keyboard.press('Enter')
    await h.doc_equals(page, '#include <stdint.h>', timeout=10000,
                       msg='accepting must close the bracket')

    # Quoted includes close with a quote in C MSXgl too (native popup).
    await h.new_file(page, 3)
    await h.set_language(page, 'C+MSXgl')
    await page.wait_for_function("window.__wbHintKey === 'msxgl'")
    await h.focus_active_editor(page)
    await _type_slow(page, '#include "msxg', pause=60)
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, 'msxgl.h'),
                    timeout=20000, msg='msxgl.h never rendered')
    await page.keyboard.press('Enter')
    await h.doc_equals(page, '#include "msxgl.h"', timeout=10000,
                       msg='accepting must close the quote')
    assert bridge['ping'] == 0, 'no local-bridge ping expected'
    assert bridge['complete'] == 0, 'no local-bridge round trips expected'
    assert not msgs, f'console errors: {msgs}'


WEBLSP_DEFAULT_SUITES = [
    ('weblsp/completions-msxgl-native', completions_msxgl_native, None),
    ('weblsp/completions-c-custom', completions_c_custom, None),
    ('weblsp/completions-pascal-native', completions_pascal_native, None),
    ('weblsp/local-variables', local_variables, None),
    ('weblsp/local-types', local_types, None),
    ('weblsp/member-complete', member_complete, None),
    ('weblsp/include-c-std', include_c_std, None),
    ('weblsp/include-msxgl-modules', include_msxgl_modules, None),
    ('weblsp/include-local', include_local_headers, None),
    ('weblsp/include-closers', include_closers, None),
    ('weblsp/hover', hover_tip, None),
    ('weblsp/signature-help', signature_help, None),
    ('weblsp/exclusive-toggle', exclusive_toggle, None),
    ('weblsp/disabled-by-config', disabled_by_config, None),
]

WEBLSP_REMOTE_SUITES = [
    # Same binary-less phase shape as local-gate: the app only looks shared.
    ('weblsp/remote-works', remote_works, {'SPACE_ID': '1'}),
]

WEBLSP_BRIDGE_SUITES = [
    # Machine-installed server present: the local bridge wins completions.
    ('weblsp/local-bridge-wins', local_bridge_wins, {'MYSLYX_LSP': 'clangd'}),
]

WEBLSP_SUITES = WEBLSP_DEFAULT_SUITES + WEBLSP_REMOTE_SUITES + WEBLSP_BRIDGE_SUITES
