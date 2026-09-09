"""Acceptance suite for user-installed plugins (per-OS config directory).

The runner installs a throwaway config directory (override via XDG_CONFIG_HOME
/ APPDATA) with two user plugins before the app starts, then the suites below
verify discovery, shadowing, serving and actual rendering of those plugins.
On macOS the user plugins dir is HOME-based, so this automated routine only
exercises the Linux and Windows layouts.
"""

import json
import sys
import tempfile
from pathlib import Path

from tests import helpers as h

# Default-enabled, all-languages plugins. Both are asserted to render in the
# discovery/serving/rendering suite below.
USER_PLUGINS = [
    ('color-swatches', 'red'),
    ('user-swatches', 'green'),
]

# Plugins that exercise the documented plugin.json contract: enabledByDefault
# and languages. Each maps to (name, color, plugin.json metadata or None).
META_PLUGINS = [
    # Off unless the user config explicitly enables it (enabledByDefault:false).
    ('lazy-swatches', 'orange', {'enabledByDefault': False}),
    # Only applies to C files (languages:["C"]).
    ('c-swatches', 'cyan', {'languages': ['C']}),
]


def _module(name: str, color: str) -> str:
    """A minimal, self-identifying plugin module (renders fixed-color boxes)."""
    fn = name.replace('-', '_') + 'Factory'
    return f'''export default function {fn}(CM) {{
    const {{ EditorView, Decoration, WidgetType, StateField }} = CM;
    class Box extends WidgetType {{
        constructor(c) {{ super(); this.color = c; }}
        eq(o) {{ return o.color === this.color; }}
        toDOM() {{
            const b = document.createElement('span');
            b.style.display = 'inline-block';
            b.style.width = '12px';
            b.style.height = '12px';
            b.style.marginLeft = '4px';
            b.style.verticalAlign = 'middle';
            b.style.borderRadius = '2px';
            b.style.backgroundColor = '{color}';
            return b;
        }}
    }}
    function decos(state) {{
        const rx = /#[0-9a-fA-F]{{3,8}}\\b/g;
        const text = state.doc.toString();
        const out = [];
        let m;
        while ((m = rx.exec(text)) !== null) {{
            out.push(Decoration.widget({{ widget: new Box(m[0]), side: 1 }}).range(m.index + m[0].length));
        }}
        return Decoration.set(out);
    }}
    return StateField.define({{
        create(s) {{ return decos(s); }},
        update(d, tr) {{ return tr.docChanged ? decos(tr.state) : d.map(tr.changes); }},
        provide: f => EditorView.decorations.from(f),
    }});
}}
'''


def prepare_user_plugin_layout() -> Path:
    """Create a throwaway config dir with plugins; returns its root path.

    The runner sets XDG_CONFIG_HOME/APPDATA to this root before spawning the
    app, and removes it afterwards. Writes plugin.json (when provided) so the
    metadata-driven suites (enable/disable, language filtering) run against
    real manifest entries.
    """
    root = Path(tempfile.mkdtemp(prefix='wb-user-plugins-'))
    plugins = root / 'myslyx' / 'plugins'
    plugins.mkdir(parents=True, exist_ok=True)
    for name, color in USER_PLUGINS:
        _write_user_plugin(plugins, name, color)
    for name, color, meta in META_PLUGINS:
        _write_user_plugin(plugins, name, color, meta=meta)
    return root


def _write_user_plugin(plugins: Path, name: str, color: str, meta: dict | None = None) -> None:
    plugin_dir = plugins / name
    plugin_dir.mkdir()
    (plugin_dir / f'{name}.js').write_text(_module(name, color))
    if meta:
        (plugin_dir / 'plugin.json').write_text(json.dumps(meta))


async def _render_state(page) -> dict:
    """Count the color widgets rendered by user plugins in the active editor."""
    return await page.evaluate(
        """() => getElement(window.__wbEditorId).editorPromise.then(v => {
            const out = { red: 0, green: 0, orange: 0, cyan: 0 };
            v.contentDOM.querySelectorAll('.cm-line span').forEach(s => {
                const c = getComputedStyle(s).backgroundColor;
                if (c === 'rgb(255, 0, 0)') out.red++;
                if (c === 'rgb(0, 128, 0)') out.green++;
                if (c === 'rgb(255, 165, 0)') out.orange++;
                if (c === 'rgb(0, 255, 255)') out.cyan++;
            });
            return out;
        })""")


