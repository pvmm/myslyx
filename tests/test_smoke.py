"""Smoke suite: wrap toggle, export-symbols, hints browsing and counts."""

from tests import helpers as h


async def wrap_toggle_preserves_content(page, msgs):
    await h.new_file(page, 2)
    await page.keyboard.type('PRINT 42')
    await h.doc_equals(page, 'PRINT 42')
    before = await h.doc_text(page)
    assert before == 'PRINT 42'
    await h.open_settings(page)
    wrap_row = page.locator('#wb-settings-wrap')
    # The WRAP row must not use the orange .active highlight (reserved for
    # hover/open flyout); its ON/OFF state shows as the value text instead.
    assert await wrap_row.evaluate("el => !el.classList.contains('active')"), \
        'WRAP row must not stay orange via .active'
    before_state = await page.evaluate(
        "document.getElementById('wb-settings-wrap')?.dataset.value || 'OFF'")
    await page.click('#wb-settings-wrap')
    await h.wait_for_settings_value(page, 'wb-settings-wrap',
                                    'OFF' if before_state == 'ON' else 'ON')
    after = await h.doc_text(page)
    assert after == before, f'wrap toggle must not alter content: {after!r}'
    assert await wrap_row.evaluate("el => !el.classList.contains('active')"), \
        'WRAP row must stay unhighlighted after toggling'
    assert msgs == []


async def wrap_off_preserves_content(page, msgs):
    await h.new_file(page, 2)
    await page.keyboard.type('LINE1')
    await h.doc_equals(page, 'LINE1')
    # Default wrap state is whatever persisted; toggling twice nets out but
    # must still preserve content.
    cur = await page.evaluate(
        "document.getElementById('wb-settings-wrap')?.dataset.value || 'OFF'")
    for _ in range(2):
        await h.open_settings(page)
        await page.click('#wb-settings-wrap')
        cur = 'OFF' if cur == 'ON' else 'ON'
        await h.wait_for_settings_value(page, 'wb-settings-wrap', cur)
    assert await h.doc_text(page) == 'LINE1'
    assert msgs == []


async def export_disabled_for_text(page, msgs):
    # STARTUP.txt is plain text -> the export-symbols toggle must be disabled.
    export = page.locator('#wb-export-btn')
    await export.wait_for(state='visible', timeout=10000)
    assert await export.is_disabled(), 'export toggle must be disabled for Text language'
    label = (await export.inner_text()).replace('\n', ' ')
    assert '---' in label, f'unexpected label for disabled export: {label!r}'
    # Import a .bas file (HitBasic) -> the toggle must re-enable.
    before = await page.evaluate("document.querySelectorAll('.wb-file-tab').length")
    await page.evaluate("""() => {
        const dt = new DataTransfer();
        dt.items.add(new File(['PRINT 42'], 'demo.bas', {type: 'text/plain'}));
        const ev = new Event('drop', {bubbles: true, cancelable: true});
        try { Object.defineProperty(ev, 'dataTransfer', {value: dt}); } catch(e) { ev.dataTransfer = dt; }
        document.dispatchEvent(ev);
    }""")
    await page.wait_for_function(
        f"document.querySelectorAll('.wb-file-tab').length === {before + 1}")
    await page.wait_for_function("""() => {
        const b = document.getElementById('wb-export-btn');
        return !!b && !b.disabled;
    }""", timeout=15000)
    assert not await export.is_disabled(), 'export toggle must re-enable for a code language'
    label = (await export.inner_text()).replace('\n', ' ')
    assert 'ON' in label, f'unexpected label for enabled export: {label!r}'
    assert msgs == []


async def export_disabled_on_language_switch(page, msgs):
    # New files default to HitBasic -> the export toggle is usable.
    await h.new_file(page, 2)
    export = page.locator('#wb-export-btn')
    await export.wait_for(state='visible', timeout=10000)
    assert not await export.is_disabled(), 'code language -> export toggle enabled'
    # Switching the active file to plain text disables the toggle.
    await h.set_language(page, 'Text')
    await page.wait_for_function("""() => {
        const b = document.getElementById('wb-export-btn');
        return !!b && b.disabled;
    }""", timeout=10000)
    assert await export.is_disabled(), 'export must disable after switching to Text'
    label = (await export.inner_text()).replace('\n', ' ')
    assert '---' in label, f'unexpected label for disabled export: {label!r}'
    # A document in Text cannot toggle it, even programmatically.
    state = await page.evaluate("""() => {
        const f = window.__wbPyBridge.getFiles();
        const active = f.find(x => x.id === window.__wbPyBridge.getActive());
        return active ? active.export_symbols : null;
    }""")
    assert state is True, f'export_symbols must stay untouched in Text: {state}'
    # Switching back to a code language re-enables the toggle.
    await h.set_language(page, 'HitBasic')
    await page.wait_for_function("""() => {
        const b = document.getElementById('wb-export-btn');
        return !!b && !b.disabled;
    }""", timeout=10000)
    assert not await export.is_disabled(), 'export must re-enable after leaving Text'
    label = (await export.inner_text()).replace('\n', ' ')
    assert 'ON' in label, f'unexpected re-enabled label: {label!r}'
    # The toggle itself still flips ON <-> OFF for code languages.
    await page.click('#wb-export-btn')
    await page.wait_for_function("""() => {
        const t = document.getElementById('wb-export-btn');
        return !!t && t.textContent.indexOf('OFF') !== -1;
    }""", timeout=10000)
    label = (await export.inner_text()).replace('\n', ' ')
    assert 'OFF' in label, f'toggle did not switch OFF: {label!r}'
    await page.click('#wb-export-btn')
    await page.wait_for_function("""() => {
        const t = document.getElementById('wb-export-btn');
        return !!t && t.textContent.indexOf('ON') !== -1;
    }""", timeout=10000)
    label = (await export.inner_text()).replace('\n', ' ')
    assert 'ON' in label, f'toggle did not switch back ON: {label!r}'
    assert msgs == []


async def file_stats_counts(page, msgs):
    # The bundled file-stats plugin injects a counts node under the active
    # file name and fills it from the active editor's document.
    counts = page.locator('#wb-file-counts')
    await counts.wait_for(state='attached', timeout=10000)
    await page.wait_for_function("""
        () => /chars/.test((document.getElementById('wb-file-counts') || {}).textContent || '')
    """)
    # A fresh file is empty -> the counts line clears.
    await h.new_file(page, 2)
    await page.wait_for_function("""
        () => (document.getElementById('wb-file-counts') || {}).textContent === ''
    """)
    # Typing updates counts live: "PRINT 42\nREM hi" -> 15 chars, 4 words, 2 lines.
    await h.active_cm(page).click()
    await page.keyboard.type('PRINT 42\nREM hi')
    await page.wait_for_function("""
        () => (document.getElementById('wb-file-counts') || {}).textContent
                 === '15 chars \u00b7 4 words \u00b7 2 lines'
    """)
    assert msgs == []


async def hints_page_title(page):
    return await page.evaluate("""() => {
        const t = document.querySelector('#hints-content .hint-title');
        return t ? t.textContent : null;
    }""")


async def hints_nav_browse(page, msgs):
    # The HINTS panel records every shown page; the ◀ ▶ buttons in the title
    # bar move back and forward through the visited pages.
    nav = page.locator('.wb-hints-nav-btn')
    await nav.nth(0).wait_for(state='attached', timeout=10000)
    await h.new_file(page, 2)
    # Typing a word with a tip pushes a page; two words -> two history entries
    # (the root page shown by "new file" is the first entry). GOTO's partial
    # prefixes are not hints, so it adds exactly one page.
    await h.active_cm(page).click()
    await page.keyboard.type('PRINT GOTO')
    await page.wait_for_function("""
        () => (document.querySelector('#hints-content .hint-title') || {}).textContent === 'GOTO'
    """)
    title = await hints_page_title(page)
    assert title == 'GOTO', f'expected GOTO hint, got {title!r}'
    # End of history: back is enabled, forward is not.
    assert not await nav.nth(0).is_disabled(), 'back must be enabled after a tip'
    assert await nav.nth(1).is_disabled(), 'forward must be disabled at the newest page'
    # One step back -> the earlier PRINT tip.
    await nav.nth(0).click()
    await page.wait_for_function("""
        () => (document.querySelector('#hints-content .hint-title') || {}).textContent === 'PRINT'
    """)
    assert not await nav.nth(1).is_disabled(), 'forward must re-enable after going back'
    # And forward again -> GOTO.
    await nav.nth(1).click()
    await page.wait_for_function("""
        () => (document.querySelector('#hints-content .hint-title') || {}).textContent === 'GOTO'
    """)
    assert msgs == []


