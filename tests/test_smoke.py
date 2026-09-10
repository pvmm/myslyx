"""Smoke suite: wrap toggle, export-symbols, hints browsing and counts."""

from tests import helpers as h


async def wrap_toggle_preserves_content(page, msgs):
    await h.new_file(page, 2)
    await page.keyboard.type('PRINT 42')
    await page.wait_for_timeout(400)
    before = await h.doc_text(page)
    assert before == 'PRINT 42'
    await h.open_settings(page)
    wrap_row = page.locator('#wb-settings-wrap')
    # The WRAP row must not use the orange .active highlight (reserved for
    # hover/open flyout); its ON/OFF state shows as the value text instead.
    assert await wrap_row.evaluate("el => !el.classList.contains('active')"), \
        'WRAP row must not stay orange via .active'
    await page.click('#wb-settings-wrap')
    await page.wait_for_timeout(500)
    after = await h.doc_text(page)
    assert after == before, f'wrap toggle must not alter content: {after!r}'
    assert await wrap_row.evaluate("el => !el.classList.contains('active')"), \
        'WRAP row must stay unhighlighted after toggling'
    assert msgs == []


async def wrap_off_preserves_content(page, msgs):
    await h.new_file(page, 2)
    await page.keyboard.type('LINE1')
    await page.wait_for_timeout(300)
    # Default wrap state is whatever persisted; toggling twice nets out but
    # must still preserve content.
    for _ in range(2):
        await h.open_settings(page)
        await page.click('#wb-settings-wrap')
        await page.wait_for_timeout(400)
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
    await page.wait_for_timeout(800)
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
    assert not await export.is_disabled(), 'export must re-enable after leaving Text'
    label = (await export.inner_text()).replace('\n', ' ')
    assert 'ON' in label, f'unexpected re-enabled label: {label!r}'
    # The toggle itself still flips ON <-> OFF for code languages.
    await page.click('#wb-export-btn')
    await page.wait_for_timeout(400)
    label = (await export.inner_text()).replace('\n', ' ')
    assert 'OFF' in label, f'toggle did not switch OFF: {label!r}'
    await page.click('#wb-export-btn')
    await page.wait_for_timeout(400)
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
    # Ctrl+Space opens and closes the SETTINGS menu; arrows move the focus.
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
    await page.keyboard.press('Control+Space')
    await page.wait_for_function("""
        () => { const m = document.getElementById('wb-settings-menu');
                return !!m && m.style.display !== 'none'; }
    """)
    # While the menu is open the editor must not hold keyboard focus.
    assert not await in_editor(), 'menu must hold focus, not the editor'
    # ArrowDown focuses the first row; ArrowUp cycles to the last.
    await page.keyboard.press('ArrowDown')
    focused = await page.evaluate("""() =>
        document.querySelectorAll('#wb-settings-menu .wb-settings-row.keyboard').length""")
    assert focused == 1, f'ArrowDown must focus one row, got {focused}'
    await page.keyboard.press('ArrowUp')
    moved = await page.evaluate("""() => {
        const rows = document.querySelectorAll('#wb-settings-menu .wb-settings-row');
        const k = document.querySelectorAll('#wb-settings-menu .wb-settings-row.keyboard');
        return k.length === 1 && rows.length >= 2
            ? rows.item(rows.length - 1).classList.contains('keyboard')
            : false;
    }""")
    assert moved, 'ArrowUp must move focus to the last settings row'
    # Escape closes and restores the editor focus; Ctrl+Space re-opens.
    await page.keyboard.press('Escape')
    assert not await menu_open(), 'Escape must close the menu'
    await page.wait_for_function("""() => {
        const a = document.activeElement;
        return !!a && a.classList && a.classList.contains('cm-content');
    }""")
    await page.keyboard.press('Control+Space')
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
    await page.wait_for_timeout(300)
    expected = "' PRINT 42\n' GOTO 10"
    toggled = False
    for _ in range(6):
        await page.keyboard.press('Control+a')
        await page.keyboard.press('Control+/')
        await page.wait_for_timeout(150)
        if await h.doc_text(page) == expected:
            toggled = True
            break
    assert toggled, 'Ctrl+/ must comment HitBasic lines with a leading apostrophe'
    await page.keyboard.press('Control+a')
    await page.keyboard.press('Control+/')
    await page.wait_for_timeout(150)
    assert await h.doc_text(page) == 'PRINT 42\nGOTO 10', 'Ctrl+/ second press must uncomment'
    assert msgs == []


