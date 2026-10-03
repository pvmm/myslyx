#!/usr/bin/env python3
"""Generate static/hints/lammassaari.json from Kari Lammassaari's KARI library.

Reads the Turbo Pascal 3 MSX include files (*.INC) and their companion prose
documentation (*.TXT) that Kari Lammassaari shipped with the KARI routines, and
turns them into a Myslyx hint dictionary for the "Pascal Lammassaari" dialect
(the same way tools/gen_msxgl_hints.py turns the MSXgl C engine into
msxgl.json):

  * `builtins` - every Procedure/Function declared in the includes (drives
                 autocomplete)
  * `types`    - every const, type and global var declared at file scope
                 (drives type/constant autocomplete)
  * `tips`     - per-symbol markdown (description, Pascal signature, parameters)
                 keyed by the UPPER-CASE symbol name
  * `structs`  - record types declared in the includes with their fields
  * `root`     - the HINTS panel root page: one collapsible <details> section
                 per include file (module), each listing its symbols as
                 hint: cross-links, followed by a section for the constants,
                 types and variables

Descriptions are taken from the *.TXT prose files when a symbol is covered
there (they are the richest source), then from the catalog inside the leading
`{ ... }` comment of the *.INC file, and finally from an inline comment next to
the declaration. The script is deterministic and re-runnable; re-run it after
upgrading the KARI sources.

Usage:
    python tools/gen_lammassaari_hints.py [--src <KARI dir>] [--out <hints json>]

Defaults:
    --src  ../../pascal/Lammassaari/KARI   (relative to the repo root)
    --out  myslyx/static/hints/lammassaari.json
"""

import argparse
import json
import os
import re
import sys
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Turbo Pascal keyword list, shared with static/hints/pascal.json. The KARI
# dialect is plain Turbo Pascal 3, so it keeps the plain Pascal keyword set
# (like msxgl.json keeps the plain C keyword set); base Pascal builtins/tips
# are intentionally not duplicated - switch LANG to Pascal for those.
PASCAL_KEYWORDS = [
    "program", "uses", "const", "type", "var", "label", "forward",
    "function", "procedure", "begin", "end", "if", "then", "else", "case",
    "of", "while", "do", "repeat", "until", "for", "to", "downto", "goto",
    "with", "and", "or", "not", "div", "mod", "xor", "shl", "shr", "in",
    "array", "record", "set", "file", "nil", "write", "writeln", "read",
    "readln", "external",
]

DEFAULT_SRC = os.path.normpath(
    os.path.join(ROOT, "../../pascal/Lammassaari/KARI"))

PROC_RE = re.compile(r"\b(procedure|function)\s+([A-Za-z_]\w*)", re.I)
SEC_RE = re.compile(r"(?im)^[ \t]*(const|type|var)\b")
ASSIGN_RE = re.compile(r"\s*([A-Za-z_]\w*)\s*=\s*")
END_RE = re.compile(r"(?i)\bend\b")
IDENT_TAIL_RE = re.compile(r"[A-Za-z_]\w*")
HEADING_INC_RE = re.compile(r"^[A-Za-z0-9_]+\.(inc|txt)\s*$", re.I)
HEADING_RULE_RE = re.compile(r"^[\s*=\-_#.]{3,}$")
HEADING_CAPS_RE = re.compile(r"^[A-Z][A-Z ]{7,}$")


# ---------------------------------------------------------------------------
# Comment handling
# ---------------------------------------------------------------------------

def strip_comments(text):
    """Return (clean, comments).

    `clean` has the same length and newlines as `text` with every `{...}`,
    `(*...*)` and `//...` comment blanked (so offsets stay aligned with the
    original), and `comments` is a list of (start, end, text) tuples.
    """
    out = list(text)
    comments = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "{":
            j = text.find("}", i + 1)
            end = (j + 1) if j >= 0 else n
            for k in range(i, end):
                if out[k] != "\n":
                    out[k] = " "
            comments.append((i, end, text[i + 1:j if j >= 0 else n]))
            i = end
        elif text.startswith("(*", i):
            j = text.find("*)", i + 2)
            end = (j + 2) if j >= 0 else n
            for k in range(i, end):
                if out[k] != "\n":
                    out[k] = " "
            comments.append((i, end, text[i + 2:j if j >= 0 else n]))
            i = end
        elif text.startswith("//", i):
            j = text.find("\n", i)
            end = j if j >= 0 else n
            comments.append((i, end, text[i + 2:end]))
            i = end
        else:
            i += 1
    return "".join(out), comments


