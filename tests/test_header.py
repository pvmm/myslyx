"""Header acceptance suite: the plugins menu button fills with the favicon."""

from tests import helpers as h


async def favicon_button(page, msgs):
    btn = page.locator('#wb-plugins-btn')
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


async def plugins_menu_opens(page, msgs):
    btn = page.locator('#wb-plugins-btn')
    await btn.wait_for(state='visible', timeout=10000)
    await btn.click()
    await page.wait_for_timeout(500)
    open_ = await page.evaluate(
        "(() => { const m = document.getElementById('wb-plugins-menu'); "
        "return m && m.style.display !== 'none'; })()")
    assert open_, 'plugins menu did not open'
    assert msgs == []


HEADER_SUITES = [
    ('header/favicon-background', favicon_button),
    ('header/plugins-menu-opens', plugins_menu_opens),
]