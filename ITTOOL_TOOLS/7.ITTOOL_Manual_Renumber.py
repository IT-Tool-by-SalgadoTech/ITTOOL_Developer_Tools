#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =====================================================================
#   ___ _____   _____ ___   ___  _
#  |_ _|_   _| |_   _/ _ \ / _ \| |
#   | |  | |     | || | | | | | | |
#   | |  | |     | || |_| | |_| | |___
#  |___| |_|     |_| \___/ \___/|_____|
#
#   ITTOOL MANUAL RENUMBER  -  SalgadoTech
#   Realigns script reference numbers in the Word manual (.docx)
#   to match the current file_list.txt of the ITTOOL SD library.
# ---------------------------------------------------------------------
#   Logic:
#     - file_list.txt holds the CORRECT (current) numbers.
#     - The manual references each script as  <number>.<name> <desc>.
#     - When new scripts are inserted, numbers shift; names DO NOT.
#     - Match key = parent folder + normalized script name
#       (the number is exactly what changes, so it is NOT the key).
#     - Only the leading number of each entry is rewritten.
#       Names, descriptions, examples and all formatting are kept.
#     - DRY-RUN first (report). Nothing is written until you confirm.
#     - Output is ALWAYS a NEW file; the original is never modified.
# =====================================================================

import os
import re
import sys
import copy
import shutil
import difflib

# ---------------------------------------------------------------------
# Colors (ANSI). Works on Linux and on Windows 10+ terminals.
# ---------------------------------------------------------------------
class C:
    R = "\033[91m"   # red
    G = "\033[92m"   # green
    Y = "\033[93m"   # yellow
    B = "\033[96m"   # cyan
    W = "\033[97m"   # white
    D = "\033[90m"   # dim
    X = "\033[0m"    # reset

if os.name == "nt":
    os.system("")  # enable ANSI on Windows consoles

def cprint(color, text):
    print(color + text + C.X)

# ---------------------------------------------------------------------
# Dependency: python-docx  (auto-installed the first time if missing)
# ---------------------------------------------------------------------
def _load_docx():
    import importlib
    try:
        d = importlib.import_module("docx")
        p = importlib.import_module("docx.text.paragraph")
        return d.Document, p.Paragraph
    except ImportError:
        return None, None

Document, Paragraph = _load_docx()

if Document is None:
    cprint(C.Y, "[setup] 'python-docx' is missing. Installing it now (one time)...")
    import subprocess
    ok = False
    for args in (
        [sys.executable, "-m", "pip", "install", "python-docx"],
        [sys.executable, "-m", "pip", "install", "--user", "python-docx"],
    ):
        try:
            subprocess.check_call(args)
            ok = True
            break
        except Exception:
            continue
    import importlib
    importlib.invalidate_caches()
    Document, Paragraph = _load_docx()
    if Document is None:
        cprint(C.R, "[ERROR] Could not install 'python-docx' automatically.")
        cprint(C.Y, "        Run this command once, then start the script again:")
        cprint(C.W, "          pip install python-docx")
        input("\nPress Enter to exit...")
        sys.exit(1)
    cprint(C.G, "[setup] 'python-docx' ready.\n")

# ---------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------
def banner():
    cprint(C.B, "=" * 62)
    cprint(C.W, "         ITTOOL MANUAL RENUMBER  -  SalgadoTech")
    cprint(C.D, "   Align manual script numbers with file_list.txt (SD)")
    cprint(C.B, "=" * 62)

# ---------------------------------------------------------------------
# Normalization: turn any script name into a comparable key.
#   - lowercase
#   - drop a trailing .txt
#   - any run of separators  _  .  -  spaces  -> single space
#   - collapse + strip
# ---------------------------------------------------------------------
def normalize(name):
    s = name.strip()
    if s.lower().endswith(".txt"):
        s = s[:-4]
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)   # parentheses, $, ', +, commas -> space
    s = re.sub(r"\s+", " ", s).strip()
    return s

# Split a leaf "<number><sep><rest>"  ->  (number:int, rest:str)
# Returns (None, leaf) if it has no leading number.
NUM_RE = re.compile(r"^\s*(\d+)\s*[._]?\s*(.*)$", re.DOTALL)

