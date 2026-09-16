"""Acceptance suite for native (CodeMirror) autocomplete.

C MSXgl is the reference implementation for native autocomplete in Myslyx;
Pascal follows the same pattern. C MSXgl and Pascal swap the custom
.wb-autocomplete-popup for CodeMirror's built-in autocomplete
(native-completions.js). C MSXgl member access on "." / "->" resolves through
the parse tree plus the shared struct model, and plain words complete from
msxgl.json (keywords incl. SDCC, builtins, types) plus user symbols; Pascal
completes words from pascal.json (keywords, builtins, user symbols —
case-insensitive, no member completion). All other languages keep the custom
popup. Both popups follow the editor's FONT/BASE FONT SIZE controls (the CSS
vars --wb-editor-font / --wb-editor-font-size).
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


async def _goto_pascal(page):
    await h.new_file(page, 2)
    await h.set_language(page, 'Pascal')
    await page.wait_for_function("window.__wbHintKey === 'pascal'")
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


async def _accept_label(page, labels, timeout=15000):
    """Press Enter and make sure the highlighted completion was really inserted.

    CodeMirror treats an Enter as a plain newline when it arrives within its
    interactionDelay (~75ms) of the popup opening, on purpose (typists). Wait
    past that window and retry until the accept lands.
    """
    deadline = __import__('time').monotonic() + timeout / 1000
    while True:
        await page.wait_for_timeout(250)
        await page.keyboard.press('Enter')
        try:
            await h.doc_equals(page, labels[0], timeout=1500)
            return
        except Exception:
            if __import__('time').monotonic() >= deadline:
                raise


async def native_pascal_word_completion(page, msgs):
    """Pascal (case-insensitive) completes natively, never via the custom popup."""
    await _goto_pascal(page)

    # Builtins from pascal.json render in the native tooltip.
    await page.keyboard.type('writ')
    await _labels_rendered(page)
    labels = await _labels(page)
    assert 'writeln' in labels, f'pascal builtins missing: {labels}'
    assert not await _custom_popup_present(page), 'custom popup must not show for Pascal'

    # Keywords complete too, and uppercase input still matches (Pascal is
    # case-insensitive); Enter accepts the highlighted match.
    await page.keyboard.press('Escape')
    await page.keyboard.press('Control+a')
    await page.keyboard.press('Backspace')
    await page.keyboard.type('PROC')
    await _labels_rendered(page)
    labels = await _labels(page)
    assert 'procedure' in labels, f'pascal keywords missing: {labels}'
    assert not await _custom_popup_present(page), 'custom popup must not show for Pascal'
    await _accept_label(page, labels)

    # A member-style "type." must NOT offer struct-member completions (Julia's
    # pascal.json has no structs; the member source is C-only).
    await page.keyboard.press('Control+a')
    await page.keyboard.press('Backspace')
    await page.keyboard.type('r.rounded;')
    await page.wait_for_timeout(600)
    assert not await _custom_popup_present(page), 'custom popup must not show for Pascal'
    assert msgs == []


async def native_pascal_language_toggle(page, msgs):
    """Switching a Pascal view to HitBasic restores the custom popup and back."""
    await _goto_pascal(page)
    await page.keyboard.type('writ')

    # HitBasic still uses the custom popup (only Pascal/C MSXgl participate in
    # the native one).
    await h.set_language(page, 'HitBasic')
    await page.wait_for_function("window.__wbHintKey === 'hitbasic'")
    await h.focus_active_editor(page)
    await page.keyboard.press('Control+a')
    await page.keyboard.press('Backspace')
    await page.keyboard.type('pr')
    await page.wait_for_function(
        "!!document.querySelector('.wb-autocomplete-popup')", timeout=10000)
    assert msgs == []


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


async def _pick_font(page, font_label):
    """Select ``font_label`` from the FONT combo (second .wb-select)."""
    await page.locator('.wb-select').nth(1).click()
    await page.wait_for_function("""() => {
        const m = document.querySelector('.q-menu');
        if (!m) return false;
        const cs = getComputedStyle(m);
        return cs.visibility !== 'hidden' && cs.opacity !== '0'
            && m.getBoundingClientRect().width > 0;
    }""", timeout=10000)
    await page.locator('.q-menu').get_by_text(font_label, exact=True).first.click()
    await page.wait_for_function("""() => {
        const m = document.querySelector('.q-menu');
        return !m || m.getBoundingClientRect().width === 0;
    }""", timeout=10000)


async def native_font_follows_editor(page, msgs):
    """The autocomplete tooltip uses the editor's font family AND size.

    The @codemirror/autocomplete base theme pins the tooltip's list to
    'monospace' ("& > ul"), so the override lives in retro.css on
    '.cm-tooltip-autocomplete > ul'; a live var change (the FONT combo) must
    restyle an already-open popup without a reload.
    """
    await _goto_pascal(page)
    await page.keyboard.type('writ')
    await _labels_rendered(page)

    # Rebinding the editor font through the FONT combo must restyle the popup.
    await _pick_font(page, 'Courier New')
    await h.focus_active_editor(page)
    await page.keyboard.press('End')
    await page.keyboard.type('e')
    await _labels_rendered(page)
    probe = await page.evaluate("""() => {
        const pick = (sel) => {
            const el = document.querySelector(sel);
            if (!el) return null;
            const cs = getComputedStyle(el);
            return cs.fontFamily + ' @ ' + cs.fontSize;
        };
        const root = getComputedStyle(document.documentElement);
        return {
            font: root.getPropertyValue('--wb-editor-font'),
            size: root.getPropertyValue('--wb-editor-font-size'),
            tooltip: pick('.cm-tooltip-autocomplete'),
            label: pick('.cm-tooltip-autocomplete .cm-completionLabel'),
            matched: pick('.cm-tooltip-autocomplete .cm-completionMatchedText'),
        };
    }""")
    assert 'Courier New' in probe['font'], f'FONT combo must set the var: {probe["font"]!r}'
    assert probe['label'] is not None, 'native tooltip must render after reopening'
    assert 'Courier New' in probe['tooltip'], f'tooltip shell must follow editor font: {probe}'
    assert 'Courier New' in probe['label'], f'label must follow editor font: {probe}'
    assert 'Courier New' in probe['matched'], f'matched text must follow editor font: {probe}'

    # Font size: the same CSS-var mechanism (drive the var exactly like
    # _apply_editor_font_size does) must resize an open popup immediately.
    await page.evaluate("""() =>
        document.documentElement.style.setProperty('--wb-editor-font-size', '10px')""")
    await page.wait_for_timeout(150)
    probe2 = await page.evaluate("""() => {
        const e = document.querySelector('.cm-tooltip-autocomplete .cm-completionLabel');
        return e ? getComputedStyle(e).fontSize : null;
    }""")
    assert probe2 == '10px', f'popup must resize with the editor font size: {probe2!r}'
    assert msgs == []


async def native_msxgl_function_keeps_case(page, msgs):
    """C user functions autocomplete in their declared case.

    C is case-sensitive: a local `myFunc` must complete as `myFunc`, never as
    the uppercased `MYFUNC` the symbol scanner historically stored.
    """
    await _goto_msxgl(page)
    await page.keyboard.type('void myFunc(void) {')
    await page.keyboard.press('Enter')
    await page.keyboard.type('    x += 1;')
    await page.keyboard.press('Enter')
    await page.keyboard.type('}')
    await page.wait_for_timeout(600)  # symbol scan (scheduleScan debounce ~250ms)

    await page.keyboard.press('End')
    await page.keyboard.press('Enter')
    await page.keyboard.type('my')
    await _labels_rendered(page)
    labels = await _labels(page)
    assert 'myFunc' in labels, f'user function must keep its original case: {labels}'
    assert 'MYFUNC' not in labels, f'user function must not be uppercased: {labels}'

    # Plain C shows the same name in the custom popup.
    await page.keyboard.press('Escape')
    await h.set_language(page, 'C')
    await page.wait_for_function("window.__wbHintKey === 'c'")
    await h.focus_active_editor(page)
    await page.keyboard.press('End')
    await page.keyboard.press('Enter')
    await page.keyboard.type('my')
    await page.wait_for_function(
        "!!document.querySelector('.wb-autocomplete-popup')", timeout=10000)
    custom = await page.evaluate("""() =>
        Array.from(document.querySelectorAll('.wb-autocomplete-popup div'))
            .map(e => e.textContent.trim()).filter(Boolean)""")
    assert any('myFunc' in t for t in custom), f'custom popup must keep case: {custom}'
    assert not any('MYFUNC' in t for t in custom), f'custom popup uppercased: {custom}'
    assert msgs == []
    custom = await page.evaluate("""() =>
        Array.from(document.querySelectorAll('.wb-autocomplete-popup div'))
            .map(e => e.textContent.trim()).filter(Boolean)""")
    assert any('myFunc' in t for t in custom), f'custom popup must keep case: {custom}'
    assert not any('MYFUNC' in t for t in custom), f'custom popup uppercased: {custom}'
    assert msgs == []


NATIVE_SUITES = [
    ('native/msxgl-member', native_msxgl_member_completion),
    ('native/msxgl-lang-toggle', native_msxgl_language_toggle),
    ('native/pascal-word', native_pascal_word_completion),
    ('native/pascal-lang-toggle', native_pascal_language_toggle),
    ('native/font-follows-editor', native_font_follows_editor),
    ('native/msxgl-function-case', native_msxgl_function_keeps_case),
]