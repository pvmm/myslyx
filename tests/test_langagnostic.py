"""Acceptance suite for language-agnostic plugin behaviour.

The LSP plugins resolve the current language through ONE descriptor
(`window.WBLanguage` in static/retro.js) instead of hardcoding hint keys:
plain C and C MSXgl are two dialects of the same base language ('c'), Pascal
is a different one. These suites pin that contract, so a future dialect (or a
regression that reintroduces a hardcoded key) shows up here:

- `descriptor` walks every language and asserts the descriptor's answers
  (family, popup, LSP languageId, whether the machine bridge may serve it).
- `c-vs-msxgl-roundtrip` switches ONE file between C and C MSXgl and back,
  asserting each dialect completes through the popup its descriptor promises
  and that the worker keeps answering across the switches.
- `pascal-not-c` asserts a different family does not inherit C's behaviour
  (native popup, no `#include` header list).
- `text-inert` asserts a language with no family is left completely alone.

Both language servers are covered where they can run: these suites need no
server binary (the in-browser worker), so they are registration-env free.
"""

import json

from tests import helpers as h
from tests.test_weblsp import _reset_config, _wait_ready, _watch_lsp_bridge
from tests.test_lsp import (
    _custom_labels,
    _goto_new_file,
    _labels_contain,
    _native_labels,
    _type_slow,
    _wait_for,
)

# (name, fn, env). env None -> the default server.


# ----- helpers -------------------------------------------------------------

async def _descriptor(page):
    """The editor's language descriptor for the active file, as JSON."""
    return await page.evaluate("""() => {
        const L = window.WBLanguage;
        return {
            base: L.base(),
            hintKey: L.hintKey(),
            label: L.label(),
            hasFamily: L.hasFamily(),
            usesNativePopup: L.usesNativePopup(),
            languageId: L.lspLanguageId(),
            hasHeaders: L.hasHeaders(),
            localLspServes: L.localLspServes(),
        };
    }""")


async def _set_language(page, label, hint_key):
    """Switch the active file's language and wait for the descriptor to follow."""
    await h.set_language(page, label)
    await page.wait_for_function(
        "() => window.__wbHintKey === %s" % json.dumps(hint_key), timeout=10000)


async def _select_all_and_replace(page, text):
    """Clear the buffer, then type `text` (fresh query for the new language)."""
    await page.keyboard.press('Control+a')
    await page.keyboard.press('Delete')
    await page.wait_for_timeout(150)
    await _type_slow(page, text, pause=60)


# ----- suites --------------------------------------------------------------

async def descriptor(page, msgs):
    """WBLanguage answers per language, and both C dialects share one family."""
    await _reset_config(page)

    # Plain C: base family 'c', retro popup, C headers, bridge may serve it.
    await _goto_new_file(page, 'C', 'c')
    d = await _descriptor(page)
    assert d['base'] == 'c', f'plain C base language: {d}'
    assert d['hintKey'] == 'c', f'plain C dictionary: {d}'
    assert d['hasFamily'] is True, f'plain C must have a language family: {d}'
    assert d['usesNativePopup'] is False, f'plain C uses the retro popup: {d}'
    assert d['languageId'] == 'c', f'plain C LSP languageId: {d}'
    assert d['hasHeaders'] is True, f'plain C has #include headers: {d}'
    assert d['localLspServes'] is True, f'plain C is bridge-servable: {d}'

    # C MSXgl: a DIFFERENT dictionary on the SAME family -> native popup.
    await _set_language(page, 'C+MSXgl', 'msxgl')
    d = await _descriptor(page)
    assert d['base'] == 'c', f'C MSXgl must share the C family: {d}'
    assert d['hintKey'] == 'msxgl', f'C MSXgl dictionary: {d}'
    assert d['languageId'] == 'c', f'C MSXgl LSP languageId: {d}'
    assert d['usesNativePopup'] is True, f'C MSXgl uses the native popup: {d}'
    assert d['hasHeaders'] is True, f'C MSXgl has #include headers: {d}'
    assert d['localLspServes'] is True, f'C MSXgl is bridge-servable: {d}'

    # Pascal: another family, no headers, and the bridge must not claim it.
    await _set_language(page, 'Pascal', 'pascal')
    d = await _descriptor(page)
    assert d['base'] == 'pascal', f'Pascal family: {d}'
    assert d['hintKey'] == 'pascal', f'Pascal dictionary: {d}'
    assert d['languageId'] == 'pascal', f'Pascal LSP languageId: {d}'
    assert d['usesNativePopup'] is True, f'Pascal uses the native popup: {d}'
    assert d['hasHeaders'] is False, f'Pascal has no #include headers: {d}'
    assert d['localLspServes'] is False, f'Pascal must not be bridge-servable: {d}'

    # Plain text: no family at all -> every language server stays out.
    await _set_language(page, 'Text', 'plaintext')
    d = await _descriptor(page)
    assert d['hasFamily'] is False, f'plain text must have no family: {d}'
    assert d['languageId'] is None, f'plain text must not name a languageId: {d}'
    assert d['localLspServes'] is False, f'plain text is not bridge-servable: {d}'

    assert not msgs, f'console errors: {msgs}'