def split_number(text):
    m = NUM_RE.match(text)
    if not m:
        return None, text.strip()
    return int(m.group(1)), m.group(2).strip()

# ---------------------------------------------------------------------
# Parse file_list.txt  ->  index keyed by (parent_folder, norm_name)
#   value = list of dicts {number, leaf, path}
# Also collects: duplicate numbers, key collisions, entries w/o number.
# ---------------------------------------------------------------------
def parse_file_list(path):
    index = {}          # norm_name -> [entry, ...]   (global, folder-independent)
    order = []          # entries in file order (for placing missing scripts)
    by_number = {}      # number -> [path, ...]   (to detect dup numbers)
    no_number = []      # leaves without a leading number
    total = 0

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip().replace("\\", "/")
            if not line:
                continue
            parts = line.split("/")
            leaf = parts[-1]
            parent = parts[-2] if len(parts) >= 2 else ""
            num, rest = split_number(leaf)
            if num is None:
                no_number.append(line)
                continue
            total += 1
            # human title = leaf without trailing .txt and without the number
            title = leaf[:-4] if leaf.lower().endswith(".txt") else leaf
            _, title = split_number(title)
            norm = normalize(rest)
            entry = {"number": num, "leaf": leaf, "path": line, "title": title,
                     "parent": parent, "norm": norm}
            index.setdefault(norm, []).append(entry)
            order.append(entry)
            by_number.setdefault(num, []).append(line)

    # longest names first so longest-prefix wins during matching
    names = sorted(index.keys(), key=len, reverse=True)
    dup_numbers = {n: p for n, p in by_number.items() if len(p) > 1}
    collisions = {k: v for k, v in index.items() if len(v) > 1}
    return {
        "index": index,
        "order": order,
        "names": names,
        "total": total,
        "no_number": no_number,
        "dup_numbers": dup_numbers,
        "collisions": collisions,
    }


# Folder-name comparison (manual heading vs file_list parent folder).
# Used only to disambiguate names that collide in file_list.
def folder_norm(text):
    s = normalize(text)
    if s.startswith("inside "):
        s = s[7:]
    return s


def folder_similarity(a, b):
    return difflib.SequenceMatcher(None, folder_norm(a), folder_norm(b)).ratio()

# ---------------------------------------------------------------------
# Manual paragraph helpers
# ---------------------------------------------------------------------
def para_text(p):
    return "".join(r.text for r in p.runs)

def is_heading_style(p):
    try:
        name = (p.style.name or "")
    except Exception:
        name = ""
    return name.startswith("Heading")

def is_toc_style(p):
    try:
        name = (p.style.name or "")
    except Exception:
        name = ""
    return name.startswith("TOC") or name.startswith("Contents")

# Find the run that holds the leading digits and rewrite only the number.
def set_entry_number(p, new_number):
    for r in p.runs:
        if r.text and r.text.strip():
            if re.match(r"^\s*\d+", r.text):
                r.text = re.sub(r"^(\s*)\d+", r"\g<1>" + str(new_number), r.text, count=1)
                return True
            return False  # first non-empty run does not start with a number
    return False

# ---------------------------------------------------------------------
# "Empty" placeholder handling
#   An entry whose description (text after "<number><name>") is blank
#   OR exactly the word "Empty" is treated as still-empty / a stub.
# ---------------------------------------------------------------------
PLACEHOLDER = "Empty"
W14 = "{http://schemas.microsoft.com/office/word/2010/wordml}"

def is_placeholder_desc(desc):
    d = (desc or "").strip().strip(".").strip().lower()
    return d == "" or d == PLACEHOLDER.lower()