async def hints_back_restores_state(page, msgs):
    # The ◀ button returns to the previous hint page exactly as it was left:
    # same scroll offset and the same <details> sections open. ▶ restores the
    # page the user navigated away from.
    await h.new_file(page, 2)
    await h.set_language(page, 'C+MSXgl')
    await page.wait_for_function("""() => {
        const h1 = document.querySelector('#hints-content .hint-text h1');
        return !!h1 && h1.textContent.trim() === 'MSXgl (C + engine)';
    }""", timeout=15000)
    # Open the vdp.h module section and scroll the panel down.
    await page.evaluate("""() => {
        const d = Array.from(document.querySelectorAll('#hints-content details'))
            .find(d => d.querySelector('summary').textContent.includes('vdp.h'));
        if (d) d.open = true;
    }""")
    await page.evaluate("""() => {
        const el = document.getElementById('hints-content');
        el.scrollTop = el.scrollHeight;  // scroll to the bottom
    }""")
    scroll_saved = await page.evaluate("""() =>
        document.getElementById('hints-content').scrollTop""")
    assert scroll_saved > 0, f'panel must be scrollable, got scrollTop={scroll_saved}'
    # Jump into a tip (navigates away from the root page). A real click is not
    # used: Playwright scrolls the target into view before mousedown, which
    # changes the panel's scroll before the jump. element.click() only fires
    # the click handler, mirroring what a user does on an already-visible link.
    await page.evaluate("""() => {
        document.querySelector('#hints-content .hint-text a[href="hint:VDP_SETMODE"]')
            .click();
    }""")
    await page.wait_for_function("""() =>
        document.querySelector('#hints-content .hint-title')?.textContent === 'VDP_SETMODE'""")
    # Back: the root page must come back scrolled, with vdp.h still open.
    nav = page.locator('.wb-hints-nav-btn')
    await nav.nth(0).click()
    await page.wait_for_function("""() => {
        const h1 = document.querySelector('#hints-content .hint-text h1');
        return !!h1 && h1.textContent.trim() === 'MSXgl (C + engine)';
    }""", timeout=15000)
    restored_scroll = await page.evaluate("""() =>
        document.getElementById('hints-content').scrollTop""")
    assert restored_scroll == scroll_saved, \
        f'back must restore scroll {scroll_saved}, got {restored_scroll}'
    vdp_open = await page.evaluate("""() => {
        const d = Array.from(document.querySelectorAll('#hints-content details'))
            .find(d => d.querySelector('summary').textContent.includes('vdp.h'));
        return !!d && d.open;
    }""")
    assert vdp_open, 'back must restore the open vdp.h section'
    # Forward: returns to the VDP_SetMode tip.
    await nav.nth(1).click()
    await page.wait_for_function("""() =>
        document.querySelector('#hints-content .hint-title')?.textContent === 'VDP_SETMODE'""")
    assert msgs == []


async def hints_root_page(page, msgs):
    # A new file opens its language's root page in the HINTS panel.
    await h.new_file(page, 2)
    root_on = """
        () => { const t = document.querySelector('#hints-content .hint-text');
                return !!t && t.textContent.indexOf('Commands, functions') !== -1; }
    """
    await page.wait_for_function(root_on)
    # Typing a tip replaces the root page...
    await h.active_cm(page).click()
    await page.keyboard.type('PRINT')
    await page.wait_for_function("""
        () => (document.querySelector('#hints-content .hint-title') || {}).textContent === 'PRINT'
    """)
    # ...and F2 reloads the root page.
    await page.keyboard.press('F2')
    await page.wait_for_function(root_on)
    assert await hints_page_title(page) is None, 'F2 must show the root page, not a tip'
    assert msgs == []


async def settings_menu_keyboard(page, msgs):
    # Ctrl+, opens and closes the SETTINGS menu; arrows move the focus.
    await page.locator('#wb-settings-btn').wait_for(state='visible', timeout=10000)
    async def menu_open():
        return await page.evaluate("""() => {
            const m = document.getElementById('wb-settings-menu');
            return !!m && m.style.display !== 'none';
        }""")
    async def in_editor():
        return await page.evaluate("""() => {
            const a = document.activeElement;
            return !!a && a.classList && a.classList.contains('cm-content');
        }""")
    assert not await menu_open(), 'menu starts closed'
    await page.keyboard.press('Control+,')
    await page.wait_for_function("""
        () => { const m = document.getElementById('wb-settings-menu');
                return !!m && m.style.display !== 'none'; }
    """)
    # While the menu is open the editor must not hold keyboard focus.
    assert not await in_editor(), 'menu must hold focus, not the editor'
    # Opening activates the top row (PLUGINS) so the cursor position is never
    # ambiguous; arrows move the focus and wrap around the ends.
    await page.wait_for_function("""() => {
        const m = document.getElementById('wb-settings-menu');
        const k = m && m.querySelector('.wb-settings-row.keyboard');
        return !!k && k.id === 'wb-settings-plugins';
    }""")
    # ArrowDown moves to the next row (still exactly one focused).
    await page.keyboard.press('ArrowDown')
    focused = await page.evaluate("""() =>
        document.querySelectorAll('#wb-settings-menu .wb-settings-row.keyboard').length""")
    assert focused == 1, f'ArrowDown must focus one row, got {focused}'
    await page.wait_for_function("""() => {
        const k = document.querySelector('#wb-settings-menu .wb-settings-row.keyboard');
        return !!k && k.id === 'wb-settings-wrap';
    }""")
    # ArrowUp cycles back to the top row; another ArrowUp wraps to the last.
    await page.keyboard.press('ArrowUp')
    await page.wait_for_function("""() => {
        const k = document.querySelector('#wb-settings-menu .wb-settings-row.keyboard');
        return !!k && k.id === 'wb-settings-plugins';
    }""")
    await page.keyboard.press('ArrowUp')
    moved = await page.evaluate("""() => {
        const rows = document.querySelectorAll('#wb-settings-menu .wb-settings-row');
        const k = document.querySelectorAll('#wb-settings-menu .wb-settings-row.keyboard');
        return k.length === 1 && rows.length >= 2
            ? rows.item(rows.length - 1).classList.contains('keyboard')
            : false;
    }""")
    assert moved, 'ArrowUp on the top row must wrap focus to the last settings row'
    # Escape closes and restores the editor focus; Ctrl+, re-opens.
    await page.keyboard.press('Escape')
    assert not await menu_open(), 'Escape must close the menu'
    await page.wait_for_function("""() => {
        const a = document.activeElement;
        return !!a && a.classList && a.classList.contains('cm-content');
    }""")
    await page.keyboard.press('Control+,')
    await page.wait_for_function("""
        () => { const m = document.getElementById('wb-settings-menu');
                return !!m && m.style.display !== 'none'; }
    """)
    assert msgs == []


