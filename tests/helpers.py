"""Shared Playwright helpers for the Myslyx browser acceptance tests."""


async def doc_text(page):
    """Return the active editor's document as plain text (or None).

    Polls until the active editor is actually mounted (up to 3s) so a read
    racing the cold-boot mount can never return a stale None.
    """
    return await page.evaluate("""() => new Promise((res) => {
        const deadline = Date.now() + 3000;
        const tick = () => {
            try {
                const el = getElement(window.__wbEditorId);
                if (el && el.editorPromise) {
                    el.editorPromise.then(
                        (v) => res(v.state.doc.toString()),
                        () => (Date.now() < deadline ? setTimeout(tick, 50) : res(null)));
                    return;
                }
            } catch (e) {}
            if (Date.now() < deadline) setTimeout(tick, 50); else res(null);
        };
        tick();
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
    await page.locator('.q-menu').get_by_text(label, exact=True).first.click()
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


async def focus_active_editor(page):
    """Click the active editor and wait until browser focus lands inside it."""
    await active_cm(page).click()
    await page.wait_for_function("""() => {
        const a = document.activeElement;
        return a && a.closest && a.closest('.wb-editor-slot:not(.wb-editor-hidden) .cm-editor');
    }""")


async def readonly_guard_ready(page):
    """Wait until the read-only input guard is attached to the active editor."""
    await page.wait_for_function("""() => {
        const c = document.querySelector('.wb-editor-slot:not(.wb-editor-hidden) .cm-content');
        return !!(c && c._wbReadOnlyHandler);
    }""")


async def doc_unchanged_for(page, expected, ms=400):
    """Observation-window check: poll the active doc and return True if it
    stayed equal to ``expected`` for the whole ``ms`` window, False if it
    ever changed. Replaces the sleep-then-assert antipattern."""
    return await page.evaluate(
        """({expected, ms}) => new Promise((res) => {
            const start = Date.now();
            const read = () => {
                const el = getElement(window.__wbEditorId);
                return el && el.editorPromise
                    ? el.editorPromise.then(v => v.state.doc.toString())
                    : Promise.resolve(null);
            };
            const tick = () => {
                read().then((v) => {
                    if (v !== expected) return res(false);
                    if (Date.now() - start >= ms) return res(true);
                    setTimeout(tick, 40);
                });
            };
            tick();
        })""",
        {"expected": expected, "ms": ms})


async def doc_equals(page, expected, timeout=10000):
    """Wait until the active editor's document equals ``expected``."""
    await page.wait_for_function(
        """expected => new Promise((res) => {
            const el = getElement(window.__wbEditorId);
            if (!el || !el.editorPromise) { res(false); return; }
            el.editorPromise.then(v => res(v.state.doc.toString() === expected));
        })""",
        arg=expected, timeout=timeout)