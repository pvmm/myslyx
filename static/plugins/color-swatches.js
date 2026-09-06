// Myslyx Text Editor - example plugin: inline color swatches.
// Scans the document for #rrggbb-style hex tokens and renders a small
// color box right after each one. No popup yet - this is the minimal
// proof-of-concept that exercises the plugin runtime end to end.
(function() {
    'use strict';

    var SWATCH_RE = /#([0-9a-fA-F]{3,8})(?![0-9a-fA-F])/g;

    // Inject the swatch styling once, keeping the core retro.css untouched.
    (function injectStyles() {
        var cssId = 'wb-color-swatch-css';
        if (document.getElementById(cssId)) return;
        var st = document.createElement('style');
        st.id = cssId;
        st.textContent =
            '.wb-color-swatch{' +
            'display:inline-block;width:10px;height:10px;' +
            'vertical-align:middle;margin-left:3px;' +
            'border:1px solid #888;box-shadow:inset 1px 1px 0 #555;' +
            'cursor:pointer;flex:none;' +
            '}';
        document.head.appendChild(st);
    })();

    // Widget: a swatch box whose colour comes from the matched hex token.
    function ColorSwatchWidget(hex) {
        this.hex = hex;
    }
    ColorSwatchWidget.prototype.toDOM = function() {
        var el = document.createElement('span');
        el.className = 'wb-color-swatch';
        el.style.background = '#' + this.hex;
        el.title = '#' + this.hex.toUpperCase();
        return el;
    };
    ColorSwatchWidget.prototype.eq = function(other) {
        return other instanceof ColorSwatchWidget && other.hex === this.hex;
    };

    // Builds the CodeMirror 6 view extension for one editor instance.
    function swatchExtension(CM) {
        var matcher = new CM.MatchDecorator({
            regexp: SWATCH_RE,
            decoration: function(m) {
                return CM.Decoration.widget({
                    widget: new ColorSwatchWidget(m[1]),
                    side: 1 // place the swatch after the token, not before it
                });
            }
        });

        var SwatchViewPlugin = function(view) {
            this.decorations = matcher.createDeco(view);
        };
        SwatchViewPlugin.prototype.update = function(update) {
            this.decorations = matcher.updateDeco(update, this.decorations);
        };

        return CM.ViewPlugin.fromClass(SwatchViewPlugin, {
            decorations: function(v) { return v.decorations; }
        });
    }

    window.WBPlugins.register({
        name: 'color-swatches',
        languages: ['*'],
        enabledByDefault: true,
        extensions: function(view, CM) {
            return [swatchExtension(CM)];
        }
    });
})();