def comment_at(comments, start, end, window=60):
    """First comment starting within [start, end+window], flattened to one line."""
    for cs, _ce, text in comments:
        if start <= cs <= end + window:
            flat = " ".join(text.split())
            if flat:
                return flat
    return ""


def normalize_ws(s):
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# Declaration scanning (top-level prefix)
# ---------------------------------------------------------------------------

def split_semis(body, base):
    """Split on ';' at bracket depth 0 (strings respected).

    Returns a list of (text, abs_start, abs_end).
    """
    segs = []
    depth = 0
    instr = False
    start = 0
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "'":
            instr = not instr
        elif not instr:
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth = max(0, depth - 1)
            elif ch == ";" and depth == 0:
                segs.append((body[start:i], base + start, base + i))
                start = i + 1
        i += 1
    if body[start:].strip():
        segs.append((body[start:], base + start, base + len(body)))
    return segs


def take_until_semi(body, i):
    depth = 0
    instr = False
    start = i
    while i < len(body):
        ch = body[i]
        if ch == "'":
            instr = not instr
        elif not instr:
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth = max(0, depth - 1)
            elif ch == ";" and depth == 0:
                return body[start:i]
        i += 1
    return body[start:]


def parse_const_body(body, base, comments):
    out = []
    for text, s, e in split_semis(body, base):
        m = re.match(r"\s*([A-Za-z_]\w*)\s*(?::\s*([^=]+?))?\s*=\s*(.*)",
                     text, re.S)
        if not m:
            continue
        out.append({
            "name": m.group(1),
            "value": normalize_ws(m.group(3)),
            "comment": comment_at(comments, s, e),
        })
    return out


def parse_var_body(body, base, comments):
    out = []
    for text, s, e in split_semis(body, base):
        m = re.match(
            r"\s*([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*:\s*(.+?)\s*$",
            text, re.S)
        if not m:
            continue
        vtype = re.sub(r"(?i)\s*absolute\s+.*$", "", m.group(2))
        vtype = normalize_ws(vtype)
        cmt = comment_at(comments, s, e)
        for nm in m.group(1).split(","):
            nm = nm.strip()
            if nm:
                out.append({"name": nm, "type": vtype, "comment": cmt})
    return out


def parse_record_fields(block):
    """Fields of a `Record ... End` body as (type, name, comment) triples."""
    fields = []
    for seg in block.split(";"):
        if not seg or re.search(r"(?i)\b(case|end|record)\b", seg):
            continue
        m = re.match(
            r"\s*([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*:\s*(.+?)\s*$",
            seg, re.S)
        if not m:
            continue
        ftype = normalize_ws(m.group(2))
        for nm in m.group(1).split(","):
            nm = nm.strip()
            if nm:
                fields.append([ftype, nm, ""])
    return fields


def parse_type_body(body, base, comments):
    """Parse a Type section body into type entries and record structs."""
    entries = []
    structs = OrderedDict()
    pos = 0
    while True:
        m = ASSIGN_RE.search(body, pos)
        if not m:
            break
        name = m.group(1)
        vstart = m.end()
        s = base + m.start()
        if re.match(r"(?i)record\b", body[vstart:vstart + 8].lstrip()):
            em = END_RE.search(body, vstart)
            vend = em.end() if em else len(body)
            value = normalize_ws(body[vstart:vend])
            fields = parse_record_fields(body[vstart:vend])
            entries.append({
                "name": name, "kind": "record", "value": value,
                "comment": comment_at(comments, s, base + vend),
            })
            if fields:
                structs[name] = fields
            nxt = re.match(r"\s*;", body[vend:])
            pos = vend + (nxt.end() if nxt else 0)
        else:
            piece = take_until_semi(body, vstart)
            entries.append({
                "name": name, "kind": "type",
                "value": normalize_ws(piece),
                "comment": comment_at(comments, s, base + vstart + len(piece)),
            })
            pos = vstart + len(piece)
            if pos < len(body) and body[pos] == ";":
                pos += 1
    return entries, structs


