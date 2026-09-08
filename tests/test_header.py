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


HEADER_SUITES = [
    ('header/favicon-background', favicon_button),
    ('header/settings-menu-opens', settings_menu_opens),
    ('header/plugins-submenu', plugins_submenu_lists_plugins),
]