# Build a new script paragraph "<number>.<title>  Empty" by cloning a
# template paragraph from the SAME section, so colors / fonts / shading
# match. Only the text changes; styling is inherited. The clone is then
# inserted before or after a reference paragraph.
def make_stub(template_para, number, title, ref_para, where):
    new_p = copy.deepcopy(template_para._p)
    # drop the unique paragraph ids so Word can regenerate them
    for attr in (W14 + "paraId", W14 + "textId"):
        if new_p.get(attr) is not None:
            del new_p.attrib[attr]
    # never let a stub be a heading-styled paragraph
    pPr = new_p.find("w:pPr", new_p.nsmap)
    if pPr is not None:
        pStyle = pPr.find("w:pStyle", new_p.nsmap)
        if pStyle is not None:
            val = pStyle.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val", "")
            if val.startswith("Heading"):
                pPr.remove(pStyle)

    if where == "after":
        ref_para._p.addnext(new_p)
    else:
        ref_para._p.addprevious(new_p)
    np = Paragraph(new_p, ref_para._parent)

    runs = np.runs
    if runs:
        runs[0].text = "%d.%s" % (number, title)   # number + title (styled)
        if len(runs) >= 2:
            runs[1].text = "  " + PLACEHOLDER         # reuse colored run
            for r in runs[2:]:                        # drop old description
                r._r.getparent().remove(r._r)
        else:
            r = np.add_run("  " + PLACEHOLDER)
    else:
        np.add_run("%d.%s" % (number, title))
        np.add_run("  " + PLACEHOLDER)
    return np

# ---------------------------------------------------------------------
# Match a manual entry against file_list by normalized NAME (global,
# folder-independent), using the LONGEST word-boundary name prefix.
# If that name collides in file_list (e.g. Windows/Linux twins), the
# winner is chosen by folder-name similarity, then by closeness to the
# manual's OLD number. Returns (entry, "ok") | (None, reason).
# ---------------------------------------------------------------------
def match_entry(heading, norm_text, old_num, fl):
    names = fl["names"]
    index = fl["index"]

    best_name = None
    for fnorm in names:                       # names sorted longest-first
        if not fnorm:
            continue
        if norm_text == fnorm or norm_text.startswith(fnorm + " "):
            best_name = fnorm
            break
    if best_name is None:
        return None, "no-match"

    entries = index[best_name]
    if len(entries) == 1:
        return entries[0], "ok"

    # Collision (e.g. Windows/Linux twins). Strongest signal first:
    # if the manual entry's CURRENT number already equals one of the
    # candidates, keep it -> makes repeated runs converge (idempotent).
    for e in entries:
        if e["number"] == old_num:
            return e, "ok"

    # Otherwise disambiguate. Score = (folder_similarity, -|new-old|)
    scored = []
    for e in entries:
        fsim = folder_similarity(heading, e["parent"])
        dist = abs(e["number"] - old_num)
        scored.append((fsim, -dist, e))
    scored.sort(reverse=True)
    best = scored[0]
    second = scored[1]

    # Confident only if the top candidate clearly wins on folder match,
    # or (folders inconclusive) it clearly wins on number proximity.
    fsim_gap = best[0] - second[0]
    dist_gap = abs(best[1] - second[1])
    if fsim_gap >= 0.10 or (best[0] >= 0.55 and fsim_gap > 0.0) or \
       (fsim_gap < 0.05 and dist_gap >= 3):
        return best[2], "ok"
    return None, "ambiguous-collision"

