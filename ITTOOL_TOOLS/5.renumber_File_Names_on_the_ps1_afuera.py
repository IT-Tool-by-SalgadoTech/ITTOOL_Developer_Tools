#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  SalgadoTech - IT-Tool
  ittool_renumber_from_filelist.py
--------------------------------------------------------------------------------
  Purpose : Update the leading NUMBER of every script file (.ps1 / .py / .sh /
            .txt) inside a target folder so it matches the up-to-date number
            defined in file_list.txt, matching by NAME (not by old number).

  How it works:
    1. Asks for the file_list.txt path  (the SINGLE SOURCE OF TRUTH).
    2. Asks for the folder to update.
    3. Matches each file to its file_list entry by:
         a) parent folder name + normalized file name  (primary, exact)
         b) parent folder name + letter sub-index (A. B. C...) as a fallback
            ONLY when the descriptive name has drifted (reported separately).
    4. Shows a full preview, writes an audit log, and renames ONLY after you
       confirm. Names are NEVER altered - only the leading number changes.

  Notes:
    - Normalization absorbs spelling drift between file_list and the folder:
      lower-case, '&' -> 'and', and every non [a-z0-9] char ignored
      (so "SIMPLE VOLUME" == "SIMPLE_VOLUME", "Raid 0,1,5" == "Raid_0_1_5").
    - Renames are collision-safe (two phases: move to temp, then to final).
    - file_list.txt is treated as the source of truth. No old-vs-new logic.
