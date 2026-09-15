#!/usr/bin/env python3
"""Generate static/hints/msxgl.json from the MSXgl engine sources.

Reads every MSXgl header (engine/src/**/*.h) and turns the Natural Docs style
function comments into a Myslyx hint dictionary:

  * `builtins`    - all MSXgl function names (drives autocomplete)
  * `types`       - every enum, struct and union declared in the headers
                    (documented or not) plus their enum constant names
                    (drives type autocomplete)
  * `tips`        - per-function markdown (description, C signature, params,
                    return value), keyed by the UPPER-CASE function name
  * `root`        - the HINTS panel root page: one collapsible <details>
                    section per module (header file), each listing its
                    functions as hint: cross-links, followed by a separate
                    <details> section for the enums, structs and unions
                    declared by the engine

The tip for every function whose signature uses an enum or struct also lists
that type as a hint: cross-link to its own documentation page.  Additionally,
angle-bracket references like <VDP_MODE> in descriptions are automatically
converted to hint: links whenever the referenced symbol is documented.

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

# SDCC compiler keywords/extensions (only valid for the MSXgl C dialect, so
# they are appended to the msxgl.json keyword list after C_KEYWORDS; c.json for
# plain C keeps the standard C set). Includes the MSXgl engine's own __-prefixed
# conventions (macros such as __NAKED are widely used in example code even
# though they are defined elsewhere).
SDCC_KEYWORDS = [
    "__asm", "__endasm", "__at", "__sfr", "__naked",
    "__z88dk_fastcall", "__sdcccall", "__sdcc_call_hl", "__sdcc_call_iy",
    "__data", "__xdata", "__idata", "__pdata", "__sdata", "__code", "__bit",
    "__critical", "__interrupt", "__using", "__reentrant", "__small",
    "__large", "__packed", "__aligned", "__signed", "__unsigned",
    "__NAKED", "__PRESERVES", "__FASTCALL", "__CALLEE",
]


def _msxgl_keywords(builtin_names, type_names):
    """Keyword list for msxgl.json: standard C + SDCC, minus anything already
    offered as a builtin or type (a name can only complete once)."""
    taken = set(builtin_names) | set(type_names)
    return C_KEYWORDS + [kw for kw in SDCC_KEYWORDS if kw not in taken]

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
_NOT_DECL = ("typedef", "enum", "struct", "union", "register", "define", "static assert")
_ENUM_DOC_RE = re.compile(r"^\s*//\s*Enum:\s*(\w+)")
_ENUM_HEAD_RE = re.compile(r"^(?://\s*)?enum\s+(\w+)\s*\{?$")
_TYPEDEF_AGG_RE = re.compile(r"^\s*typedef\s+(struct|union)\s*(.*)$")
_STRUCT_HEAD_RE = re.compile(r"^\s*struct\s+(\w+)\s*\{?$")
_UNION_HEAD_RE = re.compile(r"^\s*union\s+(\w+)\s*\{?$")
_STRUCT_CLOSE_RE = re.compile(r"^\s*}\s*(\w+)\s*;")
_STRUCT_BARE_CLOSE_RE = re.compile(r"^\s*}\s*;")
_STRUCT_FIELD_RE = re.compile(r"^([^/;{}]+?)\s+(\w+(?:\s*\[[^\]]*\])?(?:\s*:\s*\d+)?)\s*;(.*)")


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


# ---------------------------------------------------------------------------
# Enum / struct parsing
# ---------------------------------------------------------------------------

def _strip_comment(s):
    """Remove trailing C-style comment from a source line."""
    i = s.find("//")
    if i >= 0:
        s = s[:i]
    return s.rstrip()


def parse_types_from_file(path):
    """Extract enum and struct definitions from one header file.

    Returns list of dicts:
        { kind, name, desc, members, srcfile }
    where
        kind    'enum' or 'struct'
        name    the typedef/tag name (e.g. 'VDP_MODE', 'PSG_Data')
        desc    list of description strings (from doc comments)
        members for enums:  [(const_name, value_str, comment), ...]
                for structs: [(field_type, field_name, comment), ...]
        srcfile the relative header path
    """
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()

    types = []
    n = len(lines)
    rel = os.path.basename(path)

    i = 0
    while i < n:
        s = lines[i]

        # --- Enum with doc comment: // Enum: NAME ----------------------------------
        em = _ENUM_DOC_RE.match(s)
        if em:
            name = em.group(1)
            desc = []
            i += 1
            # grab description lines until the enum block starts
            while i < n:
                ln = lines[i].strip()
                if _ENUM_HEAD_RE.match(ln):
                    break
                if ln.startswith("//"):
                    text = ln.lstrip("/").strip()
                    if text:
                        desc.append(text)
                elif ln:
                    break
                i += 1
            members, end = _parse_enum(lines, i)
            types.append({"kind": "enum", "name": name, "desc": desc,
                          "members": members, "srcfile": rel})
            i = end
            continue

        # --- Plain enum (no doc comment): enum NAME { … } --------------------------
        em2 = _ENUM_HEAD_RE.match(s)
        if em2:
            name = em2.group(1)
            members, end = _parse_enum(lines, i)
            types.append({"kind": "enum", "name": name, "desc": [],
                          "members": members, "srcfile": rel})
            i = end
            continue

        # --- typedef (struct|union) NAME { … } NAME;  or  { … } Name; -----------------
        am = _TYPEDEF_AGG_RE.match(s)
        if am:
            kind = am.group(1)
            rest = am.group(2).rstrip()
            desc = _struct_desc_above(lines, i)
            named = re.match(r"^([A-Za-z_]\w*)\s*\{?\s*$", rest)
            anonymous = (not rest) or rest.lstrip().startswith("{")
            if named or anonymous:
                members, end, tname = _parse_struct_body(lines, i)
                if members is not None:
                    if named:
                        tname = named.group(1)
                    if tname:
                        types.append({"kind": kind, "name": tname, "desc": desc,
                                      "members": members, "srcfile": rel})
                i = end
            else:
                i += 1
            continue

        # --- struct NAME { … };  (plain tag, no typedef) ----------------------------
        shm = _STRUCT_HEAD_RE.match(s)
        if shm:
            name = shm.group(1)
            desc = _struct_desc_above(lines, i)
            members, end, _alias = _parse_struct_body(lines, i)
            types.append({"kind": "struct", "name": name, "desc": desc,
                          "members": members, "srcfile": rel})
            i = end
            continue

        # --- union NAME { … };  (plain tag, no typedef) -----------------------------
        uhm = _UNION_HEAD_RE.match(s)
        if uhm:
            name = uhm.group(1)
            desc = _struct_desc_above(lines, i)
            members, end, _alias = _parse_struct_body(lines, i)
            types.append({"kind": "union", "name": name, "desc": desc,
                          "members": members, "srcfile": rel})
            i = end
            continue

        i += 1

    return types


def _struct_desc_above(lines, brace_line):
    """Collect doc comment lines immediately above a struct definition."""
    desc = []
    j = brace_line - 1
    while j >= 0:
        ln = lines[j].strip()
        if ln.startswith("//"):
            text = ln.lstrip("/").strip()
            if text and not text.startswith("=") and len(text) > 1:
                desc.insert(0, text)
            j -= 1
        elif not ln:
            j -= 1
        else:
            break
    return desc


def _parse_enum(lines, start):
    """Parse an enum body starting at its definition line.

    Supports real C bodies (`enum NAME { ... };`) and bodies that are
    commented out inside a doc block (`// enum NAME`, `// {`, `// X,`).
    Returns (members, index_after_closing_semicolon).
    """
    n = len(lines)
    commented = lines[start].lstrip().startswith("//")

    # Locate the opening brace line.
    open_idx = None
    j = start
    while j < n:
        ln = lines[j]
        if commented:
            ln = ln.lstrip().lstrip("/")
        if "{" in ln:
            open_idx = j
            break
        j += 1
    if open_idx is None:
        return [], start + 1

    members = []
    depth = 0
    k = open_idx
    while k < n:
        ln = lines[k]
        if commented:
            ln = ln.lstrip().lstrip("/")
        depth += ln.count("{") - ln.count("}")
        if depth <= 0:
            break  # this is the closing brace line
        code, _, cmt = ln.partition("//")
        cmt = cmt.strip()
        text = code.strip().rstrip(",").strip()
        if not text or text in ("}", "};"):
            k += 1
            continue
        for part in text.split(","):
            part = part.strip()
            if not part or part in ("}", "};"):
                continue
            cm = re.match(r"^(\w+)(?:\s*=\s*(.*))?$", part)
            if cm:
                cname = cm.group(1)
                cval = cm.group(2).strip() if cm.group(2) else ""
                members.append((cname, cval, cmt))
        k += 1

    # Scan past the closing `};` (real or commented).
    while k < n:
        ln = lines[k]
        if commented:
            ln = ln.lstrip().lstrip("/")
        if re.match(r"^\s*}\s*;", ln):
            return members, k + 1
        k += 1
    return members, k


def _parse_struct_body(lines, start):
    """Parse struct (or union) fields starting at the `typedef struct NAME` line.

    Locates the opening brace line first (it may be on the same line or the
    next one) so brace depth starts at zero. Stops at the matching closing
    `}` and returns (members, index_after_closing_semicolon_line, alias)
    where alias is the typedef name written after the closing `}`, or None
    when the block ends with a bare `};` (plain tag, no typedef).
    """
    n = len(lines)
    open_idx = None
    j = start
    while j < n:
        if "{" in lines[j]:
            open_idx = j
            break
        j += 1
    if open_idx is None:
        return None, start + 1, None

    members = []
    depth = 0
    i = open_idx
    while i < n:
        ln = lines[i]
        depth += ln.count("{") - ln.count("}")
        if depth <= 0:
            break
        stripped = ln.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            i += 1
            continue
        # Skip extern declarations and function pointers that are global variables.
        code, _, cmt = ln.partition("//")
        cmt = cmt.strip().lstrip("/").strip()
        # Try to match: TYPE FIELDNAME; or TYPE FIELDNAME[...]; or TYPE FIELDNAME : bits;
        clean = _strip_comment(stripped).rstrip()
        if not clean or clean in ("{", "};"):
            i += 1
            continue
        # Remove trailing ;
        if clean.endswith(";"):
            clean = clean[:-1].rstrip()
        fm = _STRUCT_FIELD_RE.match(clean + ";")
        if fm:
            ftype = fm.group(1).strip()
            fname_raw = fm.group(2).strip()
            # Skip extern declarations and function pointer typedefs.
            if ftype.startswith("extern") or "(" in fname_raw:
                i += 1
                continue
            members.append((ftype, fname_raw, cmt))
        i += 1

    # find the closing } NAME; line (or a bare }; for plain tags)
    for j in range(open_idx, min(open_idx + 500, n)):
        cm = _STRUCT_CLOSE_RE.match(lines[j])
        if cm:
            return members, j + 1, cm.group(1)
        if _STRUCT_BARE_CLOSE_RE.match(lines[j]):
            return members, j + 1, None
    return members, i + 1, None


def collect_types(src):
    """Walk all headers under src and return a dict name -> type info."""
    all_types = OrderedDict()
    for rel in scandir_files(src):
        path = os.path.join(src, rel)
        for t in parse_types_from_file(path):
            if t["name"] not in all_types:
                all_types[t["name"]] = t
    return all_types


def type_tip_markdown(t):
    """Render a type's tip (enum or struct)."""
    parts = []
    if t["kind"] == "enum":
        parts.append("```c\nenum %s {\n%s\n};\n```" % (
            t["name"],
            "\n".join("    %s%s%s" % (
                m[0],
                (" = " + m[1]) if m[1] else "",
                (",  // " + m[2]) if m[2] else ",")
                for m in t["members"]) if t["members"] else "    /* ... */"))
    else:
        fields = t["members"]
        body = "\n".join("    %s %s;" % (m[0], m[1]) for m in fields) if fields else "    /* ... */"
        keyword = "union" if t["kind"] == "union" else "struct"
        parts.append("```c\ntypedef %s %s {\n%s\n} %s;\n```" %
                     (keyword, t["name"], body, t["name"]))
    if t["desc"]:
        parts.append("\n".join(t["desc"]))
    # members with comments (only if at least one has a comment)
    if t["kind"] == "enum" and any(m[2] for m in t["members"]):
        lines = ["**Constants:**"]
        for m in t["members"]:
            val = " = %s" % m[1] if m[1] else ""
            cmt = " — %s" % m[2] if m[2] else ""
            lines.append("- `%s%s`%s" % (m[0], val, cmt))
        parts.append("\n".join(lines))
    elif t["kind"] in ("struct", "union") and any(m[2] for m in t["members"]):
        lines = ["**Fields:**"]
        for m in t["members"]:
            cmt = " — %s" % m[2] if m[2] else ""
            lines.append("- `%s %s`%s" % (m[0], m[1], cmt))
        parts.append("\n".join(lines))
    src = t.get("srcfile", "")
    if src:
        parts.append("*Defined in* `%s`." % src)
    return "\n\n".join(parts)


