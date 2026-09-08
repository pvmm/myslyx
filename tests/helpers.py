"""Shared Playwright helpers for the Myslyx browser acceptance tests."""


async def doc_text(page):
    """Return the active editor's document as plain text (or None)."""
    return await page.evaluate("""() => new Promise(res => {
        try { const el = getElement(window.__wbEditorId); el.editorPromise.then(function(v){ res(v.state.doc.toString()); }); }
        catch(e) { res(null); }
    })""")


async def visible_editors(page):
    """Number of editor slots currently NOT hidden."""
    return await page.evaluate(
        "document.querySelectorAll('.wb-editor-slot:not(.wb-editor-hidden)').length")


async def open_settings(page):
    """Open the settings menu (favicon button) and wait for it to settle.

    Clicking the button toggles the menu, so only click when it is closed.
    """
    for _ in range(3):
        is_open = await page.evaluate("""() => {
            const m = document.getElementById('wb-settings-menu');
            return !!m && m.style.display !== 'none';
        }""")
        if is_open:
            break
        await page.click('#wb-settings-btn')
        await page.wait_for_timeout(300)
    await page.wait_for_timeout(300)


async def set_language(page, label):
    """Pick a language from the toolbar LANG dropdown by its shown label."""
    await page.click('.wb-select')
    await page.wait_for_timeout(500)
    await page.click(f'.q-menu .q-item:has-text("{label}")')
    await page.wait_for_timeout(600)


def active_cm(page):
    """Locator for the currently visible editor's content area."""
    return page.locator('.wb-editor-slot:not(.wb-editor-hidden) .cm-content')


def tab_by_name(page, name):
    """Locator for the dock tab whose visible file name contains ``name``."""
    return page.locator('.wb-file-tab').filter(
        has=page.locator('.file-name', has_text=name)).first


async def active_tab_name(page):
    """Name of the currently active dock tab, or None."""
    return await page.evaluate("""() => {
        const a = document.querySelector('.wb-file-tab.active');
        return a ? (a.querySelector('.file-name') || {}).textContent : null;
    }""")


async def go(page, name):
    """Click the dock tab named ``name`` and wait for the switch to settle."""
    await tab_by_name(page, name).click()
    await page.wait_for_timeout(700)


async def new_file(page, expected_tabs):
    """Click NEW FILE and wait until ``expected_tabs`` dock tabs exist."""
    await page.click('.wb-new-file')
    await page.wait_for_function(
        f"document.querySelectorAll('.wb-file-tab').length === {expected_tabs}")