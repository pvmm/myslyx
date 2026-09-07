// Myslyx Text Editor - plugin runtime.
// Plugins register (via window.WBPlugins.register) a set of CodeMirror 6
// extensions that are appended to the editor once its view exists. Enabled
// state comes from the shared client config (WBStorage.loadConfig().plugins).
// See static/plugins/README.md for the plugin contract.
(function() {
    'use strict';

    var registry = [];

    window.WBPlugins = {
        // Register a plugin definition. Called by plugin scripts at load time.
        register: function(def) {
            if (!def || !def.name || typeof def.extensions !== 'function') return;
            registry.push(def);
        },

        // List installed plugins as plain definitions, for UIs like the plugins
        // menu. Read enabled state with _enabled().
        list: function() {
            return registry.map(function(d) {
                return { name: d.name, enabledByDefault: d.enabledByDefault !== false };
            });
        },

        // A plugin is enabled unless the config explicitly disables it.
        _enabled: function(def) {
            var cfg = window.WBStorage ? window.WBStorage.loadConfig() : {};
            var plugs = cfg.plugins || {};
            var val = plugs[def.name];
            if (val === undefined || val === null) val = def.enabledByDefault !== false;
            return !!val;
        },

        // A plugin runs for its declared languages (the current file's language
        // as tracked by the server in window.__wbCurrentLang). '*' = all.
        _langOk: function(def) {
            var langs = def.languages;
            if (!langs || langs.indexOf('*') >= 0) return true;
            var cur = window.__wbCurrentLang || 'Text';
            return langs.indexOf(cur) >= 0;
        },

        // Attach the enabled plugins' extensions to a CodeMirror view. Runs once
        // per view; config changes take effect on the next page load.
        install: function(view) {
            if (!view || view._wbPluginsApplied) return;
            view._wbPluginsApplied = true;
            import('nicegui-codemirror').then(function(CM) {
                if (!view) return;
                var exts = [];
                registry.forEach(function(def) {
                    try {
                        if (WBPlugins._enabled(def) && WBPlugins._langOk(def)) {
                            var got = def.extensions(view, CM, { config: (window.WBStorage.loadConfig().plugins || {})[def.name] || {} });
                            if (got) exts = exts.concat(got);
                        }
                    } catch(e) {
                        console.warn('WBPlugins: ' + def.name + ' failed to provide extensions', e);
                    }
                });
                if (exts.length) {
                    view.dispatch({
                        effects: CM.StateEffect.appendConfig.of(exts)
                    });
                }
            }).catch(function(e) {
                console.warn('WBPlugins: failed to load CodeMirror namespace', e);
            });
        },

        // Same editor-id resolution + retry strategy used by static/hints.js.
        tryHook: function() {
            var elId = window.__wbEditorId;
            if (!elId) return false;
            var el = window.getElement ? window.getElement(elId) : null;
            if (!el || !el.editorPromise) return false;
            el.editorPromise.then(WBPlugins.install);
            return true;
        }
    };

    var attempts = 0;
    var iv = setInterval(function() {
        if (WBPlugins.tryHook() || ++attempts > 100) clearInterval(iv);
    }, 200);

    // Re-bind whenever the server activates a (possibly new) editor. Installs
    // are idempotent per view (view._wbPluginsApplied).
    window.addEventListener('wb-active-editor', function() {
        try { WBPlugins.tryHook(); } catch(e) {}
    });
})();