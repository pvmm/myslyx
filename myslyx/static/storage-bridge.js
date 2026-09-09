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
