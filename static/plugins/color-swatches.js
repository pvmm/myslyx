// Myslyx Text Editor - color-swatches plugin.
// Minimal proof-of-concept: scans for #rrggbb-style hex tokens and renders
// a small color box right after each one. Uses a StateField with
// Decoration.widget (side: 1) so the cursor enters hex tokens normally.
// Adapted from the vanilla CM6 extension with no structural changes.

(function() {
    'use strict';

    var SWATCH_RE = /#([0-9a-fA-F]{3,8})(?![0-9a-fA-F])/g;

    // Inject the swatch styling once.
    (function injectStyles() {
        var cssId = 'wb-color-swatch-css';
        if (document.getElementById(cssId)) return;
        var st = document.createElement('style');
        st.id = cssId;
        st.textContent =
            '.wb-color-swatch{' +
            'display:inline-block;width:12px;height:12px;' +
            'vertical-align:middle;margin-left:4px;' +
            'border:1px solid #ccc;border-radius:2px;' +
            '}';
        document.head.appendChild(st);
    })();

    // Widget: a swatch box whose colour comes from the matched hex token.
    // Subclass the CodeMirror bundle's real WidgetType (a native ES class) so
    // every lifecycle method (compare/eq, updateDOM, coordsAt, ignoreEvent,
    // destroy) resolves from the base prototype, exactly like a native CM6
    // extension.
    function makeColorWidget(CM) {
        var ColorWidget = class extends CM.WidgetType {
            constructor(hex) {
                super();
                this.hex = hex;
            }
            eq(other) {
                return other instanceof ColorWidget && other.hex === this.hex;
            }
            toDOM() {
                var el = document.createElement('span');
                el.setAttribute('aria-hidden', 'true');
                el.className = 'wb-color-swatch';
                el.style.backgroundColor = '#' + this.hex;
                return el;
            }
        };
        return ColorWidget;
    }

    // Scan the full document and build widget decorations (zero-length ranges
    // at each token end, side: 1 places the swatch right after).
    function getColorDecorations(CM, ColorWidget, state) {
        var widgets = [];
        var text = state.doc.toString();
        var re = new RegExp(SWATCH_RE.source, 'g');
        var m;
        while ((m = re.exec(text)) !== null) {
            var end = m.index + m[0].length;
            var deco = CM.Decoration.widget({
                widget: new ColorWidget(m[1]),
                side: 1
            });
            widgets.push(deco.range(end));
        }
        return CM.Decoration.set(widgets);
    }

    // Build the CodeMirror 6 StateField extension.
    function swatchField(CM) {
        var ColorWidget = makeColorWidget(CM);
        return CM.StateField.define({
            create: function(state) {
                return getColorDecorations(CM, ColorWidget, state);
            },
            update: function(decorations, tr) {
                if (tr.docChanged) return getColorDecorations(CM, ColorWidget, tr.state);
                return decorations.map(tr.changes);
            },
            provide: function(f) { return CM.EditorView.decorations.from(f); }
        });
    }

    window.WBPlugins.register({
        name: 'color-swatches',
        languages: ['*'],
        enabledByDefault: true,
        extensions: function(view, CM, ctx) {
            return [swatchField(CM)];
        }
    });
})();