def render_type_links(type_names):
    """Render a markdown line of links to referenced types, or '' if none."""
    if not type_names:
        return ""
    parts = []
    for tn in sorted(type_names):
        parts.append("[`%s`](hint:%s)" % (tn, tn.upper()))
    return "**Types:** " + "  ".join(parts)


_ANGLE_TOKEN_RE = re.compile(r"<([A-Za-z_]\w*)>")


def _link_angle_refs(text, all_tip_keys):
    """Convert <NAME> tokens to hint: links when NAME is a documented symbol."""
    parts = re.split(r"(```[\s\S]*?```|`[^`]+`)", text)
    for i, seg in enumerate(parts):
        if i % 2 == 0:
            parts[i] = _ANGLE_TOKEN_RE.sub(
                lambda m: ("[`%s`](hint:%s)" % (m.group(1), m.group(1).upper()))
                if m.group(1).upper() in all_tip_keys
                else m.group(0),
                seg)
    return "".join(parts)


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
        return (os.path.basename(p).lower(), p.lower())

    modules = []
    for rel in sorted(by_path, key=key):
        base = os.path.basename(rel)
        label = MODULE_LABELS.get(base[:-2] if base.endswith(".h") else base,
                                  base[:-2].replace("_", " ").title())
        modules.append((label, rel, list(by_path[rel].items())))
    return modules


