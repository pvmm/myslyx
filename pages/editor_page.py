import json
from typing import Any
from nicegui import ui


# Language options - keys match CodeMirror language names
LANGUAGES: dict[str, str] = {
    'Python': 'Python',
    'JavaScript': 'JavaScript',
    'TypeScript': 'TypeScript',
    'HTML': 'HTML',
    'CSS': 'CSS',
    'JSON': 'JSON',
    'Markdown': 'Markdown',
    'Shell': 'Shell',
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
                'python': 'python', 'Python': 'python',
                'javascript': 'javascript', 'JavaScript': 'javascript',
                'typescript': 'typescript', 'TypeScript': 'typescript',
                'plaintext': 'plaintext', 'Text': 'plaintext'
            };
            const hintLang = langMap[lang] || langMap[window.__wbCurrentLang] || 'plaintext';
            const langHints = window.WBHints ? window.WBHints[hintLang] : null;
            const matches = getCompletions(word, langHints);
            if (matches.length > 0) {
                matches.forEach(function(m) { popupItems._match = m; });
                /* We need to tag each match with itself */
                const tagged = matches.map(function(m) {
                    const taggedItem = m;
                    return taggedItem;
                });
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
                'python': 'python', 'Python': 'python',
                'javascript': 'javascript', 'JavaScript': 'javascript',
                'typescript': 'typescript', 'TypeScript': 'typescript',
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


@ui.page('/editor', favicon='/static/favicon.ico')
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
            lang_select = (
                ui.select(
                    {k: v for k, v in LANGUAGES.items()},
                    value='Python',
                    on_change=lambda e: _on_language_change(e.value),
                )
                .classes('wb-select')
            )

            font_select = (
                ui.select(
                    FONTS,
                    value=DEFAULT_FONT,
                    on_change=lambda e: _on_font_change(e.value),
                )
                .classes('wb-select')
                .style('margin-left:8px;')
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
                .style('font-family:var(--wb-font);font-size:9px;color:var(--wb-white);margin-left:12px;')
            )

            with ui.element('div').style('margin-left:auto;display:flex;gap:4px;'):
                ui.button('SAVE', on_click=lambda: _save_current_file()).classes('wb-button')
                ui.button('NEW', on_click=lambda: _new_file()).classes('wb-button')
                ui.button('HOME', on_click=lambda: ui.navigate.to('/')).classes('wb-button')

        # === Main area: editor + hints sidebar ===
        with ui.element('div').classes('wb-main-area'):
            # Editor area
            with ui.element('div').classes('wb-editor-area'):
                code_editor = (
                    ui.codemirror(
                        value='',
                        language='Python',
                        theme='basicDark',
                        on_change=lambda e: _on_editor_change(e.value),
                    )
                    .style('flex:1;width:100%;')
                )

                # Status bar
                with ui.element('div').classes('wb-status-bar'):
                    status_lang = ui.label('Python').style(
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
            'python': 'py', 'Python': 'py',
            'javascript': 'js', 'JavaScript': 'js',
            'typescript': 'ts', 'TypeScript': 'ts',
            'html': 'html', 'HTML': 'html',
            'css': 'css', 'CSS': 'css',
            'json': 'json', 'JSON': 'json',
            'markdown': 'md', 'Markdown': 'md',
            'shell': 'sh', 'Shell': 'sh',
            'plaintext': 'txt', 'Text': 'txt',
        }.get(lang, 'txt')

    def _base_name(name: str) -> str:
        return name.rsplit('.', 1)[0] if '.' in name else name

    def _file_icon(language: str) -> str:
        return {
            'python': 'PY', 'Python': 'PY',
            'javascript': 'JS', 'JavaScript': 'JS',
            'typescript': 'TS', 'TypeScript': 'TS',
            'html': 'HT', 'HTML': 'HT',
            'css': 'CS', 'CSS': 'CS',
            'json': 'JN', 'JSON': 'JN',
            'markdown': 'MD', 'Markdown': 'MD',
            'shell': 'SH', 'Shell': 'SH',
            'plaintext': 'TX', 'Text': 'TX',
        }.get(language, '??')

    # ===== File pool management =====

    def _refresh_file_pool() -> None:
        nonlocal file_tabs
        for tab_id, tab_el in file_tabs.items():
            try:
                tab_el.delete()
            except Exception:
                pass
        file_tabs.clear()

        for f in client_state['files']:
            is_active = f['id'] == client_state['active_id']
            tab = ui.element('div').classes(
                'wb-file-tab' + (' active' if is_active else '')
            )
            with tab:
                ui.label(_file_icon(f.get('language', 'Text'))).classes('file-icon')
                ui.label(f['name']).classes('file-name')
                close_btn = ui.element('div').classes('file-close')
                with close_btn:
                    ui.label('X')
                close_btn.on('click', lambda e, fid=f['id']: _close_file(fid))
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
        _refresh_file_pool()
        _save_to_storage()

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
        file_name_label.set_text(f['name'])
        cm_lang = f.get('language', 'Text')
        code_editor.set_language(cm_lang)
        ui.run_javascript(f"window.__wbCurrentLang = '{cm_lang}';")
        ui.run_javascript(_autocomplete_inject_js(hints_content_id))
        status_lang.set_text(LANGUAGES.get(cm_lang, cm_lang))
        ui.run_javascript('''
            (function() {
                const el = document.querySelector('.cm-editor .cm-content');
                if (el) el.focus();
            })()
        ''')

    def _sync_editor_to_active() -> None:
        if not client_state['active_id']:
            return
        for f in client_state['files']:
            if f['id'] == client_state['active_id']:
                f['content'] = code_editor.value
                break

    def _save_current_file() -> None:
        _sync_editor_to_active()
        _save_to_storage()

    def _on_editor_change(value: str) -> None:
        _sync_editor_to_active()
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
        ui.run_javascript(
            f"document.documentElement.style.setProperty('--wb-editor-font', '{font}');"
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

    # ===== Initialize from localStorage =====
    def _init() -> None:
        ui.run_javascript('''
            (function() {
                if (window.__wbPyBridge && !window.__wbPyBridge.hasFiles()) {
                    window.__wbPyBridge.initDefaults();
                }
                var font = localStorage.getItem('wb_editor_font') || 'Press Start 2P';
                return JSON.stringify({
                    files: window.__wbPyBridge ? window.__wbPyBridge.getFiles() : [],
                    active: window.__wbPyBridge ? window.__wbPyBridge.getActive() : null
                });
            })()
        ''', callback=_on_storage_loaded)
        # Restore the saved font preference
        ui.run_javascript('''
            (function() {
                const f = localStorage.getItem('wb_editor_font') || 'Press Start 2P';
                document.documentElement.style.setProperty('--wb-editor-font', f);
                const fs = localStorage.getItem('wb_editor_font_size') || '13';
                document.documentElement.style.setProperty('--wb-editor-font-size', fs + 'px');
            })()
        ''')

    def _on_storage_loaded(result: Any) -> None:
        try:
            data = json.loads(result) if isinstance(result, str) else result
        except (json.JSONDecodeError, TypeError):
            data = {'files': [], 'active': None}

        client_state['files'] = data.get('files', [])
        client_state['active_id'] = data.get('active')

        _refresh_file_pool()

        if client_state['files'] and client_state['active_id']:
            target = next(
                (f for f in client_state['files'] if f['id'] == client_state['active_id']),
                client_state['files'][0],
            )
            client_state['active_id'] = target['id']
            _load_file_into_editor(target)
        elif client_state['files']:
            client_state['active_id'] = client_state['files'][0]['id']
            _load_file_into_editor(client_state['files'][0])

    ui.timer(0.8, _init, once=True)
