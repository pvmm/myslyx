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

# Default language for newly created files. The LANG combo box mirrors the
# language of the currently visible file (see _load_file_into_editor), so
# new files keep this fixed default instead of inheriting the active file's.
DEFAULT_LANG = 'HitBasic'

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
    'HitBasic': 'hitbasic',
    'Pascal': 'pascal',
    'C': 'c',
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
    ui.add_head_html('<script src="/static/storage-bridge.js"></script>')
    ui.add_head_html('<script src="/static/retro.js"></script>')
    ui.add_head_html('<script src="/static/vendor/marked.min.js"></script>')
    ui.add_head_html('<script src="/static/hints.js"></script>')
    ui.add_head_html('<script src="/static/plugins.js"></script>')
    ui.add_head_html('<script src="/static/folding.js"></script>')
    ui.add_head_html('<script src="/static/editor-init.js"></script>')
    ui.add_head_html('<script src="/static/editor-upload.js"></script>')
    ui.add_head_html('<script src="/static/editor-keyboard.js"></script>')
    ui.add_head_html('<script src="/static/settings-menu.js"></script>')
    ui.add_head_html('<script src="/static/editor-toolbar.js"></script>')
    ui.add_head_html('<script src="/static/shortcuts.js"></script>')
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
                        value=DEFAULT_LANG,
                        on_change=lambda e: _on_language_change(e.value),
                    )
                    .classes('wb-select')
                    .props('id=wb-lang-select')
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
                    ui.button('UPLOAD', on_click=lambda: _upload_file()).classes('wb-button').props('id=wb-upload-btn')
                    ui.button('DOWNLOAD', on_click=lambda: _download_current_file()).classes('wb-button').props('id=wb-download-btn')
                # Download the whole file pool as a single zip, unstacked.
                download_all_btn = ui.button('DOWNLOAD\nALL', on_click=lambda: _download_all_files()).classes('wb-button').props('id=wb-download-all-btn')
                # separator between DOWNLOAD ALL and RESET FILE POOL
                ui.element('div').style('width:2px;height:20px;background:var(--wb-black);align-self:center;margin:0 6px;')
                with download_all_btn:
                    # Nest the tooltip (the id override makes Quasar log an
                    # 'Anchor not found' warning for unattached tooltips).
                    ui.tooltip('Download every file in the pool as a single .zip')
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
            ui.button('+ NEW', on_click=lambda: _new_file()).classes('wb-new-file').props('id=wb-new-file-btn')

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
        lang = DEFAULT_LANG
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
        # _load_file_into_editor asks the hints panel to open this language's
        # root page after the new file's editor becomes active.
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
        # Keep the toolbar LANG combo in sync with the file being shown. The
        # value matches the file's language, so _on_language_change no-ops.
        lang_select.set_value(cm_lang)
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
        ui.run_javascript(f'window.WBSetReadonly.apply({str(readonly).lower()});')
        _update_export_button()
        # Let static scripts (hints.js, plugins.js) bind to the now-active
        # editor and have the hints panel open this file's language root page.
        ui.run_javascript(f'''
            (function() {{
                try {{
                    window.__wbPendingRoot = true;
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
        target = next((f for f in client_state['files'] if f['id'] == fid), None)
        if target is None:
            return
        # Read-only files (e.g. the bundled STARTUP.txt) keep their language.
        # The combo is locked client-side too, but guard the handler anyway.
        if target.get('readonly'):
            lang_select.set_value(target['language'])
            return
        # The LANG combo is synced programmatically whenever a file is
        # activated; if it already matches this file, the on_change is a
        # no-op so we do not rename/reconfigure a file just for showing it.
        if target['language'] == language:
            return
        new_name = _base_name(target['name']) + '.' + _ext_for_lang(language)
        if any(f['id'] != fid and f['name'] == new_name for f in client_state['files']):
            _start_lang_clash_resolution(target, language)
            return
        _apply_language_change(fid, language, None)

    def _apply_language_change(fid: str, language: str, name: str | None) -> None:
        """Apply a language switch (and optional explicit new filename)."""
        target = next((f for f in client_state['files'] if f['id'] == fid), None)
        if target is None:
            return
        target['language'] = language
        target['name'] = name or (_base_name(target['name']) + '.' + _ext_for_lang(language))
        file_name_label.set_text(target['name'] + (' 🔒' if target.get('readonly') else ''))
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
                    window.__wbPendingRoot = true;
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

    def _download_all_files() -> None:
        # Zip every editable (non-locked) file in the pool and stream it to
        # the browser. Locked files (e.g. the read-only STARTUP.txt) are
        # excluded. Duplicate member names (the pool does not enforce
        # uniqueness) get a numeric suffix before the extension so no entry
        # overwrites another.
        from io import BytesIO
        import zipfile
        editable = [f for f in client_state['files'] if not f.get('readonly')]
        if not editable:
            return
        buf = BytesIO()
        seen: dict[str, int] = {}
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in editable:
                name = f.get('name') or 'untitled.txt'
                count = seen.get(name, 0)
                seen[name] = count + 1
                if count:
                    stem, dot, ext = name.rpartition('.')
                    name = f'{stem} ({count + 1}){dot}{ext}' if dot else f'{name} ({count + 1})'
                zf.writestr(name, f.get('content', ''))
        ui.download(buf.getvalue(), 'myslyx-files.zip')

    def _upload_file() -> None:
        # Use client-side file picker and hand the parsed file to the server via
        # the open bridge so it gets its own editor instance + dock tab.
        ui.run_javascript('window.WBFileImport.run();')

    # ===== Initialize from localStorage =====
    def _trigger_reset() -> None:
        """Trigger a full client-side reset (storage + caches) and reload."""
        ui.notify('Resetting editor storage and clearing caches...')
        ui.run_javascript('window.location.href = window.location.pathname + "?reset=1";')

    def _init() -> None:
        ui.run_javascript('window.WBEditorBoot.run();')
        # Ask the client to push its localStorage file pool back to the server
        # so server state matches what the browser owns.  The bridge (below)
        # forwards it into _on_storage_loaded.  This keeps a user's files
        # intact across reloads (e.g. toggling a plugin in the Settings menu)
        # instead of overwriting them with a fresh starter file.
        ui.run_javascript(
            "const el = document.getElementById('wb-storage-sync-bridge');"
            "if (el) el.dispatchEvent(new CustomEvent('wb-storage-sync', { detail: {} }));"
        )
        ui.run_javascript('window.WBEditorKeyboard.install();')
        ui.run_javascript('window.WBShortcuts.install();')
        ui.run_javascript('window.WBSettingsMenu.install();')

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

    # Hidden bridge for client->server file pool sync.  The client owns the
    # source of truth (localStorage); on page load it pushes its pool here so
    # the server adopts it.  Mirrors the wb-open-bridge pattern above.
    _storage_sync_done = {'done': False}

    def _on_storage_sync(e) -> None:
        if _storage_sync_done['done']:
            return
        _storage_sync_done['done'] = True
        _on_storage_loaded(e.args)

    ui.element('div').props('id=wb-storage-sync-bridge').style('display:none;').on(
        'wb-storage-sync',
        _on_storage_sync,
        js_handler="() => window.WBStorageSync.emitFiles(emit)",
    )

    ui.timer(0.8, _init, once=True)

    # Safety net: if the bridge never fires (e.g. client storage broken),
    # fall back to the previous behavior of creating the README starter file.
    def _storage_sync_fallback() -> None:
        if not _storage_sync_done['done']:
            _storage_sync_done['done'] = True
            _on_storage_loaded(None)

    ui.timer(2.5, _storage_sync_fallback, once=True)

    # ===== Shortcuts dialog =====
    shortcut_dialog = ui.dialog()
    with shortcut_dialog:
        with ui.element('div').classes('wb-dialog wb-shortcut-dialog'):
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
                        {'keys': 'Ctrl+,', 'action': 'Open SETTINGS menu'},
                        {'keys': 'Ctrl+/', 'action': 'Toggle code comment'},
                        {'keys': 'Ctrl+Shift+[', 'action': 'Fold block'},
                        {'keys': 'Ctrl+Shift+]', 'action': 'Unfold block'},
                        {'keys': 'F1', 'action': 'Open shortcuts window'},
                        {'keys': 'F2', 'action': 'Reload hints root page'},
                        {'keys': 'F5', 'action': 'Refresh editor'},
                        {'keys': 'Ctrl+Alt+E', 'action': 'Toggle EXPORT SYMBOLS'},
                        {'keys': 'Ctrl+Alt+R', 'action': 'Rename current file'},
                        {'keys': 'Ctrl+Alt+U', 'action': 'Upload file'},
                        {'keys': 'Ctrl+Alt+D', 'action': 'Download current file'},
                        {'keys': 'Ctrl+Alt+X', 'action': 'Delete current file'},
                        {'keys': 'Ctrl+Alt+N', 'action': 'Create a new file'},
                        {'keys': 'Ctrl+Alt+[', 'action': 'Previous file in pool'},
                        {'keys': 'Ctrl+Alt+]', 'action': 'Next file in pool'},
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
        ui.run_javascript('window.WBFocusInput.focus("wb-rename-input");')

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

    # ===== LANG-clash dialog =====
    # Changing a file's LANG derives a new filename; if another file already
    # has that name, ask the user to pick a different base name until the new
    # name no longer clashes (or Cancel aborts the language change).
    _clash_state: dict = {}

    lang_clash_dialog = ui.dialog().props('persistent')
    with lang_clash_dialog:
        with ui.element('div').classes('wb-dialog'):
            with ui.element('div').classes('wb-title-bar'):
                ui.label('File name clash').classes('title-text')
            with ui.element('div').classes('wb-dialog-body'):
                clash_prompt = ui.label('').style('white-space:pre-line;').props('id=wb-clash-prompt')
                clash_input = ui.input(label='New base name').props('id=wb-clash-input')
            with ui.element('div').classes('wb-dialog-buttons'):
                ui.button('Cancel', on_click=lambda: _cancel_lang_clash()).classes('wb-button')
                ui.button('OK', on_click=lambda: _confirm_lang_clash()).classes('wb-button')

    def _start_lang_clash_resolution(target: dict, language: str) -> None:
        ext = _ext_for_lang(language)
        clash_name = _base_name(target['name']) + '.' + ext
        _clash_state.update({'fid': target['id'], 'language': language, 'ext': ext})
        clash_prompt.set_text(
            f'{clash_name} is already used by another file.\n'
            f'Choose a different base name for {target["name"]} so it can be '
            f'renamed to a {LANGUAGES.get(language, language)} file.')
        clash_input.set_value(_base_name(target['name']))
        lang_clash_dialog.open()
        ui.run_javascript('window.WBFocusInput.focus("wb-clash-input");')

    def _confirm_lang_clash() -> None:
        base = clash_input.value.strip() if hasattr(clash_input, 'value') else None
        fid = _clash_state.get('fid')
        language = _clash_state.get('language')
        ext = _clash_state.get('ext')
        if not base or not fid or not language or not ext:
            lang_clash_dialog.close()
            return
        cand = _base_name(base) + '.' + ext
        if any(f['id'] != fid and f['name'] == cand for f in client_state['files']):
            # Still clashing: keep asking until the name is free.
            clash_prompt.set_text(
                f'{cand} is still in use. Please pick another base name.')
            clash_input.set_value(_base_name(base))
            ui.run_javascript('window.WBFocusInput.focus("wb-clash-input");')
            return
        if client_state['active_id'] != fid:
            # The user switched to another file while the dialog was open; the
            # combo is synced to that file, so do not touch it.
            lang_clash_dialog.close()
            return
        lang_clash_dialog.close()
        _apply_language_change(fid, language, _base_name(base) + '.' + ext)

    def _cancel_lang_clash() -> None:
        fid = _clash_state.get('fid')
        lang_clash_dialog.close()
        if client_state['active_id'] != fid:
            return
        # Revert the combo to the file's actual (unchanged) language.
        target = next((f for f in client_state['files'] if f['id'] == fid), None)
        if target is not None:
            lang_select.set_value(target['language'])

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
