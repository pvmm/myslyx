import json
from pathlib import Path
from typing import Any
from nicegui import ui


FAVICON_PATH = str(Path(__file__).resolve().parents[1] / 'static' / 'favicon.svg')

# Language options. Keys are the values stored with files (CodeMirror language
# names), values are the labels shown in the dropdown.
LANGUAGES: dict[str, str] = {
    # HitBasic is a BASIC dialect, so use CodeMirror's BASIC (VBScript) highlighter.
    'VBScript': 'HitBasic',
    'Text': 'Text',
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


def _autocomplete_inject_js(hints_content_id: str) -> str:
    """Return JS that injects a custom autocomplete overlay for CodeMirror 6
    and wires up the hints panel to update on cursor changes."""
    return '''
    (function() {
        /* ===== CM6 EditorView finder ===== */
        function getCmView() {
            const el = document.querySelector('.cm-editor');
            if (!el) return null;
            return el.cmView ? el.cmView.view : null;
        }

        /* ===== Autocomplete popup state ===== */
        let popup = null;
        let popupItems = [];
        let popupIndex = 0;

        function removePopup() {
            if (popup) { popup.remove(); popup = null; }
            popupItems = [];
            popupIndex = 0;
        }

        function showPopup(cm, matches, pos) {
            removePopup();
            if (matches.length === 0) return;

            popup = document.createElement('div');
            popup.className = 'wb-autocomplete-popup';
            popup.style.cssText =
                'position:fixed;z-index:10000;background:#fff;border:2px solid #000;' +
                'box-shadow:inset 1px 1px 0 #555,3px 3px 0 rgba(0,0,0,0.3);' +
                'font-family:"Press Start 2P",monospace;font-size:9px;max-height:180px;' +
                'overflow-y:auto;min-width:160px;';

            matches.forEach(function(m, i) {
                const item = document.createElement('div');
                item.style.cssText =
                    'padding:5px 8px;cursor:pointer;display:flex;justify-content:space-between;gap:12px;';
                if (i === 0) {
                    item.style.background = '#0055aa';
                    item.style.color = '#fff';
                }
                const label = document.createElement('span');
                label.textContent = m.label;
                const kind = document.createElement('span');
                kind.textContent = m.detail || '';
                kind.style.opacity = '0.6';
                kind.style.fontSize = '7px';
                item.appendChild(label);
                item.appendChild(kind);
                item.addEventListener('mouseenter', function() {
                    popupItems.forEach(function(p) {
                        p.style.background = '';
                        p.style.color = '';
                    });
                    item.style.background = '#0055aa';
                    item.style.color = '#fff';
                    popupIndex = i;
                });
                item.addEventListener('click', function() {
                    insertCompletion(cm, m);
                });
                popup.appendChild(item);
                popupItems.push(item);
            });

            document.body.appendChild(popup);

            /* Position near cursor */
            const coords = cm.coordsAtPos(pos);
            if (coords) {
                popup.style.left = coords.left + 'px';
                popup.style.top = (coords.bottom + 4) + 'px';
            }
            popupIndex = 0;
        }

        function insertCompletion(cm, match) {
            const state = cm.state;
            const sel = state.selection.main;
            const line = state.doc.lineAt(sel.head);
            const lineText = line.text;
            const cursorCol = sel.head - line.from;

            /* Find the start of the current word */
            let wordStart = cursorCol;
            while (wordStart > 0 && /[a-zA-Z0-9_]/.test(lineText[wordStart - 1])) {
                wordStart--;
            }
            const prefix = lineText.slice(wordStart, cursorCol);

            /* Calculate replacement range */
            const from = line.from + wordStart;
            const to = sel.head;

            cm.dispatch({
                changes: { from: from, to: to, insert: match.label },
                selection: { anchor: from + match.label.length }
            });
            removePopup();
            cm.focus();
        }

        function getCompletions(word, langHints) {
            if (!langHints || !word) return [];
            const all = (langHints.keywords || []).concat(langHints.builtins || []);
            const lower = word.toLowerCase();
            return all.filter(function(w) {
                return w.toLowerCase().startsWith(lower) && w !== word;
            }).slice(0, 12).map(function(w) {
                const isKw = (langHints.keywords || []).indexOf(w) >= 0;
                return { label: w, detail: isKw ? 'keyword' : 'builtin' };
            });
        }

        /* ===== Wire up CM6 key events ===== */
        let debounceTimer = null;

        function wireEvents() {
            const cm = getCmView();
            if (!cm) return false;

            /* Prevent double-wiring */
            if (cm._wbWired) return true;
            cm._wbWired = true;

            /* Listen for DOM events on the CM content */
            const contentEl = cm.dom.querySelector('.cm-content');
            if (!contentEl) return false;

            contentEl.addEventListener('input', function() {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(function() { checkCompletions(cm); }, 80);
            });

            contentEl.addEventListener('keydown', function(e) {
                if (!popup) return;
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    movePopup(cm, 1);
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    movePopup(cm, -1);
                } else if (e.key === 'Enter' || e.key === 'Tab') {
                    if (popupItems.length > 0) {
                        e.preventDefault();
                        insertCompletion(cm, popupItems[popupIndex]._match);
                    }
                } else if (e.key === 'Escape') {
                    removePopup();
                }
            });

            /* Close popup on blur */
            contentEl.addEventListener('blur', function() {
                setTimeout(removePopup, 150);
            });

            /* Update hints panel on cursor activity */
            cm.dispatch = (function(origDispatch) {
                return function(tr) {
                    origDispatch.call(cm, tr);
                    if (tr.selection || tr.docChanged) {
                        updateHintsPanel(cm);
                    }
                };
            })(cm.dispatch.bind(cm));

            return true;
        }

        function movePopup(cm, dir) {
            if (popupItems.length === 0) return;
            popupItems[popupIndex].style.background = '';
            popupItems[popupIndex].style.color = '';
            popupIndex = (popupIndex + dir + popupItems.length) % popupItems.length;
            popupItems[popupIndex].style.background = '#0055aa';
            popupItems[popupIndex].style.color = '#fff';
            popupItems[popupIndex].scrollIntoView({ block: 'nearest' });
        }

        function checkCompletions(cm) {
            const state = cm.state;
            const sel = state.selection.main;
            const line = state.doc.lineAt(sel.head);
            const lineText = line.text;
            const cursorCol = sel.head - line.from;

            /* Get current word */
            let end = cursorCol;
            while (end < lineText.length && /[a-zA-Z0-9_]/.test(lineText[end])) end++;
            let start = cursorCol;
            while (start > 0 && /[a-zA-Z0-9_]/.test(lineText[start - 1])) start--;
            const word = lineText.slice(start, end);
            if (!word || word.length < 1) { removePopup(); return; }

            /* Determine language from CM state */
            const lang = getLanguageFromView(cm);
            /* Map CodeMirror language names to hint keys */
            const langMap = {
                'vbscript': 'basic', 'VBScript': 'basic',
                'plaintext': 'plaintext', 'Text': 'plaintext'
            };
            const hintLang = langMap[lang] || langMap[window.__wbCurrentLang] || 'plaintext';
            const langHints = window.WBHints ? window.WBHints[hintLang] : null;
            const matches = getCompletions(word, langHints);
            if (matches.length > 0) {
                /* We need to tag each match with itself */
                const tagged = matches.map(function(m) { return m; });
                /* Rewrite popup items to have _match reference */
                showPopup(cm, tagged, line.from + start);
                /* Re-tag items on popup */
                const items = popup.querySelectorAll('div');
                items.forEach(function(item, i) {
                    item._match = tagged[i];
                });
            } else {
                removePopup();
            }
        }

        /* ===== Hints panel updater ===== */
        function getLanguageFromView(cm) {
            /* Try to extract language from CM6 state */
            try {
                const langFacet = cm.state.facet ? cm.state.facet(cm.state.facet.constructor) : null;
            } catch(e) {}
            /* Fallback: look at the data-lang attribute or class */
            const el = cm.dom;
            if (el) {
                const cls = el.className || '';
                const m = cls.match(/lang-(\\w+)/);
                if (m) return m[1];
            }
            return window.__wbCurrentLang || 'plaintext';
        }

        function updateHintsPanel(cm) {
            const hintsEl = document.getElementById("''' + hints_content_id + '''");
            if (!hintsEl) return;

            const state = cm.state;
            const sel = state.selection.main;
            const line = state.doc.lineAt(sel.head);
            const lineText = line.text;
            const cursorCol = sel.head - line.from;

            /* Get current word */
            let end = cursorCol;
            while (end < lineText.length && /[a-zA-Z0-9_]/.test(lineText[end])) end++;
            let start = cursorCol;
            while (start > 0 && /[a-zA-Z0-9_]/.test(lineText[start - 1])) start--;
            const word = lineText.slice(start, end);

            if (!word || !window.WBHints) {
                hintsEl.innerHTML = '<div class="hint-empty">Type code and move cursor to see hints.</div>';
                return;
            }

            const rawLang = getLanguageFromView(cm);
            const langMap = {
                'vbscript': 'basic', 'VBScript': 'basic',
                'plaintext': 'plaintext', 'Text': 'plaintext'
            };
            const lang = langMap[rawLang] || langMap[window.__wbCurrentLang] || 'plaintext';
            const hints = window.WBHints[lang];
            if (!hints) {
                hintsEl.innerHTML = '<div class="hint-empty">No hints for ' + rawLang + '.</div>';
                return;
            }

            /* Check word tips */
            let tip = hints.tips ? hints.tips[word] : null;

            /* Check pattern-based tips */
            if (!tip && hints.patterns) {
                for (let i = 0; i < hints.patterns.length; i++) {
                    try {
                        const re = new RegExp(hints.patterns[i].re);
                        const m = lineText.match(re);
                        if (m) {
                            tip = hints.patterns[i].tip;
                            break;
                        }
                    } catch(e) {}
                }
            }

            if (tip) {
                const lines = tip.split('\\n').map(function(l) { return '<div>' + l + '</div>'; }).join('');
                hintsEl.innerHTML =
                    '<div class="hint-title">' + word + '</div>' +
                    '<div class="hint-text">' + lines + '</div>';
            } else if ((hints.keywords || []).indexOf(word) >= 0) {
                hintsEl.innerHTML =
                    '<div class="hint-title">' + word + '</div>' +
                    '<div class="hint-text">' + word + ' is a language keyword.</div>';
            } else if ((hints.builtins || []).indexOf(word) >= 0) {
                hintsEl.innerHTML =
                    '<div class="hint-title">' + word + '</div>' +
                    '<div class="hint-text">' + word + ' is a builtin function/object.</div>';
            } else {
                hintsEl.innerHTML = '<div class="hint-empty">No hint for "' + word + '".</div>';
            }
        }

        /* ===== Public API ===== */
        window.__wbCM = {
            wireEvents: wireEvents,
            getCmView: getCmView,
            removePopup: removePopup
        };

        /* Try wiring immediately, else retry */
        if (!wireEvents()) {
            let retries = 0;
            const iv = setInterval(function() {
                if (wireEvents() || ++retries > 30) clearInterval(iv);
            }, 200);
        }
    })();
    '''



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


@ui.page('/editor', favicon=FAVICON_PATH)
def editor_page() -> None:
    ui.add_head_html('<link rel="stylesheet" href="/static/retro.css">')
    ui.add_head_html(_storage_io_js())
    ui.add_head_html('<script src="/static/retro.js"></script>')

    hints_content_id = 'hints-content'

    with ui.element('div').classes('wb-root'):
        # === App Header ===
        with ui.element('div').classes('wb-app-header'):
            ui.label('HITBASIC').classes('app-title')
            ui.label('EDITOR v1.0').classes('app-version')

        # === Toolbar ===
        with ui.element('div').classes('wb-toolbar'):
            ui.label('LANG').classes('wb-select-label').style(
                'font-family:var(--wb-font);font-size:8px;color:var(--wb-white);margin-right:4px;'
            )
            lang_select = (
                ui.select(
                    LANGUAGES,
                    value='VBScript',
                    on_change=lambda e: _on_language_change(e.value),
                )
                .classes('wb-select')
            )

            ui.label('FONT').classes('wb-select-label').style(
                'font-family:var(--wb-font);font-size:8px;color:var(--wb-white);margin-left:8px;margin-right:4px;'
            )
            font_select = (
                ui.select(
                    FONTS,
                    value=DEFAULT_FONT,
                    on_change=lambda e: _on_font_change(e.value),
                )
                .classes('wb-select')
            )

            font_size_label = (
                ui.label(f'{DEFAULT_FONT_SIZE}px')
                .style('font-family:var(--wb-font);font-size:8px;color:var(--wb-white);margin-left:8px;width:28px;')
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
                # RESET ALL unstacked
                ui.button('RESET ALL', on_click=lambda: _trigger_reset(), color='red').classes('wb-button').style('background:#aa0000;color:#fff;')

        # === Main area: editor + hints sidebar ===
        with ui.element('div').classes('wb-main-area'):
            # Editor area
            with ui.element('div').classes('wb-editor-area'):
                code_editor = (
                    ui.codemirror(
                        value='',
                        language='VBScript',
                        theme='basicDark',
                        on_change=lambda e: _on_editor_change(e.value),
                    )
                    .style('flex:1;width:100%;')
                )

                # Status bar
                with ui.element('div').classes('wb-status-bar'):
                    status_lang = ui.label('HitBasic').style(
                        'font-family:var(--wb-font);font-size:8px;'
                    )
                    status_files = ui.label('0 files').style(
                        'font-family:var(--wb-font);font-size:8px;'
                    )

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

    # ===== Helper functions =====

    def _ext_for_lang(lang: str) -> str:
        return {
            'vbscript': 'bas', 'VBScript': 'bas',
            'plaintext': 'txt', 'Text': 'txt',
        }.get(lang, 'txt')

    def _base_name(name: str) -> str:
        return name.rsplit('.', 1)[0] if '.' in name else name

    def _file_icon(language: str) -> str:
        return {
            'vbscript': 'BAS', 'VBScript': 'BAS',
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
                    # Append a padlock icon for read-only files
                    ui.label(f.get('name', '') + (' 🔒' if f.get('readonly') else '')).classes('file-name')
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
        }
        client_state['files'].append(new)
        client_state['active_id'] = fid
        _refresh_file_pool()
        _save_to_storage()
        _load_file_into_editor(new)

    def _close_file(fid: str) -> None:
        client_state['files'] = [f for f in client_state['files'] if f['id'] != fid]
        if client_state['active_id'] == fid:
            if client_state['files']:
                client_state['active_id'] = client_state['files'][0]['id']
                _load_file_into_editor(client_state['files'][0])
            else:
                client_state['active_id'] = None
                code_editor.set_value('')
                file_name_label.set_text('no files')
        # Persist state before mutating UI elements. If we refresh (delete)
        # UI elements while this click handler's slot is still active, NiceGUI
        # may raise "The parent element this slot belongs to has been deleted.".
        _save_to_storage()
        _refresh_file_pool()

    def _switch_to_file(fid: str) -> None:
        if fid == client_state['active_id']:
            return
        _sync_editor_to_active()
        target = next((f for f in client_state['files'] if f['id'] == fid), None)
        if not target:
            return
        client_state['active_id'] = fid
        _load_file_into_editor(target)
        _refresh_file_pool()
        _save_to_storage()

    def _load_file_into_editor(f: dict[str, Any]) -> None:
        code_editor.set_value(f.get('content', ''))
        # Indicate read-only files in the UI and update toolbar state.
        readonly = bool(f.get('readonly', False))
        # Show a padlock icon for read-only files instead of text
        file_name_label.set_text(f['name'] + (' 🔒' if readonly else ''))
        cm_lang = f.get('language', 'Text')
        if cm_lang not in LANGUAGES:
            # Migrate files saved with a language that no longer exists.
            cm_lang = 'Text'
            f['language'] = 'Text'
        if cm_lang == 'Text':
            # Plain text: clear the language extension instead of passing the
            # name 'Text' (which CodeMirror does not know) to set_language.
            code_editor.set_language(None)
        else:
            code_editor.set_language(cm_lang)
        ui.run_javascript(f"window.__wbCurrentLang = '{cm_lang}';")
        ui.run_javascript(_autocomplete_inject_js(hints_content_id))
        status_lang.set_text(LANGUAGES.get(cm_lang, cm_lang))
        # ensure undo/redo stacks exist for this file
        f.setdefault('undos', [])
        f.setdefault('redos', [])
        ui.run_javascript(f'''
            (function() {{
                var id = {code_editor.id};
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
        # a short-circuiting input handler directly to the CM content element.
        readonly_js = str(readonly).lower()
        ui.run_javascript((
            """
            (function(){
                try{
                    var r = {{READONLY}};
                    window.__wbActiveReadonly = r;
                    function makeHandler(){
                        return function(e){
                            // Block undo/redo (Cmd/Ctrl+Z/Y, Cmd/Ctrl+Shift+Z) on read-only files
                            if (e.ctrlKey || e.metaKey) {
                                if (e.key === 'z' || e.key === 'y') { e.preventDefault(); e.stopPropagation(); return false; }
                            }
                            // Allow navigation keys but block text input and commands
                            var blocked = !(e.key && (e.key.startsWith('Arrow') || e.key==='Tab' || e.key==='Escape' || e.ctrlKey || e.metaKey));
                            if (blocked) { e.preventDefault(); e.stopPropagation(); return false; }
                        };
                    }
                    var wrap = document.querySelector('.cm-editor');
                    if (wrap){
                        var el = wrap.querySelector('.cm-content');
                        if (el){
                            // Remove any previous handler
                            if (el._wbReadOnlyHandler) { el.removeEventListener('keydown', el._wbReadOnlyHandler, true); el.removeEventListener('beforeinput', el._wbReadOnlyHandler, true); el._wbReadOnlyHandler = null; }
                            if (r){
                                el._wbReadOnlyHandler = makeHandler();
                                el.addEventListener('keydown', el._wbReadOnlyHandler, true);
                                el.addEventListener('beforeinput', el._wbReadOnlyHandler, true);
                            }
                        }
                    }
                }catch(e){}
            })();
            """
        ).replace("{{READONLY}}", readonly_js))
        # Disable/enable toolbar buttons for read-only files by ID
        ui.run_javascript(f"(function(){{try{{var r={str(readonly).lower()}; var rn=document.getElementById('wb-rename-btn'); if(rn) rn.disabled = r; var d=document.getElementById('wb-delete-btn'); if(d) d.disabled = r; var u=document.getElementById('wb-undo-btn'); if(u) u.disabled = r; var rr=document.getElementById('wb-redo-btn'); if(rr) rr.disabled = r; }}catch(e){{}}}})()")

    def _sync_editor_to_active() -> None:
        if not client_state['active_id']:
            return
        for f in client_state['files']:
            if f['id'] == client_state['active_id']:
                f['content'] = code_editor.value
                break

    def _on_editor_change(value: str) -> None:
        # Autosave: maintain per-file undo/redo stacks and persist content to
        # storage on every edit of the opened file (unless read-only).
        if client_state['active_id']:
            # Ignore edits on read-only files
            cur = next((f for f in client_state['files'] if f['id'] == client_state['active_id']), None)
            if cur and cur.get('readonly'):
                return
            for f in client_state['files']:
                if f['id'] == client_state['active_id']:
                    undos = f.setdefault('undos', [])
                    # push previous content to undos (avoid duplicates)
                    prev = f.get('content', '')
                    if not undos or undos[-1] != prev:
                        undos.append(prev)
                    # clear redo stack on new edit
                    f['redos'] = []
                    f['content'] = value
                    break
        _save_to_storage()

    def _on_language_change(language: str) -> None:
        _sync_editor_to_active()
        if client_state['active_id']:
            for f in client_state['files']:
                if f['id'] == client_state['active_id']:
                    f['language'] = language
                    f['name'] = _base_name(f['name']) + '.' + _ext_for_lang(language)
                    break
            _load_file_into_editor(
                next(f for f in client_state['files'] if f['id'] == client_state['active_id'])
            )
            _refresh_file_pool()
            _save_to_storage()

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
        ui.run_javascript(
            f"document.documentElement.style.setProperty('--wb-editor-font-size', '{int(font_size)}px');"
        )
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
                content = code_editor.value
                filename = 'untitled.txt'
        else:
            content = code_editor.value
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
        # Use client-side file picker, store into WBStorage and reload page
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
                            var files = WBStorage.loadFiles() || [];
                            var newid = WBStorage.generateId();
                            var newfile = { id: newid, name: f.name, language: 'Text', content: e.target.result };
                            files.push(newfile);
                            WBStorage.saveFiles(files);
                            WBStorage.saveActive(newid);

                            // Try to set the editor content in-place using CM view
                            try {
                                const wrap = document.querySelector('.cm-editor');
                                const view = wrap && wrap.cmView && wrap.cmView.view ? wrap.cmView.view : null;
                                if (view && view.dispatch) {
                                    const docLen = view.state.doc.length || 0;
                                    view.dispatch({changes: {from: 0, to: docLen, insert: e.target.result}});
                                    if (typeof view.focus === 'function') view.focus();
                                } else {
                                    // Fallback: try to find the content element and set text
                                    const el = document.querySelector('.cm-editor .cm-content');
                                    if (el) {
                                        // This won't update CM state perfectly but provides visible feedback
                                        el.textContent = e.target.result;
                                    }
                                }
                            } catch(err) { console.warn('apply upload to editor failed', err); }

                            // Simple visual feedback
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

                // ===== Drag-and-drop import (client-side) =====
                function loadFileIntoEditor(f) {
                    try {
                        // Update the editor content using CM view if possible
                        const wrap = document.querySelector('.cm-editor');
                        const view = wrap && wrap.cmView && wrap.cmView.view ? wrap.cmView.view : null;
                        if (view && view.dispatch) {
                            const docLen = view.state.doc.length || 0;
                            view.dispatch({changes: {from: 0, to: docLen, insert: f.content}});
                            if (typeof view.focus === 'function') view.focus();
                        } else {
                            const el = document.querySelector('.cm-editor .cm-content');
                            if (el) el.textContent = f.content;
                        }
                        // Update file name label
                        try { const lbl = document.getElementById('wb-file-name'); if (lbl) lbl.textContent = f.name + (f.readonly ? ' 🔒' : ''); } catch(e){}
                        // set current language hint
                        try { window.__wbCurrentLang = f.language || 'Text'; } catch(e){}
                    } catch(e) { console.warn('loadFileIntoEditor error', e); }
                }

                function makeDockTabForFile(f) {
                    try {
                        const dock = document.querySelector('.wb-dock');
                        if (!dock) return null;
                        // create tab
                        const tab = document.createElement('div');
                        tab.className = 'wb-file-tab';
                        // icon
                        const icon = document.createElement('div'); icon.className='file-icon'; icon.textContent = (f.language && f.language.toLowerCase().startsWith('python')) ? 'PY' : 'TX';
                        const name = document.createElement('div'); name.className='file-name'; name.textContent = f.name + (f.readonly ? ' 🔒' : '');
                        const close = document.createElement('div'); close.className='file-close'; close.textContent='X';
                        close.addEventListener('click', function(ev){ ev.stopPropagation(); try{
                            var files = WBStorage.loadFiles() || [];
                            var idx = files.findIndex(function(x){ return x.id===f.id; });
                            if (idx>=0) { files.splice(idx,1); WBStorage.saveFiles(files); }
                            if (WBStorage.loadActive()===f.id) {
                                if (files.length) { WBStorage.saveActive(files[0].id); loadFileIntoEditor(files[0]); }
                                else { WBStorage.saveActive(null); var lbl=document.getElementById('wb-file-name'); if(lbl) lbl.textContent='no files'; }
                            }
                        }catch(e){} tab.remove(); });
                        tab.addEventListener('click', function(){ try{ document.querySelectorAll('.wb-file-tab').forEach(function(t){ t.classList.remove('active'); }); tab.classList.add('active'); WBStorage.saveActive(f.id); loadFileIntoEditor(f);}catch(e){} });
                        tab.appendChild(icon); tab.appendChild(name); tab.appendChild(close);
                        dock.appendChild(tab);
                        return tab;
                    } catch(e) { console.warn('makeDockTabForFile error', e); return null; }
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
                                        var files = WBStorage.loadFiles() || [];
                                        var newid = WBStorage.generateId();
                                        var lang = 'Text';
                                        if (file.name && file.name.endsWith('.bas')) lang='VBScript';
                                        var newfile = { id: newid, name: file.name, language: lang, content: ev.target.result };
                                        files.push(newfile);
                                        WBStorage.saveFiles(files);
                                        WBStorage.saveActive(newid);
                                        // create dock tab and load into editor
                                        try { document.querySelectorAll('.wb-file-tab').forEach(function(t){ t.classList.remove('active'); }); } catch(e){}
                                        makeDockTabForFile(newfile);
                                        loadFileIntoEditor(newfile);
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
                // Global undo/redo operating directly on the editor view.
                // CodeMirror handles Ctrl/Cmd+Z and Ctrl/Cmd+Y natively while the
                // editor is focused; these helpers cover focus elsewhere.
                function wbCmDo(action) {
                    if (window.__wbActiveReadonly) return;
                    getElement(@CMID@).editorPromise.then(function(p) {
                        import('nicegui-codemirror').then(function(CM) {
                            try {
                                if (action === 'undo') CM.undo(p); else CM.redo(p);
                                try { p.focus(); } catch(e) {}
                            } catch(e) {}
                        });
                    });
                }
                window.__wbUndo = function() { wbCmDo('undo'); };
                window.__wbRedo = function() { wbCmDo('redo'); };
                document.addEventListener('keydown', function(e) {
                    const mod = e.ctrlKey || e.metaKey;
                    if (!mod) return;
                    if (e.key === 'z' && !e.shiftKey) {
                        e.preventDefault();
                        window.__wbUndo();
                    } else if (e.key === 'y' || (e.key === 'z' && e.shiftKey)) {
                        e.preventDefault();
                        window.__wbRedo();
                    }
                });
            })()
        '''.replace('@CMID@', str(code_editor.id)))
        # Give focus back to the editor after toolbar button clicks so the user
        # can keep typing. Rename/Delete open dialogs with their own focus, so
        # they are excluded.
        ui.run_javascript(f'''
            (function() {{
                var cmId = {code_editor.id};
                window.wbRefocusEditor = function() {{
                    try {{
                        var el = getElement(cmId);
                        if (el && el.editorPromise) {{
                            el.editorPromise.then(function(v) {{ try {{ v.focus(); }} catch(e) {{}} }});
                            return true;
                        }}
                    }} catch(e) {{}}
                    return false;
                }};
                document.addEventListener('click', function(e) {{
                    try {{
                        var t = e.target && e.target.closest ? e.target.closest('button') : null;
                        if (!t) return;
                        var id = t.id || '';
                        if (id === 'wb-rename-btn' || id === 'wb-delete-btn') return;
                        window.wbRefocusEditor();
                    }} catch(e) {{}}
                }}, true);
            }})();
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
        # (e.g. saved as Python or Markdown) to plain text.
        for f in client_state['files']:
            if f.get('language') not in LANGUAGES:
                f['language'] = 'Text'

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
                    '# HITBASIC Editor\n\n'
                    'Welcome to HITBASIC Editor.\n'
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
