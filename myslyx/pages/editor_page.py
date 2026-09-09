import json
import logging
from pathlib import Path
from typing import Any
from nicegui import ui

from myslyx.paths import user_plugins_dir


FAVICON_PATH = str(Path(__file__).resolve().parents[1] / 'static' / 'favicon.svg')

# Language options offered by the LANG combo box. Keys are the values stored
# with files (CodeMirror language names), values are the labels shown here.
LANGUAGES: dict[str, str] = {
    # HitBasic is a BASIC dialect. Its CodeMirror language support ships as a
    # plugin (static/plugins/hitbasic/): it builds on the VBScript highlighter
    # and declares "'" as the line-comment token, so Ctrl-/ works in BASIC.
    'HitBasic': 'HitBasic',
    'Pascal': 'Pascal',
    'C': 'C',
    'Z80': 'Z80 Assembly',
    'Text': 'Text',
}

# Stored language ids that once existed in LANGUAGES but are no longer
# offered by the combo box. Files saved with such an id keep working: they
# resolve to the current id instead of falling back to plain text.
LEGACY_LANGUAGES: dict[str, str] = {
    'VBScript': 'HitBasic',
}


def _canonical_lang(lang: str | None) -> str | None:
    """Resolve a stored language value to a current LANGUAGES key.

    Returns None only for values that were never a real language id.
    """
    if lang in LANGUAGES:
        return lang
    return LEGACY_LANGUAGES.get(lang) if lang is not None else None

# Maps stored CodeMirror language values to hint dictionary keys (files under
# static/hints/<key>.json). Unknown languages fall back to plain text.
HINT_KEYS: dict[str, str] = {
    'HitBasic': 'basic',
    'Pascal': 'plaintext',
    'C': 'plaintext',
    'Z80': 'plaintext',
    'Text': 'plaintext',
}

# Editor font choices (CSS font-family values)
FONTS: dict[str, str] = {
    'Press Start 2P': 'Press Start 2P',
    'VT323': 'VT323',
    'Source Code Pro': 'Source Code Pro',
    'Fira Code': 'Fira Code',
    'Courier Prime': 'Courier Prime',
    'Courier New': 'Courier New',
    'monospace': 'monospace',
}

DEFAULT_FONT = 'Press Start 2P'
DEFAULT_FONT_SIZE = 13
MIN_FONT_SIZE = 8
MAX_FONT_SIZE = 28




def _storage_io_js() -> str:
    """Return JS that exposes file pool operations via window.__wbPyBridge."""
    return '''
    <script>
    (function() {
        window.__wbPyBridge = {
            getFiles: function() { return WBStorage.loadFiles(); },
            setFiles: function(files) { WBStorage.saveFiles(files); },
            getActive: function() { return WBStorage.loadActive(); },
            setActive: function(id) { WBStorage.saveActive(id); },
            hasFiles: function() {
                var f = WBStorage.loadFiles();
                return f && f.length > 0;
            },
            initDefaults: function() {
                var files = WBDefaults.createStarterFiles();
                WBStorage.saveFiles(files);
                WBStorage.saveActive(files[0].id);
                return files;
            }
        };
    })();
    </script>
    '''


def _plugin_metadata(plugin_dir: Path) -> dict[str, Any] | None:
    """Metadata for one plugin directory (static/plugins/<name>/)."""
    name = plugin_dir.name
    entry = f'{name}.js'
    if not (plugin_dir / entry).is_file():
        return None
    meta: dict[str, Any] = {'name': name, 'dir': name, 'entry': entry}
    meta_file = plugin_dir / 'plugin.json'
    if meta_file.is_file():
        try:
            extra = json.loads(meta_file.read_text())
            if isinstance(extra.get('languages'), list):
                meta['languages'] = extra['languages']
            if isinstance(extra.get('enabledByDefault'), bool):
                meta['enabledByDefault'] = extra['enabledByDefault']
            # "boot": load and run the module factory at page startup so global
            # side effects (e.g. registering a language in the catalog) happen
            # before the server can activate an editor that needs them.
            if isinstance(extra.get('boot'), bool):
                meta['boot'] = extra['boot']
        except (OSError, ValueError):
            logging.warning('Invalid plugin.json in %s', plugin_dir)
    return meta