def tip_markdown(doc, referenced_types=None):
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
    if referenced_types:
        parts.append(render_type_links(referenced_types))
    return "\n\n".join(parts)


def root_markdown(modules, all_doc_enums=None, all_doc_structs=None,
                  all_doc_unions=None):
    """Render the root page: module sections followed by a Types section."""
    out = [
        "# MSXgl (C + engine)\n",
        "MSXgl engine API reference for MSX MSX1/MSX2/MSX2+, compiled with "
        "the **SDCC** C compiler (Small Device C Compiler). Functions are "
        "grouped by module - expand a module to browse its functions and click "
        "a function to open its documentation. The **Types** section lists the "
        "enums, structs and unions declared by the engine. Press **F2** to "
        "return here.",
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
    # Types section (every type declared by the engine)
    enum_list = sorted(all_doc_enums or [])
    struct_list = sorted(all_doc_structs or [])
    union_list = sorted(all_doc_unions or [])
    if enum_list or struct_list or union_list:
        total = len(enum_list) + len(struct_list) + len(union_list)
        out.append("<details><summary><b>Types</b> - enums, structs &amp; "
                   "unions (%d)</summary>" % total)
        out.append("")
        if enum_list:
            out.append("### Enums")
            out.append("")
            for name in enum_list:
                out.append("- [`%s`](hint:%s)" % (name, name.upper()))
            out.append("")
        if struct_list:
            out.append("### Structs")
            out.append("")
            for name in struct_list:
                out.append("- [`%s`](hint:%s)" % (name, name.upper()))
            out.append("")
        if union_list:
            out.append("### Unions")
            out.append("")
            for name in union_list:
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

    # --- Types (enums + structs + unions) ---------------------------------------
    # Every type declared in the headers is available to the autocomplete
    # system, whether or not it appears in a documented function or macro.
    all_types = collect_types(src)
    all_doc_types = set(all_types.keys())
    all_doc_enums = sorted(n for n, t in all_types.items()
                           if t["kind"] == "enum")
    all_doc_structs = sorted(n for n, t in all_types.items()
                             if t["kind"] == "struct")
    all_doc_unions = sorted(n for n, t in all_types.items()
                            if t["kind"] == "union")

    # Enum constant names are globally-scoped values; they must autocomplete
    # alongside the type names that own them.
    enum_const_names = set()
    for t in all_types.values():
        if t["kind"] == "enum":
            for m in t.get("members") or []:
                if m[0]:
                    enum_const_names.add(m[0])
    all_symbol_names = sorted(all_doc_types | enum_const_names)

    # Per-function: which types does each signature reference?
    fn_type_map = {}
    for name, doc in all_names.items():
        sig = doc.get("signature") or ""
        if not sig:
            continue
        refs = set()
        for tn in all_doc_types:
            if re.search(r"\b" + re.escape(tn) + r"\b", sig):
                refs.add(tn)
        if refs:
            fn_type_map[name] = sorted(refs)

    # --- Tips (functions + types) ---------------------------------------------
    tips = OrderedDict()
    for name, doc in all_names.items():
        tips[name.upper()] = tip_markdown(doc, fn_type_map.get(name))
    for tn in all_doc_types:
        tips[tn.upper()] = type_tip_markdown(all_types[tn])

    # Convert <NAME> tokens to hint: links for every documented symbol.
    all_tip_keys = set(tips.keys())
    for key in list(tips.keys()):
        tips[key] = _link_angle_refs(tips[key], all_tip_keys)

    # Base structs map: every parsed struct and union (documented or not) with
    # its members as [type, field, comment] triples. Drives the c-struct-complete
    # plugin's ". / ->" member autocomplete; keeping undocumented types lets
    # nested member resolution (a.b.c) work even for internal-only types.
    structs = {
        n: [[ftype, fname, cmt] for (ftype, fname, cmt) in (t.get("members") or [])]
        for n, t in all_types.items() if t["kind"] in ("struct", "union")
    }

    data = {
        "root": root_markdown(modules, all_doc_enums, all_doc_structs,
                              all_doc_unions) or "# MSXgl",
        "keywords": _msxgl_keywords(all_names.keys(), all_symbol_names),
        "builtins": list(all_names.keys()),
        "types": all_symbol_names,
        "tips": tips,
        "patterns": [],
        "structs": structs,
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")

    print("wrote %s" % args.out)
    print("  functions: %d builtins, %d tips" % (len(data["builtins"]),
                                                  len(all_names)))
    print("  types: %d enums, %d structs, %d unions (%d total)" % (
        len(all_doc_enums), len(all_doc_structs), len(all_doc_unions),
        len(all_doc_types)))
    print("  modules: %d (root page)" % len(modules))


if __name__ == "__main__":
    main()