# ---------------------------------------------------------------------
# Walk the document, build the change plan.
# ---------------------------------------------------------------------
def build_plan(doc, fl):
    plan = {"changes": [], "unchanged": [], "unmatched": [], "ambiguous": [],
            "anomalies": [], "present": {}, "placeholders": 0}
    current_parent = ""
    heading_stack = []  # (level, text)

    for p in doc.paragraphs:
        text = para_text(p).strip()
        if not text:
            continue

        if is_toc_style(p):
            continue

        num, rest = split_number(text)

        # --- Folder heading: heading-styled AND does NOT start with a number
        if num is None and is_heading_style(p):
            # determine level from style name "Heading N"
            m = re.search(r"(\d+)", p.style.name or "")
            level = int(m.group(1)) if m else 99
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, text))
            current_parent = text  # immediate folder = this heading text
            continue

        # --- Script entry: text starts with a number
        if num is not None:
            norm_text = normalize(rest)
            entry, status = match_entry(current_parent, norm_text, num, fl)
            record = {"parent": current_parent, "old": num,
                      "name": rest[:60], "para": p}
            if status == "ok":
                record["new"] = entry["number"]
                record["path"] = entry["path"]
                plan["present"][entry["path"]] = p
                # description = manual text after the matched file_list name
                desc = norm_text[len(entry["norm"]):]
                if is_placeholder_desc(desc):
                    plan["placeholders"] += 1
                if entry["number"] == num:
                    plan["unchanged"].append(record)
                else:
                    plan["changes"].append(record)
            elif status.startswith("ambiguous"):
                record["reason"] = status
                plan["ambiguous"].append(record)
            else:
                # Best-effort suggestion (NEVER auto-applied) so the
                # name drift between manual and SD can be reconciled.
                cand = difflib.get_close_matches(norm_text.split(" desc")[0],
                                                 fl["names"], n=1, cutoff=0.6)
                if not cand:
                    short = " ".join(norm_text.split()[:6])
                    cand = difflib.get_close_matches(short, fl["names"],
                                                     n=1, cutoff=0.5)
                if cand:
                    sug = fl["index"][cand[0]][0]
                    record["suggest"] = f"#{sug['number']} {sug['leaf']}"
                else:
                    record["suggest"] = "(no close name in file_list)"
                plan["unmatched"].append(record)
            continue
        # else: ordinary prose paragraph -> ignore

    return plan

# ---------------------------------------------------------------------
# Missing scripts = numbered file_list entries that are NOT present in
# the manual. Returned in file_list order so they can be placed next to
# their existing neighbours (keeps them in the right section / order).
# ---------------------------------------------------------------------
def compute_missing(fl, plan):
    present = plan["present"]
    return [e for e in fl["order"] if e["path"] not in present]

# Insert one "<number>.<title>  Empty" paragraph per missing script,
# anchored to the nearest existing neighbour in file_list order.
def create_missing(fl, plan):
    present = plan["present"]
    created = 0
    anchor = None        # last present-or-inserted paragraph
    pending_first = []   # missing entries that precede the very first present one

    for e in fl["order"]:
        if e["path"] in present:
            para = present[e["path"]]
            # flush any leading missing entries before the first present para
            for me in pending_first:
                stub = make_stub(para, me["number"], me["title"], para, "before")
                created += 1
            pending_first = []
            anchor = para
            continue
        # missing entry
        if anchor is None:
            pending_first.append(e)
        else:
            stub = make_stub(anchor, e["number"], e["title"], anchor, "after")
            anchor = stub
            created += 1
    return created

# ---------------------------------------------------------------------
# ORDER BY SCRIPT NUMBER
#   After renumbering, lay every entry out in ascending script-number
#   order (1, 2, 3, ...), grouped under its section heading. file_list
#   numbers are the source of truth. Existing headings are reused; a
#   section heading is created only when the manual has entries for a
#   folder but no heading for it (so the numeric list stays labeled).
#   Replaces the neighbour-anchored placement of create_missing.
# ---------------------------------------------------------------------
WP_TAG = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"

def _folder_segments(path):
    return tuple(path.replace("\\", "/").split("/")[:-1])

def _clone_heading(donor_p, text):
    new_p = copy.deepcopy(donor_p)
    for attr in (W14 + "paraId", W14 + "textId"):
        if new_p.get(attr) is not None:
            del new_p.attrib[attr]
    np = Paragraph(new_p, None)
    for r in list(np.runs):
        r._r.getparent().remove(r._r)
    np.add_run(text)
    return new_p