@ui.page('/editor', favicon=FAVICON_PATH)
def editor_page() -> None:
    ui.add_head_html('<link rel="stylesheet" href="/static/retro.css">')
    ui.add_head_html(_storage_io_js())
    ui.add_head_html('<script src="/static/retro.js"></script>')
    ui.add_head_html('<script src="/static/vendor/marked.min.js"></script>')
    ui.add_head_html('<script src="/static/hints.js"></script>')
    ui.add_head_html('<script src="/static/plugins.js"></script>')
    plugin_manifest_by_name: dict[str, Any] = {}

    def collect(base_url: str, plugins_dir: Path) -> None:
        for plugin_dir in sorted(d for d in plugins_dir.iterdir() if d.is_dir()):
            meta = _plugin_metadata(plugin_dir)
            if not meta:
                continue
            meta['base'] = base_url
            plugin_manifest_by_name[meta['name']] = meta

    # Bundled first, then user plugins: an installation in the user config
    # directory shadows a bundled plugin with the same name.
    collect('/static/plugins/', Path(__file__).resolve().parents[1] / 'static' / 'plugins')
    user_plugins = user_plugins_dir()
    if user_plugins.is_dir():
        collect('/user-plugins/', user_plugins)
    plugin_manifest = list(plugin_manifest_by_name.values())
    if plugin_manifest:
        ui.add_head_html(f'<script>window.WB_PLUGIN_MANIFEST = {json.dumps(plugin_manifest)};</script>')
        ui.add_head_html('<script src="/static/plugins/lifecycle.js"></script>')

    hints_content_id = 'hints-content'

    with ui.element('div').classes('wb-root'):
        # === App Header ===
        with ui.element('div').classes('wb-app-header'):
            with ui.button(color='transparent').classes('wb-button').props('id=wb-settings-btn'):
                pass
            ui.label('Myslyx Text Editor v1.0').classes('app-title')
            ui.button('?').classes('wb-button').style('margin-left:auto;').props('id=wb-shortcut-btn').on_click(lambda: _open_shortcut_dialog())

        # === Toolbar ===
        with ui.element('div').classes('wb-toolbar'):
            # LANG: label stacked above the combo box
            with ui.element('div').style('display:flex;flex-direction:column;justify-content:center;gap:2px;'):
                ui.label('LANG').classes('wb-select-label').style(
                    'font-family:var(--wb-font);font-size:8px;color:var(--wb-white);'
                )
                lang_select = (
                    ui.select(
                        LANGUAGES,
                        value='HitBasic',
                        on_change=lambda e: _on_language_change(e.value),
                    )
                    .classes('wb-select')
                )

            # FONT: label stacked above the combo box
            with ui.element('div').style('display:flex;flex-direction:column;justify-content:center;gap:2px;margin-left:8px;'):
                ui.label('FONT').classes('wb-select-label').style(
                    'font-family:var(--wb-font);font-size:8px;color:var(--wb-white);'
                )
                font_select = (
                    ui.select(
                        FONTS,
                        value=DEFAULT_FONT,
                        on_change=lambda e: _on_font_change(e.value),
                    )
                    .classes('wb-select')
                )

            # Font size: label stacked above the slider
            with ui.element('div').style('display:flex;flex-direction:column;justify-content:center;gap:2px;margin-left:8px;'):
                ui.label('BASE FONT SIZE').classes('wb-select-label').style(
                    'font-family:var(--wb-font);font-size:8px;color:var(--wb-white);'
                )
                with ui.element('div').style('display:flex;align-items:center;'):
                    font_size_label = (
                        ui.label(f'{DEFAULT_FONT_SIZE}px')
                        .style('font-family:var(--wb-font);font-size:8px;color:var(--wb-white);width:28px;')
                    )
                    font_size_slider = (
                        ui.slider(
                            min=MIN_FONT_SIZE,
                            max=MAX_FONT_SIZE,
                            step=1,
                            value=DEFAULT_FONT_SIZE,
                            on_change=lambda e: _on_font_size_change(e.value),
                        )
                        .style('width:90px;margin-left:6px;')
                    )

            file_name_label = (
                ui.label('untitled')
                .props('id=wb-file-name')
                .style('font-family:var(--wb-font);font-size:9px;color:var(--wb-white);margin-left:12px;')
            )

            with ui.element('div').style('margin-left:auto;display:flex;align-items:stretch;gap:4px;'):
                # Undo/redo stacked in two rows (operate directly on the editor view)
                with ui.element('div').style('display:flex;flex-direction:column;gap:4px;'):
                    undo_btn = ui.button('UNDO').classes('wb-button')
                    undo_btn.props('id=wb-undo-btn')
                    redo_btn = ui.button('REDO').classes('wb-button')
                    redo_btn.props('id=wb-redo-btn')
                undo_btn.on('click', lambda: ui.run_javascript('if (window.__wbUndo) window.__wbUndo();'))
                redo_btn.on('click', lambda: ui.run_javascript('if (window.__wbRedo) window.__wbRedo();'))
                # separator between undo/redo and other actions
                ui.element('div').style('width:2px;height:20px;background:var(--wb-black);align-self:center;margin:0 6px;')
                # Toggle: globally export the current file's symbols or keep them local
                export_btn = ui.button('EXPORT\nSYMBOLS\nON').classes('wb-button').props('id=wb-export-btn')
                export_btn.on('click', lambda: _toggle_symbol_export())
                with export_btn:
                    # Nest the tooltip (instead of export_btn.tooltip()) because the
                    # shortcut sets target='#c<id>' while this button overrides its DOM
                    # id via props('id=wb-export-btn'), leaving a dangling anchor that
                    # makes Quasar log 'Anchor: target "#c…" not found'.
                    ui.tooltip('When ON, this file\'s symbols (functions, subs) are available to every open file. Toggle OFF to keep them local to this file.')
                # separator between toggle buttons and other actions
                ui.element('div').style('width:2px;height:20px;background:var(--wb-black);align-self:center;margin:0 6px;')
                # Rename/delete stacked in two rows
                with ui.element('div').style('display:flex;flex-direction:column;gap:4px;'):
                    rename_btn = ui.button('RENAME', on_click=lambda: _open_rename_dialog()).classes('wb-button')
                    rename_btn.props('id=wb-rename-btn')
                    delete_btn = ui.button('DELETE', on_click=lambda: _open_delete_dialog(), color='red').classes('wb-button')
                    delete_btn.props('id=wb-delete-btn')
                ui.element('div').style('width:2px;height:20px;background:var(--wb-black);align-self:center;margin:0 6px;')
                # Upload/download stacked in two rows
                with ui.element('div').style('display:flex;flex-direction:column;gap:4px;'):
                    ui.button('UPLOAD', on_click=lambda: _upload_file()).classes('wb-button')
                    ui.button('DOWNLOAD', on_click=lambda: _download_current_file()).classes('wb-button')
                # RESET FILE POOL unstacked
                ui.button('RESET\nFILE\nPOOL', on_click=lambda: _open_reset_dialog(), color='red').classes('wb-button').style('background:#aa0000;color:#fff;')

        # Hidden bridge for client->server file open/import requests
        open_bridge = ui.element('div').props('id=wb-open-bridge').style('display:none;')
        open_bridge.on(
            'wb-open-file',
            lambda e: _open_file_request(e.args),
            js_handler="() => { try { const f = window.__wbPendingFile || null; delete window.__wbPendingFile; emit(f); } catch(e) { emit(null); } }",
        )

        # === Main area: editor + hints sidebar ===
        with ui.element('div').classes('wb-main-area'):
            # Editor area: one CodeMirror instance per open file, hidden
            # except the active one (built lazily via _ensure_editor).
            with ui.element('div').classes('wb-editor-area'):
                editor_host = ui.element('div').classes('wb-editor-host')

                # Status bar
                with ui.element('div').classes('wb-status-bar'):
                    status_lang = ui.label('HitBasic').style(
                        'font-family:var(--wb-font);font-size:8px;'
                    )
                    status_files = ui.label('0 files').style(
                        'font-family:var(--wb-font);font-size:8px;'
                    )

            # Resizable divider between editor and hints sidebar
            with ui.element('div').props('id=wb-hints-resizer').classes('wb-hints-resizer'):
                pass

            # Hints sidebar
            with ui.element('div').classes('wb-hints-sidebar'):
                with ui.element('div').classes('hints-header'):
                    ui.label('HINTS')
                with ui.element('div').classes('hints-content').props(f'id={hints_content_id}'):
                    ui.label('Type code and move cursor to see hints.').classes('hint-empty')

        # === File Pool Dock ===
        with ui.element('div').classes('wb-dock') as dock:
            ui.button('+ NEW', on_click=lambda: _new_file()).classes('wb-new-file')

    # ===== Client-side state =====
    client_state: dict[str, Any] = {
        'files': [],
        'active_id': None,
    }
    file_tabs: dict[str, Any] = {}
    editors: dict[str, Any] = {}
    editor_slots: dict[str, Any] = {}

    # ===== Helper functions =====

    def _ext_for_lang(lang: str) -> str:
        return {
            'hitbasic': 'bas', 'HitBasic': 'bas', 'vbscript': 'bas', 'VBScript': 'bas',
            'pascal': 'pas', 'Pascal': 'pas',
            'c': 'c', 'C': 'c',
            'z80': 'asm', 'Z80': 'asm',
            'plaintext': 'txt', 'Text': 'txt',
        }.get(lang, 'txt')

    def _base_name(name: str) -> str:
        return name.rsplit('.', 1)[0] if '.' in name else name

    def _lang_for_name(name: str) -> str:
        lowered = name.lower()
        if lowered.endswith(('.bas', '.vb', '.vbs')):
            return 'HitBasic'
        if lowered.endswith(('.pas', '.pp', '.inc')):
            return 'Pascal'
        if lowered.endswith(('.c', '.h')):
            return 'C'
        if lowered.endswith(('.asm', '.s', '.z80')):
            return 'Z80'
        return 'Text'

    def _file_icon(language: str) -> str:
        return {
            'hitbasic': 'BAS', 'HitBasic': 'BAS', 'vbscript': 'BAS', 'VBScript': 'BAS',
            'pascal': 'PAS', 'Pascal': 'PAS',
            'c': 'C', 'C': 'C',
            'z80': 'ASM', 'Z80': 'ASM',
            'plaintext': 'TXT', 'Text': 'TXT',
        }.get(language, '??')

    # ===== File pool management =====

    def _refresh_file_pool() -> None:
        nonlocal file_tabs, dock
        for tab_id, tab_el in file_tabs.items():
            try:
                tab_el.delete()
            except Exception:
                pass
        file_tabs.clear()

        # Create tabs inside the bottom dock so files appear in the dock area
        with dock:
            for f in client_state['files']:
                is_active = f['id'] == client_state['active_id']
                tab = ui.element('div').classes(
                    'wb-file-tab' + (' active' if is_active else '')
                )
                with tab:
                    ui.label(_file_icon(f.get('language', 'Text'))).classes('file-icon')
                    # Read-only files get a separate padlock element centered
                    # vertically next to the (extension-less) name.
                    with ui.element('div').classes('file-name-row'):
                        ui.label(_base_name(f.get('name', ''))).classes('file-name')
                        if f.get('readonly'):
                            ui.label('🔒').classes('file-lock')
                    close_btn = ui.element('div').classes('file-close')
                    with close_btn:
                        ui.label('X')
                    close_btn.on('click', lambda e, fid=f['id']: _request_close_file(fid))
                tab.on('click', lambda e, fid=f['id']: _switch_to_file(fid))
                file_tabs[f['id']] = tab

        n = len(client_state['files'])
        status_files.set_text(f'{n} file{"s" if n != 1 else ""}')

    def _save_to_storage() -> None:
        ui.run_javascript(
            f'window.__wbPyBridge.setFiles({json.dumps(client_state["files"])})'
        )
        if client_state['active_id']:
            ui.run_javascript(
                f'window.__wbPyBridge.setActive("{client_state["active_id"]}")'
            )

    def _new_file() -> None:
        import random
        fid = f'file_{random.randint(100000, 999999)}'
        lang = lang_select.value or 'Text'
        new = {
            'id': fid,
            'name': f'untitled_{len(client_state["files"]) + 1}.{_ext_for_lang(lang)}',
            'language': lang,
            'content': '',
            'export_symbols': True,
        }
        client_state['files'].append(new)
        client_state['active_id'] = fid
        _refresh_file_pool()
        _save_to_storage()
        # Ask the hints panel to open this language's root page after the
        # new file's editor becomes active.
        ui.run_javascript('window.__wbPendingRoot = true;')
        _load_file_into_editor(new)

    def _toggle_symbol_export() -> None:
        if not client_state['active_id']:
            return
        f = next(
            (f for f in client_state['files'] if f['id'] == client_state['active_id']),
            None,
        )
        if not f:
            return
        if f.get('language') == 'Text':
            return  # symbol export is not meaningful for plain text
        f['export_symbols'] = not bool(f.get('export_symbols', True))
        _save_to_storage()
        _update_export_button()

    def _update_export_button() -> None:
        if not client_state['active_id']:
            return
        f = next(
            (f for f in client_state['files'] if f['id'] == client_state['active_id']),
            None,
        )
        exporting = bool(f.get('export_symbols', True)) if f else True
        disabled = bool(f and f.get('language') == 'Text')
        label = ('EXPORT\nSYMBOLS\n---' if disabled
                 else ('EXPORT\nSYMBOLS\nON' if exporting else 'EXPORT\nSYMBOLS\nOFF'))
        export_btn.set_text(label)
        ui.run_javascript(f'''
            (function() {{
                var b = document.getElementById('wb-export-btn');
                if (!b) return;
                b.disabled = {str(disabled).lower()};
                b.classList.toggle('active', !b.disabled && {str(exporting).lower()});
            }})();
        ''')

    def _close_file(fid: str) -> None:
        # Drop any persisted user symbols for this file.
        ui.run_javascript(f'window.__wbPruneSymbols && window.__wbPruneSymbols("{fid}");')
        ed = editors.pop(fid, None)
        slot = editor_slots.pop(fid, None)
        target_el = slot if slot is not None else ed
        if target_el is not None:
            ui.run_javascript(f'window.__wbEditorIds && delete window.__wbEditorIds["{fid}"];')
            try:
                target_el.delete()
            except Exception:
                pass
        client_state['files'] = [f for f in client_state['files'] if f['id'] != fid]
        if client_state['active_id'] == fid:
            if client_state['files']:
                client_state['active_id'] = client_state['files'][0]['id']
                _load_file_into_editor(client_state['files'][0])
            else:
                client_state['active_id'] = None
                ui.run_javascript('window.__wbEditorId = null;')
                file_name_label.set_text('no files')
        # Persist state before mutating UI elements. If we refresh (delete)
        # UI elements while this click handler's slot is still active, NiceGUI
        # may raise "The parent element this slot belongs to has been deleted.".
        _save_to_storage()
        _refresh_file_pool()

    def _ensure_editor(f: dict[str, Any]) -> Any:
        # Lazily create one CodeMirror instance per open file. Each view keeps
        # its own native undo/redo history, so edits never leak across files.
        # Returns the visible container slot (hidden until activated).
        fid = f['id']
        if fid in editor_slots:
            return editor_slots[fid]
        cm_lang = f.get('language', 'Text')
        canonical = _canonical_lang(cm_lang)
        if canonical is None:
            canonical = 'Text'
            f['language'] = 'Text'
        cm_lang = canonical
        with editor_host:
            with ui.element('div').props(f'id=wb-edit-slot-{fid}').classes('wb-editor-slot wb-editor-hidden') as slot:
                ed = (
                    ui.codemirror(
                        value=f.get('content', ''),
                        language=cm_lang,
                        theme='basicDark',
                        on_change=lambda e, fid=fid: _on_editor_change(fid, e.value),
                    )
                    .style('flex:1;width:100%;')
                )
        if cm_lang == 'Text':
            ed.set_language(None)
        else:
            ed.set_language(cm_lang)
        editors[fid] = ed
        editor_slots[fid] = slot
        ui.run_javascript(f'window.__wbEditorIds["{fid}"] = {ed.id};')
        return slot

    def _open_file_request(file: Any) -> None:
        # Client-side imports (UPLOAD button, drag-and-drop) land here so the
        # server owns file state, dock tabs and editor instances.
        import random
        if not isinstance(file, dict):
            return
        fid = str(file.get('id') or f'file_{random.randint(100000, 999999)}')
        name = str(file.get('name') or 'untitled.txt')
        lang = str(file.get('language') or _lang_for_name(name))
        canonical = _canonical_lang(lang)
        lang = canonical if canonical is not None else 'Text'
        content = file.get('content') if isinstance(file.get('content'), str) else ''
        target = next((f for f in client_state['files'] if f['id'] == fid), None)
        if target is None:
            target = {
                'id': fid,
                'name': name,
                'language': lang,
                'content': content,
                'export_symbols': True,
            }
            client_state['files'].append(target)
        else:
            target['name'] = name
            target['language'] = lang
            if content:
                target['content'] = content
        client_state['active_id'] = fid
        _load_file_into_editor(target)
        _refresh_file_pool()
        _save_to_storage()

    def _switch_to_file(fid: str) -> None:
        if fid == client_state['active_id']:
            return
        target = next((f for f in client_state['files'] if f['id'] == fid), None)
        if not target:
            return
        client_state['active_id'] = fid
        _load_file_into_editor(target)
        _refresh_file_pool()
        _save_to_storage()

    def _load_file_into_editor(f: dict[str, Any]) -> None:
        # Activate this file's own editor instance (creating it lazily) and
        # make it the only visible one. Every other editor slot is hidden so
        # callers do not need to order active_id updates around this call.
        fid = f['id']
        for other_fid, other_slot in editor_slots.items():
            if other_fid != fid:
                try:
                    other_slot.classes(add='wb-editor-hidden')
                except Exception:
                    pass
        slot = _ensure_editor(f)
        slot.classes(remove='wb-editor-hidden')
        ed = editors[fid]
        client_state['active_id'] = fid

        # Indicate read-only files in the UI and update toolbar state.
        readonly = bool(f.get('readonly', False))
        file_name_label.set_text(f['name'] + (' 🔒' if readonly else ''))
        cm_lang = f.get('language', 'Text')
        canon = _canonical_lang(cm_lang)
        # Migrate files saved with a language that no longer exists (or with a
        # legacy id superseded by a rename) to the current stored value.
        f['language'] = canon if canon is not None else 'Text'
        cm_lang = f['language']
        if cm_lang == 'Text':
            # Plain text: clear the language extension instead of passing the
            # name 'Text' (which CodeMirror does not know) to set_language.
            ed.set_language(None)
        else:
            ed.set_language(cm_lang)
        f.setdefault('export_symbols', True)
        ui.run_javascript(f"window.__wbCurrentLang = '{cm_lang}';")
        ui.run_javascript(
            f"window.__wbHintKey = '{HINT_KEYS.get(cm_lang, 'plaintext')}';"
            f"window.__wbActiveFid = '{fid}';"
            f"window.__wbEditorId = {ed.id};"
        )
        status_lang.set_text(LANGUAGES.get(cm_lang, cm_lang))
        ui.run_javascript(f'''
            (function() {{
                var id = {ed.id};
                var attempts = 0;

                function wbFocus() {{
                    try {{
                        var el = getElement(id);
                        if (el && el.editorPromise) {{
                            el.editorPromise.then(function(v) {{ try {{ v.focus(); }} catch(e) {{}} }});
                            return true;
                        }}
                    }} catch(e) {{}}
                    return false;
                }}

                if (!wbFocus()) {{
                    var iv = setInterval(function() {{
                        if (wbFocus() || ++attempts > 60) clearInterval(iv);
                    }}, 150);
                }}

                // Re-assert focus shortly after the page settles, unless the user
                // has already moved focus somewhere else.
                setTimeout(function() {{
                    try {{
                        var a = document.activeElement;
                        if (!a || a === document.body) wbFocus();
                    }} catch(e) {{}}
                }}, 400);
            }})();
        ''')
        # Prevent editing in the editor for read-only files by attaching
        # a short-circuiting input handler directly to the CM content element
        # of THIS file's editor only.
        ui.run_javascript(f'''
            (function() {{
                try {{
                    var r = {str(readonly).lower()};
                    window.__wbActiveReadonly = r;
                    function makeHandler(){{
                        return function(e){{
                            // Block undo/redo (Cmd/Ctrl+Z/Y, Cmd/Ctrl+Shift+Z) on read-only files
                            if (e.ctrlKey || e.metaKey) {{
                                if (e.key === 'z' || e.key === 'y') {{ e.preventDefault(); e.stopPropagation(); return false; }}
                            }}
                            // Allow navigation keys but block text input and commands.
                            // F1/F2 are app shortcuts (shortcuts window / hints root)
                            // handled at the document level, so let them through.
                            var blocked = !(e.key && (e.key.startsWith('Arrow') || e.key==='Tab' || e.key==='Escape' || e.key==='F1' || e.key==='F2' || e.ctrlKey || e.metaKey));
                            if (blocked) {{ e.preventDefault(); e.stopPropagation(); return false; }}
                        }};
                    }}
                    var slot = document.getElementById('wb-edit-slot-{fid}');
                    var wrap = slot ? slot.querySelector('.cm-editor') : null;
                    if (wrap){{
                        var el = wrap.querySelector('.cm-content');
                        if (el){{
                            // Remove any previous handler
                            if (el._wbReadOnlyHandler) {{ el.removeEventListener('keydown', el._wbReadOnlyHandler, true); el.removeEventListener('beforeinput', el._wbReadOnlyHandler, true); el._wbReadOnlyHandler = null; }}
                            if (r){{
                                el._wbReadOnlyHandler = makeHandler();
                                el.addEventListener('keydown', el._wbReadOnlyHandler, true);
                                el.addEventListener('beforeinput', el._wbReadOnlyHandler, true);
                            }}
                        }}
                    }}
                }}catch(e){{}}
            }})();
        ''')
        # Disable/enable toolbar buttons for read-only files by ID
        ui.run_javascript(f"(function(){{try{{var r={str(readonly).lower()}; var rn=document.getElementById('wb-rename-btn'); if(rn) rn.disabled = r; var d=document.getElementById('wb-delete-btn'); if(d) d.disabled = r; var u=document.getElementById('wb-undo-btn'); if(u) u.disabled = r; var rr=document.getElementById('wb-redo-btn'); if(rr) rr.disabled = r; }}catch(e){{}}}})()")
        _update_export_button()
        # Let static scripts (hints.js, plugins.js) bind to the now-active editor.
        ui.run_javascript(f'''
            (function() {{
                try {{
                    window.dispatchEvent(new CustomEvent('wb-active-editor', {{ detail: '{fid}' }}));
                }} catch(e) {{}}
            }})();
        ''')

    def _on_editor_change(fid: str, value: str) -> None:
        # Autosave: persist content to storage on every edit of a writable file.
        cur = next((f for f in client_state['files'] if f['id'] == fid), None)
        if cur is not None and not cur.get('readonly'):
            cur['content'] = value
        _save_to_storage()

    def _on_language_change(language: str) -> None:
        fid = client_state['active_id']
        if not fid:
            return
        for f in client_state['files']:
            if f['id'] == fid:
                f['language'] = language
                f['name'] = _base_name(f['name']) + '.' + _ext_for_lang(language)
                file_name_label.set_text(f['name'] + (' 🔒' if f.get('readonly') else ''))
                break
        ed = editors.get(fid)
        if ed is not None:
            if language == 'Text':
                ed.set_language(None)
            else:
                ed.set_language(language)
        ui.run_javascript(f"window.__wbHintKey = '{HINT_KEYS.get(language, 'plaintext')}';")
        ui.run_javascript(f"window.__wbCurrentLang = '{language}';")
        status_lang.set_text(LANGUAGES.get(language, language))
        ui.run_javascript(f'''
            (function() {{
                try {{
                    window.dispatchEvent(new CustomEvent('wb-active-editor', {{ detail: '{fid}' }}));
                }} catch(e) {{}}
            }})();
        ''')
        _refresh_file_pool()
        _save_to_storage()
        _update_export_button()

    def _apply_editor_font(font: str) -> None:
        """Apply the chosen font to the CodeMirror editor via a CSS variable."""
        safe = f"'{font}', monospace"
        ui.run_javascript(
            f"document.documentElement.style.setProperty('--wb-editor-font', \"{safe}\");"
        )

    def _on_font_change(font: str) -> None:
        _apply_editor_font(font)
        ui.run_javascript(
            f"localStorage.setItem('wb_editor_font', '{font}');"
        )

    def _apply_editor_font_size(font_size: float) -> None:
        ui.run_javascript(f"""
            (function() {{
                // 1. Update the CSS variable for the font size
                document.documentElement.style.setProperty('--wb-editor-font-size', '{int(font_size)}px');
                // 2. Safely grab the active NiceGUI element and resolve its CodeMirror EditorView instance
                var el = getElement(window.__wbEditorId);
                if (el && el.editorPromise) {{
                    el.editorPromise.then(function(view) {{
                        if (view && typeof view.requestMeasure === 'function') {{
                            // 3. Force CodeMirror to recalculate gutter sizing
                            view.requestMeasure();
                        }}
                    }});
                }}
            }})()
        """)
        font_size_label.set_text(f'{int(font_size)}px')

    def _on_font_size_change(font_size: float) -> None:
        _apply_editor_font_size(font_size)
        ui.run_javascript(
            f"localStorage.setItem('wb_editor_font_size', '{int(font_size)}');"
        )

    # ===== Editor actions: undo/redo, download, upload =====
    def _download_current_file() -> None:
        # Determine content and filename
        if client_state['active_id']:
            target = next((f for f in client_state['files'] if f['id'] == client_state['active_id']), None)
            if target:
                content = target.get('content', '')
                filename = target.get('name', 'untitled.txt')
            else:
                content = ''
                filename = 'untitled.txt'
        else:
            content = ''
            filename = 'untitled.txt'
        # Trigger browser download
        ui.run_javascript(f"""
            (function() {{
                const content = {json.dumps(content)};
                const filename = {json.dumps(filename)};
                const blob = new Blob([content], {{type:'text/plain'}});
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url; a.download = filename;
                document.body.appendChild(a); a.click(); a.remove();
                URL.revokeObjectURL(url);
            }})()
        """)

    def _upload_file() -> None:
        # Use client-side file picker and hand the parsed file to the server via
        # the open bridge so it gets its own editor instance + dock tab.
        ui.run_javascript('''
            (function() {
                const inp = document.createElement('input');
                inp.type = 'file'; inp.accept = '*/*';
                inp.onchange = function(ev) {
                    const f = ev.target.files[0];
                    if (!f) return;
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        try {
                            var lang = 'Text';
                            var n = (f.name || '').toLowerCase();
                            if (n.endsWith('.bas')) lang = 'HitBasic';
                            else if (n.endsWith('.pas') || n.endsWith('.pp') || n.endsWith('.inc')) lang = 'Pascal';
                            else if (n.endsWith('.c') || n.endsWith('.h')) lang = 'C';
                            else if (n.endsWith('.asm') || n.endsWith('.s') || n.endsWith('.z80')) lang = 'Z80';
                            window.__wbPendingFile = { name: f.name, language: lang, content: e.target.result, export_symbols: true };
                            const br = document.getElementById('wb-open-bridge');
                            if (br) br.dispatchEvent(new CustomEvent('wb-open-file', { detail: {} }));
                            try { alert('Imported: ' + f.name); } catch(_) { console.log('Imported', f.name); }
                        } catch(err) { console.error(err); }
                    };
                    reader.readAsText(f);
                };
                inp.click();
            })();
        ''')

    # ===== Initialize from localStorage =====
    def _trigger_reset() -> None:
        """Trigger a full client-side reset (storage + caches) and reload."""
        ui.notify('Resetting editor storage and clearing caches...')
        ui.run_javascript('window.location.href = window.location.pathname + "?reset=1";')

    def _init() -> None:
        ui.run_javascript('''
            (function() {
                // Shared map of file id -> CodeMirror element id, created before
                // any editor is registered by the server.
                window.__wbEditorIds = window.__wbEditorIds || {};
                try {
                    const SCHEMA_KEY = 'wb_editor_schema_v';
                    const SCHEMA_VERSION = '2';

                    // If the URL contains ?reset=1, wipe storage and caches, then reload the whole app
                    try {
                        const params = new URLSearchParams(window.location.search || '');
                        if (params.get('reset') === '1') {
                            try {
                                ['wb_editor_files', 'wb_editor_active', 'wb_editor_schema_v',
                                 'wb_editor_font', 'wb_editor_font_size']
                                    .forEach(k => localStorage.removeItem(k));
                            } catch(e) {}
                            if (window.__wbPyBridge && window.__wbPyBridge.initDefaults) {
                                window.__wbPyBridge.initDefaults();
                            }
                            localStorage.setItem(SCHEMA_KEY, SCHEMA_VERSION);
                            // Reload only after clearing CacheStorage (service workers, etc.),
                            // with a cache-busting param so the whole app is re-fetched.
                            var reloadNow = function() {
                                try {
                                    const url = new URL(window.location.href);
                                    url.searchParams.delete('reset');
                                    url.searchParams.set('r', String(Date.now()));
                                    window.history.replaceState({}, '', url.toString());
                                } catch(e) {}
                                window.location.reload();
                            };
                            try {
                                if (window.caches && window.caches.keys) {
                                    window.caches.keys().then(function(names) {
                                        var deletes = names.map(function(n) {
                                            return window.caches.delete(n).catch(function() {});
                                        });
                                        Promise.all(deletes).then(reloadNow).catch(reloadNow);
                                    }).catch(reloadNow);
                                } else {
                                    reloadNow();
                                }
                            } catch(e) { reloadNow(); }
                            return;
                        }
                        // Strip a leftover cache-buster param from a previous reset
                        try {
                            if (params.get('r')) {
                                const url = new URL(window.location.href);
                                url.searchParams.delete('r');
                                window.history.replaceState({}, '', url.toString());
                            }
                        } catch(e) {}
                    } catch(e) {}

                    // If schema changed or missing, reinitialize client storage
                    if (localStorage.getItem(SCHEMA_KEY) !== SCHEMA_VERSION) {
                        try {
                            if (window.__wbPyBridge && window.__wbPyBridge.initDefaults) {
                                window.__wbPyBridge.initDefaults();
                            }
                        } catch(e) {}
                        localStorage.setItem(SCHEMA_KEY, SCHEMA_VERSION);
                    } else {
                        if (window.__wbPyBridge && !window.__wbPyBridge.hasFiles()) {
                            window.__wbPyBridge.initDefaults();
                        }
                    }
                } catch(e) {}
                // Do not rely on server-side callback here; storage will be read
                // when the client interacts or on subsequent syncs.

                // ===== Drag-and-drop import =====
                // Handed to the server via the open bridge; the server creates
                // the file, a dock tab and its own editor instance.
                function importFile(file, content, lang) {
                    try {
                        window.__wbPendingFile = { name: file.name, language: lang, content: content, export_symbols: true };
                        const br = document.getElementById('wb-open-bridge');
                        if (br) br.dispatchEvent(new CustomEvent('wb-open-file', { detail: {} }));
                    } catch(e) { console.warn('importFile error', e); }
                }

                document.addEventListener('dragover', function(e){ try{ e.preventDefault(); }catch(e){} }, false);
                document.addEventListener('drop', function(e){
                    try {
                        e.preventDefault();
                        const items = e.dataTransfer && e.dataTransfer.files ? e.dataTransfer.files : null;
                        if (!items || items.length === 0) return;
                        for (let i=0;i<items.length;i++) {
                            const f = items[i];
                            (function(file){
                                const reader = new FileReader();
                                reader.onload = function(ev) {
                                    try {
                                        var lang = 'Text';
                                        var n = (file.name || '').toLowerCase();
                                        if (n.endsWith('.bas')) lang='HitBasic';
                                        else if (n.endsWith('.pas') || n.endsWith('.pp') || n.endsWith('.inc')) lang='Pascal';
                                        else if (n.endsWith('.c') || n.endsWith('.h')) lang='C';
                                        else if (n.endsWith('.asm') || n.endsWith('.s') || n.endsWith('.z80')) lang='Z80';
                                        importFile(file, ev.target.result, lang);
                                    } catch(e) { console.error(e); }
                                };
                                reader.readAsText(file);
                            })(f);
                        }
                    } catch(e) { console.warn('drop handler error', e); }
                }, false);
            })()
        ''')
        # Fallback: call storage loader without client result; client storage will
        # be used by client-side code and saved back to server on changes.
        _on_storage_loaded(None)
        # Restore the saved font preference
        ui.run_javascript('''
            (function() {
                const f = localStorage.getItem('wb_editor_font') || 'Press Start 2P';
                document.documentElement.style.setProperty('--wb-editor-font', "'" + f + "', monospace");
                const fs = localStorage.getItem('wb_editor_font_size') || '13';
                document.documentElement.style.setProperty('--wb-editor-font-size', fs + 'px');
                // Map of file id -> NiceGUI element id, filled by the server as
                // editors are created. __wbEditorId is the ACTIVE editor's id.
                window.__wbEditorIds = window.__wbEditorIds || {};
                // Global undo/redo operate on the ACTIVE editor view. CodeMirror
                // keeps native per-view history, so each file (its own view)
                // gets independent undo/redo without client-side stacks.
                function wbCmDo(action) {
                    if (window.__wbActiveReadonly) return;
                    var elId = window.__wbEditorId;
                    if (!elId) return;
                    getElement(elId).editorPromise.then(function(p) {
                        try {
                            import('nicegui-codemirror').then(function(CM) {
                                try {
                                    if (action === 'undo') CM.undo(p); else CM.redo(p);
                                } catch(e) {}
                                try { p.focus(); } catch(e) {}
                            });
                        } catch(e) {}
                    });
                }
                window.__wbUndo = function() { wbCmDo('undo'); };
                window.__wbRedo = function() { wbCmDo('redo'); };
                document.addEventListener('keydown', function(e) {
                    var mod = e.ctrlKey || e.metaKey;
                    if (!mod) return;
                    if (e.key === 'z' && !e.shiftKey) {
                        // When focus is inside an editor, Let CodeMirror's own
                        // keymap handle undo natively (per-view history). The
                        // global fallback only covers focus on toolbar controls.
                        if (e.target && e.target.closest && e.target.closest('.cm-editor')) return;
                        e.preventDefault();
                        window.__wbUndo();
                    } else if (e.key === 'y' || (e.key === 'z' && e.shiftKey)) {
                        if (e.target && e.target.closest && e.target.closest('.cm-editor')) return;
                        e.preventDefault();
                        window.__wbRedo();
                    }
                });
            })()
        ''')
        # Settings menu (favicon button): WRAP toggle plus a PLUGINS submenu
        # that enables/disables the installed plugins individually.
        ui.run_javascript('''
            (function() {
                function setupSettingsMenu() {
                    var btn = document.getElementById('wb-settings-btn');
                    if (!btn || (window.WBPlugins && !window.WBPlugins.list)) return false;
                    if (btn._wbSettingsMenu) return true;
                    btn._wbSettingsMenu = true;

                    var menu = document.createElement('div');
                    menu.id = 'wb-settings-menu';
                    menu.className = 'wb-settings-menu';
                    menu.style.display = 'none';
                    menu.tabIndex = -1;
                    (btn.closest('.wb-app-header') || document.body).appendChild(menu);

                    var title = document.createElement('div');
                    title.className = 'wb-settings-title';
                    title.textContent = 'SETTINGS';
                    menu.appendChild(title);

                    function closeSubmenu() {
                        submenu.style.display = 'none';
                        pluginsRow.classList.remove('active');
                    }
                    function toggleSubmenu() {
                        if (submenu.style.display === 'block') closeSubmenu();
                        else {
                            rebuildPlugins();
                            submenu.style.display = 'block';
                            pluginsRow.classList.add('active');
                        }
                    }

                    // "PLUGINS" row -> opens the plugins submenu.
                    var pluginsRow = document.createElement('div');
                    pluginsRow.id = 'wb-settings-plugins';
                    pluginsRow.className = 'wb-settings-row';
                    pluginsRow.tabIndex = 0;
                    pluginsRow.setAttribute('role', 'button');
                    var pluginsLabel = document.createElement('span');
                    pluginsLabel.className = 'wb-settings-row-label';
                    pluginsLabel.textContent = 'PLUGINS';
                    var arrow = document.createElement('span');
                    arrow.className = 'wb-settings-arrow';
                    arrow.textContent = '>';
                    pluginsRow.appendChild(pluginsLabel);
                    pluginsRow.appendChild(arrow);
                    pluginsRow.addEventListener('click', function(ev) {
                        ev.stopPropagation();
                        toggleSubmenu();
                    });
                    menu.appendChild(pluginsRow);

                    // "WRAP" row -> toggles word wrap for every editor.
                    var wrapRow = document.createElement('div');
                    wrapRow.id = 'wb-settings-wrap';
                    wrapRow.className = 'wb-settings-row';
                    wrapRow.tabIndex = 0;
                    wrapRow.setAttribute('role', 'button');
                    var wrapLabel = document.createElement('span');
                    wrapLabel.className = 'wb-settings-row-label';
                    wrapLabel.textContent = 'WRAP';
                    var wrapValue = document.createElement('span');
                    wrapValue.className = 'wb-settings-value';
                    wrapRow.appendChild(wrapLabel);
                    wrapRow.appendChild(wrapValue);

                    function wrapIsOn() {
                        try { return !!window.WBStorage.loadConfig().wrap; } catch(e) { return false; }
                    }
                    function applyWrap() {
                        var on = wrapIsOn();
                        var ids = window.__wbEditorIds || {};
                        Object.keys(ids).forEach(function(fid) {
                            var el = getElement(ids[fid]);
                            if (el && typeof el.setLineWrapping === 'function') {
                                el.setLineWrapping(on);
                            }
                        });
                        // Do not use .active here: that is the orange hover /
                        // open-flyout highlight. Wrap state shows in the value.
                        wrapValue.classList.toggle('on', on);
                        wrapValue.textContent = on ? 'ON' : 'OFF';
                    }
                    wrapRow.addEventListener('click', function(ev) {
                        ev.stopPropagation();
                        try {
                            var cfg = window.WBStorage.loadConfig();
                            cfg.wrap = !cfg.wrap;
                            window.WBStorage.saveConfig(cfg);
                            applyWrap();
                        } catch(e) { console.warn('settings wrap toggle failed', e); }
                    });
                    menu.appendChild(wrapRow);
                    applyWrap();

                    // Re-assert wrapping whenever the server activates an editor.
                    window.addEventListener('wb-active-editor', function() {
                        try { applyWrap(); } catch(e) {}
                    });

                    // "LIGATURES" row -> toggles font ligatures for every editor.
                    // Off by default (retro fonts draw ugly "fi" pairs).
                    var ligatureRow = document.createElement('div');
                    ligatureRow.id = 'wb-settings-ligatures';
                    ligatureRow.className = 'wb-settings-row';
                    ligatureRow.tabIndex = 0;
                    ligatureRow.setAttribute('role', 'button');
                    var ligatureLabel = document.createElement('span');
                    ligatureLabel.className = 'wb-settings-row-label';
                    ligatureLabel.textContent = 'LIGATURES';
                    var ligatureValue = document.createElement('span');
                    ligatureValue.className = 'wb-settings-value';
                    ligatureRow.appendChild(ligatureLabel);
                    ligatureRow.appendChild(ligatureValue);

                    function ligaturesOn() {
                        try { return !!window.WBStorage.loadConfig().ligatures; } catch(e) { return false; }
                    }
                    function applyLigatures() {
                        var on = ligaturesOn();
                        document.querySelectorAll('.cm-editor .cm-content').forEach(function(el) {
                            if (on) {
                                el.style.fontVariantLigatures = 'common-ligatures';
                                el.style.fontFeatureSettings = '"liga" 1, "clig" 1';
                            } else {
                                el.style.fontVariantLigatures = 'no-common-ligatures';
                                el.style.fontFeatureSettings = '"liga" 0, "clig" 0';
                            }
                        });
                        ligatureValue.classList.toggle('on', on);
                        ligatureValue.textContent = on ? 'ON' : 'OFF';
                    }
                    ligatureRow.addEventListener('click', function(ev) {
                        ev.stopPropagation();
                        try {
                            var cfg = window.WBStorage.loadConfig();
                            cfg.ligatures = !cfg.ligatures;
                            window.WBStorage.saveConfig(cfg);
                            applyLigatures();
                        } catch(e) { console.warn('settings ligatures toggle failed', e); }
                    });
                    menu.appendChild(ligatureRow);
                    applyLigatures();

                    // Re-assert ligatures whenever the server activates an editor.
                    window.addEventListener('wb-active-editor', function() {
                        try { applyLigatures(); } catch(e) {}
                    });

                    // "FOLD" row -> toggles code folding for every editor.
                    // On by default: the bundled CodeMirror basics already ship
                    // a fold gutter and Ctrl-Shift-[ / Ctrl-Shift-] fold keys.
                    var foldRow = document.createElement('div');
                    foldRow.id = 'wb-settings-fold';
                    foldRow.className = 'wb-settings-row';
                    foldRow.tabIndex = 0;
                    foldRow.setAttribute('role', 'button');
                    var foldLabel = document.createElement('span');
                    foldLabel.className = 'wb-settings-row-label';
                    foldLabel.textContent = 'FOLD';
                    var foldValue = document.createElement('span');
                    foldValue.className = 'wb-settings-value';
                    foldRow.appendChild(foldLabel);
                    foldRow.appendChild(foldValue);

                    // Keybindings the foldKeymap ships with in this bundle.
                    var FOLD_KEYS = [
                        'Ctrl-Shift-[', 'Ctrl-Shift-]', 'Ctrl-Alt-[', 'Ctrl-Alt-]'
                    ];
                    function foldIsOn() {
                        // Folding ships enabled; only an explicit 'false' turns it off.
                        try { return window.WBStorage.loadConfig().fold !== false; } catch(e) { return true; }
                    }
                    function foldBlockers(CM) {
                        return [
                            CM.EditorView.theme({
                                '.cm-gutter.cm-foldGutter, .cm-foldPlaceholder': { display: 'none !important' }
                            }),
                            CM.Prec.high(CM.keymap.of(FOLD_KEYS.map(function(key) {
                                return { key: key, run: function() { return true; } };
                            })))
                        ];
                    }
                    function applyFold() {
                        var on = foldIsOn();
                        foldValue.classList.toggle('on', on);
                        foldValue.textContent = on ? 'ON' : 'OFF';
                        var ids = window.__wbEditorIds || {};
                        Object.keys(ids).forEach(function(fid) {
                            var el = getElement(ids[fid]);
                            if (!el || !el.editorPromise) return;
                            el.editorPromise.then(function(view) {
                                return import('nicegui-codemirror').then(function(CM) {
                                    var effects = [];
                                    if (on) {
                                        if (view._wbFoldCompartment) {
                                            effects.push(view._wbFoldCompartment.reconfigure([]));
                                        }
                                    } else {
                                        try { CM.unfoldAll(view.state, view.dispatch); } catch(e) {}
                                        if (!view._wbFoldCompartment) {
                                            view._wbFoldCompartment = new CM.Compartment();
                                            effects.push(CM.StateEffect.appendConfig.of([
                                                view._wbFoldCompartment.of(foldBlockers(CM))
                                            ]));
                                        } else {
                                            effects.push(view._wbFoldCompartment.reconfigure(foldBlockers(CM)));
                                        }
                                    }
                                    if (effects.length) view.dispatch({ effects: effects });
                                });
                            }).catch(function(e) {
                                console.warn('settings fold toggle failed', e);
                            });
                        });
                    }
                    foldRow.addEventListener('click', function(ev) {
                        ev.stopPropagation();
                        try {
                            var cfg = window.WBStorage.loadConfig();
                            cfg.fold = !foldIsOn();
                            window.WBStorage.saveConfig(cfg);
                            applyFold();
                        } catch(e) { console.warn('settings fold toggle failed', e); }
                    });
                    menu.appendChild(foldRow);
                    applyFold();

                    // Re-assert folding whenever the server activates an editor.
                    window.addEventListener('wb-active-editor', function() {
                        try { applyFold(); } catch(e) {}
                    });

                    // Plugins submenu (a panel beside the settings menu).
                    var submenu = document.createElement('div');
                    submenu.id = 'wb-plugins-menu';
                    submenu.className = 'wb-plugins-menu';
                    submenu.style.display = 'none';
                    menu.appendChild(submenu);

                    var subTitle = document.createElement('div');
                    subTitle.className = 'wb-plugins-title';
                    subTitle.textContent = 'PLUGINS';
                    submenu.appendChild(subTitle);
                    var hint = document.createElement('div');
                    hint.className = 'wb-plugins-hint';
                    hint.textContent = 'changes reload the editor';
                    submenu.appendChild(hint);

                    function rebuildPlugins() {
                        submenu.querySelectorAll('.wb-plugin-row').forEach(function(r) { r.remove(); });
                        var defs = window.WBPlugins.list();
                        if (!defs.length) {
                            var empty = document.createElement('div');
                            empty.className = 'wb-plugin-empty';
                            empty.textContent = '(no plugins installed)';
                            submenu.appendChild(empty);
                            return;
                        }
                        defs.forEach(function(def) {
                            var row = document.createElement('label');
                            row.className = 'wb-plugin-row';
                            var name = document.createElement('span');
                            name.className = 'wb-plugin-name';
                            name.textContent = def.name;
                            var cb = document.createElement('input');
                            cb.type = 'checkbox';
                            cb.className = 'wb-plugin-check';
                            cb.checked = !!window.WBPlugins._enabled(def);
                            cb.addEventListener('change', function() {
                                try {
                                    var cfg = window.WBStorage.loadConfig();
                                    cfg.plugins = cfg.plugins || {};
                                    cfg.plugins[def.name] = cb.checked;
                                    window.WBStorage.saveConfig(cfg);
                                    clearTimeout(menu._reloadT);
                                    menu._reloadT = setTimeout(function() {
                                        window.location.reload();
                                    }, 300);
                                } catch(e) { console.warn('plugins toggle failed', e); }
                            });
                            row.appendChild(name);
                            row.appendChild(cb);
                            submenu.appendChild(row);
                        });
                    }

                    function position() {
                        var r = btn.getBoundingClientRect();
                        menu.style.left = r.right + 'px';
                        menu.style.top = (r.bottom + 6) + 'px';
                        var w = menu.offsetWidth;
                        if (r.right - w >= 0) menu.style.left = (r.right - w) + 'px';
                    }

                    function settingsRows() {
                        return Array.prototype.slice.call(
                            menu.querySelectorAll('.wb-settings-row'));
                    }
                    function clearRowFocus() {
                        settingsRows().forEach(function(r) { r.classList.remove('keyboard'); });
                    }
                    function focusRow(delta) {
                        var rows = settingsRows();
                        if (!rows.length) return;
                        var idx = rows.indexOf(menu.querySelector('.wb-settings-row.keyboard'));
                        var next = idx < 0 ? (delta > 0 ? 0 : rows.length - 1) : idx + delta;
                        if (next < 0) next = rows.length - 1;
                        if (next >= rows.length) next = 0;
                        clearRowFocus();
                        rows[next].classList.add('keyboard');
                    }
                    function restoreEditorFocus() {
                        try {
                            var c = document.querySelector(
                                '.wb-editor-slot:not(.wb-editor-hidden) .cm-content');
                            if (c) c.focus();
                        } catch(e) {}
                    }

                    function open() {
                        applyWrap();
                        clearRowFocus();
                        menu.style.display = 'block';
                        position();
                        btn.classList.add('active');
                        try { menu.focus({ preventScroll: true }); } catch(e) { menu.focus(); }
                    }
                    function close() {
                        closeSubmenu();
                        clearRowFocus();
                        menu.style.display = 'none';
                        btn.classList.remove('active');
                        restoreEditorFocus();
                    }

                    btn.addEventListener('click', function(ev) {
                        ev.stopPropagation();
                        if (menu.style.display === 'block') close(); else open();
                    });
                    document.addEventListener('click', function(ev) {
                        if (menu.style.display === 'block' && !menu.contains(ev.target)) close();
                    });
                    document.addEventListener('keydown', function(ev) {
                        if (menu.style.display !== 'block') return;
                        if (ev.key === 'Escape') { close(); return; }
                        if (ev.key === 'ArrowDown') { ev.preventDefault(); focusRow(1); }
                        else if (ev.key === 'ArrowUp') { ev.preventDefault(); focusRow(-1); }
                        else if (ev.key === 'Enter' || ev.key === ' ') {
                            var cur = menu.querySelector('.wb-settings-row.keyboard');
                            if (cur) { ev.preventDefault(); cur.click(); }
                        }
                    });

                    // Ctrl+Space opens/closes the SETTINGS menu from anywhere.
                    document.addEventListener('keydown', function(ev) {
                        if ((ev.ctrlKey || ev.metaKey) && (ev.key === ' ' || ev.code === 'Space')) {
                            ev.preventDefault();
                            if (menu.style.display === 'block') close(); else open();
                        }
                    });

                    // F1 opens the Shortcut window from anywhere.
                    document.addEventListener('keydown', function(ev) {
                        if (ev.key === 'F1') {
                            ev.preventDefault();
                            var s = document.getElementById('wb-shortcut-btn');
                            if (s && s.click) s.click();
                        }
                    });

                    return true;
                }

                var _attempts = 0;
                var _iv = setInterval(function() {
                    if (setupSettingsMenu() || ++_attempts > 50) clearInterval(_iv);
                }, 200);
            })()
        ''')
        # Give focus back to the editor after toolbar button clicks so the user
        # can keep typing. Rename/Delete open dialogs with their own focus, so
        # they are excluded.
        ui.run_javascript('''
            (function() {
                window.wbRefocusEditor = function() {
                    try {
                        var elId = window.__wbEditorId;
                        if (!elId) return false;
                        var el = getElement(elId);
                        if (el && el.editorPromise) {
                            el.editorPromise.then(function(v) { try { v.focus(); } catch(e) {} });
                            return true;
                        }
                    } catch(e) {}
                    return false;
                };
                document.addEventListener('click', function(e) {
                    try {
                        var t = e.target && e.target.closest ? e.target.closest('button') : null;
                        if (!t) return;
                        var id = t.id || '';
                        if (id === 'wb-rename-btn' || id === 'wb-delete-btn') return;
                        window.wbRefocusEditor();
                    } catch(e) {}
                }, true);
            })();
        ''')

    def _on_storage_loaded(result: Any) -> None:
        try:
            if result is None:
                data = {'files': [], 'active': None}
            else:
                data = json.loads(result) if isinstance(result, str) else result
        except (json.JSONDecodeError, TypeError):
            data = {'files': [], 'active': None}
        client_state['files'] = data.get('files', [])
        client_state['active_id'] = data.get('active')

        # Migrate files that carry a language no longer offered by the editor
        # (e.g. saved as Python or Markdown) to plain text, and legacy ids
        # (e.g. "VBScript") to their renamed value.
        for f in client_state['files']:
            canon = _canonical_lang(f.get('language'))
            f['language'] = canon if canon is not None else 'Text'

        # If there are no files in storage, create a starter file so the UI
        # shows an initial file next to the '+ NEW' button and loads it into
        # the editor. Persist to client storage so page reloads keep it.
        if not client_state['files']:
            import random
            # Read the startup file so the initial file can be edited directly
            # on disk (STARTUP.txt in the repository root).
            readme_path = Path(__file__).resolve().parents[1] / 'STARTUP.txt'
            try:
                readme_content = readme_path.read_text(encoding='utf-8')
            except (OSError, UnicodeDecodeError):
                readme_content = (
                    '# Myslyx Text Editor\n\n'
                    'Welcome to Myslyx Text Editor.\n'
                    'Edit STARTUP.txt in the project folder to customize this page.\n'
                )
            # Only create a single INITIAL starter file and make it active (read-only)
            fid_readme = f'file_{random.randint(100000, 999999)}'
            starter_readme = {
                'id': fid_readme,
                'name': 'STARTUP.txt',
                'language': 'Text',
                'content': readme_content,
                'undos': [],
                'redos': [],
                'readonly': True,
                'export_symbols': True,
            }
            client_state['files'] = [starter_readme]
            client_state['active_id'] = starter_readme['id']

        _refresh_file_pool()

        # Load the active file into the editor if present
        if client_state['files'] and client_state['active_id']:
            target = next(
                (f for f in client_state['files'] if f['id'] == client_state['active_id']),
                client_state['files'][0],
            )
            client_state['active_id'] = target['id']
            _load_file_into_editor(target)

        # Ensure server-side state is persisted to client localStorage so the
        # newly created starter file remains available on subsequent loads.
        _save_to_storage()

    ui.timer(0.8, _init, once=True)

    # ===== Shortcuts dialog =====
    shortcut_dialog = ui.dialog()
    with shortcut_dialog:
        with ui.element('div').classes('wb-dialog'):
            with ui.element('div').classes('wb-title-bar'):
                ui.label('Keyboard Shortcuts').classes('title-text')
            with ui.element('div').classes('wb-dialog-body'):
                ui.table(
                    columns=[
                        {'name': 'keys', 'label': 'Shortcut', 'field': 'keys', 'align': 'left'},
                        {'name': 'action', 'label': 'Action', 'field': 'action', 'align': 'left'},
                    ],
                    rows=[
                        {'keys': 'Ctrl+C', 'action': 'Copy'},
                        {'keys': 'Ctrl+V', 'action': 'Paste'},
                        {'keys': 'Ctrl+Z', 'action': 'Undo'},
                        {'keys': 'Ctrl+Y', 'action': 'Redo'},
                        {'keys': 'Ctrl++', 'action': 'Increase font size'},
                        {'keys': 'Ctrl+-', 'action': 'Decrease font size'},
                        {'keys': 'Ctrl+Space', 'action': 'Open SETTINGS menu'},
                        {'keys': 'Ctrl+/', 'action': 'Toggle comment (HitBasic, Pascal, C)'},
                        {'keys': 'F1', 'action': 'Open shortcuts window'},
                        {'keys': 'F2', 'action': 'Reload hints root page'},
                        {'keys': 'F5', 'action': 'Refresh editor'},
                    ],
                    row_key='keys',
                ).classes('wb-shortcuts-table').style('width:100%;')
            with ui.element('div').classes('wb-dialog-buttons'):
                ui.button('Close', on_click=lambda: shortcut_dialog.close()).classes('wb-button')

    def _open_shortcut_dialog() -> None:
        shortcut_dialog.open()

    # ===== Rename dialog =====
    rename_dialog = ui.dialog()
    with rename_dialog:
        with ui.element('div').classes('wb-dialog'):
            with ui.element('div').classes('wb-title-bar'):
                ui.label('Rename current file').classes('title-text')
            with ui.element('div').classes('wb-dialog-body'):
                rename_input = ui.input(label='New file name').props('id=wb-rename-input')
            with ui.element('div').classes('wb-dialog-buttons'):
                ui.button('Cancel', on_click=lambda: rename_dialog.close()).classes('wb-button')
                ui.button('OK', on_click=lambda: _confirm_rename()).classes('wb-button')

    def _open_rename_dialog() -> None:
        if not client_state['active_id']:
            return
        target = next((f for f in client_state['files'] if f['id'] == client_state['active_id']), None)
        if not target:
            return
        rename_input.set_value(target.get('name', ''))
        rename_dialog.open()
        # focus the input inside the dialog after a short delay
        ui.run_javascript("setTimeout(function(){const el=document.getElementById('wb-rename-input'); if (el) { const inp = el.querySelector('input'); if (inp) inp.focus(); } }, 50);")

    def _confirm_rename() -> None:
        val = rename_input.value.strip() if hasattr(rename_input, 'value') else None
        if not val:
            rename_dialog.close()
            return
        if client_state['active_id']:
            for f in client_state['files']:
                if f['id'] == client_state['active_id']:
                    f['name'] = val
                    break
        file_name_label.set_text(val)
        _refresh_file_pool()
        _save_to_storage()
        rename_dialog.close()

    # ===== Delete dialog (shared by the DELETE button and the dock X buttons) =====
    _pending_delete_fid: str | None = None
    delete_dialog = ui.dialog()
    with delete_dialog:
        with ui.element('div').classes('wb-dialog'):
            with ui.element('div').classes('wb-title-bar'):
                ui.label('Delete file?').classes('title-text')
            with ui.element('div').classes('wb-dialog-body'):
                delete_prompt = ui.label('This will permanently remove the file from the file pool.').style('white-space:pre-line;')
            with ui.element('div').classes('wb-dialog-buttons'):
                ui.button('Cancel', on_click=lambda: _cancel_delete()).classes('wb-button')
                ui.button('Delete', on_click=lambda: _confirm_delete()).classes('wb-button')

    def _open_delete_dialog() -> None:
        _request_close_file(client_state['active_id'])

    def _request_close_file(fid: str | None) -> None:
        nonlocal _pending_delete_fid
        if not fid:
            return
        target = next((f for f in client_state['files'] if f['id'] == fid), None)
        if target and not (target.get('content') or '').strip():
            # A blank, unedited file can be dropped without confirmation.
            _close_file(fid)
            return
        _pending_delete_fid = fid
        if target:
            delete_prompt.set_text(f'Delete "{target["name"]}"?\n\nThis will permanently remove it from the file pool.')
        else:
            delete_prompt.set_text('This will permanently remove the file from the file pool.')
        delete_dialog.open()

    def _cancel_delete() -> None:
        nonlocal _pending_delete_fid
        delete_dialog.close()
        _pending_delete_fid = None

    def _confirm_delete() -> None:
        nonlocal _pending_delete_fid
        fid = _pending_delete_fid
        delete_dialog.close()
        _pending_delete_fid = None
        if fid:
            _close_file(fid)

    # ===== RESET FILE POOL dialog =====
    reset_dialog = ui.dialog()
    with reset_dialog:
        with ui.element('div').classes('wb-dialog'):
            with ui.element('div').classes('wb-title-bar'):
                ui.label('Reset file pool?').classes('title-text')
            with ui.element('div').classes('wb-dialog-body'):
                reset_prompt = ui.label(
                    'This will delete every file in the pool, clear the editor storage, '
                    'and reload the whole app.\n\nThis cannot be undone.'
                ).style('white-space:pre-line;')
            with ui.element('div').classes('wb-dialog-buttons'):
                ui.button('Cancel', on_click=lambda: _cancel_reset()).classes('wb-button')
                ui.button('Reset', on_click=lambda: _confirm_reset()).classes('wb-button')

    def _open_reset_dialog() -> None:
        reset_dialog.open()

    def _cancel_reset() -> None:
        reset_dialog.close()

    def _confirm_reset() -> None:
        reset_dialog.close()
        _trigger_reset()
