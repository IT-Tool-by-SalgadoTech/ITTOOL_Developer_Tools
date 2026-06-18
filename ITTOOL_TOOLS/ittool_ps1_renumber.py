#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ===================================================================
#  IT-Tool by SalgadoTech
#  Script: ittool_ps1_renumber.py
#  ScriptID: ST-PY-RENUM
#  Version: 1.0
#  Date: 2025-06-17
#  Category: Tools > Maintenance > PS1 Renumbering Assistant
#  Description: Syncs the script number of every .ps1 to the number
#               held in an updated file_list.txt. Matches by name +
#               folder context (so duplicate names are disambiguated)
#               and updates THREE numeric tokens, surgically:
#                 1) the .ps1 file name leading number
#                 2) the   "  Script: <N>_Name.ps1"   header line
#                 3) the   "  ScriptID: ST-WIN-<NNNN>" header line
#  (c) 2025 SalgadoTech - All Rights Reserved
#  Unauthorized distribution prohibited
# ===================================================================
#
#  USAGE
#    Dry-run (default, writes NOTHING, shows the full plan):
#        python ittool_ps1_renumber.py file_list.txt  .\A_Windows
#
#    Apply the changes:
#        python ittool_ps1_renumber.py file_list.txt  .\A_Windows --apply
#
#    Options:
#        --apply         actually rename files and edit headers
#        --no-rename     edit headers only, do NOT rename .ps1 files
#        --report FILE   write the full plan to a CSV file
#
#  SAFETY
#    * Default mode is DRY-RUN: it only reports what it would do.
#    * Only the file name and the two header lines are ever touched.
#      Every other byte of every .ps1 is left untouched.
#    * Encoding is preserved as UTF-8 without BOM.
#    * Line endings (CRLF / LF) are preserved per file.
#    * .ps1 with no entry in the list are reported and SKIPPED.
#    * List entries with no matching .ps1 are simply ignored.
#    * Ambiguous matches (same name + same folder twice) are
#      reported and SKIPPED, never guessed.
# ===================================================================

import os
import re
import sys
import csv

# ----- ASCII color (Windows Terminal / modern consoles) ------------
class C:
    CYAN   = "\033[96m"
    DCYAN  = "\033[36m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    GREY   = "\033[90m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

def _enable_ansi_on_windows():
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)
        except Exception:
            pass

# ----- normalization helpers ---------------------------------------
_NUM_PREFIX = re.compile(r'^\s*\d+\s*[._ ]\s*')   # leading "5.", "60. ", "20_"

def norm_name(filename):
    """Canonical comparable name: drop extension, drop leading number,
    keep sub-letters (A. B. ...), lowercase, unify spaces/underscores."""
    stem = re.sub(r'\.(ps1|py|txt)$', '', filename, flags=re.IGNORECASE)
    stem = _NUM_PREFIX.sub('', stem)
    stem = stem.strip().lower()
    stem = re.sub(r'[\s]+', '_', stem)     # spaces -> underscore
    stem = re.sub(r'_+', '_', stem)        # collapse repeats
    return stem

def norm_folder(seg):
    """Canonical comparable folder segment. Strips the ordering prefix
    used on either tree:  'A.Admin_And_Security' / 'A__Admin_And_Security'
    / 'B.A.A__Ports1'  ->  'admin_and_security' / 'ports1'."""
    if '__' in seg:
        seg = seg.split('__')[-1]
    else:
        seg = re.sub(r'^(?:[A-Za-z0-9]+\.)+', '', seg)
    seg = seg.strip().lower()
    seg = re.sub(r'[\s]+', '_', seg)
    seg = re.sub(r'_+', '_', seg)
    return seg

def leading_number(filename):
    m = re.match(r'^\s*(\d+)', filename)
    return m.group(1) if m else None

