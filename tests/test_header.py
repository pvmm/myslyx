"""Header acceptance suite: the settings menu button fills with the favicon."""

from tests import helpers as h


async def favicon_button(page, msgs):
    btn = page.locator('#wb-settings-btn')
    await btn.wait_for(state='visible', timeout=10000)
    style = await btn.evaluate("""el => {
        const s = getComputedStyle(el);
        return { bg: s.backgroundImage, size: s.backgroundSize,
                 pos: s.backgroundPosition, rep: s.backgroundRepeat,
                 w: el.getBoundingClientRect().width, h: el.getBoundingClientRect().height };
    }""")
    assert 'favicon.svg' in style['bg'], f'favicon background missing: {style["bg"]}'
    assert style['size'] == 'cover', f'expected cover, got {style["size"]}'
    assert style['rep'] == 'no-repeat', f'expected no-repeat, got {style["rep"]}'
    # The button must render at the intended size across all browsers.
    assert 20 <= style['w'] <= 30, f'unexpected width {style["w"]}'
    assert 16 <= style['h'] <= 22, f'unexpected height {style["h"]}'
    assert msgs == []


async def settings_menu_opens(page, msgs):
    btn = page.locator('#wb-settings-btn')
    await btn.wait_for(state='visible', timeout=10000)
    await btn.click()
    await page.wait_for_timeout(500)
    state = await page.evaluate(
        "(() => { const m = document.getElementById('wb-settings-menu'); "
        "if (!m || m.style.display === 'none') return null; "
        "const t = m.querySelector('.wb-settings-title'); "
        "return t ? t.textContent : ''; })()")
    assert state == 'SETTINGS', f'settings menu did not open: {state!r}'
    assert msgs == []


async def plugins_submenu_lists_plugins(page, msgs):
    btn = page.locator('#wb-settings-btn')
    await btn.wait_for(state='visible', timeout=10000)
    await btn.click()
    await page.wait_for_timeout(500)
    # Both settings rows must be present, and the WRAP row must report a state.
    rows = await page.evaluate("""() => {
        const m = document.getElementById('wb-settings-menu');
        const wrap = m.querySelector('#wb-settings-wrap .wb-settings-value');
        return {
            plugins: !!m.querySelector('#wb-settings-plugins'),
            wrap: wrap ? wrap.textContent : null,
        };
    }""")
    assert rows['plugins'], 'PLUGINS setting row missing'
    assert rows['wrap'] in ('ON', 'OFF'), f'unexpected WRAP value: {rows["wrap"]}'
    # The plugins submenu opens on demand and lists the installed plugins.
    await page.click('#wb-settings-plugins')
    await page.wait_for_timeout(500)
    open_ = await page.evaluate(
        "(() => { const m = document.getElementById('wb-plugins-menu'); "
        "return m && m.style.display !== 'none'; })()")
    assert open_, 'plugins submenu did not open'
    names = await page.evaluate("""() => {
        const m = document.getElementById('wb-plugins-menu');
        return Array.from(m.querySelectorAll('.wb-plugin-name')).map(n => n.textContent);
    }""")
    assert 'color-swatches' in names, f'bundled plugin missing: {names}'
    assert msgs == []


async def plugin_toggle_preserves_file_pool(page, msgs):
    # Regression: toggling a plugin in the Settings menu schedules a page
    # reload, and that reload must NOT wipe the user's file pool (it used to
    # get replaced with a fresh STARTUP starter on every reload).
    await h.new_file(page, 2)
    name = await h.active_tab_name(page)
    assert name, 'expected a writable active file after NEW FILE'
    await h.active_cm(page).click()
    await page.keyboard.type('PRINT 42')
    await page.wait_for_timeout(400)
    # Open the settings menu and the PLUGINS submenu so the plugin rows exist.
    btn = page.locator('#wb-settings-btn')
    await btn.wait_for(state='visible', timeout=10000)
    await btn.click()
    await page.wait_for_timeout(500)
    await page.click('#wb-settings-plugins')
    await page.wait_for_timeout(500)
    # Toggle the first plugin row; the change handler persists config and
    # reloads the page after ~300ms.
    async with page.expect_navigation(wait_until='load'):
        await page.evaluate("""() => {
            const cb = document.querySelector('.wb-plugin-check');
            cb.checked = !cb.checked;
            cb.dispatchEvent(new Event('change', {bubbles: true}));
        }""")
    # The editor comes back once the storage sync bridge hands the pool over.
    await page.wait_for_selector('.wb-file-tab', timeout=20000)
    await page.wait_for_timeout(1500)
    tabs = await page.evaluate("""() => Array.from(
        document.querySelectorAll('.wb-file-tab .file-name')).map(n => n.textContent)""")
    assert name in tabs, f'created file vanished after plugin toggle: {tabs}'
    assert await h.doc_text(page) == 'PRINT 42', 'doc content lost after plugin toggle'
    assert msgs == []


HEADER_SUITES = [
    ('header/favicon-background', favicon_button),
    ('header/settings-menu-opens', settings_menu_opens),
    ('header/plugins-submenu', plugins_submenu_lists_plugins),
    ('header/plugin-toggle-preserves-files', plugin_toggle_preserves_file_pool),
]