def reorder_by_number(doc, fl, plan):
    present = plan["present"]
    body = doc.element.body

    # entries in ascending SCRIPT-NUMBER order (this is the whole point)
    seq = sorted(fl["order"], key=lambda e: (e["number"], e["path"]))

    headings = []
    for p in doc.paragraphs:
        if is_heading_style(p):
            m = re.search(r"(\d+)", p.style.name or "")
            headings.append([int(m.group(1)) if m else 5, para_text(p).strip(), p, False])
    if not headings:                          # no structure -> classic behavior
        return create_missing(fl, plan)

    # every folder (and its ancestors) the manual needs
    needed, seen = [], set()
    for e in seq:
        ft = _folder_segments(e["path"])
        for k in range(1, len(ft) + 1):
            if ft[:k] not in seen:
                seen.add(ft[:k]); needed.append(ft[:k])

    # assign each folder a heading: reuse by name, else mark to synthesize
    assign = {}
    for sub in needed:
        name = sub[-1]; best, bi = -1.0, None
        for i, h in enumerate(headings):
            if h[3]:
                continue
            s = folder_similarity(name, h[1])
            if s > best:
                best, bi = s, i
        if bi is not None and best >= 0.55:
            headings[bi][3] = True
            assign[sub] = ("reuse", headings[bi][2]._p)
        else:
            assign[sub] = ("new", name)

    donor = max(headings, key=lambda h: h[0])[2]._p
    generic_tmpl = None
    folder_tmpl = {}
    for e in seq:
        if e["path"] in present:
            if generic_tmpl is None:
                generic_tmpl = present[e["path"]]
            folder_tmpl.setdefault(_folder_segments(e["path"]), present[e["path"]])

    target, emitted, created = [], set(), 0

    def ensure_heading(ft):
        for k in range(1, len(ft) + 1):
            sub = ft[:k]
            if sub in emitted:
                continue
            emitted.add(sub)
            kind, payload = assign[sub]
            target.append(payload if kind == "reuse" else _clone_heading(donor, payload))

    for e in seq:
        ft = _folder_segments(e["path"])
        ensure_heading(ft)
        if e["path"] in present:
            p = present[e["path"]]
            set_entry_number(p, e["number"])
            target.append(p._p)
        else:
            tmpl = folder_tmpl.get(ft) or generic_tmpl
            if tmpl is None:
                continue
            stub = make_stub(tmpl, e["number"], e["title"], tmpl, "after")
            target.append(stub._p); created += 1

    # re-anchor the whole ordered sequence right after the intro
    children = list(body.iterchildren())
    first_idx = children.index(headings[0][2]._p)
    anchor = children[first_idx - 1]
    target_ids = set(id(el) for el in target)
    for el in target:
        anchor.addnext(el); anchor = el

    # keep any leftover paragraph (unmatched entries, duplicates) at the end
    for el in [c for c in children[first_idx:]
               if c.tag == WP_TAG and id(c) not in target_ids]:
        anchor.addnext(el); anchor = el

    return created

# ---------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------
def report(plan, fl, missing):
    cprint(C.B, "\n----------------------  DRY RUN  ----------------------")
    print(f"  file_list scripts (numbered) : {C.W}{fl['total']}{C.X}")
    print(f"  Present in manual            : {C.W}{len(plan['present'])}{C.X}")
    print(f"  Entries to RENUMBER          : {C.Y}{len(plan['changes'])}{C.X}")
    print(f"  Already correct             : {C.G}{len(plan['unchanged'])}{C.X}")
    print(f"  Missing -> CREATE as 'Empty' : {C.B}{len(missing)}{C.X}")
    print(f"  Existing 'Empty' stubs       : {C.D}{plan['placeholders']}{C.X}")
    print(f"  UNMATCHED (need review)     : {C.R}{len(plan['unmatched'])}{C.X}")
    print(f"  AMBIGUOUS (need review)     : {C.R}{len(plan['ambiguous'])}{C.X}")

    if fl["dup_numbers"]:
        cprint(C.R, "\n  [!] Duplicate numbers inside file_list.txt:")
        for n, paths in sorted(fl["dup_numbers"].items()):
            cprint(C.D, f"      #{n}:")
            for pth in paths:
                cprint(C.D, f"         {pth}")

    if plan["changes"]:
        cprint(C.Y, "\n  Proposed number changes:")
        for r in plan["changes"]:
            print(f"   {C.D}[{r['parent']}]{C.X}")
            print(f"     {C.R}{r['old']:>4}{C.X} -> {C.G}{r['new']:<4}{C.X}  {r['name']}")

    if missing:
        cprint(C.B, f"\n  New 'Empty' entries to create ({len(missing)}):")
        for e in missing[:25]:
            print(f"     {C.G}{e['number']:>4}{C.X}.  {e['title']}  {C.D}Empty{C.X}")
        if len(missing) > 25:
            cprint(C.D, f"     ... and {len(missing) - 25} more")

    if plan["unmatched"]:
        cprint(C.R, "\n  Unmatched manual entries (left UNCHANGED):")
        for r in plan["unmatched"]:
            print(f"     {r['old']:>4}.  {r['name']}   {C.D}[{r['parent']}]{C.X}")
            print(f"           {C.Y}closest in file_list: {r.get('suggest','')}{C.X}")

    if plan["ambiguous"]:
        cprint(C.R, "\n  Ambiguous manual entries (left UNCHANGED):")
        for r in plan["ambiguous"]:
            print(f"     {r['old']:>4}.  {r['name']}   {C.D}({r['reason']}) [{r['parent']}]{C.X}")

    cprint(C.B, "-------------------------------------------------------")

