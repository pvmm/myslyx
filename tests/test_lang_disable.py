"""Acceptance suite for the ``MYSLYX_DISABLED_LANGS`` deployment gate.

An operator hides languages per deployment with a comma-separated env var
(see ``myslyx/languages.py``). These suites run dedicated server phases with
that variable set and assert the two observable effects:

- hidden languages disappear from the LANG combo box, and a stored file using
  one re-resolves to an enabled dialect of the same base (else ``Text``);
- plugins scoped to a hidden language are disabled and greyed out in
  Settings > PLUGINS. A base-scoped plugin is withheld only once the whole
  base is hidden, so hiding a single dialect leaves it usable.

Each phase below spawns its own server (the runner groups by env dict).
"""

from tests import helpers as h


# (name, fn, env). env -> a dedicated server phase with the variable set.

async def _lang_options(page):
    """Open the LANG combo and return the option labels it shows."""
    await page.click('.wb-select')
    await page.wait_for_function("""() => {
        return Array.from(document.querySelectorAll('.q-menu')).some(m => {
            const cs = getComputedStyle(m);
            return cs.visibility !== 'hidden' && cs.opacity !== '0'
                && m.getBoundingClientRect().width > 0;
        });
    }""", timeout=10000)
    labels = await page.evaluate("""() => {
        const m = Array.from(document.querySelectorAll('.q-menu')).find(x =>
            x.getBoundingClientRect().width > 0);
        return Array.from(m.querySelectorAll('.q-item')).map(e => e.innerText.trim());
    }""")
    await page.keyboard.press('Escape')
    await page.wait_for_function("""() => !Array.from(document.querySelectorAll('.q-menu'))
        .some(x => x.getBoundingClientRect().width > 0)""", timeout=10000)
    return labels


async def _plugin_rows(page):
    """Open Settings > PLUGINS and snapshot each row's name/locked/state."""
    await page.click('#wb-settings-btn')
    await page.wait_for_function("""() => {
        const m = document.getElementById('wb-settings-menu');
        return !!m && m.style.display === 'block';
    }""", timeout=10000)
    await page.click('#wb-settings-plugins')
    await page.wait_for_function("""() => {
        const m = document.getElementById('wb-plugins-menu');
        return !!m && m.style.display === 'block';
    }""", timeout=10000)
    rows = await page.evaluate("""() => {
        const m = document.getElementById('wb-plugins-menu');
        return Array.from(m.querySelectorAll('.wb-plugin-row')).map(r => ({
            name: r.querySelector('.wb-plugin-name').textContent,
            locked: r.classList.contains('wb-plugin-disabled'),
            checked: r.querySelector('.wb-plugin-check').checked,
            disabled: r.querySelector('.wb-plugin-check').disabled,
        }));
    }""")
    await page.click('#wb-settings-btn')  # close (no config change -> no reload)
    return rows


async def _store_language(page, language):
    """Persist one file with ``language`` as the pool, reload, wait for load."""
    await page.evaluate("""(lang) => {
        window.WBStorage.saveFiles([{
            id: 'file_keep1', name: 'keep.c', language: lang,
            content: 'int main() { return 0; }',
            readonly: false, export_symbols: true
        }]);
        window.WBStorage.saveActive('file_keep1');
    }""", language)
    await page.reload(wait_until='load')
    await page.wait_for_selector('.wb-file-tab', timeout=20000)


async def partial_base_still_usable(page, msgs):
    """Hiding C MSXgl alone keeps plain C and base-scoped plugins usable."""
    assert await page.evaluate('window.__wbDisabledLangs') == ['C MSXgl'], \
        'the C MSXgl key must be the only exact language hidden'
    assert await page.evaluate('window.__wbDisabledBaseLangs') == [], \
        'base c still has an enabled dialect, so it must not be locked'

    # The LANG combo is locked while the read-only STARTUP file is active;
    # create a writable file before opening it.
    await h.new_file(page, 2)
    labels = await _lang_options(page)
    assert 'C+MSXgl' not in labels, f'hidden C+MSXgl still offered: {labels}'
    for shown in ('HitBasic', 'Pascal', 'C', 'Z80 Assembly', 'Text'):
        assert shown in labels, f'{shown!r} must stay offered: {labels}'

    rows = {r['name']: r for r in await _plugin_rows(page)}
    # c-swatches ({languages:["C"]}) and base-c-swatches ({baseLang:["c"]}) both
    # still apply to plain C, so neither may be locked by hiding C MSXgl.
    for name in ('c-swatches', 'base-c-swatches', 'c-struct-complete'):
        row = rows.get(name)
        assert row is not None, f'{name} missing from the plugins menu: {sorted(rows)}'
        assert row['locked'] is False, f'{name} must stay usable: {row}'
        assert row['disabled'] is False, f'{name} checkbox must stay enabled: {row}'
        assert row['checked'] is True, f'{name} must stay checked: {row}'

    # A file stored as C MSXgl re-resolves to the still-enabled C dialect.
    await _store_language(page, 'C MSXgl')
    await page.wait_for_function("window.__wbCurrentLang === 'C'", timeout=10000)
    assert await page.evaluate('window.__wbHintKey') == 'c', \
        'the re-resolved file must use the plain C dictionary'
    assert await page.evaluate('window.__wbBaseLang') == 'c'
    assert not msgs, f'console errors: {msgs}'


