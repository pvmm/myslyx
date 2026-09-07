"""Smoke suite: wrap toggle and font controls keep the document intact."""

from tests import helpers as h


async def wrap_toggle_preserves_content(page, msgs):
    await h.new_file(page, 2)
    await page.keyboard.type('PRINT 42')
    await page.wait_for_timeout(400)
    before = await h.doc_text(page)
    assert before == 'PRINT 42'
    await page.click('#wb-wrap-btn')
    await page.wait_for_timeout(500)
    after = await h.doc_text(page)
    assert after == before, f'wrap toggle must not alter content: {after!r}'
    assert msgs == []


async def wrap_off_preserves_content(page, msgs):
    await h.new_file(page, 2)
    await page.keyboard.type('LINE1')
    await page.wait_for_timeout(300)
    # Default wrap state is whatever persisted; toggling twice nets out but
    # must still preserve content.
    for _ in range(2):
        await page.click('#wb-wrap-btn')
        await page.wait_for_timeout(400)
    assert await h.doc_text(page) == 'LINE1'
    assert msgs == []


SMOKE_SUITES = [
    ('smoke/wrap-on-preserves', wrap_toggle_preserves_content),
    ('smoke/wrap-toggle-twice', wrap_off_preserves_content),
]