async def f1_shortcuts_window(page, msgs):
    # F1 must open the shortcuts window even when the (read-only) editor holds
    # keyboard focus: the read-only input handler must not swallow F1/F2.
    async def shortcut_open():
        return await page.evaluate("""() => {
            const t = document.querySelector('.wb-dialog .title-text');
            return !!t && t.textContent === 'Keyboard Shortcuts';
        }""")
    assert await h.active_tab_name(page) == 'STARTUP'
    await h.active_cm(page).click()
    focused = await page.evaluate("""() => {
        const a = document.activeElement;
        return !!a && a.classList && a.classList.contains('cm-content');
    }""")
    assert focused, 'editor must hold focus while pressing F1'
    assert not await shortcut_open(), 'shortcuts window starts closed'
    await page.keyboard.press('F1')
    await page.wait_for_function("""
        () => { const t = document.querySelector('.wb-dialog .title-text');
                return !!t && t.textContent === 'Keyboard Shortcuts'; }
    """)
    # The shortcuts window is 50% wider than the standard dialog (750px cap
    # instead of 500px), so it must render above the old cap once the async
    # q-table has laid out.
    await page.wait_for_function("""() => {
        const d = document.querySelector('.wb-dialog.wb-shortcut-dialog');
        return !!d && Math.round(d.getBoundingClientRect().width) > 520;
    }""", timeout=10000)
    # The first column ("Shortcut") is separated from "Action" by a grey line.
    await page.wait_for_function("""() => {
        const th = document.querySelector('.wb-shortcuts-table thead th:first-child');
        return !!th && getComputedStyle(th).borderRightWidth === '1px';
    }""")
    # The window must never outgrow the viewport: the table area scrolls
    # vertically and the Close button stays on screen.
    await page.wait_for_function("""() => {
        const d = document.querySelector('.wb-dialog.wb-shortcut-dialog');
        const body = d && d.querySelector('.wb-dialog-body');
        if (!body) return false;
        return body.clientHeight < body.scrollHeight &&
               getComputedStyle(body).overflowY === 'auto';
    }""", timeout=10000)
    await page.wait_for_function("""() => {
        const d = document.querySelector('.wb-dialog.wb-shortcut-dialog');
        const b = d && d.querySelector('.wb-dialog-buttons button');
        return !!b && Math.round(b.getBoundingClientRect().bottom) <= window.innerHeight;
    }""", timeout=10000)
    await page.keyboard.press('Escape')
    await page.wait_for_function("""() => {
        const t = document.querySelector('.wb-dialog .title-text');
        return !t || t.textContent !== 'Keyboard Shortcuts';
    }""")
    assert msgs == []


async def comment_toggle_basic(page, msgs):
    # Ctrl+/ toggles comments natively in HitBasic via the pluggable language
    # whose commentTokens declare "'". Select-all + toggle must produce a
    # leading "' " on every non-blank line, and a second press must undo it.
    await h.new_file(page, 2)
    await h.active_cm(page).click()
    await page.keyboard.type('PRINT 42\nGOTO 10')
    await h.doc_equals(page, 'PRINT 42\nGOTO 10')
    expected = "' PRINT 42\n' GOTO 10"
    toggled = False
    for _ in range(6):
        await page.keyboard.press('Control+a')
        await page.keyboard.press('Control+/')
        try:
            await h.doc_equals(page, expected, timeout=2000)
            toggled = True
            break
        except Exception:
            continue
    assert toggled, 'Ctrl+/ must comment HitBasic lines with a leading apostrophe'
    await page.keyboard.press('Control+a')
    await page.keyboard.press('Control+/')
    await h.doc_equals(page, 'PRINT 42\nGOTO 10', msg='Ctrl+/ second press must uncomment')
    assert msgs == []


async def ligatures_toggle(page, msgs):
    # The LIGATURES settings row toggles font ligatures for the editor and
    # persists the choice in the global config. It is OFF by default.
    await h.new_file(page, 2)
    await h.open_settings(page)
    row = page.locator('#wb-settings-ligatures')
    await row.wait_for(state='attached', timeout=10000)
    assert await row.evaluate("el => !el.classList.contains('active')"), \
        'LIGATURES row must not use the orange .active highlight'
    value = await row.locator('.wb-settings-value').inner_text()
    assert value == 'OFF', f'ligatures default must be OFF, got {value!r}'
    # Toggle ON: config saved and every content node re-renders with ligatures.
    await page.click('#wb-settings-ligatures')
    await h.wait_for_settings_value(page, 'wb-settings-ligatures', 'ON')
    value = await row.locator('.wb-settings-value').inner_text()
    assert value == 'ON', f'ligatures must show ON after toggle, got {value!r}'
    saved = await page.evaluate("() => !!window.WBStorage.loadConfig().ligatures")
    assert saved, 'config must record ligatures ON'
    await page.wait_for_function("""() => {
        const el = document.querySelector('.wb-editor-slot:not(.wb-editor-hidden) .cm-content');
        return el && getComputedStyle(el).fontVariantLigatures === 'common-ligatures';
    }""", timeout=10000)
    # Toggle back OFF: config and rendering follow.
    await page.click('#wb-settings-ligatures')
    await h.wait_for_settings_value(page, 'wb-settings-ligatures', 'OFF')
    value = await row.locator('.wb-settings-value').inner_text()
    assert value == 'OFF', f'ligatures must show OFF after second toggle, got {value!r}'
    saved = await page.evaluate("() => !!window.WBStorage.loadConfig().ligatures")
    assert not saved, 'config must record ligatures OFF'
    await page.wait_for_function("""() => {
        const el = document.querySelector('.wb-editor-slot:not(.wb-editor-hidden) .cm-content');
        return el && getComputedStyle(el).fontVariantLigatures === 'no-common-ligatures';
    }""", timeout=10000)
    assert msgs == []


async def fold_keyword_basic(page, msgs):
    # The foldService keyword provider folds HitBasic blocks (IF/END IF,
    # FOR/NEXT...) with the native fold gutter and keys, even though the
    # stream highlighter has no syntax tree. Text (and Z80) stay unfoldable.
    # Folding only hides lines in the view; the stored document is untouched.
    await h.new_file(page, 2)
    await h.active_cm(page).click()
    await page.keyboard.type(
        'IF A THEN\nPRINT 1\nFOR I = 1 TO 3\nPRINT I\nNEXT\nEND IF')

    # The gutter shows one fold marker per block opener (IF and FOR); waiting
    # on the markers doubles as the settle for the typed text being applied.
    # (The fold gutter also renders a visibility:hidden spacer row with the
    # same "Unfold line" title; it is excluded via the inline-style filter.)
    markers = page.locator(
        '.wb-editor-slot:not(.wb-editor-hidden) .cm-foldGutter .cm-gutterElement span[title="Fold line"]')
    await markers.first.wait_for(state='attached', timeout=10000)
    assert await markers.count() >= 2, \
        f'IF and FOR lines must be foldable, got {await markers.count()} markers'
    before = await h.doc_text(page)

    # Ctrl-Shift-[ collapses the block whose body the cursor sits in (fold
    # ranges start right after the opener keyword, keeping that line visible).
    await page.keyboard.press('Control+Home')
    await page.keyboard.press('ArrowDown')
    await page.keyboard.press('Control+Shift+[')
    await page.wait_for_function("""() =>
        document.querySelectorAll(
            '.wb-editor-slot:not(.wb-editor-hidden) .cm-foldGutter .cm-gutterElement' +
            ':not([style*="visibility"]) span[title="Unfold line"]').length >= 1""")
    assert await h.doc_text(page) == before

    # Ctrl-Shift-] unfolds again; the cursor sits on the opener line.
    await page.keyboard.press('Control+Shift+]')
    await page.wait_for_function("""() =>
        document.querySelectorAll(
            '.wb-editor-slot:not(.wb-editor-hidden) .cm-foldGutter .cm-gutterElement' +
            ':not([style*="visibility"]) span[title="Unfold line"]').length === 0""")
    assert await h.doc_text(page) == before

    # Text files have no block structure: no fold markers at all.
    await h.set_language(page, 'Text')
    await page.wait_for_function("""() =>
        document.querySelectorAll(
            '.wb-editor-slot:not(.wb-editor-hidden) .cm-foldGutter .cm-gutterElement span' +
            '[title="Fold line"]').length === 0""")
    assert msgs == []


async def fold_keyword_c(page, msgs):
    # C folding keys off '{...}' brace pairs found anywhere in a line.
    await h.new_file(page, 2)
    await h.set_language(page, 'C')
    await h.active_cm(page).click()
    await page.keyboard.type('int main() {\nprintf("hi");\nreturn 0;\n}')

    open_marker = page.locator(
        '.wb-editor-slot:not(.wb-editor-hidden) .cm-foldGutter .cm-gutterElement span[title="Fold line"]')
    await open_marker.first.wait_for(state='attached', timeout=10000)
    before = await h.doc_text(page)
    # The C fold key folds the block that opens with the brace on the
    # brace line, so fold ranges start right after the '{'.
    # Ctrl-Shift-[ on the brace line folds, Ctrl-Shift-] unfolds.
    await page.keyboard.press('Control+Home')
    await page.keyboard.press('Control+Shift+[')
    await page.wait_for_function("""() =>
        document.querySelectorAll(
            '.wb-editor-slot:not(.wb-editor-hidden) .cm-foldGutter .cm-gutterElement' +
            ':not([style*="visibility"]) span[title="Unfold line"]').length >= 1""")
    assert await h.doc_text(page) == before
    await page.keyboard.press('Control+Shift+]')
    await page.wait_for_function("""() =>
        document.querySelectorAll(
            '.wb-editor-slot:not(.wb-editor-hidden) .cm-foldGutter .cm-gutterElement' +
            ':not([style*="visibility"]) span[title="Unfold line"]').length === 0""")
    assert await h.doc_text(page) == before
    assert msgs == []


