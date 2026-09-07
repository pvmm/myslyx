import { EditorState } from "@codemirror/state";
import { EditorView, basicSetup } from "codemirror";

let state = EditorState.create({
  doc: "body { color: #ff0055; background: #00ffff; }",
  extensions: [
    basicSetup,
    colorPreviewExtension // <-- Adds your custom color preview logic
  ]
});

let view = new EditorView({
  state,
  parent: document.querySelector("#editor")
});
