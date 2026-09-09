// Settings flyout for the wrap toggle and plugins submenu.
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
                }
                function toggleSubmenu() {
                    if (submenu.style.display === 'block') closeSubmenu();
                    else {
                        rebuildPlugins();
                        submenu.style.display = 'block';
                        pluginsRow.classList.add('active');
                    }
                }

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

                function rebuildPlugins() {
                    if (!window.WBPlugins || !window.WBPlugins.list) return;
                    var list = window.WBPlugins.list();
                    if (!list || list.length === 0) return;
                    var rows = menu.querySelectorAll('.wb-plugin-toggle');
                    rows.forEach(function(r) { r.remove(); });
                    list.forEach(function(info) {
                        var row = document.createElement('div');
                        row.className = 'wb-settings-row wb-plugin-toggle';
                        row.tabIndex = 0;
                        var label = document.createElement('span');
                        label.className = 'wb-settings-row-label';
                        label.textContent = info.name;
                        var value = document.createElement('span');
                        value.className = 'wb-settings-value';
                        value.textContent = info.enabled ? 'ON' : 'OFF';
                        row.appendChild(label);
                        row.appendChild(value);
                        row.addEventListener('click', function(ev) {
                            ev.stopPropagation();
                            window.WBPlugins.toggle(info.name);
                            value.textContent = window.WBPlugins.isEnabled(info.name) ? 'ON' : 'OFF';
                        });
                        menu.appendChild(row);
                    });
                }

                // Keep the menu bound to the button, even when the plugin state changes.
                btn.addEventListener('click', function(ev) {
                    ev.stopPropagation();
                    var shown = menu.style.display === 'block';
                    menu.style.display = shown ? 'none' : 'block';
                    if (!shown) {
                        rebuildPlugins();
                    }
                });
                document.addEventListener('click', function() {
                    menu.style.display = 'none';
                    if (pluginsRow) pluginsRow.classList.remove('active');
                });
                return true;
            }

            setupSettingsMenu();
        })();
    }

    window.WBSettingsMenu = { install: install };
    if (document.readyState !== 'loading') {
        install();
    } else {
        document.addEventListener('DOMContentLoaded', install, { once: true });
    }
})();