async def fold_name_placeholder(page, msgs):
    # Folded HitBasic blocks keep the opener's detail in the placeholder
    # (SUB name, IF test condition) instead of a bare ellipsis, the way C
    # shows the function signature before its folded body.
    await h.new_file(page, 2)
    await h.active_cm(page).click()
    await page.keyboard.type(
        'SUB GREET(NAME)\nPRINT NAME\nEND SUB\n'
        'IF X > 2 THEN\nPRINT "big"\nEND IF')

    # Wait for the SUB/IF fold markers; this doubles as the settle for the
    # typed text being applied before the fold shortcuts run.
    markers = page.locator(
        '.wb-editor-slot:not(.wb-editor-hidden) .cm-foldGutter .cm-gutterElement span[title="Fold line"]')
    await markers.first.wait_for(state='attached', timeout=10000)

    async def fold_placeholder():
        await page.keyboard.press('Control+Shift+[')
        await page.wait_for_function("""() =>
            document.querySelectorAll(
                '.wb-editor-slot:not(.wb-editor-hidden) .cm-foldGutter .cm-gutterElement' +
                ':not([style*="visibility"]) span[title="Unfold line"]').length >= 1""")
        return (await page.locator(
            '.wb-editor-slot:not(.wb-editor-hidden) .cm-foldPlaceholder').first.text_content()).strip()

    async def unfold():
        await page.keyboard.press('Control+Shift+]')
        await page.wait_for_function("""() =>
            document.querySelectorAll(
                '.wb-editor-slot:not(.wb-editor-hidden) .cm-foldGutter .cm-gutterElement' +
                ':not([style*="visibility"]) span[title="Unfold line"]').length === 0""")

    # Fold the SUB block from its opener line; the placeholder keeps the name.
    await page.keyboard.press('Control+Home')
    sub_ph = await fold_placeholder()
    assert 'GREET' in sub_ph, sub_ph
    await unfold()

    # Fold the IF block from its opener line; the placeholder keeps the test.
    await page.keyboard.press('Control+Home')
    await page.keyboard.press('ArrowDown')
    await page.keyboard.press('ArrowDown')
    await page.keyboard.press('ArrowDown')
    if_ph = await fold_placeholder()
    assert 'X > 2' in if_ph, if_ph
    assert msgs == []


async def lang_combo_tracks_active_file(page, msgs):
    # The LANG combo box must mirror the language of the currently visible
    # file (STARTUP.txt is plain text).
    async def combo_shows(label):
        await page.wait_for_function(
            """label => {
            const el = document.getElementById('wb-lang-select');
            if (!el) return false;
            const t = el.querySelector('.ellipsis');
            return (t || el).textContent.trim() === label;
        }""", arg=label)

    await combo_shows('Text')
    # Importing a HitBasic file activates it -> the combo flips to HitBasic.
    await page.evaluate("""() => {
        const dt = new DataTransfer();
        dt.items.add(new File(['PRINT 42'], 'demo.bas', {type: 'text/plain'}));
        const ev = new Event('drop', {bubbles: true, cancelable: true});
        try { Object.defineProperty(ev, 'dataTransfer', {value: dt}); } catch(e) { ev.dataTransfer = dt; }
        document.dispatchEvent(ev);
    }""")
    await combo_shows('HitBasic')
    # Switching back to STARTUP (plain text) restores 'Text'.
    await h.go(page, 'STARTUP')
    await combo_shows('Text')
    assert msgs == []


async def lang_combo_locked_for_readonly(page, msgs):
    # STARTUP.txt is read-only, so its LANG combo must be locked: greyed out,
    # refusing to open, and the server must reject any language change anyway.
    assert await h.active_tab_name(page) == 'STARTUP'
    locked = await page.evaluate("""() => {
        const el = document.getElementById('wb-lang-select');
        return !!el && el.classList.contains('wb-locked');
    }""")
    assert locked, 'LANG combo must be locked for the read-only STARTUP.txt'
    # A raw mouse press over the combo (the field has pointer-events: none,
    # so Playwright's actionability-aware click would not click at all) must
    # not open the popup.
    pt = await page.evaluate("""() => {
        const r = document.querySelector('.wb-select').getBoundingClientRect();
        return {x: r.x + r.width / 2, y: r.y + r.height / 2};
    }""")
    await page.mouse.click(pt['x'], pt['y'])
    await page.wait_for_timeout(500)
    popup_open = await page.evaluate("""() => {
        return Array.from(document.querySelectorAll('.q-menu')).some(function(m) {
            const cs = getComputedStyle(m);
            return cs.visibility !== 'hidden' && cs.opacity !== '0' &&
                   m.getBoundingClientRect().width > 0;
        });
    }""")
    assert not popup_open, 'LANG popup must stay closed for a read-only file'
    # Bypass the client lock on purpose: the server must still reject it.
    await page.evaluate("""() => {
        const native = document.getElementById('wb-lang-select');
        native.classList.remove('wb-locked');
        const field = native.closest('.wb-select');
        if (field) field.classList.remove('wb-locked');
    }""")
    await h.set_language(page, 'Pascal')
    await page.wait_for_function("""() => {
        const el = document.getElementById('wb-lang-select');
        const t = el.querySelector('.ellipsis');
        return (t || el).textContent.trim() === 'Text';
    }""")
    assert await h.active_tab_name(page) == 'STARTUP', \
        'read-only file must keep its language and name'
    assert 'STARTUP' == await page.evaluate("""() => {
        const a = document.querySelector('.wb-file-tab.active .file-name');
        return a ? a.textContent : null;
    }""")
    # A writable file unlocks the combo again.
    await page.evaluate("""() => {
        const dt = new DataTransfer();
        dt.items.add(new File(['PRINT 42'], 'demo.bas', {type: 'text/plain'}));
        const ev = new Event('drop', {bubbles: true, cancelable: true});
        try { Object.defineProperty(ev, 'dataTransfer', {value: dt}); } catch(e) { ev.dataTransfer = dt; }
        document.dispatchEvent(ev);
    }""")
    await page.wait_for_function("""() => {
        const el = document.getElementById('wb-lang-select');
        return !!el && !el.classList.contains('wb-locked');
    }""")
    assert msgs == []