async def c_vs_msxgl_roundtrip(page, msgs):
    """C and C MSXgl both complete, each through its own popup, back and forth."""
    bridge = _watch_lsp_bridge(page)
    await _reset_config(page)
    await _goto_new_file(page, 'C', 'c')
    await _wait_ready(page)

    # 1. Plain C -> retro .wb-autocomplete-popup, fed by the worker.
    await h.focus_active_editor(page)
    await _type_slow(page, 'int main() { strl', pause=60)
    await _wait_for(page, lambda: _labels_contain(page, _custom_labels, 'strlen'),
                    timeout=20000, msg='plain C: strlen never in the custom popup')
    assert await _custom_labels(page), 'plain C: the retro popup stayed empty'

    # 2. Same file, C MSXgl -> native popup, still fed by the same worker.
    await _set_language(page, 'C+MSXgl', 'msxgl')
    await h.focus_active_editor(page)
    await _select_all_and_replace(page, 'int main() { VDP_SetM')
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, 'VDP_SetMode'),
                    timeout=20000, msg='C MSXgl: VDP_SetMode never in the native popup')
    labels = await _native_labels(page)
    assert any('VDP_SetMode' in s for s in labels), f'C MSXgl: VDP_SetMode missing: {labels}'

    # 3. Back to plain C -> retro popup again (the descriptor drives the popup,
    #    not the file's history).
    await _set_language(page, 'C', 'c')
    await h.focus_active_editor(page)
    await _select_all_and_replace(page, 'int main() { strl')
    await _wait_for(page, lambda: _labels_contain(page, _custom_labels, 'strlen'),
                    timeout=20000, msg='back to plain C: strlen never in the custom popup')

    assert bridge['ping'] == 0, 'no local-bridge ping expected'
    assert bridge['complete'] == 0, 'no local-bridge round trips expected'
    assert not msgs, f'console errors: {msgs}'


async def pascal_not_c(page, msgs):
    """A different family does not inherit C's behaviour."""
    bridge = _watch_lsp_bridge(page)
    await _reset_config(page)
    await _goto_new_file(page, 'Pascal', 'pascal')
    await _wait_ready(page)
    await h.focus_active_editor(page)

    # Pascal completes through the native popup...
    await _type_slow(page, 'begin writ', pause=60)
    await _wait_for(page, lambda: _labels_contain(page, _native_labels, 'writeln'),
                    timeout=20000, msg='Pascal: writeln never in the native popup')
    assert not await _custom_labels(page), 'Pascal must not use the retro popup'

    # ...and gets no C header list: `#include` is not its syntax.
    await _select_all_and_replace(page, '#include <strin')
    await page.wait_for_timeout(1200)
    labels = await _native_labels(page) + await _custom_labels(page)
    assert not any(s.endswith('.h') for s in labels), \
        f'Pascal must not offer C headers: {labels}'

    assert bridge['ping'] == 0, 'no local-bridge ping expected'
    assert bridge['complete'] == 0, 'no local-bridge round trips expected'
    assert not msgs, f'console errors: {msgs}'


async def text_inert(page, msgs):
    """A language with no family is left completely alone."""
    bridge = _watch_lsp_bridge(page)
    await _reset_config(page)
    await _goto_new_file(page, 'Text', 'plaintext')
    await _wait_ready(page)
    await h.focus_active_editor(page)
    await _type_slow(page, 'strl', pause=60)
    await page.wait_for_timeout(1200)

    d = await _descriptor(page)
    assert d['hasFamily'] is False, f'plain text must have no family: {d}'
    assert not await _custom_labels(page), 'plain text must not open the retro popup'
    assert not await _native_labels(page), 'plain text must not open the native popup'
    assert bridge['ping'] == 0, 'no local-bridge ping expected'
    assert bridge['complete'] == 0, 'no local-bridge round trips expected'
    assert not msgs, f'console errors: {msgs}'


LANG_AGNOSTIC_SUITES = [
    ('langagnostic/descriptor', descriptor, None),
    ('langagnostic/c-vs-msxgl-roundtrip', c_vs_msxgl_roundtrip, None),
    ('langagnostic/pascal-not-c', pascal_not_c, None),
    ('langagnostic/text-inert', text_inert, None),
]