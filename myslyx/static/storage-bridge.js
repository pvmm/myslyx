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

    // Client side of the wb-storage-sync bridge: push the localStorage pool
    // back to the server so it adopts the state the browser owns.
    window.WBStorageSync = {
        emitFiles: function(emit) {
            try {
                var fs = WBStorage.loadFiles();
                var act = WBStorage.loadActive();
                emit(fs && fs.length ? JSON.stringify({ files: fs, active: act }) : null);
            } catch (e) {
                emit(null);
            }
        }
    };
})();