def matching_paren(s, i):
    depth = 0
    while i < len(s):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(s)


def parse_procs(clean):
    """Every Procedure/Function declaration in the cleaned source."""
    out = []
    for m in PROC_RE.finditer(clean):
        kind = m.group(1).lower()
        name = m.group(2)
        j = m.end()
        while j < len(clean) and clean[j] in " \t\r\n":
            j += 1
        params_text = ""
        if j < len(clean) and clean[j] == "(":
            end = matching_paren(clean, j)
            params_text = clean[j + 1:end - 1]
            j = end
        while j < len(clean) and clean[j] in " \t\r\n":
            j += 1
        ret = ""
        if kind == "function" and j < len(clean) and clean[j] == ":":
            semi = clean.find(";", j)
            if semi < 0:
                continue
            ret = normalize_ws(clean[j + 1:semi])
        else:
            semi = clean.find(";", j)
            if semi < 0:
                continue
        sig = normalize_ws(clean[m.start():semi + 1])
        params = []
        for group in params_text.split(";"):
            group = re.sub(r"(?i)\b(var|const)\b", "", group)
            head = group.split(":", 1)[0]
            for nm in head.split(","):
                nm = nm.strip()
                if re.fullmatch(r"[A-Za-z_]\w*", nm):
                    params.append(nm)
        out.append({
            "name": name, "kind": kind, "signature": sig,
            "params": params, "ret": ret,
        })
    return out


def first_proc_offset(clean):
    m = PROC_RE.search(clean)
    return m.start() if m else len(clean)


def parse_inc(path):
    with open(path, encoding="latin-1", errors="replace") as fh:
        raw = fh.read()
    clean, comments = strip_comments(raw)

    prefix_end = first_proc_offset(clean)
    prefix = clean[:prefix_end]

    consts, types, structs, vars = [], [], OrderedDict(), []
    for sm in SEC_RE.finditer(prefix):
        kw = sm.group(1).lower()
        start = sm.end()
        nxt = SEC_RE.search(prefix, start)
        end = nxt.start() if nxt else len(prefix)
        body = prefix[start:end]
        if kw == "const":
            consts.extend(parse_const_body(body, start, comments))
        elif kw == "var":
            vars.extend(parse_var_body(body, start, comments))
        else:
            te, st = parse_type_body(body, start, comments)
            types.extend(te)
            structs.update(st)

    procs = parse_procs(clean)

    # Leading `{ ... }` doc blocks, in order, before the first declaration.
    header_texts = []
    for cs, _ce, text in comments:
        if cs < prefix_end:
            header_texts.append(text)

    return {
        "file": os.path.basename(path),
        "header_texts": header_texts,
        "consts": consts,
        "types": types,
        "structs": structs,
        "vars": vars,
        "procs": procs,
    }


# ---------------------------------------------------------------------------
# Prose catalog extraction (TXT docs and INC header blocks)
# ---------------------------------------------------------------------------

def entry_symbol(line, known):
    s = re.sub(r"^[-*\u2022]+\s*", "", line.strip())
    s = re.split(r"\{\s*|\(\*", s, maxsplit=1)[0]
    if re.match(r"(?i)^(type|const|var)\b", s):
        return None
    m = re.search(r"(?i)\b(?:procedure|function)\s+([A-Za-z_]\w*)", s)
    if m and m.group(1).lower() in known:
        return known[m.group(1).lower()]
    m2 = re.match(r"([A-Za-z_]\w*)\s*[\(;:]", s)
    if m2 and m2.group(1).lower() in known:
        return known[m2.group(1).lower()]
    return None


