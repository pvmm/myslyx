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


WEBLSP_DEFAULT_SUITES = [
    ('weblsp/completions-msxgl-native', completions_msxgl_native, None),
    ('weblsp/completions-c-custom', completions_c_custom, None),
    ('weblsp/completions-pascal-native', completions_pascal_native, None),
    ('weblsp/local-variables', local_variables, None),
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
