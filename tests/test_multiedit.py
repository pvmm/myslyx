"""Multi-instance editor acceptance suite.

Verifies the one-CodeMirror-per-open-file refactor: native per-file undo/redo
histories, read-only STARTUP, single visible editor, and the drag-and-drop
import path through the wb-open-file server bridge.
"""

from tests import helpers as h


def _console_errors(msgs, allowed=()):
    return [m for m in msgs if m not in allowed]


async def readonly_startup(page, msgs):
    start_name = await h.active_tab_name(page)
    assert start_name == 'STARTUP', f'expected STARTUP active, got {start_name!r}'
    assert await h.visible_editors(page) == 1
    await page.wait_for_function("""() => {
        const u = document.getElementById('wb-undo-btn');
        const r = document.getElementById('wb-redo-btn');
        return !!(u && u.disabled && r && r.disabled);
    }""")
    before = await h.doc_text(page)
    await h.focus_active_editor(page)
    await h.readonly_guard_ready(page)
    await page.keyboard.type('Q')
    assert await h.doc_unchanged_for(page, before), \
        'readonly STARTUP must not accept typing'
    assert _console_errors(msgs) == []


async def native_grouping(page, msgs):
    await h.new_file(page, 2)
    name_a = await h.active_tab_name(page)
    assert name_a
    await page.keyboard.type('AB')
    await page.wait_for_timeout(400)
    assert await h.doc_text(page) == 'AB'
    assert await h.visible_editors(page) == 1

    await page.click('#wb-undo-btn')
    await page.wait_for_timeout(400)
    assert await h.doc_text(page) == '', 'single UNDO should clear the whole AB group'

    await page.click('#wb-redo-btn')
    await page.wait_for_timeout(400)
    assert await h.doc_text(page) == 'AB'


async def per_file_isolation(page, msgs):
    await h.new_file(page, 2)
    name_a = await h.active_tab_name(page)
    await page.keyboard.type('X')
    await page.wait_for_timeout(400)
    await h.new_file(page, 3)
    name_b = await h.active_tab_name(page)
    assert name_b and name_b != name_a
    await page.keyboard.type('C')
    await page.wait_for_timeout(400)
    assert await h.doc_text(page) == 'C'

    await page.click('#wb-undo-btn')
    await page.wait_for_timeout(400)
    assert await h.doc_text(page) == ''
    await page.click('#wb-redo-btn')
    await page.wait_for_timeout(400)
    assert await h.doc_text(page) == 'C'
    assert await h.visible_editors(page) == 1

    # switch back: A untouched, undo/redo still local
    await h.go(page, name_a)
    assert await h.doc_text(page) == 'X'
    await page.click('#wb-undo-btn')
    await page.wait_for_timeout(400)
    assert await h.doc_text(page) == '', 'undo in A gives A baseline, not B content'
    await page.click('#wb-redo-btn')
    await page.wait_for_timeout(400)
    assert await h.doc_text(page) == 'X'

    # keyboard isolation
    await h.active_cm(page).click()
    await page.keyboard.press('Control+z')
    await page.wait_for_timeout(400)
    assert await h.doc_text(page) == ''
    await page.keyboard.press('Control+y')
    await page.wait_for_timeout(400)
    assert await h.doc_text(page) == 'X'
    await h.go(page, name_b)
    assert await h.doc_text(page) == 'C'
    await h.active_cm(page).click()
    await page.keyboard.press('Control+z')
    await page.wait_for_timeout(400)
    assert await h.doc_text(page) == '', 'Ctrl+Z in B must not touch A'
    await page.keyboard.press('Control+y')
    await page.wait_for_timeout(400)
    assert await h.doc_text(page) == 'C'
    assert _console_errors(msgs) == []


async def drag_drop_bridge(page, msgs):
    before = await page.evaluate("document.querySelectorAll('.wb-file-tab').length")
    await page.evaluate("""() => {
        const dt = new DataTransfer();
        dt.items.add(new File(['DEMO CONTENT\\nX'], 'demo.bas', {type: 'text/plain'}));
        const ev = new Event('drop', {bubbles: true, cancelable: true});
        try { Object.defineProperty(ev, 'dataTransfer', {value: dt}); } catch(e) { ev.dataTransfer = dt; }
        document.dispatchEvent(ev);
    }""")
    await page.wait_for_function(f"document.querySelectorAll('.wb-file-tab').length === {before + 1}")
    await page.wait_for_timeout(800)
    assert await h.doc_text(page) == 'DEMO CONTENT\nX', 'imported file content must load'
    assert await h.tab_by_name(page, 'demo').count() == 1, 'exactly ONE dock tab for the import'
    assert await h.visible_editors(page) == 1
    assert _console_errors(msgs) == []


async def no_double_undo(page, msgs):
    await h.new_file(page, 2)
    name_g = await h.active_tab_name(page)
    await h.active_cm(page).click()
    await page.keyboard.type('W')
    await page.wait_for_timeout(700)   # separate undo group
    await page.keyboard.type('E')
    await page.wait_for_timeout(400)
    assert await h.doc_text(page) == 'WE'
    await page.keyboard.press('Control+z')
    await page.wait_for_timeout(400)
    assert await h.doc_text(page) == 'W', 'one Ctrl+Z must undo exactly one group'
    await page.keyboard.press('Control+z')
    await page.wait_for_timeout(400)
    assert await h.doc_text(page) == ''
    await page.keyboard.press('Control+z')
    await page.wait_for_timeout(400)
    assert await h.doc_text(page) == ''
    await h.go(page, name_g)
    assert _console_errors(msgs) == []


async def readonly_after_switches(page, msgs):
    await h.new_file(page, 2)
    await page.wait_for_timeout(400)
    await h.go(page, 'STARTUP')
    await page.wait_for_timeout(400)
    before = await h.doc_text(page)
    await h.active_cm(page).click()
    await page.keyboard.type('W')
    await page.wait_for_timeout(300)
    assert await h.doc_text(page) == before, 'STARTUP typing still blocked'
    assert await page.locator('#wb-undo-btn').is_disabled()
    assert _console_errors(msgs) == []


MULTIEDIT_SUITES = [
    ('multiedit/readonly-startup', readonly_startup),
    ('multiedit/grouped-undo', native_grouping),
    ('multiedit/per-file-isolation', per_file_isolation),
    ('multiedit/drag-drop-bridge', drag_drop_bridge),
    ('multiedit/no-double-undo', no_double_undo),
    ('multiedit/readonly-after-switches', readonly_after_switches),
]