async def lang_clash_prompts_rename(page, msgs):
    # Changing a file's language derives a new filename; if that name already
    # belongs to another file, a dialog must ask for a different base name.
    await h.new_file(page, 2)   # untitled_2.bas (HitBasic)
    await h.new_file(page, 3)   # untitled_3.bas (HitBasic)
    # Give untitled_2 a Pascal extension: it becomes the clashing target.
    await h.go(page, 'untitled_2')
    await h.set_language(page, 'Pascal')
    # Rename the active untitled_3.bas so its Pascal name would collide:
    # base 'untitled_2' + '.pas' == untitled_2.pas (already taken).
    await h.go(page, 'untitled_3')
    await page.keyboard.press('Control+Alt+r')
    await page.locator('.wb-dialog:visible .title-text').filter(
        has_text='Rename current file').wait_for(timeout=10000)
    await page.locator('.wb-dialog:visible input.q-field__native').click()
    await page.keyboard.press('Control+a')
    await page.keyboard.type('untitled_2.txt')
    await page.locator('.wb-dialog:visible').locator(
        '.wb-button', has_text='OK').click()
    await page.wait_for_function("""() => {
        const a = document.querySelector('.wb-file-tab.active .file-name');
        return !!a && a.textContent === 'untitled_2';
    }""")
    # Setting Pascal now must trigger the clash dialog instead of renaming.
    await h.set_language(page, 'Pascal')
    await page.locator('.wb-dialog:visible .title-text').filter(
        has_text='File name clash').wait_for(timeout=10000)
    prompt = await page.text_content('#wb-clash-prompt')
    assert 'untitled_2.pas' in prompt, f'clash message missing clashing name: {prompt!r}'
    # Cancelling reverts the combo to the file's actual language (HitBasic).
    await page.locator('.wb-dialog:visible').locator(
        '.wb-button', has_text='Cancel').click()
    await page.wait_for_function("""() => {
        const el = document.getElementById('wb-lang-select');
        const t = el ? el.querySelector('.ellipsis') : null;
        return !!t && t.textContent.trim() === 'HitBasic';
    }""")
    # Trying again opens the clash dialog; pick a free base name to succeed.
    await h.set_language(page, 'Pascal')
    await page.locator('.wb-dialog:visible .title-text').filter(
        has_text='File name clash').wait_for(timeout=10000)
    await page.locator('.wb-dialog:visible input.q-field__native').click()
    await page.keyboard.press('Control+a')
    await page.keyboard.type('untitled_4')
    await page.locator('.wb-dialog:visible').locator(
        '.wb-button', has_text='OK').click()
    # The file is now untitled_4.pas with Pascal active.
    await page.wait_for_function("""() => {
        const a = document.querySelector('.wb-file-tab.active .file-name');
        return !!a && a.textContent === 'untitled_4';
    }""")
    await page.wait_for_function("""() => {
        const el = document.getElementById('wb-lang-select');
        const t = el ? el.querySelector('.ellipsis') : null;
        return !!t && t.textContent.trim() === 'Pascal';
    }""")
    assert msgs == []


async def hints_c_pascal_root_pages(page, msgs):
    # C and Pascal have their own hint dictionaries; the HINTS panel must show
    # each language's root page when such a file is displayed.
    await h.new_file(page, 2)
    await h.set_language(page, 'Pascal')
    await page.wait_for_function("""() => {
        const h = document.querySelector('#hints-content .hint-text h1');
        return !!h && h.textContent.trim() === 'Pascal';
    }""")
    await h.set_language(page, 'C')
    await page.wait_for_function("""() => {
        const h = document.querySelector('#hints-content .hint-text h1');
        return !!h && h.textContent.trim() === 'C';
    }""")
    assert msgs == []


async def hint_link_jumps_to_tip(page, msgs):
    # "hint:" markdown links in a root page navigate the panel to that entry's
    # tip; the link itself is styled with a dashed underline.
    await h.new_file(page, 2)
    await h.set_language(page, 'C')
    await page.wait_for_function("""() => {
        const a = document.querySelector('#hints-content .hint-text a[href^="hint:"]');
        return !!a && a.textContent === 'for';
    }""")
    styled = await page.evaluate("""() => {
        const a = document.querySelector('#hints-content .hint-text a[href^="hint:"]');
        return a ? getComputedStyle(a).borderBottomStyle : null;
    }""")
    assert styled == 'dashed', f'for link must be dashed-underlined, got {styled!r}'
    await page.click('#hints-content .hint-text a[href^="hint:"]')
    await page.wait_for_function("""() => {
        const t = document.querySelector('#hints-content .hint-title');
        return !!t && t.textContent === 'FOR';
    }""")
    text = await page.evaluate("""() => {
        const t = document.querySelector('#hints-content .hint-text');
        return t ? t.textContent : '';
    }""")
    assert 'Loop:' in text, f'FOR tip must render the loop example, got {text!r}'
    assert msgs == []


async def hints_msxgl_root_and_builtins(page, msgs):
    # The C+MSXgl language maps to static/hints/msxgl.json: its root page must
    # group the engine functions by module (collapsible <details>) and functions
    # must be autocomplete builtins with full tips.
    await h.new_file(page, 2)
    await h.set_language(page, 'C+MSXgl')
    # Root page: MSXgl reference mentioning SDCC, module sections, function links.
    await page.wait_for_function("""() => {
        const h1 = document.querySelector('#hints-content .hint-text h1');
        return !!h1 && h1.textContent.trim() === 'MSXgl (C + engine)';
    }""", timeout=15000)
    body = await page.evaluate("""() =>
        document.querySelector('#hints-content .hint-text').textContent || ''""")
    assert 'SDCC' in body, 'root page must mention the SDCC compiler'
    assert 'psg.h' in body, 'root page must list a PSG module section'
    assert body.count('(') > 10, 'root page must list per-module function counts'
    # Module sections are ordered alphabetically by header name (ignoring the
    # directory they live in), so tool/kanji.h comes before vdp.h.
    sections = await page.evaluate("""() =>
        Array.from(document.querySelectorAll('#hints-content details summary'))
            .map(s => s.textContent).filter(t => t.includes('.h'))""")
    def section_key(t):
        return t.split(' - ')[-1].split('/')[-1].lower()
    bases = [section_key(t) for t in sections]
    assert bases == sorted(bases), \
        f'root module sections must be alphabetical by header name, got {sections!r}'
    assert any('kanji.h' in t for t in sections) and any('vdp.h' in t for t in sections)
    assert section_key([t for t in sections if 'kanji.h' in t][0]) < \
        section_key([t for t in sections if 'vdp.h' in t][0]), \
        f'tool/kanji.h must sort before vdp.h, got {sections!r}'
    # A hint: link jumps to the function's tip (expand the PSG module first).
    await page.evaluate("""() => {
        const d = Array.from(document.querySelectorAll('#hints-content details'))
            .find(d => d.querySelector('summary').textContent.includes('psg.h'));
        if (d) d.open = true;
    }""")
    await page.click('#hints-content .hint-text a[href="hint:PSG_SETREGISTER"]')
    await page.wait_for_function("""() =>
        document.querySelector('#hints-content .hint-title')?.textContent === 'PSG_SETREGISTER'""")
    tip = await page.evaluate("""() =>
        document.querySelector('#hints-content .hint-text')?.textContent || ''""")
    assert 'Set the value of a given register' in tip, \
        f'PSG_SetRegister tip must include the description, got {tip!r}'
    assert 'Parameters:' in tip, 'tip must render the Parameters section'
    assert 'reg' in tip and 'value' in tip, 'tip must list the parameters'
    # F2 restores the module index root page.
    await page.keyboard.press('F2')
    await page.wait_for_function("""() => {
        const h1 = document.querySelector('#hints-content .hint-text h1');
        return !!h1 && h1.textContent.trim() === 'MSXgl (C + engine)';
    }""", timeout=15000)
    # MSXgl functions are autocomplete builtins.
    await h.active_cm(page).click()
    await page.keyboard.type('PSG_Set')
    await page.wait_for_selector('.wb-autocomplete-popup', timeout=15000)
    popup = await page.evaluate("""() =>
        Array.from(document.querySelectorAll('.wb-autocomplete-popup div'))
            .map(el => el.textContent.trim()).filter(Boolean)""")
    assert any('PSG_SetRegister' in t for t in popup), \
        f'autocomplete must offer PSG_SetRegister, got {popup!r}'
    assert any('builtin' in t for t in popup), \
        f'completions must be tagged builtin, got {popup!r}'
    # MSXgl types autocomplete too, tagged "type".
    await page.keyboard.press('Escape')
    await page.keyboard.press('Control+a')
    await page.keyboard.press('Backspace')
    await page.keyboard.type('VDP_MO')
    await page.wait_for_selector('.wb-autocomplete-popup', timeout=15000)
    popup = await page.evaluate("""() =>
        Array.from(document.querySelectorAll('.wb-autocomplete-popup div'))
            .map(el => el.textContent.trim()).filter(Boolean)""")
    assert any('VDP_MODE' in t for t in popup), \
        f'autocomplete must offer VDP_MODE, got {popup!r}'
    assert any('VDP_MODE_GRAPHIC4' in t for t in popup), \
        f'autocomplete must offer the enum constant VDP_MODE_GRAPHIC4, got {popup!r}'
    assert any('type' in t for t in popup), \
        f'type completions must be tagged "type", got {popup!r}'
    assert msgs == []