def is_heading(line):
    st = line.strip()
    if not st:
        return False
    if HEADING_INC_RE.match(st) or HEADING_RULE_RE.match(st):
        return True
    if HEADING_CAPS_RE.match(st):
        return True
    return False


SOFT_HEAD_RE = re.compile(
    r"(?i)^(contains|general info|notes?|see also|example|description|"
    r"syntax|format|parameters?|returns?)\s*:?\s*$")


def signature_end(text):
    """Index just after a Procedure/Function (or bare call) signature."""
    m = re.search(r"(?i)\b(?:procedure|function)\b", text)
    base = m.end() if m else 0
    lp = text.find("(", base)
    semi = text.find(";", base)
    if lp != -1 and (semi == -1 or lp < semi):
        depth = 0
        i = lp
        while i < len(text):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        semi2 = text.find(";", i)
        return (semi2 + 1) if semi2 != -1 else (i + 1)
    if semi != -1:
        return semi + 1
    return 0


def block_description(block):
    """Description for one catalog entry from its block of lines."""
    text = "\n".join(block)
    candidates = text[signature_end(text):].split("\n")
    out = []
    for ln in candidates:
        if not ln.strip():
            if out:
                break
            continue
        s = re.sub(r"^[-*\u2022]+\s*", "", ln.strip()).strip()
        s = s.strip("{}() ,;")
        s = re.sub(r"(?i)^rem[\s.:]+", "", s).strip()
        if not s:
            continue
        if re.match(r"(?i)^rem\b", s):
            break
        if SOFT_HEAD_RE.match(s):
            continue
        if is_heading(ln) or is_heading(s):
            break
        out.append(s)
    return "\n".join(out).strip()


def collect_catalog(text, known):
    """Map symbol name -> description from prose/catalog `text`."""
    lines = text.splitlines()
    starts = []
    for idx, line in enumerate(lines):
        sym = entry_symbol(line, known)
        if sym:
            starts.append((idx, sym))
    result = OrderedDict()
    for i, (idx, sym) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(lines)
        desc = block_description(lines[idx:end])
        if desc and sym not in result and desc.strip().lower() != sym.lower():
            result[sym] = desc
    return result


def about_text(header_texts):
    """A short module blurb from the first INC doc block(s)."""
    for text in header_texts:
        paragraphs = re.split(r"\n\s*\n", text.strip())
        for para in paragraphs:
            para = " ".join(para.split())
            if not para:
                continue
            # Skip a pure catalog ("Contains: - Procedure ...").
            if re.search(r"(?i)\b(procedure|function)\b\s+\w+\s*\(", para):
                continue
            if len(para) > 400:
                para = para[:397].rstrip() + "..."
            return para
    return ""


def find_deps(text):
    deps = []
    for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\.inc\b", text, re.I):
        name = m.group(1) + ".INC"
        if name not in deps:
            deps.append(name)
    return deps


# ---------------------------------------------------------------------------
# Aggregation and rendering
# ---------------------------------------------------------------------------

def clean_entry_desc(name, text):
    t = (text or "").strip()
    if not t or t.lower() == name.lower() or re.fullmatch(r"(?i)end", t):
        return ""
    return t


def render_const_tip(entry, desc, srcfile):
    parts = ["```pascal\n%s = %s;\n```" % (entry["name"], entry["value"])]
    if desc:
        parts.append(desc)
    parts.append("*Defined in* `%s`." % srcfile)
    return "\n\n".join(parts)


def render_var_tip(entry, desc, srcfile):
    parts = ["```pascal\n%s : %s;\n```" % (entry["name"], entry["type"])]
    if desc:
        parts.append(desc)
    parts.append("*Defined in* `%s`." % srcfile)
    return "\n\n".join(parts)


