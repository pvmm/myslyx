"""Shared Playwright helpers for the Myslyx browser acceptance tests."""


async def doc_text(page):
    """Return the active editor's document as plain text (or None).

    Resolves through the shared race-safe WBEditorActive view helper, which
    polls the current __wbEditorId until the CodeMirror view mounts (up to 3s)
    so a read racing the cold-boot mount can never return a stale None.
    """
    return await page.evaluate("""() => window.WBEditorActive.current(3000).then(
        (v) => (v ? v.state.doc.toString() : null))""")


async def visible_editors(page):
    """Number of editor slots currently NOT hidden."""
    return await page.evaluate(
        "document.querySelectorAll('.wb-editor-slot:not(.wb-editor-hidden)').length")


async def open_settings(page):
    """Open the settings menu (favicon button) and wait until it is shown.

    Polls the menu's display state instead of sleeping a fixed amount. The
    button toggles the menu, so only click it when the menu is closed.
    """
    is_open = await page.evaluate("""() => {
        const m = document.getElementById('wb-settings-menu');
        return !!m && m.style.display === 'block';
    }""")
    if not is_open:
        await page.click('#wb-settings-btn')
    await page.wait_for_function("""() => {
        const m = document.getElementById('wb-settings-menu');
        return !!m && m.style.display === 'block';
    }""", timeout=10000)


async def wait_for_settings_value(page, row_id, value, timeout=10000):
    """Poll until the settings row ``row_id`` acks ``value`` as applied.

    The rows stamp a machine-readable data-value ack synchronously when they
    applying config to every editor, so consumers observe the settled state
    instead of sleeping a fixed amount and guessing.
    """
    await page.wait_for_function(
        f"document.getElementById('{row_id}')?.dataset.value === '{value}'",
        timeout=timeout)


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
            const read = () => window.WBEditorActive.current(3000).then(
                (v) => (v ? v.state.doc.toString() : null));
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
        """expected => window.WBEditorActive.current(10000).then(v =>
            !!(v && v.state.doc.toString() === expected))""",
        arg=expected, timeout=timeout + 2000)