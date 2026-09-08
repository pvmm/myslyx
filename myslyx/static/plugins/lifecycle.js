// Myslyx Text Editor - plugin lifecycle glue.
// Binds plugin modules to the editor through the WBPlugins runtime. Each
// plugin lives in its own directory (one directory per plugin) under
// static/plugins/<name>/ and exposes an ES module named <name>.js whose
// default export is a factory taking the 'nicegui-codemirror' namespace (CM)
// and returning one or more CodeMirror 6 extensions. The list of plugin
// directories is injected by pages/editor_page.py as window.WB_PLUGIN_MANIFEST.
(function() {
    'use strict';

    var base = '/static/plugins/';
    var manifest = window.WB_PLUGIN_MANIFEST || [];

    manifest.forEach(function(def) {
        if (!def || !def.name || !def.dir || !def.entry) return;
        WBPlugins.register({
            name: def.name,
            languages: def.languages || ['*'],
            enabledByDefault: def.enabledByDefault !== false,
            extensions: function(view, CM, ctx) {
                return import(base + def.dir + '/' + def.entry).then(function(mod) {
                    if (typeof mod.default !== 'function') {
                        throw new Error(def.name + ': module does not export a default factory');
                    }
                    var got = mod.default(CM, ctx);
                    return Array.isArray(got) ? got : [got];
                });
            }
        });
    });
})();