"""Acceptance suite for C MSXgl native (CodeMirror) autocomplete.

C MSXgl swaps the custom .wb-autocomplete-popup for CodeMirror's built-in
autocomplete (native-completions.js): member access on "." / "->" resolves
through the parse tree plus the shared struct model, and plain words complete
from msxgl.json (keywords incl. SDCC, builtins, types) plus user symbols. All
other languages keep the custom popup.
"""

from tests import helpers as h


async def _labels_rendered(page, timeout=10000):
    """Wait until the native tooltip has actually rendered completion rows."""
    await page.wait_for_function(
        """() => document.querySelectorAll(
            '.cm-tooltip-autocomplete .cm-completionLabel').length > 0""",
        timeout=timeout,
    )


async def _labels(page):
    return await page.evaluate(
        """() => Array.from(document.querySelectorAll(
            '.cm-tooltip-autocomplete .cm-completionLabel'))
            .map(e => e.textContent)"""
    )


async def _custom_popup_present(page) -> bool:
    return await page.evaluate("!!document.querySelector('.wb-autocomplete-popup')")


async def _goto_msxgl(page):
    await h.new_file(page, 2)
    await h.set_language(page, 'C+MSXgl')
    await page.wait_for_function("window.__wbHintKey === 'msxgl'")
    await h.focus_active_editor(page)


async def _member_accept(page, labels, timeout=15000):
    """Press Enter and make sure the highlighted member was really inserted.

    CodeMirror treats an Enter as a plain newline when it arrives within its
    interactionDelay (~75ms) of the popup opening, on purpose (typists). Wait
    past that window and retry until the accept lands.
    """
    expected = '#include <msxgl.h>\nVDP_Sprite spr;\nspr.' + labels[0]
    deadline = __import__('time').monotonic() + timeout / 1000
    while True:
        await page.wait_for_timeout(250)
        await page.keyboard.press('Enter')
        try:
            await h.doc_equals(page, expected, timeout=1500)
            return
        except Exception:
            if __import__('time').monotonic() >= deadline:
                raise


async def native_msxgl_member_completion(page, msgs):
    """C MSXgl completes struct members natively, never via the custom popup."""
    await _goto_msxgl(page)
    await page.keyboard.type('#include <msxgl.h>')
    await page.keyboard.press('Enter')
    await page.keyboard.type('VDP_Sprite spr;')
    await page.keyboard.press('Enter')
    await page.keyboard.type('spr.')

    # The parse-tree member options render in the native tooltip.
    await _labels_rendered(page)
    labels = await _labels(page)
    assert 'X' in labels and 'Y' in labels, f'VDP_Sprite members missing: {labels}'
    assert not await _custom_popup_present(page), 'custom popup must not show for C MSXgl'

    # Enter accepts the highlighted (first) field.
    await _member_accept(page, labels)

    # Word completion from msxgl.json (case-insensitive prefix), still native.
    await page.keyboard.press('Escape')
    await page.keyboard.press('Enter')
    await page.keyboard.type('vdp_se')
    await _labels_rendered(page)
    word_labels = await _labels(page)
    assert any(l.startswith('VDP_') for l in word_labels), f'no VDP_ words: {word_labels}'
    assert not await _custom_popup_present(page), 'custom popup must not show for C MSXgl'
    assert msgs == []


async def native_msxgl_language_toggle(page, msgs):
    """Switching a C MSXgl view to plain C restores the custom popup and back."""
    await _goto_msxgl(page)
    await page.keyboard.type('#include <msxgl.h>')
    await page.keyboard.press('Enter')
    await page.keyboard.type('VDP_Sprite spr;')
    await page.keyboard.press('Enter')

    # Plain C: custom popup is back (and stays the only completion source).
    await h.set_language(page, 'C')
    await page.wait_for_function("window.__wbHintKey === 'c'")
    await h.focus_active_editor(page)
    await page.keyboard.type('s')
    await page.wait_for_function(
        "!!document.querySelector('.wb-autocomplete-popup')", timeout=10000)
    await page.keyboard.press('Escape')
    await page.wait_for_function(
        "!document.querySelector('.wb-autocomplete-popup')", timeout=10000)

    # Back to C MSXgl on the same view: the native tooltip works again and the
    # member popup never reverts to the custom one.
    await h.set_language(page, 'C+MSXgl')
    await page.wait_for_function("window.__wbHintKey === 'msxgl'")
    await h.focus_active_editor(page)
    await page.keyboard.press('Enter')
    await page.keyboard.type('spr.')
    await _labels_rendered(page)
    assert not await _custom_popup_present(page), 'custom popup must not show for C MSXgl'
    assert msgs == []


NATIVE_SUITES = [
    ('native/msxgl-member', native_msxgl_member_completion),
    ('native/msxgl-lang-toggle', native_msxgl_language_toggle),
]