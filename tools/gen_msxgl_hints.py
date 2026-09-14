#!/usr/bin/env python3
"""Generate static/hints/msxgl.json from the MSXgl engine sources.

Reads every MSXgl header (engine/src/**/*.h) and turns the Natural Docs style
function comments into a Myslyx hint dictionary:

  * `builtins`    - all MSXgl function names (drives autocomplete)
  * `tips`        - per-function markdown (description, C signature, params,
                    return value), keyed by the UPPER-CASE function name
  * `root`        - the HINTS panel root page: one collapsible <details>
                    section per module (header file), each listing its
                    functions as hint: cross-links

It is deterministic and re-runnable, so it can be re-run whenever the MSXgl
sources are upgraded (independent of MSXgl's own Natural Docs build).

Usage:
    python tools/gen_msxgl_hints.py [--src <msxgl engine/src>] [--out <hints json>]

Defaults:
    --src  ../../msx/msxgl/engine/src        (relative to the repo root)
    --out  myslyx/static/hints/msxgl.json
"""

import argparse
import json
import os
import re
import sys
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# C language keywords shared with static/hints/c.json.
C_KEYWORDS = [
    "auto", "break", "case", "char", "const", "continue", "default",
    "do", "double", "else", "enum", "extern", "float", "for", "goto",
    "if", "inline", "int", "long", "register", "restrict", "return",
    "short", "signed", "sizeof", "static", "struct", "switch",
    "typedef", "union", "unsigned", "void", "volatile", "while",
]

# Human-friendly module labels shown on the root page.
MODULE_LABELS = {
    "psg": "PSG",
    "vdp": "VDP",
    "v9990": "V9990",
    "bios": "BIOS",
    "dos": "DOS",
    "scc": "SCC",
    "msx-music": "MSX-Music",
    "msx-audio": "MSX-Audio",
    "vdp_inl": "VDP (inline)",
    "fixed_point": "Fixed-point",
    "memory_mapper": "Memory mapper",
    "input_manager": "Input manager",
    "sprite_fx": "Sprite FX",
    "basic_usr": "BASIC USR",
    "game_pawn": "Game pawn",
    "dos_mapper": "DOS mapper",
    "bios_hook": "BIOS hooks",
    "rom_mapper": "ROM mapper",
    "system_port": "System ports",
}

_FUNC_RE = re.compile(r"^\s*//\s*Function:\s*(\w+)")
_DECL_OK = re.compile(r"^[^#].*\(")
_NOT_DECL = ("typedef", "enum", "struct", "union", "register", "define", "static assert")


def scandir_files(src):
    """Yield relative paths of all *.h files under src in deterministic order."""
    found = []
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames.sort()
        for fn in sorted(filenames):
            if fn.endswith(".h"):
                found.append(os.path.relpath(os.path.join(dirpath, fn), src))
    found.sort(key=lambda p: (os.sep in p, p.lower()))
    return found


def parse_params(lines):
    """Parse Natural Docs parameter lines '//   name - description'."""
    out = []
    for line in lines:
        stripped = line.strip(" \t-")
        if not stripped:
            continue
        m = re.match(r"^(\S+)\s+-\s?(.*)$", stripped)
        if m:
            out.append((m.group(1), m.group(2)))
        else:
            out.append((stripped, ""))
    return out


