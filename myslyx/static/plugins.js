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
        // menu. Read enabled state with _enabled(), and whether a plugin is
        // withheld by the deployment's disabled-language gate with _disabledOk().
        list: function() {
            return registry.map(function(d) {
                return {
                    name: d.name,
                    enabledByDefault: d.enabledByDefault !== false,
                    languageServer: d.languageServer === true,
                    languages: d.languages || ['*'],
                    baseLang: d.baseLang || null,
                };
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

        // A plugin runs for its declared languages and/or its base language
        // (window.__wbBaseLang). Two orthogonal scopes:
        //   - "languages" scopes to the exact languages (the LANGUAGES keys
        //     from editor_page.py, e.g. "C", "C MSXgl");
        //   - "baseLang" scopes to any language sharing a base (e.g. "c"
        //     covers both plain C and the MSXgl C framework, and any future
        //     C-derived language). '*' = all.
        // An absent filter passes; when both are declared they both must match.
        _langOk: function(def) {
            var cur = window.__wbCurrentLang || 'Text';
            var langs = def.languages;
            if (langs && langs.indexOf('*') < 0) {
                if (langs.indexOf(cur) < 0
                    // "HitBasic" superseded the "VBScript" stored id; keep
                    // plugin manifests written for the old id matching too.
                    && !(cur === 'HitBasic' && langs.indexOf('VBScript') >= 0)) {
                    return false;
                }
            }
            var bases = def.baseLang;
            if (bases && bases.length) {
                var base = window.__wbBaseLang || 'text';
                if (bases.indexOf(base) < 0) return false;
            }
            return true;
        },

        // A local-only plugin (plugin.json "onlyLocal": true) runs only when
        // the server reports a local run via window.__wbLocal. Shared
        // deployments keep their plugins inert (still listed in the menu).
        _localOk: function(def) {
            return !(def.onlyLocal && !window.__wbLocal);
        },

        // A deployment may hide languages via MYSLYX_DISABLED_LANGS (published
        // as window.__wbDisabledLangs / __wbDisabledBaseLangs). A plugin scoped
        // to a disabled language is withheld entirely and greyed out in the
        // menu. Exact-scope plugins match a disabled language key; base-scope
        // plugins match a base family only once NO dialect of it is enabled
        // (so disabling just "C MSXgl" leaves a baseLang:["c"] plugin useful
        // for plain C).
        _disabledOk: function(def) {
            var langs = def.languages || [];
            var disLangs = window.__wbDisabledLangs || [];
            for (var i = 0; i < langs.length; i++) {
                if (langs[i] !== '*' && disLangs.indexOf(langs[i]) >= 0) return false;
            }
            var bases = def.baseLang || [];
            var disBases = window.__wbDisabledBaseLangs || [];
            for (var j = 0; j < bases.length; j++) {
                if (disBases.indexOf(bases[j]) >= 0) return false;
            }
            return true;
        },

        // Attach the enabled plugins' extensions to a CodeMirror view. Runs once
        // per view; config changes take effect on the next page load. Extension
        // providers may be synchronous (an array) or asynchronous (a Promise,
        // e.g. one that dynamic-imports the plugin module).
        install: function(view) {
            if (!view || view._wbPluginsApplied) return;
            view._wbPluginsApplied = true;
            import('nicegui-codemirror').then(function(CM) {
                if (!view) return;
                var providers = registry.map(function(def) {
                    return Promise.resolve().then(function() {
                        if (WBPlugins._enabled(def) && WBPlugins._langOk(def) && WBPlugins._localOk(def) && WBPlugins._disabledOk(def)) {
                            return def.extensions(view, CM, { config: (window.WBStorage.loadConfig().plugins || {})[def.name] || {} });
                        }
                        return [];
                    }).catch(function(e) {
                        console.warn('WBPlugins: ' + def.name + ' failed to provide extensions', e);
                        return [];
                    });
                });
                Promise.all(providers).then(function(results) {
                    if (!view) return;
                    var exts = [];
                    results.forEach(function(r) {
                        if (r) exts = exts.concat(r);
                    });
                    if (exts.length) {
                        view.dispatch({
                            effects: CM.StateEffect.appendConfig.of(exts)
                        });
                    }
                });
            }).catch(function(e) {
                console.warn('WBPlugins: failed to load CodeMirror namespace', e);
            });
        },

        // Resolve the active CodeMirror view through the shared race-safe
        // helper (same as static/hints.js) and install the enabled plugins.
        tryHook: function() {
            window.WBEditorActive.withView(WBPlugins.install);
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