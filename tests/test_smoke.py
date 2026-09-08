"""Smoke suite: wrap toggle, export-symbols, font controls and file counts."""

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
    # Import a .bas file (VBScript) -> the toggle must re-enable.
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
    # New files default to VBScript -> the export toggle is usable.
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


SMOKE_SUITES = [
    ('smoke/wrap-on-preserves', wrap_toggle_preserves_content),
    ('smoke/wrap-toggle-twice', wrap_off_preserves_content),
    ('smoke/export-disabled-for-text', export_disabled_for_text),
    ('smoke/export-language-switch', export_disabled_on_language_switch),
    ('smoke/file-stats-counts', file_stats_counts),
]