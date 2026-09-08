// Myslyx Text Editor - plugin lifecycle glue.
// Binds plugin modules to the editor through the WBPlugins runtime. Each
// plugin lives in its own directory (one directory per plugin) under
// static/plugins/<name>/ and exposes an ES module named <name>.js whose
// default export is a factory taking the 'nicegui-codemirror' namespace (CM)
// and returning one or more CodeMirror 6 extensions. Plugin directories are
// listed in window.WB_PLUGIN_MANIFEST (a dict built by pages/editor_page.py);
// each entry carries the URL prefix it is served under ('/static/plugins/'
// for bundled plugins, '/user-plugins/' for plugins installed in the
// per-OS user configuration directory, see myslyx/paths.py).
(function() {
    'use strict';

    var manifest = window.WB_PLUGIN_MANIFEST || [];

    manifest.forEach(function(def) {
        if (!def || !def.name || !def.dir || !def.entry) return;
        WBPlugins.register({
            name: def.name,
            languages: def.languages || ['*'],
            enabledByDefault: def.enabledByDefault !== false,
            extensions: function(view, CM, ctx) {
                var url = (def.base || '/static/plugins/') + def.dir + '/' + def.entry;
                return import(url).then(function(mod) {
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