================================================================================
"""

import os
import re
import csv
import uuid
import datetime

EXTS = (".ps1", ".py", ".sh", ".txt")


# ----------------------------------------------------------------------------- helpers
def banner():
    print()
    print("  ====================================================")
    print("   SalgadoTech  |  IT-Tool")
    print("   Renumber assistant  (file_list.txt = source of truth)")
    print("  ====================================================")
    print()


def norm_name(text):
    t = text.lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]", "", t)


def remove_known_ext(name):
    changed = True
    while changed:
        changed = False
        for e in EXTS:
            if name.lower().endswith(e):
                name = name[: -len(e)]
                changed = True
    return name


def name_parts(base_name):
    """Parse a base file name -> (number, rest, letter, norm_key)."""
    stem = remove_known_ext(base_name)
    num = None
    rest = stem
    m = re.match(r"^(\d+)\.(.*)$", stem)
    if m:
        num = m.group(1)
        rest = m.group(2)
    letter = None
    lm = re.match(r"^([A-Za-z]\d?)\.", rest)
    if lm:
        letter = lm.group(1).upper()
    return num, rest, letter, norm_name(rest)


def ask_path(message, kind):
    while True:
        p = input(message + ": ").strip().strip('"').strip("'")
        if not p:
            print("  Path cannot be empty.")
            continue
        if kind == "file" and os.path.isfile(p):
            return os.path.abspath(p)
        if kind == "folder" and os.path.isdir(p):
            return os.path.abspath(p)
        print("  Not found (or wrong type): %s" % p)


# ----------------------------------------------------------------------------- main
def main():
    banner()

    file_list_path = ask_path("  Step 1) Full path to file_list.txt", "file")
    target_folder = ask_path("  Step 2) Full path to the folder to renumber", "folder")

    print()
    print("  file_list : %s" % file_list_path)
    print("  folder    : %s" % target_folder)
    print()

    # ----- build index from file_list
    by_name = {}    # "parent|normkey" -> {num, rest, source}
    by_letter = {}  # "parent|LETTER"  -> [ {num, rest, source}, ... ]

    fl_count = 0
    with open(file_list_path, "r", encoding="utf-8-sig") as fh:
        for line in fh:
            rel = line.strip().lstrip("\ufeff")
            if not rel:
                continue
            parts = re.split(r"[\\/]", rel)
            if not parts:
                continue
            base = parts[-1]
            parent = parts[-2] if len(parts) >= 2 else ""
            num, rest, letter, nk = name_parts(base)
            if num is None:
                continue  # entries without a number are not renumber targets
            fl_count += 1

            name_key = "%s|%s" % (parent, nk)
            if name_key not in by_name:
                by_name[name_key] = {"num": num, "rest": rest, "source": rel}
            if letter:
                let_key = "%s|%s" % (parent, letter)
                by_letter.setdefault(let_key, []).append(
                    {"num": num, "rest": rest, "source": rel}
                )

    print("  Loaded %d numbered entries from file_list.txt" % fl_count)

    # ----- classify folder files
    changes = []     # exact name match, number differs
    ok_same = []     # exact name match, already correct
    letter_ops = []  # matched only by letter (name drifted) - verify
    unmatched = []
    no_number = []

    scanned = 0
    for dirpath, _dirs, filenames in os.walk(target_folder):
        for fn in filenames:
            if not fn.lower().endswith(EXTS):
                continue
            scanned += 1
            full = os.path.join(dirpath, fn)
            parent = os.path.basename(dirpath)
            num, rest, letter, nk = name_parts(fn)

            if num is None:
                no_number.append(full)
                continue

            name_key = "%s|%s" % (parent, nk)
            if name_key in by_name:
                new_num = by_name[name_key]["num"]
                rem = fn[len(num):]              # ".Tracert.ps1" (everything after old number)
                new_name = "%s%s" % (new_num, rem)
                row = {
                    "full": full, "dir": dirpath, "parent": parent,
                    "old_name": fn, "new_name": new_name,
                    "old_num": num, "new_num": new_num,
                    "method": "NAME", "source": by_name[name_key]["source"],
                }
                (ok_same if new_num == num else changes).append(row)
                continue

            if letter:
                let_key = "%s|%s" % (parent, letter)
                cands = by_letter.get(let_key, [])
                if len(cands) == 1:
                    cand = cands[0]
                    rem = fn[len(num):]
                    new_name = "%s%s" % (cand["num"], rem)
                    letter_ops.append({
                        "full": full, "dir": dirpath, "parent": parent,
                        "old_name": fn, "new_name": new_name,
                        "old_num": num, "new_num": cand["num"],
                        "method": "LETTER", "source": cand["source"],
                    })
                    continue

            unmatched.append(full)

    # ----- report
    print()
    print("  -------------------- SCAN RESULT --------------------")
    print("   Files scanned ............... %d" % scanned)
    print("   Number CHANGES (by name) .... %d" % len(changes))
    print("   Already correct ............. %d" % len(ok_same))
    print("   Matched by LETTER (verify) .. %d" % len(letter_ops))
    print("   UNMATCHED ................... %d" % len(unmatched))
    print("   No leading number (skipped) . %d" % len(no_number))
    print("  -----------------------------------------------------")

    if changes:
        print()
        print("  CHANGES TO APPLY (old -> new) :")
        for r in changes:
            print("    [%4s -> %4s]  %s\\%s" % (r["old_num"], r["new_num"], r["parent"], r["old_name"]))

    if letter_ops:
        print()
        print("  LETTER-ONLY matches (descriptive name drifted - confirm separately):")
        for r in letter_ops:
            print("    [%4s -> %4s]  zip:'%s'  file_list:'%s'" % (
                r["old_num"], r["new_num"], r["old_name"], r["source"]))

    if unmatched:
        print()
        print("  UNMATCHED (left untouched):")
        for u in unmatched:
            print("    %s" % u)

    if no_number:
        print()
        print("  NO LEADING NUMBER (left untouched):")
        for n in no_number:
            print("    %s" % n)

    # ----- audit log
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(os.getcwd(), "ITTOOL_Renumber_Log_%s.csv" % stamp)
    with open(log_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Category", "Folder", "OldName", "NewName", "OldNum", "NewNum", "Method", "FileListSource"])
        for r in changes:
            w.writerow(["CHANGE", r["parent"], r["old_name"], r["new_name"], r["old_num"], r["new_num"], r["method"], r["source"]])
        for r in letter_ops:
            w.writerow(["LETTER", r["parent"], r["old_name"], r["new_name"], r["old_num"], r["new_num"], r["method"], r["source"]])
        for r in ok_same:
            w.writerow(["OK_SAME", r["parent"], r["old_name"], r["new_name"], r["old_num"], r["new_num"], r["method"], r["source"]])
        for u in unmatched:
            w.writerow(["UNMATCHED", "", u, "", "", "", "", ""])
        for n in no_number:
            w.writerow(["NO_NUMBER", "", n, "", "", "", "", ""])
    print()
    print("  Audit log written: %s" % log_path)

    if not changes and not letter_ops:
        print()
        print("  Nothing to rename. Everything is already aligned.")
        return

    # ----- confirmation
    ops = []

    if changes:
        print()
        ans = input("  Apply the %d NAME-matched number changes? (y/N): " % len(changes)).strip().lower()
        if ans in ("y", "yes"):
            ops.extend(changes)
        else:
            print("  Name-matched changes skipped.")

    if letter_ops:
        print()
        ans2 = input("  Also apply the %d LETTER-only matches (names drifted)? (y/N): " % len(letter_ops)).strip().lower()
        if ans2 in ("y", "yes"):
            ops.extend(letter_ops)
        else:
            print("  Letter-only matches skipped.")

    if not ops:
        print()
        print("  No operations selected. No files changed.")
        return

    # ----- rename (collision-safe, two phases)
    print()
    print("  Renaming %d file(s)..." % len(ops))

    phase1 = []
    ok = 0
    fail = 0

    # Phase 1: source -> unique temp name (same directory)
    for r in ops:
        try:
            tmp = os.path.join(r["dir"], "__ITTMP__%s__%s" % (uuid.uuid4().hex, r["new_name"]))
            os.rename(r["full"], tmp)
            phase1.append({"temp": tmp, "final": os.path.join(r["dir"], r["new_name"]), "row": r})
        except Exception as ex:
            fail += 1
            print("    [FAIL p1] %s  (%s)" % (r["old_name"], ex))

    # Phase 2: temp -> final name
    for p in phase1:
        try:
            if os.path.exists(p["final"]):
                fail += 1
                print("    [CONFLICT] target exists, left as temp: %s" % p["final"])
                print("               temp file: %s" % p["temp"])
                continue
            os.rename(p["temp"], p["final"])
            ok += 1
            print("    [OK] %4s -> %4s  %s" % (p["row"]["old_num"], p["row"]["new_num"], p["row"]["new_name"]))
        except Exception as ex:
            fail += 1
            print("    [FAIL p2] %s  (%s)" % (p["row"]["new_name"], ex))

    print()
    print("  -------------------- DONE --------------------")
    print("   Renamed OK ... %d" % ok)
    print("   Failed ....... %d" % fail)
    print("   Log .......... %s" % log_path)
    print("  ----------------------------------------------")
    print()


if __name__ == "__main__":
    main()