# ----- file_list index ---------------------------------------------
def build_index(file_list_path):
    """Returns dict: norm_name -> list of records.
    record = {'num': '289', 'folders': [norm seg, ...], 'raw': original line}"""
    index = {}
    with open(file_list_path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip().replace("\\", "/")
            if not line or not line.lower().endswith(".txt"):
                continue
            parts = [p for p in line.split("/") if p]
            fname = parts[-1]
            num = leading_number(fname)
            if num is None:
                continue  # entries without a leading number are not renumber targets
            key = norm_name(fname)
            folders = [norm_folder(p) for p in parts[:-1]]
            index.setdefault(key, []).append(
                {"num": num, "folders": folders, "raw": line}
            )
    return index

def common_suffix_len(a, b):
    n = 0
    for x, y in zip(reversed(a), reversed(b)):
        if x == y:
            n += 1
        else:
            break
    return n

def resolve(ps1_folders, candidates):
    """Pick the best file_list record for a given .ps1.
    Returns (record, status) where status is 'ok' | 'ambiguous' | 'none'."""
    if not candidates:
        return None, "none"
    if len(candidates) == 1:
        return candidates[0], "ok"
    # multiple candidates with same name -> disambiguate by folder context
    scored = [(common_suffix_len(ps1_folders, c["folders"]), c) for c in candidates]
    scored.sort(key=lambda t: t[0], reverse=True)
    best = scored[0][0]
    winners = [c for s, c in scored if s == best]
    if len(winners) == 1:
        return winners[0], "ok"
    return None, "ambiguous"

# ----- surgical header rewriting -----------------------------------
RE_SCRIPT = re.compile(r'(Script:\s*)(\d+)([._])')
# group 1 = everything up to and including the final dash (label + family);
# group 2 = the numeric token only. The family prefix is preserved as-is.
RE_ID     = re.compile(r'(ScriptID:\s*[A-Za-z]+-[A-Za-z]+-)(\d+)')

def plan_edits(text, new_num):
    """Return (new_text, edits, found_script, found_id). Only the first
    match of each header line is touched. Labels, family prefix, spacing
    and separators are preserved; only the numeric token is swapped."""
    edits = []
    id_token = f"{int(new_num):04d}"

    def _script_sub(m):
        old = m.group(2)
        if old != new_num:
            edits.append(("Script", old, new_num))
        return f"{m.group(1)}{new_num}{m.group(3)}"

    def _id_sub(m):
        old = m.group(2)
        if old != id_token:
            edits.append(("ScriptID", old, id_token))
        return f"{m.group(1)}{id_token}"

    new_text, n1 = RE_SCRIPT.subn(_script_sub, text, count=1)
    new_text, n2 = RE_ID.subn(_id_sub, new_text, count=1)
    return new_text, edits, (n1 > 0), (n2 > 0)

# --- .py header rules ----------------------------------------------
# In .py files the same two fields appear in more than one place (top
# comment block AND inside show_header()). We reuse the SAME surgical
# logic as .ps1: ONLY the numeric token is swapped. Everything else is
# preserved exactly - separators, any "-PY" suffix, "| vX.X" version
# text, internal names, etc. Nothing other than the number is touched.
def plan_edits_py(text, new_num):
    """Renumber EVERY occurrence of Script:/ScriptID: in a .py file,
    swapping only the number. Returns (new_text, edits, found_s, found_i)."""
    edits = []
    id_token = f"{int(new_num):04d}"

    def _script_sub(m):
        old = m.group(2)
        if old != new_num:
            edits.append(("Script", old, new_num))
        return f"{m.group(1)}{new_num}{m.group(3)}"

    def _id_sub(m):
        old = m.group(2)
        if old != id_token:
            edits.append(("ScriptID", old, id_token))
        return f"{m.group(1)}{id_token}"

    new_text, n1 = RE_SCRIPT.subn(_script_sub, text)   # ALL occurrences
    new_text, n2 = RE_ID.subn(_id_sub, new_text)        # ALL occurrences
    return new_text, edits, (n1 > 0), (n2 > 0)

# ----- interactive helpers (when launched with no CLI arguments) ----
def _clean_path(s):
    # accepts drag-and-drop paths (which arrive wrapped in quotes)
    return s.strip().strip('"').strip("'").strip()

def _ask(prompt, default=""):
    try:
        v = input(prompt).strip()
    except EOFError:
        v = ""
    return v if v else default

def _pause():
    try:
        input("\n  Press Enter to exit...")
    except EOFError:
        pass

# ----- main ---------------------------------------------------------
def main():
    _enable_ansi_on_windows()
    args = sys.argv[1:]
    apply_changes = "--apply" in args
    no_rename     = "--no-rename" in args

    report_path = None
    positional = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--report":
            report_path = args[i + 1]; i += 2; continue
        if a in ("--apply", "--no-rename"):
            i += 1; continue
        positional.append(a); i += 1

    interactive = len(positional) < 2

    if not interactive:
        file_list_path, ps1_root = positional[0], positional[1]
    else:
        # No CLI arguments (e.g. launched from a .txt launcher / double-click).
        # Ask everything interactively, the same way the other IT-Tool scripts do.
        print(f"{C.CYAN}  =================================================================={C.RESET}")
        print(f"{C.CYAN}  IT-Tool by SalgadoTech  -  PS1 Renumbering Assistant v1.1{C.RESET}")
        print(f"{C.DCYAN}  Interactive mode (no arguments given).{C.RESET}")
        print(f"{C.DCYAN}  Tip: you can DRAG & DROP a file/folder onto the window to paste its path.{C.RESET}")
        print(f"{C.CYAN}  =================================================================={C.RESET}\n")

        # 1) file_list path (re-ask until valid)
        while True:
            file_list_path = _clean_path(_ask(f"{C.CYAN}  Enter file_list.txt path : {C.RESET}"))
            if file_list_path and os.path.isfile(file_list_path):
                break
            print(f"{C.RED}  File not found, try again (or close the window to cancel).{C.RESET}")

        # 2) PS1 root folder (re-ask until valid)
        while True:
            ps1_root = _clean_path(_ask(f"{C.CYAN}  Enter PS1 root folder    : {C.RESET}"))
            if ps1_root and os.path.isdir(ps1_root):
                break
            print(f"{C.RED}  Folder not found, try again (or close the window to cancel).{C.RESET}")

        # 3) options
        ans = _ask(f"{C.CYAN}  Apply changes now? (y = write / Enter = dry-run) : {C.RESET}").lower()
        apply_changes = ans in ("y", "yes", "s", "si")
        ren = _ask(f"{C.CYAN}  Rename .ps1 files too? (Enter = yes / n = no)    : {C.RESET}").lower()
        no_rename = ren in ("n", "no")
        rep = _clean_path(_ask(f"{C.CYAN}  Save CSV report? (path, or Enter to skip)      : {C.RESET}"))
        report_path = rep or None
        print()

    if not os.path.isfile(file_list_path):
        print(f"{C.RED}ERROR: file_list not found: {file_list_path}{C.RESET}")
        if interactive: _pause()
        sys.exit(1)
    if not os.path.isdir(ps1_root):
        print(f"{C.RED}ERROR: ps1 root not found: {ps1_root}{C.RESET}")
        if interactive: _pause()
        sys.exit(1)

    # banner
    print(f"{C.CYAN}  =================================================================={C.RESET}")
    print(f"{C.CYAN}  IT-Tool by SalgadoTech  -  PS1 Renumbering Assistant v1.1{C.RESET}")
    print(f"{C.DCYAN}  Mode: {'APPLY (writing changes)' if apply_changes else 'DRY-RUN (no changes)'}"
          f"   Rename files: {'NO' if no_rename else 'YES'}{C.RESET}")
    print(f"{C.CYAN}  =================================================================={C.RESET}\n")

    if interactive and apply_changes:
        conf = _ask(f"{C.YELLOW}  This WILL modify files. Type 'yes' to continue: {C.RESET}").lower()
        if conf not in ("yes", "y", "si", "s"):
            print(f"{C.DCYAN}  Cancelled - switching to DRY-RUN (no changes).{C.RESET}\n")
            apply_changes = False

    index = build_index(file_list_path)

    self_name = os.path.basename(os.path.abspath(__file__)).lower()
    targets = []
    for root, _, files in os.walk(ps1_root):
        for f in files:
            low = f.lower()
            if (low.endswith(".ps1") or low.endswith(".py")) and low != self_name:
                targets.append(os.path.join(root, f))
    targets.sort()

    rows = []   # for report / summary
    n_changed = n_same = n_unmatched = n_ambig = n_noheader = 0

    for path in targets:
        fname = os.path.basename(path)
        is_py = fname.lower().endswith(".py")
        rel   = os.path.relpath(path, ps1_root).replace("\\", "/")
        folders = [norm_folder(p) for p in os.path.dirname(rel).split("/") if p]
        key   = norm_name(fname)
        rec, status = resolve(folders, index.get(key, []))

        if status == "none":
            n_unmatched += 1
            rows.append([rel, "", "", "UNMATCHED", ""])
            print(f"{C.GREY}  [skip] no list entry : {rel}{C.RESET}")
            continue
        if status == "ambiguous":
            n_ambig += 1
            rows.append([rel, "", "", "AMBIGUOUS", ""])
            print(f"{C.YELLOW}  [ambiguous] cannot disambiguate, SKIPPED : {rel}{C.RESET}")
            continue

        new_num = rec["num"]
        old_num = leading_number(fname)

        # --- read bytes, decode utf-8, surgical header rewrite -------
        raw = open(path, "rb").read()
        had_bom = raw[:3] == b"\xef\xbb\xbf"
        text = raw.decode("utf-8-sig") if had_bom else raw.decode("utf-8")
        if is_py:
            new_text, edits, has_s, has_i = plan_edits_py(text, new_num)
        else:
            new_text, edits, has_s, has_i = plan_edits(text, new_num)

        if not (has_s or has_i):
            n_noheader += 1
            rows.append([rel, old_num, new_num, "NO-HEADER", ""])
            print(f"{C.YELLOW}  [warn] header lines not found, SKIPPED : {rel}{C.RESET}")
            continue

        # --- target file name (swap leading number, or prepend it) ---
        new_fname = fname
        if not no_rename:
            if old_num is not None:
                if old_num != new_num:
                    new_fname = re.sub(r'^\s*\d+', new_num, fname, count=1)
            else:
                new_fname = f"{new_num}.{fname}"   # no number yet -> prepend
        rename_needed = (new_fname != fname)

        will_change = bool(edits) or rename_needed
        detail = "; ".join(f"{w}:{o}->{n}" for w, o, n in edits)
        if rename_needed:
            detail = (f"file:{old_num or '(none)'}->{new_num}; " + detail).strip("; ")

        if not will_change:
            n_same += 1
            rows.append([rel, old_num, new_num, "OK (already)", ""])
            print(f"{C.GREEN}  [ok] already correct : {rel}{C.RESET}")
            continue

        n_changed += 1
        rows.append([rel, old_num, new_num, "CHANGE", detail])
        tag = "applied" if apply_changes else "would change"
        print(f"{C.CYAN}  [{tag}] {rel}{C.RESET}")
        print(f"{C.DCYAN}        {detail}{C.RESET}")

        if apply_changes:
            # write header edits first (UTF-8, no BOM, newlines preserved)
            with open(path, "wb") as fh:
                fh.write(new_text.encode("utf-8"))
            # then rename if needed
            if rename_needed:
                new_path = os.path.join(os.path.dirname(path), new_fname)
                if os.path.exists(new_path) and os.path.abspath(new_path) != os.path.abspath(path):
                    print(f"{C.RED}        ERROR: target name exists, rename skipped: {new_fname}{C.RESET}")
                    rows[-1][3] = "RENAME-CONFLICT"
                else:
                    os.rename(path, new_path)

    # ----- summary -------------------------------------------------
    print(f"\n{C.CYAN}  =================================================================={C.RESET}")
    print(f"{C.BOLD}  SUMMARY{C.RESET}")
    print(f"{C.CYAN}    Renumbered (changed) : {n_changed}{C.RESET}")
    print(f"{C.GREEN}    Already correct      : {n_same}{C.RESET}")
    print(f"{C.GREY}    Unmatched (skipped)  : {n_unmatched}{C.RESET}")
    print(f"{C.YELLOW}    Ambiguous (skipped)  : {n_ambig}{C.RESET}")
    print(f"{C.YELLOW}    No header (skipped)  : {n_noheader}{C.RESET}")
    print(f"{C.DCYAN}    Total scanned (.ps1+.py): {len(targets)}{C.RESET}")
    if not apply_changes:
        print(f"\n{C.YELLOW}  DRY-RUN: nothing was written.{C.RESET}")
        if interactive:
            print(f"{C.YELLOW}  Run again and answer 'y' at 'Apply changes now?' to commit.{C.RESET}")
        else:
            print(f"{C.YELLOW}  Re-run with --apply to commit.{C.RESET}")
    print(f"{C.CYAN}  =================================================================={C.RESET}")

    if report_path:
        with open(report_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["relative_path", "old_num", "new_num", "status", "detail"])
            w.writerows(rows)
        print(f"{C.DCYAN}  Report written: {report_path}{C.RESET}")

    if interactive:
        _pause()

if __name__ == "__main__":
    main()