# ---------------------------------------------------------------------
# Apply: first renumber existing entries, then create the missing ones.
# Always writes to a NEW file; the original is never modified.
# ---------------------------------------------------------------------
def apply_changes(doc, plan, fl, docx_path):
    n = 0
    for r in plan["changes"]:
        if set_entry_number(r["para"], r["new"]):
            n += 1
        else:
            cprint(C.R, f"   [skip] could not locate number run for: {r['name']}")
    created = reorder_by_number(doc, fl, plan)
    base, ext = os.path.splitext(docx_path)
    out = base + "_renumbered" + ext
    doc.save(out)
    return out, n, created

# ---------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------
def ask_path(prompt, must_end=None):
    while True:
        raw = input(C.W + prompt + C.X).strip().strip('"').strip("'")
        if not raw:
            cprint(C.R, "   Path cannot be empty.")
            continue
        raw = os.path.expanduser(raw)
        if not os.path.isfile(raw):
            cprint(C.R, f"   File not found: {raw}")
            continue
        if must_end and not raw.lower().endswith(must_end):
            cprint(C.R, f"   File must end with {must_end}")
            continue
        return raw

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main():
    banner()
    docx_path = ask_path("\n[1] Path to the manual .docx : ", ".docx")
    list_path = ask_path("[2] Path to file_list.txt    : ", ".txt")

    cprint(C.D, "\nReading file_list.txt ...")
    fl = parse_file_list(list_path)
    cprint(C.G, f"   {fl['total']} numbered scripts indexed.")
    if fl["no_number"]:
        cprint(C.D, f"   ({len(fl['no_number'])} entries without a number ignored, e.g. Non_CommercialScripts)")

    cprint(C.D, "Reading manual ...")
    doc = Document(docx_path)

    plan = build_plan(doc, fl)
    missing = compute_missing(fl, plan)
    report(plan, fl, missing)

    if not plan["changes"] and not missing:
        cprint(C.G, "\nNothing to do. The manual is already aligned and complete.")
        input("\nPress Enter to exit...")
        return

    cprint(C.Y, "\nApply to a NEW file?")
    cprint(C.D, f"  - renumber {len(plan['changes'])} existing entries")
    cprint(C.D, f"  - create {len(missing)} new 'Empty' entries")
    cprint(C.D, "  (the original .docx is NOT modified; descriptions are never erased)")
    ans = input(C.W + "Type 'yes' to apply: " + C.X).strip().lower()
    if ans not in ("yes", "y"):
        cprint(C.R, "Cancelled. No file written.")
        input("\nPress Enter to exit...")
        return

    out, n, created = apply_changes(doc, plan, fl, docx_path)
    cprint(C.G, f"\nDone. {n} numbers updated, {created} new 'Empty' entries created.")
    cprint(C.W, f"Saved: {out}")
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        cprint(C.R, "\nInterrupted.")
    except Exception as e:
        cprint(C.R, f"\n[ERROR] {e}")
        input("\nPress Enter to exit...")
