export default function myslyxFavicon(CM) {
    const { EditorView, Decoration, WidgetType, StateField } = CM;

    class FaviconWidget extends WidgetType {
        toDOM() {
            const wrap = document.createElement('span');
            wrap.style.display = 'inline-block';
            wrap.style.verticalAlign = 'middle';
            wrap.style.lineHeight = '1';
            wrap.style.marginRight = '0.25em';
            wrap.style.marginBottom = '0.25em';
            wrap.style.opacity = '0.9';

            const img = document.createElement('img');
            img.src = '/static/favicon.svg';
            img.alt = 'Myslyx';
            img.title = 'Myslyx';
            img.style.display = 'block';
            img.style.width = '1em';
            img.style.height = '1em';
            img.style.verticalAlign = 'middle';
            img.style.pointerEvents = 'none';

            wrap.appendChild(img);
            return wrap;
        }

        ignoreEvent() {
            return true;
        }
    }

    function getDecorations(state) {
        const widgets = [];
        const text = state.doc.toString();
        const regex = /Myslyx/g;
        let match;

        while ((match = regex.exec(text)) !== null) {
            widgets.push(
                Decoration.widget({
                    widget: new FaviconWidget(),
                    side: 1,
                    inline: true
                }).range(match.index)
            );
        }

        return Decoration.set(widgets);
    }

    return StateField.define({
        create(state) {
            return getDecorations(state);
        },
        update(decorations, tr) {
            if (tr.docChanged) {
                return getDecorations(tr.state);
            }
            return decorations.map(tr.changes);
        },
        provide: f => EditorView.decorations.from(f)
    });
}