async def ligatures_toggle(page, msgs):
    # The LIGATURES settings row toggles font ligatures for the editor and
    # persists the choice in the global config. It is OFF by default.
    await h.new_file(page, 2)
    await page.wait_for_timeout(300)
    await h.open_settings(page)
    row = page.locator('#wb-settings-ligatures')
    await row.wait_for(state='attached', timeout=10000)
    assert await row.evaluate("el => !el.classList.contains('active')"), \
        'LIGATURES row must not use the orange .active highlight'
    value = await row.locator('.wb-settings-value').inner_text()
    assert value == 'OFF', f'ligatures default must be OFF, got {value!r}'
    current = await page.evaluate("""() => {
        const el = document.querySelector('.wb-editor-slot:not(.wb-editor-hidden) .cm-content');
        return el ? getComputedStyle(el).fontVariantLigatures : null;
    }""")
    assert current == 'no-common-ligatures', f'expected no-common-ligatures, got {current!r}'
    # Toggle ON: config saved and every content node re-renders with ligatures.
    await page.click('#wb-settings-ligatures')
    await page.wait_for_timeout(400)
    value = await row.locator('.wb-settings-value').inner_text()
    assert value == 'ON', f'ligatures must show ON after toggle, got {value!r}'
    saved = await page.evaluate("() => !!window.WBStorage.loadConfig().ligatures")
    assert saved, 'config must record ligatures ON'
    current = await page.evaluate("""() => {
        const el = document.querySelector('.wb-editor-slot:not(.wb-editor-hidden) .cm-content');
        return el ? getComputedStyle(el).fontVariantLigatures : null;
    }""")
    assert current == 'common-ligatures', f'expected common-ligatures, got {current!r}'
    # Toggle back OFF: config and rendering follow.
    await page.click('#wb-settings-ligatures')
    await page.wait_for_timeout(400)
    value = await row.locator('.wb-settings-value').inner_text()
    assert value == 'OFF', f'ligatures must show OFF after second toggle, got {value!r}'
    saved = await page.evaluate("() => !!window.WBStorage.loadConfig().ligatures")
    assert not saved, 'config must record ligatures OFF'
    current = await page.evaluate("""() => {
        const el = document.querySelector('.wb-editor-slot:not(.wb-editor-hidden) .cm-content');
        return el ? getComputedStyle(el).fontVariantLigatures : null;
    }""")
    assert current == 'no-common-ligatures', f'expected no-common-ligatures, got {current!r}'
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
    await page.wait_for_timeout(400)

    # The gutter shows one fold marker per block opener (IF and FOR).
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
    await page.wait_for_timeout(400)

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


SMOKE_SUITES = [
    ('smoke/wrap-on-preserves', wrap_toggle_preserves_content),
    ('smoke/wrap-toggle-twice', wrap_off_preserves_content),
    ('smoke/export-disabled-for-text', export_disabled_for_text),
    ('smoke/export-language-switch', export_disabled_on_language_switch),
    ('smoke/file-stats-counts', file_stats_counts),
    ('smoke/hints-nav-browse', hints_nav_browse),
    ('smoke/hints-root-page', hints_root_page),
    ('smoke/settings-menu-keyboard', settings_menu_keyboard),
    ('smoke/f1-shortcuts-window', f1_shortcuts_window),
    ('smoke/comment-toggle', comment_toggle_basic),
    ('smoke/ligatures-toggle', ligatures_toggle),
    ('smoke/fold-keyword-basic', fold_keyword_basic),
    ('smoke/fold-keyword-c', fold_keyword_c),
]