async def hints_msxgl_types_section(page, msgs):
    # The C+MSXgl root page has a separate Types section listing the enums and
    # structs used by function signatures; clicking one opens its doc page and
    # functions whose signature uses a type cross-link to it.
    await h.new_file(page, 2)
    await h.set_language(page, 'C+MSXgl')
    await page.wait_for_function("""() => {
        const h1 = document.querySelector('#hints-content .hint-text h1');
        return !!h1 && h1.textContent.trim() === 'MSXgl (C + engine)';
    }""", timeout=15000)
    # The Types section is separate from the function module sections.
    bodies = await page.evaluate("""() =>
        Array.from(document.querySelectorAll('#hints-content details'))
            .map(d => d.querySelector('summary')?.textContent || '')""")
    assert any('Types' in s for s in bodies), \
        f'root page must have a Types section, summaries: {bodies!r}'
    await page.evaluate("""() => {
        const d = Array.from(document.querySelectorAll('#hints-content details'))
            .find(d => d.querySelector('summary').textContent.includes('Types'));
        if (d) d.open = true;
    }""")
    body = await page.evaluate("""() =>
        document.querySelector('#hints-content .hint-text').textContent || ''""")
    h3s = await page.evaluate("""() =>
        Array.from(document.querySelectorAll('#hints-content .hint-text h3'))
            .map(el => el.textContent.trim())""")
    assert 'Enums' in h3s, \
        f'Types section must list Enums as a heading, headings: {h3s!r}'
    assert 'Structs' in h3s, \
        f'Types section must list Structs as a heading, headings: {h3s!r}'
    assert 'INPUT_PORT' in body and 'QRCODE_ECC' in body, \
        'Types section must list the referenced enums'
    assert 'BIOS_SpriteAttributes' in body and 'VDP_Command36' in body and 'Pawn' in body, \
        'Types section must list the referenced structs'
    # Clicking an enum link opens its documentation.
    await page.click('#hints-content .hint-text a[href="hint:INPUT_PORT"]')
    await page.wait_for_function("""() =>
        document.querySelector('#hints-content .hint-title')?.textContent === 'INPUT_PORT'""")
    tip = await page.evaluate("""() =>
        document.querySelector('#hints-content .hint-text')?.textContent || ''""")
    assert 'enum INPUT_PORT' in tip, \
        f'INPUT_PORT tip must render the enum, got {tip!r}'
    assert 'INPUT_PORT1' in tip, \
        f'INPUT_PORT tip must list its constants, got {tip!r}'
    # A struct doc tip renders fields.
    await page.keyboard.press('F2')
    await page.wait_for_function("""() => {
        const h1 = document.querySelector('#hints-content .hint-text h1');
        return !!h1 && h1.textContent.trim() === 'MSXgl (C + engine)';
    }""", timeout=15000)
    await page.evaluate("""() => {
        const d = Array.from(document.querySelectorAll('#hints-content details'))
            .find(d => d.querySelector('summary').textContent.includes('Types'));
        if (d) d.open = true;
    }""")
    await page.click('#hints-content .hint-text a[href="hint:VDP_COMMAND36"]')
    await page.wait_for_function("""() =>
        document.querySelector('#hints-content .hint-title')?.textContent === 'VDP_COMMAND36'""")
    tip = await page.evaluate("""() =>
        document.querySelector('#hints-content .hint-text')?.textContent || ''""")
    assert 'typedef struct VDP_Command36' in tip, \
        f'VDP_Command36 tip must render the typedef, got {tip!r}'
    assert 'Fields:' in tip and 'u16 DX' in tip, \
        f'VDP_Command36 tip must render Fields, got {tip!r}'
    # A function whose signature uses a struct cross-links to it.
    await page.keyboard.press('F2')
    await page.wait_for_function("""() => {
        const h1 = document.querySelector('#hints-content .hint-text h1');
        return !!h1 && h1.textContent.trim() === 'MSXgl (C + engine)';
    }""", timeout=15000)
    await page.evaluate("""() => {
        const d = Array.from(document.querySelectorAll('#hints-content details'))
            .find(d => d.querySelector('summary').textContent.includes('bios.h'));
        if (d) d.open = true;
    }""")
    await page.click('#hints-content .hint-text a[href="hint:BIOS_SETSPRITEDATA"]')
    await page.wait_for_function("""() =>
        document.querySelector('#hints-content .hint-title')?.textContent === 'BIOS_SETSPRITEDATA'""")
    tip = await page.evaluate("""() =>
        document.querySelector('#hints-content .hint-text')?.textContent || ''""")
    assert 'Types:' in tip and 'BIOS_SpriteAttributes' in tip, \
        f'BIOS_SetSpriteData tip must cross-link its struct type, got {tip!r}'
    await page.click('#hints-content .hint-text a[href="hint:BIOS_SPRITEATTRIBUTES"]')
    await page.wait_for_function("""() =>
        document.querySelector('#hints-content .hint-title')?.textContent === 'BIOS_SPRITEATTRIBUTES'""")
    tip2 = await page.evaluate("""() =>
        document.querySelector('#hints-content .hint-text')?.textContent || ''""")
    assert 'typedef struct BIOS_SpriteAttributes' in tip2, \
        f'struct link must open the struct doc, got {tip2!r}'
    assert msgs == []


async def hints_msxgl_angle_brackets(page, msgs):
    # MSXgl descriptions reference other API items with angle brackets (see
    # <VDP_MODE>). The browser would swallow those as HTML element names, so
    # renderMarkdown must escape them; the literal text must be visible.
    await h.new_file(page, 2)
    await h.set_language(page, 'C+MSXgl')
    # Expand the psg.h... actually vdp.h module and open VDP_SetMode.
    await page.wait_for_function("""() => {
        const h1 = document.querySelector('#hints-content .hint-text h1');
        return !!h1 && h1.textContent.trim() === 'MSXgl (C + engine)';
    }""", timeout=15000)
    await page.evaluate("""() => {
        const d = Array.from(document.querySelectorAll('#hints-content details'))
            .find(d => d.querySelector('summary').textContent.includes('vdp.h'));
        if (d) d.open = true;
    }""")
    await page.click('#hints-content .hint-text a[href="hint:VDP_SETMODE"]')
    await page.wait_for_function("""() =>
        document.querySelector('#hints-content .hint-title')?.textContent === 'VDP_SETMODE'""")
    tip = await page.evaluate("""() =>
        document.querySelector('#hints-content .hint-text')?.textContent || ''""")
    assert 'VDP_MODE' in tip, \
        f'VDP_SetMode tip must mention VDP_MODE, got {tip!r}'
    assert '<VDP_MODE>' not in tip, \
        f'VDP_MODE must appear as a link, not bare angle brackets, got {tip!r}'
    link = await page.query_selector('#hints-content .hint-text a[href="hint:VDP_MODE"]')
    assert link is not None, \
        'VDP_SetMode tip must contain a link to the VDP_MODE enum doc'
    assert '(see VDP_MODE enumeration)' in ' '.join(tip.split()), \
        f'VDP_SetMode doc must keep the (see VDP_MODE enumeration) sentence, got {tip!r}'
    # Same fix on a struct field comment (<SEQ_CURSOR>).
    await page.keyboard.press('F2')
    await page.wait_for_function("""() => {
        const h1 = document.querySelector('#hints-content .hint-text h1');
        return !!h1 && h1.textContent.trim() === 'MSXgl (C + engine)';
    }""", timeout=15000)
    await page.evaluate("""() => {
        const d = Array.from(document.querySelectorAll('#hints-content details'))
            .find(d => d.querySelector('summary').textContent.includes('Types'));
        if (d) d.open = true;
    }""")
    await page.click('#hints-content .hint-text a[href="hint:SEQACTION"]')
    await page.wait_for_function("""() =>
        document.querySelector('#hints-content .hint-title')?.textContent === 'SEQACTION'""")
    tip = await page.evaluate("""() =>
        document.querySelector('#hints-content .hint-text')?.textContent || ''""")
    assert '<SEQ_CURSOR>' in tip, \
        f'SeqAction tip must show <SEQ_CURSOR> literally, got {tip!r}'
    # The real HTML tags used by the root page still work.
    await page.keyboard.press('F2')
    await page.wait_for_function("""() => {
        const h1 = document.querySelector('#hints-content .hint-text h1');
        return !!h1 && h1.textContent.trim() === 'MSXgl (C + engine)';
    }""", timeout=15000)
    details = await page.evaluate("""() =>
        document.querySelectorAll('#hints-content details').length""")
    assert details > 80, f'root must still render the module <details> sections, got {details}'
    assert msgs == []