async def user_installed_plugins(page, msgs):
    manifest = await page.evaluate('window.WB_PLUGIN_MANIFEST || []')
    by_name = {e['name']: e for e in manifest}
    names = [e['name'] for e in manifest]
    # The bundled color-swatches must be shadowed by the user installation.
    assert names.count('color-swatches') == 1, f'duplicate/missing color-swatches: {names}'
    assert by_name['color-swatches']['base'] == '/user-plugins/', by_name['color-swatches']
    assert by_name['user-swatches']['base'] == '/user-plugins/', by_name
    # Both user modules must be reachable at their served URL.
    for name, _ in USER_PLUGINS:
        status = await page.evaluate(
            'async (url) => (await fetch(url)).status',
            f'/user-plugins/{name}/{name}.js')
        assert status == 200, f'{name} module not served: {status}'
    # Types on screen, both plugins must render their widgets.
    await h.new_file(page, 2)
    await page.keyboard.type('#ff00ff')
    await page.wait_for_timeout(900)
    colors = await _render_state(page)
    assert colors['red'] >= 1, f'user color-swatches (red) missing: {colors}'
    assert colors['green'] >= 1, f'user-swatches (green) missing: {colors}'
    assert msgs == []


async def plugin_disable_via_config(page, msgs):
    """Disabling a user plugin in the shared config stops it rendering."""
    await page.evaluate("""() => {
        const cfg = WBStorage.loadConfig();
        cfg.plugins = cfg.plugins || {};
        cfg.plugins['color-swatches'] = true;
        cfg.plugins['user-swatches'] = false;
        WBStorage.saveConfig(cfg);
    }""")
    await page.reload(wait_until='load')
    await page.wait_for_timeout(2500)
    await h.new_file(page, 2)
    await page.keyboard.type('#ff00ff')
    await page.wait_for_timeout(900)
    colors = await _render_state(page)
    assert colors['red'] >= 1, f'enabled color-swatches must render: {colors}'
    assert colors['green'] == 0, f'disabled user-swatches must not render: {colors}'
    assert msgs == []


async def plugin_lazy_disabled_by_default(page, msgs):
    """A user plugin with enabledByDefault:false stays off until enabled."""
    # Clear any persisted override so the default (false) applies.
    await page.evaluate("""() => {
        const cfg = WBStorage.loadConfig();
        cfg.plugins = cfg.plugins || {};
        delete cfg.plugins['lazy-swatches'];
        WBStorage.saveConfig(cfg);
    }""")
    await page.reload(wait_until='load')
    await page.wait_for_timeout(2500)
    await h.new_file(page, 2)
    await page.keyboard.type('#00ff00')
    await page.wait_for_timeout(900)
    colors = await _render_state(page)
    assert colors['orange'] == 0, f'lazy-swatches must be off by default: {colors}'

    # Enabling it in the config makes it render after the next reload.
    await page.evaluate("""() => {
        const cfg = WBStorage.loadConfig();
        cfg.plugins = cfg.plugins || {};
        cfg.plugins['lazy-swatches'] = true;
        WBStorage.saveConfig(cfg);
    }""")
    await page.reload(wait_until='load')
    await page.wait_for_timeout(2500)
    await h.new_file(page, 2)
    await page.keyboard.type('#00ff00')
    await page.wait_for_timeout(900)
    colors = await _render_state(page)
    assert colors['orange'] >= 1, f'lazy-swatches must render once enabled: {colors}'
    assert msgs == []


async def plugin_language_filter(page, msgs):
    """A user plugin limited to languages:['C'] skips non-C editors."""
    await page.evaluate("""() => {
        const cfg = WBStorage.loadConfig();
        cfg.plugins = cfg.plugins || {};
        delete cfg.plugins['c-swatches'];
        WBStorage.saveConfig(cfg);
    }""")
    await page.reload(wait_until='load')
    await page.wait_for_timeout(2500)
    # New files default to HitBasic -> the C-only plugin must not render.
    await h.new_file(page, 2)
    await page.keyboard.type('#00ffff')
    await page.wait_for_timeout(900)
    colors = await _render_state(page)
    assert colors['cyan'] == 0, f'c-swatches must not render in HitBasic file: {colors}'

    # Import a C source file -> the C-only plugin must now render.
    before = await page.evaluate("document.querySelectorAll('.wb-file-tab').length")
    await page.evaluate("""() => {
        const dt = new DataTransfer();
        dt.items.add(new File(['int main(void){return 0;}'], 'prog.c', {type: 'text/plain'}));
        const ev = new Event('drop', {bubbles: true, cancelable: true});
        try { Object.defineProperty(ev, 'dataTransfer', {value: dt}); } catch(e) { ev.dataTransfer = dt; }
        document.dispatchEvent(ev);
    }""")
    await page.wait_for_function(
        f"document.querySelectorAll('.wb-file-tab').length === {before + 1}")
    await page.wait_for_timeout(800)
    await h.active_cm(page).click()
    await page.keyboard.type('#00ffff')
    await page.wait_for_timeout(900)
    colors = await _render_state(page)
    assert colors['cyan'] >= 1, f'c-swatches must render in a C file: {colors}'
    assert msgs == []


PLUGIN_SUITES = [
    ('plugins/user-installed', user_installed_plugins),
    ('plugins/disable-via-config', plugin_disable_via_config),
    ('plugins/lazy-disabled-by-default', plugin_lazy_disabled_by_default),
    ('plugins/language-filter', plugin_language_filter),
]