def parse_file(path):
    """Return ordered dict name -> doc dict for one header.

    doc keys: desc (list of lines), params (list of (name, desc)),
              ret (list of lines), signature (str or None).
    """
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()

    docs = OrderedDict()
    i = 0
    n = len(lines)
    while i < n:
        m = _FUNC_RE.match(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(1)
        desc = []
        params = []
        ret = []
        notes = []
        section = None
        sig = None
        j = i + 1
        while j < n and lines[j].lstrip().startswith("//"):
            text = lines[j].lstrip().lstrip("/").strip()
            if text.startswith("Function:"):
                break
            low = text.lower()
            if low in ("parameters:", "params:", "parameter:"):
                section = "params"
                j += 1
                continue
            if low in ("return:", "returns:"):
                section = "ret"
                j += 1
                continue
            if low in ("notes:", "note:"):
                section = "notes"
                j += 1
                continue
            # A commented-out declaration inside the doc block
            # (`// inline void Foo(...) { ... }`) is used as the signature.
            if "(" in text and text.endswith("}") and not text.startswith("-"):
                sig = text.split("{", 1)[0].rstrip() + ";"
                j += 1
                continue
            if section == "params":
                params.append(text)
            elif section == "ret":
                ret.append(text)
            elif section == "notes":
                notes.append(text)
            elif text:
                desc.append(text)
            j += 1

        signature = sig or _find_signature(lines, j)
        docs[name] = {
            "desc": desc,
            "params": parse_params(params),
            "ret": [t.strip(" \t-") for t in ret if t.strip(" \t-")],
            "notes": [t.strip(" \t-*") for t in notes if t.strip(" \t-*")],
            "signature": signature,
        }
        i = j
    return docs


def _find_signature(lines, start):
    """Best effort: the C declaration or macro that follows a doc block.

    Handles single-line prototypes (`u8 Foo(u8 a);`), single-line inline
    bodies (`inline void Foo() { g = 1; }`), multi-line declarations
    (`u16 Foo(\n  u8 a) { ... }`) and `#define` macros (`#define FOO()`).
    Returns the signature with the body stripped, or None.
    """
    n = len(lines)
    k = start
    buf = []
    while k < min(start + 12, n):
        ln = lines[k]
        if ln.startswith("//"):
            k += 1
            continue
        if not ln.strip():
            k += 1
            continue
        s = ln.strip()
        # #define macros — capture as-is (including line continuations).
        if not buf and s.startswith("#define"):
            define = s
            while define.endswith("\\") and k + 1 < n:
                define = define[:-1].rstrip() + " " + lines[k + 1].strip()
                k += 1
            return define if len(define) < 200 else define[:200]
        if ln.lstrip().startswith("#"):
            return None
        if s.startswith(_NOT_DECL):
            return None
        if not buf and "(" not in s:
            return None  # first meaningful line is not a declaration
        buf.append(s)
        merged = " ".join(buf)
        if merged.endswith(";"):
            return merged
        if merged.endswith("{"):
            return merged[:-1].rstrip() + ";"
        if merged.endswith("}"):
            if "{" not in merged:
                return None
            return merged.split("{", 1)[0].rstrip() + ";"
        if len(merged) > 200:
            return None
        k += 1
    return None


def merge(parsed, module_priority):
    """Merge per-file docs into a single OrderedDict, dropping duplicates.

    Duplicates are resolved by module priority (top-level headers win over
    subdirectories, and the first header of a module wins).
    """
    merged = OrderedDict()
    for rel, docs in parsed:
        if rel.rstrip("/").startswith("deprecated"):
            continue
        for name, doc in docs.items():
            if name not in merged:
                merged[name] = dict(doc)
    return merged


def split_modules(parsed, all_names):
    """Return ordered list of (module_label, relpath, [(name, doc)...])."""
    by_path = OrderedDict()
    for rel, docs in parsed:
        if rel.rstrip("/").startswith("deprecated"):
            continue
        for name, doc in docs.items():
            if name not in all_names:
                continue
            by_path.setdefault(rel, OrderedDict())[name] = doc

    def key(p):
        return (os.sep in p, p.lower())

    modules = []
    for rel in sorted(by_path, key=key):
        base = os.path.basename(rel)
        label = MODULE_LABELS.get(base[:-2] if base.endswith(".h") else base,
                                  base[:-2].replace("_", " ").title())
        modules.append((label, rel, list(by_path[rel].items())))
    return modules


def tip_markdown(doc):
    """Render one function's tip (shown in the HINTS panel)."""
    parts = []
    desc = "\n".join(doc["desc"]).strip()
    sig = doc["signature"]
    if sig:
        parts.append("```c\n%s\n```" % sig)
    if desc:
        parts.append(desc)
    if doc["params"]:
        lines = ["**Parameters:**"]
        for name, d in doc["params"]:
            if d:
                lines.append("- `%s` - %s" % (name, d))
            else:
                lines.append("- `%s`" % name)
        parts.append("\n".join(lines))
    if doc["ret"]:
        parts.append("**Return:**\n" + "\n".join("- %s" % r for r in doc["ret"]))
    if doc["notes"]:
        parts.append("**Notes:**\n" + "\n".join("- %s" % r for r in doc["notes"]))
    return "\n\n".join(parts)


def root_markdown(modules):
    """Render the root page: one collapsible details section per module."""
    out = [
        "# MSXgl (C + engine)\n",
        "MSXgl engine API reference for MSX MSX1/MSX2/MSX2+, compiled with "
        "the **SDCC** C compiler (Small Device C Compiler). Functions are "
        "grouped by module - expand a module to browse its functions and click "
        "a function to open its documentation. Press **F2** to return here.",
        "",
        "> Plain **C** language help (printf/scanf, stdlib, ...) stays "
        "> available by switching LANG to **C**.",
        "",
    ]
    for label, rel, funcs in modules:
        count = len(funcs)
        out.append("<details><summary><b>%s</b> - <code>%s</code> (%d)</summary>" %
                   (label, rel, count))
        out.append("")
        for name, doc in funcs:
            out.append("- [`%s`](hint:%s)" % (name, name.upper()))
        out.append("")
        out.append("</details>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=os.path.normpath(os.path.join(ROOT, "../../msx/msxgl/engine/src")),
                    help="MSXgl engine/src directory (default: %(default)s)")
    ap.add_argument("--out", default=os.path.join(ROOT, "myslyx/static/hints/msxgl.json"),
                    help="output hints JSON (default: %(default)s)")
    args = ap.parse_args()

    src = os.path.abspath(args.src)
    if not os.path.isdir(src):
        sys.exit("MSXgl sources not found at %s. Pass --src." % src)

    parsed = []
    for rel in scandir_files(src):
        docs = parse_file(os.path.join(src, rel))
        if docs:
            parsed.append((rel, docs))

    all_names = merge(parsed, None)
    modules = split_modules(parsed, all_names)

    tips = OrderedDict((name.upper(), tip_markdown(doc))
                       for name, doc in all_names.items())

    data = {
        "root": root_markdown(modules) or "# MSXgl",
        "keywords": C_KEYWORDS,
        "builtins": list(all_names.keys()),
        "tips": tips,
        "patterns": [],
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")

    print("wrote %s" % args.out)
    print("  functions: %d builtins, %d tips" % (len(data["builtins"]), len(tips)))
    print("  modules: %d (root page)" % len(modules))


if __name__ == "__main__":
    main()