async def hints_font_size_slider(page, msgs):
    # The HINTS header has a font-size slider; it rescales the hint text and
    # the chosen size is persisted in the Myslyx config (restored on reload).
    await h.new_file(page, 2)
    await page.locator('.wb-hints-size').wait_for(state='attached', timeout=10000)
    assert await page.input_value('.wb-hints-size') == '7', 'slider must default to 7px'
    initial = await page.evaluate("""() =>
        document.getElementById('hints-content')
            ? getComputedStyle(document.getElementById('hints-content')).fontSize : null""")
    assert initial == '7px', f'hints content must start at 7px, got {initial!r}'
    await page.evaluate("""() => {
        const s = document.querySelector('.wb-hints-size');
        s.value = '14';
        s.dispatchEvent(new Event('input', { bubbles: true }));
    }""")
    await page.wait_for_function("""() =>
        getComputedStyle(document.getElementById('hints-content')).fontSize === '14px'""")
    # Reload: the slider position and the applied size must come back from config.
    await page.reload()
    await page.locator('.wb-hints-size').wait_for(state='attached', timeout=10000)
    assert await page.input_value('.wb-hints-size') == '14', 'slider must restore from config'
    await page.wait_for_function("""() =>
        getComputedStyle(document.getElementById('hints-content')).fontSize === '14px'""")
    assert msgs == []


async def storage_pool_hardened(page, msgs):
    # __wbPyBridge.setFiles writes the whole pool to localStorage verbatim, so
    # a script could inject junk or drop STARTUP's lock. Boot adoption must
    # normalize: drop non-dict / duplicate-id entries, coerce shapes, map
    # unknown languages to Text and keep STARTUP.txt locked.
    await page.evaluate("""() => {
        window.WBStorage.saveFiles([
            { id: 'hack-1', name: 'hack.bas', language: 'Python', content: 123, export_symbols: 'yes' },
            { name: 'nolabel.txt', content: 'JUNK' },
            'just-a-string',
            { id: 'hack-1', name: 'dup.c', language: 'C', content: 'int x;' },
            { id: 'hack-2', name: 'STARTUP.txt', language: 'Python', content: 'injected', readonly: false },
            { id: 'hack-3', name: 'ok.bas', language: 'HitBasic', content: 'PRINT 42' },
        ]);
        window.WBStorage.saveActive('hack-2');
    }""")
    await page.reload()
    await page.wait_for_selector('.wb-file-tab', timeout=10000)
    n_tabs = await page.locator('.wb-file-tab').count()
    assert n_tabs == 3, f'normalized pool must keep 3 files, got {n_tabs}'
    icons = await page.evaluate("""() => Array.from(
        document.querySelectorAll('.wb-file-tab .file-icon')).map(e => e.textContent)""")
    # hack.bas was coerced to Text (unknown language, non-str content); the
    # duplicate hack-1 entry and the id-less entries were dropped.
    assert icons == ['TXT', 'TXT', 'BAS'], f'icons: {icons}'
    assert await h.active_tab_name(page) == 'STARTUP'
    lock = await page.evaluate("""() =>
        !!(document.querySelector('.wb-file-tab.active .file-lock'))""")
    assert lock, 'STARTUP must stay locked even if the stored flag was dropped'
    # The adopted STARTUP keeps its (injected) content but still blocks typing.
    assert await h.doc_text(page) == 'injected'
    await h.focus_active_editor(page)
    await h.readonly_guard_ready(page)
    await page.keyboard.type('Q')
    assert await h.doc_unchanged_for(page, 'injected'), \
        'readonly must be enforced server-side after reload'
    assert msgs == []


async def autocomplete_enter_completes(page, msgs):
    # Enter in the autocompletion popup must insert the selected completion
    # (replacing the typed prefix) without leaving a stray newline.
    await h.new_file(page, 2)
    await h.active_cm(page).click()
    await page.keyboard.type('PRI')
    await page.wait_for_selector('.wb-autocomplete-popup', timeout=5000)
    await page.keyboard.press('Enter')
    await page.wait_for_function("""() => new Promise(res => {
        try {
            const el = getElement(window.__wbEditorId);
            el.editorPromise.then(v => res(v.state.doc.toString() === 'PRINT'));
        } catch(e) { res(false); }
    })""")
    assert await h.doc_text(page) == 'PRINT', 'Enter must complete the word, not insert a newline'
    assert msgs == []


async def plugins_submenu_keyboard_nav(page, msgs):
    # Enter/Right over the PLUGINS row must move the cursor INTO the submenu.
    await page.locator('#wb-settings-btn').wait_for(state='visible', timeout=10000)
    await page.keyboard.press('Control+,')
    await page.wait_for_function("""() => {
        const m = document.getElementById('wb-settings-menu');
        return !!m && m.style.display !== 'none';
    }""")
    # Opening activates the top row, which is PLUGINS.
    await page.wait_for_function("""() => {
        const k = document.querySelector('#wb-settings-menu .wb-settings-row.keyboard');
        return !!k && k.id === 'wb-settings-plugins';
    }""")
    # ArrowRight opens the submenu and focuses its first plugin row.
    await page.keyboard.press('ArrowRight')
    await page.wait_for_function("""() => {
        const m = document.getElementById('wb-plugins-menu');
        return m && m.style.display !== 'none';
    }""")
    await page.wait_for_function("""() => {
        const k = document.querySelector('#wb-plugins-menu .wb-plugin-row.keyboard');
        return !!k;
    }""")
    # The keyboard-focused plugin row must show the same orange highlight as
    # a mouse hover (the .keyboard class needs matching CSS).
    await page.wait_for_function("""() => {
        const k = document.querySelector('#wb-plugins-menu .wb-plugin-row.keyboard');
        if (!k) return false;
        const c = getComputedStyle(k).backgroundColor;
        return c === 'rgb(255, 136, 0)' || c === '#ff8800';
    }""")
    # ArrowDown moves within the plugin rows (still exactly one focused).
    await page.keyboard.press('ArrowDown')
    n_focused = await page.evaluate("""() =>
        document.querySelectorAll('#wb-plugins-menu .wb-plugin-row.keyboard').length""")
    assert n_focused == 1, 'expected exactly one focused plugin row'
    await page.wait_for_function("""() => {
        const k = document.querySelector('#wb-plugins-menu .wb-plugin-row.keyboard');
        return !!k && getComputedStyle(k).backgroundColor === 'rgb(255, 136, 0)';
    }""")
    # ArrowLeft returns to the main menu with PLUGINS refocused.
    await page.keyboard.press('ArrowLeft')
    await page.wait_for_function("""() => {
        const m = document.getElementById('wb-plugins-menu');
        return !m || m.style.display === 'none';
    }""")
    await page.wait_for_function("""() => {
        const k = document.querySelector('#wb-settings-menu .wb-settings-row.keyboard');
        return !!k && k.id === 'wb-settings-plugins';
    }""")
    # Escape closes the whole menu.
    await page.keyboard.press('Escape')
    await page.wait_for_function("""() => {
        const m = document.getElementById('wb-settings-menu');
        return !m || m.style.display === 'none';
    }""")
    assert msgs == []


async def shortcuts_toolbar_actions(page, msgs):
    # + NEW, RENAME, EXPORT SYMBOLS and DELETE as non-colliding shortcuts.
    await page.keyboard.press('Control+Alt+n')
    await page.wait_for_function("document.querySelectorAll('.wb-file-tab').length === 2")
    export = page.locator('#wb-export-btn')
    await export.wait_for(state='visible', timeout=10000)
    label_before = (await export.inner_text()).replace('\n', ' ')
    assert 'ON' in label_before, f'unexpected export label before toggle: {label_before!r}'
    # RENAME opens the rename dialog (new file is writable).
    await page.keyboard.press('Control+Alt+r')
    await page.wait_for_function("""() => {
        const t = document.querySelector('.wb-dialog .title-text');
        return !!t && t.textContent === 'Rename current file';
    }""")
    await page.keyboard.press('Escape')
    await page.wait_for_function("""() =>
        !document.querySelector('.wb-dialog .title-text')""", timeout=10000)
    # EXPORT SYMBOLS toggles OFF.
    await page.keyboard.press('Control+Alt+e')
    await page.wait_for_function("""() => {
        const t = document.getElementById('wb-export-btn');
        return t && t.textContent.indexOf('OFF') !== -1;
    }""")
    # DELETE the (empty) new file: it closes without confirmation.
    await page.keyboard.press('Control+Alt+x')
    await page.wait_for_function("document.querySelectorAll('.wb-file-tab').length === 1")
    assert msgs == []