async def langs_hidden(page, msgs):
    """Hidden languages vanish from the combo; the default is a visible one."""
    dis = await page.evaluate('window.__wbDisabledLangs')
    assert sorted(dis) == ['C', 'C MSXgl', 'HitBasic'], f'unexpected disabled: {dis}'
    assert sorted(await page.evaluate('window.__wbDisabledBaseLangs')) == ['basic', 'c'], \
        'both whole families must be reported disabled'

    # The LANG combo is locked while the read-only STARTUP file is active;
    # create a writable file before opening it.
    await h.new_file(page, 2)
    labels = await _lang_options(page)
    for hidden in ('HitBasic', 'C', 'C+MSXgl'):
        assert hidden not in labels, f'hidden {hidden!r} still offered: {labels}'
    for shown in ('Pascal', 'Z80 Assembly', 'Text'):
        assert shown in labels, f'{shown!r} must stay offered: {labels}'

    # The newly created file must not start in a hidden language.
    await h.focus_active_editor(page)
    current = await page.evaluate('window.__wbCurrentLang')
    assert current not in dis, f'new file started in a hidden language: {current}'

    # A HitBasic file falls back (no other 'basic' dialect exists).
    await _store_language(page, 'HitBasic')
    await page.wait_for_function("window.__wbCurrentLang !== 'HitBasic'", timeout=10000)
    assert await page.evaluate('window.__wbCurrentLang') == 'Text', \
        'a HitBasic file must fall back to Text when its only dialect is hidden'
    assert not msgs, f'console errors: {msgs}'


async def plugins_greyed(page, msgs):
    """Plugins scoped to a fully hidden language are locked and greyed out."""
    rows = {r['name']: r for r in await _plugin_rows(page)}

    # Exact-scope plugins on a hidden key: hitbasic ({languages:["HitBasic"]})
    # and c-swatches ({languages:["C"]}).
    for name in ('hitbasic', 'c-swatches'):
        row = rows.get(name)
        assert row is not None, f'{name} missing: {sorted(rows)}'
        assert row['locked'] is True, f'{name} must be greyed: {row}'
        assert row['disabled'] is True, f'{name} checkbox must be disabled: {row}'
        assert row['checked'] is False, f'{name} must show unchecked: {row}'

    # Base-scope plugins on a fully hidden family: base-c-swatches and
    # c-struct-complete ({baseLang:["c"]}).
    for name in ('base-c-swatches', 'c-struct-complete'):
        row = rows.get(name)
        assert row is not None, f'{name} missing: {sorted(rows)}'
        assert row['locked'] is True, f'{name} must be greyed: {row}'
        assert row['disabled'] is True, f'{name} checkbox must be disabled: {row}'

    # Unrelated plugins stay available.
    for name in ('myslyx-favicon', 'local-lsp', 'weblsp'):
        row = rows.get(name)
        assert row is not None, f'{name} missing: {sorted(rows)}'
        assert row['locked'] is False, f'{name} must stay available: {row}'
        assert row['disabled'] is False, f'{name} checkbox must stay enabled: {row}'

    assert not msgs, f'console errors: {msgs}'


LANG_DISABLE_SUITES = [
    ('langdisable/partial-base-still-usable', partial_base_still_usable,
     {'MYSLYX_DISABLED_LANGS': 'C MSXgl'}),
    ('langdisable/langs-hidden', langs_hidden,
     {'MYSLYX_DISABLED_LANGS': 'HitBasic,c'}),
    ('langdisable/plugins-greyed', plugins_greyed,
     {'MYSLYX_DISABLED_LANGS': 'HitBasic,c'}),
]
