# Hint dictionaries (`static/hints/*.json`)

The editor's hints sidebar and autocomplete popup are data-driven. Each file here
is the hint dictionary for one language. They are plain JSON, fetched by `WBHints.get()`
in `static/retro.js` and rendered by `static/hints.js` (markdown via
`static/vendor/marked.min.js`).

## How a file is chosen

`HINT_KEYS` in `pages/editor_page.py` maps a stored language value to a hint key:

| Language          | Hint file             |
|-------------------|-----------------------|
| `VBScript` (HitBasic) | `basic.json`      |
| `Text`            | `plaintext.json`      |

Any unrecognized language falls back to `plaintext`.

## Schema

```json
{
  "root": "# HitBasic\n\nCommands, functions and tips are shown as you type...",
  "keywords": ["PRINT", "INPUT"],
  "builtins": ["RND", "INT"],
  "tips": {
    "PRINT": "Output text: `PRINT \"HELLO\"`\nUse `;` to stay on the same line."
  },
  "patterns": [
    { "re": "GOTO\\s+\\d+", "tip": "Prefer loops over GOTO line numbers." }
  ]
}
```

`root` is the language's **root page** (markdown). It is shown in the HINTS panel
when a new file in that language is created, and **F2** reloads it at any time.

## Writing a help text for a keyword or builtin

1. Make sure the word is listed in `keywords` (language keyword) or `builtins`
   (builtin function), so it appears in autocomplete.
2. Add the formatted help text under `tips` with the **upper-case** name as the
   key (lookup is case-insensitive, but keep keys upper-case for consistency):

   ```json
   "tips": {
     "INPUT": "Read input: `INPUT \"NAME? \"; A$`\nStore numeric values in numeric variables."
   }
   ```

3. The text is **Markdown**. You can use `**bold**`, `*italic*`, inline code
   ``` ``code`` ```, fenced code blocks, lists and headings:

   ```json
   "FORMAT$": "Formatter, e.g. `FORMAT$(value, \"##.##\")`.\n\n```basic\n10 PRINT FORMAT$(1.5, \"#\")\n```"
   ```

   Because rendering uses `breaks: true`, a single `\n` becomes a line break —
   you don't need blank lines to separate short tips.

4. If you only add the keyword/builtin but no tip, the panel still shows a
   generic *"X is a language keyword"* / *"X is a builtin function/object"* line.

5. Newlines in JSON strings must be `\n`. If a tip must contain a literal
   backslash (e.g. inside a `patterns` regex below), escape it as `\\`.

### Pattern tips (context-based)

`patterns` shows extra context help when the current line matches `re` (a JS
`RegExp` — test the JSON value on https://regex101.com with the JavaScript
flavor). The `tip` is plain markdown:

```json
{ "re": "GOSUB\\s+\\d+", "tip": "Make sure the subroutine ends with `RETURN`." }
```

## Validation

After editing, check the file parses:

```bash
.venv/bin/python -c "import json; json.load(open('static/hints/basic.json'))"
```

Then **hard-refresh** the browser (Ctrl+Shift+R). JSON is served statically, so no
server restart is needed; the client revalidates the fetch on each load.

## Notes

- User-defined `FUNCTION`/`SUB`/`DEF FN` names are discovered from the open
  documents automatically — no dictionary entry needed for them.
- `plaintext.json` is the empty `{keywords:[],builtins:[],tips:{},patterns:[]}`
  template for new languages.