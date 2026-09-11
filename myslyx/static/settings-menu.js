// Settings flyout for the wrap toggle, the LIGATURES toggle and the
// PLUGINS submenu, plus its keyboard navigation and F1 shortcut.
(function() {
    function install() {
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
                    clearPluginFocus();
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
                hint.textContent = 'changes reload the editor on close';
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
                                // Reloading while choosing is jarring, so the
                                // page refresh is deferred until the menu is
                                // closed (see close() below).
                                menu._pluginsChanged = true;
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
                // Keyboard focus for the plugin rows inside the PLUGINS submenu.
                function pluginRows() {
                    return Array.prototype.slice.call(
                        submenu.querySelectorAll('.wb-plugin-row'));
                }
                function clearPluginFocus() {
                    pluginRows().forEach(function(r) { r.classList.remove('keyboard'); });
                }
                function focusPluginRow(delta) {
                    var rows = pluginRows();
                    if (!rows.length) return;
                    var idx = rows.indexOf(submenu.querySelector('.wb-plugin-row.keyboard'));
                    var next = idx < 0 ? (delta > 0 ? 0 : rows.length - 1) : idx + delta;
                    if (next < 0) next = rows.length - 1;
                    if (next >= rows.length) next = 0;
                    clearPluginFocus();
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
                    // Plugin checkboxes only persist config; reload the page
                    // (so the new plugin set takes effect) when the menu is
                    // actually closed.
                    if (menu._pluginsChanged) {
                        menu._pluginsChanged = false;
                        window.location.reload();
                    }
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

                    // Inside the PLUGINS submenu: arrows move between plugin
                    // rows, Enter/Space toggles the focused plugin, and
                    // Escape/ArrowLeft return to the main menu.
                    if (submenu.style.display === 'block') {
                        if (ev.key === 'Escape' || ev.key === 'ArrowLeft') {
                            ev.preventDefault();
                            closeSubmenu();
                            focusRow(0);
                        } else if (ev.key === 'ArrowDown') {
                            ev.preventDefault(); focusPluginRow(1);
                        } else if (ev.key === 'ArrowUp') {
                            ev.preventDefault(); focusPluginRow(-1);
                        } else if (ev.key === 'Enter' || ev.key === ' ') {
                            var prow = submenu.querySelector('.wb-plugin-row.keyboard');
                            if (prow) {
                                ev.preventDefault();
                                var c = prow.querySelector('input[type=checkbox]');
                                if (c && !c.disabled) c.click();
                            }
                        }
                        return;
                    }

                    if (ev.key === 'Escape') { close(); return; }
                    if (ev.key === 'ArrowDown') { ev.preventDefault(); focusRow(1); }
                    else if (ev.key === 'ArrowUp') { ev.preventDefault(); focusRow(-1); }
                    else if (ev.key === 'Enter' || ev.key === ' ' || ev.key === 'ArrowRight') {
                        var cur = menu.querySelector('.wb-settings-row.keyboard');
                        if (cur) {
                            ev.preventDefault();
                            if (cur.id === 'wb-settings-plugins') {
                                // Enter/Right over PLUGINS moves into the submenu.
                                toggleSubmenu();
                                focusPluginRow(0);
                            } else if (ev.key !== 'ArrowRight') {
                                cur.click();
                            }
                        }
                    }
                });

                // Ctrl+, opens/closes the SETTINGS menu from anywhere
                // (Ctrl+Space belongs to the editor's autocompletion).
                document.addEventListener('keydown', function(ev) {
                    if ((ev.ctrlKey || ev.metaKey) && (ev.key === ',' || ev.code === 'Comma')) {
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
        })();
    }

    window.WBSettingsMenu = { install: install };
    if (document.readyState !== 'loading') {
        install();
    } else {
        document.addEventListener('DOMContentLoaded', install, { once: true });
    }
})();