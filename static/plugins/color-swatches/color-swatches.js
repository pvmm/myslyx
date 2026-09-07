// Myslyx Text Editor - color-swatches plugin module.
// Isolated CodeMirror 6 extension. Same logic as the standalone version at
// /home/pedro/projects/javascript/codemirror/color-swatches.js; the only
// difference is the module signature: instead of importing from
// "@codemirror/view" / "@codemirror/state" (which the Myslyx page has no
// import map for), the CM namespace is passed in as an argument by the plugin
// glue (static/plugins/lifecycle.js). See static/plugins/README.md.

export default function colorPreviewExtension(CM) {
    const { EditorView, Decoration, WidgetType, StateField } = CM;

    // 1. Define the DOM widget for the color box
    class ColorWidget extends WidgetType {
        constructor(color) {
            super();
            this.color = color;
        }

        eq(other) {
            return other.color === this.color;
        }

        toDOM() {
            let box = document.createElement("span");
            box.style.display = "inline-block";
            box.style.width = "0.8em";
            box.style.height = "0.8em";
            box.style.marginLeft = "4px";
            box.style.verticalAlign = "middle";
            box.style.backgroundColor = this.color;
            box.style.border = "1px solid #ccc";
            box.style.borderRadius = "2px";
            return box;
        }
    }

    // 2. Helper function to scan text and build decorations
    function getColorDecorations(state) {
        let widgets = [];
        // Regex to match #rrggbb or #rgb codes
        const hexRegex = /#[0-9a-fA-F]{3,8}\b/g;

        // Scanning the full document content
        let text = state.doc.toString();
        let match;

        while ((match = hexRegex.exec(text)) !== null) {
            let color = match[0];
            let pos = match.index + color.length;

            let deco = Decoration.widget({
                widget: new ColorWidget(color),
                side: 1 // Places the widget right after the text
            });

            widgets.push(deco.range(pos));
        }

        return Decoration.set(widgets);
    }

    // 3. Create the StateField extension
    return StateField.define({
        create(state) {
            return getColorDecorations(state);
        },
        update(decorations, tr) {
            if (tr.docChanged) {
                return getColorDecorations(tr.state);
            }
            return decorations.map(tr.changes);
        },
        provide: f => EditorView.decorations.from(f)
    });
}