async def shortcuts_file_io(page, msgs):
    # DOWNLOAD the visible file via shortcut.
    async with page.expect_download() as dl:
        await page.keyboard.press('Control+Alt+d')
    download = await dl.value
    assert 'STARTUP' in download.suggested_filename, download.suggested_filename
    # UPLOAD via shortcut opens the picker; dropping a .c file creates a tab.
    async with page.expect_file_chooser() as fc:
        await page.keyboard.press('Control+Alt+u')
    chooser = await fc.value
    await chooser.set_files({
        'name': 'demo.c', 'mimeType': 'text/plain',
        'buffer': b'int main() { return 0; }',
    })
    await page.wait_for_function("document.querySelectorAll('.wb-file-tab').length === 2")
    assert msgs == []


async def download_all_files(page, msgs):
    # DOWNLOAD ALL zips every editable file but skips locked ones (STARTUP.txt).
    await h.new_file(page, 2)
    await h.focus_active_editor(page)
    await page.keyboard.type('PRINT 42')
    await h.doc_equals(page, 'PRINT 42')
    async with page.expect_download() as dl:
        await page.click('#wb-download-all-btn')
    download = await dl.value
    assert download.suggested_filename.endswith('.zip'), download.suggested_filename
    import zipfile
    import io
    data = await download.path()
    with zipfile.ZipFile(io.BytesIO(open(data, 'rb').read())) as zf:
        names = zf.namelist()
        assert 'STARTUP.txt' not in names, names
        assert 'untitled_2.bas' in names, names
        assert zf.read('untitled_2.bas').decode() == 'PRINT 42'
    assert msgs == []


async def shortcuts_pool_cycle(page, msgs):
    # Ctrl+Alt+[ and Ctrl+Alt+] move through the open files in the dock.
    await h.new_file(page, 2)
    await h.new_file(page, 3)
    assert await h.active_tab_name(page) == 'untitled_3'
    await page.keyboard.press('Control+Alt+[')
    await page.wait_for_function("""() => {
        const a = document.querySelector('.wb-file-tab.active .file-name');
        return !!a && a.textContent === 'untitled_2';
    }""")
    await page.keyboard.press('Control+Alt+[')
    await page.wait_for_function("""() => {
        const a = document.querySelector('.wb-file-tab.active .file-name');
        return !!a && a.textContent === 'STARTUP';
    }""")
    await page.keyboard.press('Control+Alt+]')
    await page.wait_for_function("""() => {
        const a = document.querySelector('.wb-file-tab.active .file-name');
        return !!a && a.textContent === 'untitled_2';
    }""")
    await page.keyboard.press('Control+Alt+]')
    await page.wait_for_function("""() => {
        const a = document.querySelector('.wb-file-tab.active .file-name');
        return !!a && a.textContent === 'untitled_3';
    }""")
    assert msgs == []


async def js_interpolation_quoting(page, msgs):
    # Item 4: file ids, names and languages are interpolated into
    # run_javascript. A quote in any of them used to break the generated JS,
    # so a hostile pool carrying a quote-laden id/name must still load intact.
    await page.evaluate("""() => {
        const pool = [
            {id: "fi'le\\"quoted", name: "O'Brian.txt", language: 'HitBasic',
             content: 'PRINT 1'},
            {id: 'plain', name: 'notes.txt', language: 'Text', content: 'SAFE'}
        ];
        WBStorage.saveFiles(pool);
        WBStorage.saveActive("fi'le\\"quoted");
    }""")
    await page.reload(wait_until='load')
    await page.wait_for_function("document.querySelectorAll('.wb-file-tab').length === 2")
    assert await page.evaluate("window.__wbActiveFid") == 'fi\'le"quoted', \
        'quote-laden id must reach the page as-is (no JS break)'
    assert await page.evaluate("window.__wbCurrentLang") == 'HitBasic'
    assert await h.doc_text(page) == 'PRINT 1', \
        'quote-laden id must not break the editor-boot JS'
    await h.go(page, 'notes')
    await h.doc_equals(page, 'SAFE', msg='quote-laden name must not break switching to the file')
    assert msgs == []


async def server_echoes_edits(page, msgs):
    # Item 5: the server stores whatever the client's on_change reports, so
    # assert the full client->server round trip by comparing the server-echoed
    # pool (localStorage re-written by __wbPyBridge.setFiles) against the live
    # CodeMirror view — never trusting either source in isolation.
    await h.new_file(page, 2)
    await page.keyboard.type('HELLO WORLD')
    await page.wait_for_function(
        """() => window.WBEditorActive.current(3000).then(v => {
            if (!v) return false;
            const f = JSON.parse(localStorage.getItem('wb_editor_files') || '[]')
                .find(e => e && e.id === window.__wbActiveFid);
            return !!(f && f.content === v.state.doc.toString());
        })""",
        timeout=10000)
    # Ctrl+Z undoes in the view; the change must echo back to the pool too.
    await page.keyboard.press('Control+z')
    await page.wait_for_function(
        """() => window.WBEditorActive.current(3000).then(v => {
            if (!v) return false;
            const f = JSON.parse(localStorage.getItem('wb_editor_files') || '[]')
                .find(e => e && e.id === window.__wbActiveFid);
            return !!(f && f.content === v.state.doc.toString());
        })""",
        timeout=10000)
    assert msgs == []


SMOKE_SUITES = [
    ('smoke/wrap-on-preserves', wrap_toggle_preserves_content),
    ('smoke/wrap-toggle-twice', wrap_off_preserves_content),
    ('smoke/export-disabled-for-text', export_disabled_for_text),
    ('smoke/export-language-switch', export_disabled_on_language_switch),
    ('smoke/file-stats-counts', file_stats_counts),
    ('smoke/hints-nav-browse', hints_nav_browse),
    ('smoke/hints-back-restores-state', hints_back_restores_state),
    ('smoke/hints-root-page', hints_root_page),
    ('smoke/settings-menu-keyboard', settings_menu_keyboard),
    ('smoke/f1-shortcuts-window', f1_shortcuts_window),
    ('smoke/comment-toggle', comment_toggle_basic),
    ('smoke/ligatures-toggle', ligatures_toggle),
    ('smoke/fold-keyword-basic', fold_keyword_basic),
    ('smoke/fold-keyword-c', fold_keyword_c),
    ('smoke/fold-name-placeholder', fold_name_placeholder),
    ('smoke/lang-combo-tracks-file', lang_combo_tracks_active_file),
    ('smoke/lang-combo-locked-readonly', lang_combo_locked_for_readonly),
    ('smoke/lang-clash-prompts-rename', lang_clash_prompts_rename),
    ('smoke/hints-c-pascal-root', hints_c_pascal_root_pages),
    ('smoke/hint-link-jumps-to-tip', hint_link_jumps_to_tip),
    ('smoke/hints-msxgl-root-builtins', hints_msxgl_root_and_builtins),
    ('smoke/hints-msxgl-types', hints_msxgl_types_section),
    ('smoke/hints-msxgl-angle-brackets', hints_msxgl_angle_brackets),
    ('smoke/hints-font-size-slider', hints_font_size_slider),
    ('smoke/storage-pool-hardened', storage_pool_hardened),
    ('smoke/js-interpolation-quoting', js_interpolation_quoting),
    ('smoke/server-echoes-edits', server_echoes_edits),
    ('smoke/autocomplete-enter', autocomplete_enter_completes),
    ('smoke/plugins-submenu-keyboard-nav', plugins_submenu_keyboard_nav),
    ('smoke/shortcuts-toolbar-actions', shortcuts_toolbar_actions),
    ('smoke/shortcuts-file-io', shortcuts_file_io),
    ('smoke/shortcuts-pool-cycle', shortcuts_pool_cycle),
    ('smoke/download-all-files', download_all_files),
]