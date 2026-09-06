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
    // This CodeMirror bundle compares widgets with compare(), not eq().
    ColorSwatchWidget.prototype.compare = function(other) {
        return other instanceof ColorSwatchWidget && other.hex === this.hex;
    };
    ColorSwatchWidget.prototype.eq = ColorSwatchWidget.prototype.compare;
    // CodeMirror calls destroy() when an edit removes a widget from the view.
    ColorSwatchWidget.prototype.destroy = function() {};

    // Rebuilds the full swatch decoration set for the whole document.
    // MatchDecorator cannot be used here: its updateDeco() rebuilds widget
    // decorations spanning the matched text, and CodeMirror requires widgets to
    // have zero-length ranges ("Widget decorations can only have zero-length
    // ranges"). So this builds a zero-length widget range at the end of each
    // token instead, which renders the swatch right after the hex text.
    function buildSwatches(CM, view) {
        var builder = new CM.RangeSetBuilder();
        var re = new RegExp(SWATCH_RE.source, 'g');
        var text = view.state.doc.toString();
        var m;
        while ((m = re.exec(text)) !== null) {
            var end = m.index + m[0].length;
            builder.add(end, end, CM.Decoration.widget({
                widget: new ColorSwatchWidget(m[1]),
                side: 1 // place the swatch after the token, not before it
            }));
        }
        return builder.finish();
    }

    // Builds the CodeMirror 6 view extension for one editor instance.
    function swatchExtension(CM) {
        var SwatchViewPlugin = function(view) {
            this.decorations = buildSwatches(CM, view);
        };
        SwatchViewPlugin.prototype.update = function(update) {
            if (update.docChanged) {
                this.decorations = buildSwatches(CM, update.view);
            }
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