def render_type_tip(entry, desc, srcfile):
    value = entry["value"]
    if entry["kind"] == "record":
        value = re.sub(r"(?i)\s*end\s*$", "", value).strip()
        parts = ["```pascal\ntype %s = %s\nEnd;\n```" %
                 (entry["name"], value)]
    else:
        parts = ["```pascal\ntype %s = %s;\n```" %
                 (entry["name"], value)]
    if desc:
        parts.append(desc)
    parts.append("*Defined in* `%s`." % srcfile)
    return "\n\n".join(parts)


def render_proc_tip(proc, desc, files):
    parts = ["```pascal\n%s\n```" % proc["signature"]]
    if desc:
        parts.append(desc)
    if proc["params"]:
        parts.append("**Parameters:**\n" +
                     "\n".join("- `%s`" % p for p in proc["params"]))
    parts.append("*Defined in* `%s`." % files[0])
    if len(files) > 1:
        parts.append("*Also defined in* " +
                     ", ".join("`%s`" % f for f in files[1:]) + ".")
    return "\n\n".join(parts)


def module_label(filename):
    base = filename[:-4] if filename.upper().endswith(".INC") else filename
    return base.replace("_", " ").title()


def root_markdown(modules, symbols, structs):
    out = [
        "# Pascal + Lammassaari\n",
        "Turbo Pascal 3 routines for MSX by **Kari Lammassaari**. The routines "
        "are grouped below by include file; expand a file to browse its "
        "procedures and functions and click a name to open its documentation. "
        "The **Constants, types &amp; variables** section lists the global "
        "symbols declared by the library. Press **F2** to return here.",
        "",
        "> Plain **Pascal** language help (writeln/readln, declarations, "
        "control flow, ...) stays available by switching LANG to **Pascal**.",
        "",
    ]
    for filename, label, about, deps, procs in modules:
        out.append("<details><summary><b>%s</b> - <code>%s</code> "
                   "(%d)</summary>" % (label, filename, len(procs)))
        out.append("")
        if about:
            out.append(about)
            out.append("")
        if deps:
            out.append("**Needs:** " +
                       ", ".join("`%s`" % d for d in deps))
            out.append("")
        for name in procs:
            out.append("- [`%s`](hint:%s)" % (name, name.upper()))
        out.append("")
        out.append("</details>")

    consts = symbols.get("consts", [])
    types = symbols.get("types", [])
    variables = symbols.get("vars", [])
    total = len(consts) + len(types) + len(variables)
    if total:
        out.append("<details><summary><b>Constants, types &amp; variables</b> "
                   "(%d)</summary>" % total)
        out.append("")
        for title, names in (("Constants", consts),
                             ("Types", types),
                             ("Variables", variables)):
            if not names:
                continue
            out.append("### %s" % title)
            out.append("")
            for name in names:
                out.append("- [`%s`](hint:%s)" % (name, name.upper()))
            out.append("")
        out.append("</details>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=DEFAULT_SRC,
                    help="KARI directory (default: %(default)s)")
    ap.add_argument("--out",
                    default=os.path.join(ROOT,
                                         "myslyx/static/hints/lammassaari.json"),
                    help="output hints JSON (default: %(default)s)")
    args = ap.parse_args()

    src = os.path.abspath(args.src)
    if not os.path.isdir(src):
        sys.exit("KARI sources not found at %s. Pass --src." % src)

    inc_files = sorted(f for f in os.listdir(src) if f.upper().endswith(".INC"))
    txt_files = sorted(f for f in os.listdir(src) if f.upper().endswith(".TXT"))

    parsed = [parse_inc(os.path.join(src, f)) for f in inc_files]

    # Symbol universe (per-file, first declaration wins).
    proc_files = OrderedDict()
    for p in parsed:
        for proc in p["procs"]:
            proc_files.setdefault(proc["name"], []).append(p["file"])
    known = {n.lower(): n for n in proc_files}

    # Records and top-level symbols also join the known set for catalog scans.
    for p in parsed:
        for t in p["types"]:
            known.setdefault(t["name"].lower(), t["name"])
        for c in p["consts"]:
            known.setdefault(c["name"].lower(), c["name"])
        for v in p["vars"]:
            known.setdefault(v["name"].lower(), v["name"])

    # Descriptions, best source first: TXT prose, then INC header catalog,
    # then inline declaration comments.
    desc = OrderedDict()

    def add_desc(name, text, priority):
        if not text:
            return
        if name not in desc or priority > desc[name][0]:
            desc[name] = (priority, text)

    for tf in txt_files:
        with open(os.path.join(src, tf), encoding="latin-1",
                  errors="replace") as fh:
            catalog = collect_catalog(fh.read(), known)
        for name, text in catalog.items():
            add_desc(name, text, 3)

    for p in parsed:
        header = "\n".join(p["header_texts"])
        for name, text in collect_catalog(header, known).items():
            add_desc(name, text, 2)

    for p in parsed:
        for entry in p["consts"] + p["vars"] + p["types"]:
            if entry.get("comment"):
                add_desc(entry["name"], entry["comment"], 1)

    # --- Tips -----------------------------------------------------------------
    tips = OrderedDict()

    def lookup_desc(name, comment):
        text = desc.get(name, (0, ""))[1] or comment
        return clean_entry_desc(name, text)

    for p in parsed:
        for entry in p["consts"]:
            key = entry["name"].upper()
            if key not in tips:
                tips[key] = render_const_tip(
                    entry, lookup_desc(entry["name"], entry.get("comment")),
                    p["file"])
        for entry in p["vars"]:
            key = entry["name"].upper()
            if key not in tips:
                tips[key] = render_var_tip(
                    entry, lookup_desc(entry["name"], entry.get("comment")),
                    p["file"])
        for entry in p["types"]:
            key = entry["name"].upper()
            if key not in tips:
                tips[key] = render_type_tip(
                    entry, lookup_desc(entry["name"], entry.get("comment")),
                    p["file"])
    proc_meta = {}
    for p in parsed:
        for proc in p["procs"]:
            proc_meta.setdefault(proc["name"], proc)
    for name, proc in proc_meta.items():
        d = desc.get(name, (0, ""))[1]
        tips[name.upper()] = render_proc_tip(proc, d, proc_files[name])

    # --- Structs (records) ----------------------------------------------------
    structs = OrderedDict()
    for p in parsed:
        for rname, fields in p["structs"].items():
            structs.setdefault(rname, fields)

    # --- Autocomplete lists ---------------------------------------------------
    builtins = list(proc_meta.keys())
    const_names, type_names, var_names = [], [], []
    symbol_names = []
    seen = {"const": set(), "type": set(), "var": set()}
    for p in parsed:
        for kind, key, bucket in (
                ("const", "consts", const_names),
                ("type", "types", type_names),
                ("var", "vars", var_names)):
            for entry in p[key]:
                n = entry["name"]
                if n.lower() not in seen[kind]:
                    seen[kind].add(n.lower())
                    bucket.append(n)
                    symbol_names.append(n)
    taken = {n.upper() for n in builtins} | {n.upper() for n in symbol_names}
    keywords = [k for k in PASCAL_KEYWORDS if k.upper() not in taken]

    # --- Root page ------------------------------------------------------------
    modules = []
    for p in parsed:
        procs = [pr["name"] for pr in p["procs"]]
        procs = list(OrderedDict.fromkeys(procs))
        about = about_text(p["header_texts"])
        deps = [d for d in find_deps(" ".join(p["header_texts"]))
                if d.upper() != p["file"].upper()]
        modules.append((p["file"], module_label(p["file"]), about, deps, procs))

    data = {
        "root": root_markdown(modules, {
            "consts": const_names,
            "types": type_names,
            "vars": var_names,
        }, structs),
        "keywords": keywords,
        "builtins": builtins,
        "types": symbol_names,
        "tips": tips,
        "patterns": [],
        "structs": structs,
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")

    print("wrote %s" % args.out)
    print("  procedures/functions: %d" % len(builtins))
    print("  constants/types/vars: %d" % len(symbol_names))
    print("  records (structs):    %d" % len(structs))
    print("  tips:                 %d" % len(tips))
    print("  modules (root page):  %d" % len(modules))


if __name__ == "__main__":
    main()
