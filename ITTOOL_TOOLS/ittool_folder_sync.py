#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
#  SalgadoTech - IT-Tool
#  ittool_folder_sync.py
#
#  Folder-structure synchronizer.
#
#  Reads an updated "file_list.txt" (the SOURCE OF TRUTH for folder names and
#  structure) and a target folder that holds the real scripts (.ps1 / .py / .sh
#  / .txt). It compares ONLY the FOLDER names, detects what changed in each
#  folder title (position, letter, symbol) or whether a folder is new, and then
#  renames / moves / creates folders so the target matches file_list.txt.
#
#  Scripts are NEVER touched. When a folder is renamed or moved, the scripts
#  inside travel with it automatically (the folder is moved as a whole).
#
#  Matching rule:
#    Each folder name = position prefix + descriptive core.
#      A.B__Firewall_and_Security  ->  core "Firewall_and_Security"
#      A.F_Close_All_Interface_App ->  core "Close_All_Interface_App"
#      D.A.A.__Fast Process        ->  core "Fast Process"
#    The descriptive CORE is the stable identity. The prefix (letters/symbols)
#    and the position are what change. Folders are matched by core, scoped to
#    their parent (so duplicate cores in different branches never collide).
# =============================================================================

import os
import re
import sys
import shutil

# ---------------------------------------------------------------------------
# ANSI colors
# ---------------------------------------------------------------------------
if os.name == "nt":
    os.system("")  # enable ANSI on Windows 10+ consoles

RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
GREY   = "\033[90m"


def banner():
    print(CYAN + BOLD + r"""
   ____       _                 _      _____         _
  / ___|  __ _| | __ _  __ _  __| | ___|_   _|__  ___| |__
  \___ \ / _` | |/ _` |/ _` |/ _` |/ _ \ | |/ _ \/ __| '_ \
   ___) | (_| | | (_| | (_| | (_| | (_) || |  __/ (__| | | |
  |____/ \__,_|_|\__, |\__,_|\__,_|\___/ |_|\___|\___|_| |_|
                 |___/        IT-Tool  -  Folder Sync
""" + RESET)


# ---------------------------------------------------------------------------
# Name parsing
# ---------------------------------------------------------------------------
# Strip a leading position prefix: one-letter tokens joined by '.', e.g.
#   A   A.B   A.B.A   D.A.A
# followed by any run of separators ('.' or '_').
_PREFIX = re.compile(r'^[A-Z](?:\.[A-Z])*[._]+')


def core_name(folder_name: str) -> str:
    """Return the stable descriptive core of a folder name (prefix removed)."""
    stripped = _PREFIX.sub("", folder_name, count=1)
    return stripped if stripped else folder_name


# ---------------------------------------------------------------------------
# Tree models
# ---------------------------------------------------------------------------
def read_desired_tree(file_list_path: str):
    """
    Parse file_list.txt and return:
      - root_name: the top folder component used in file_list (e.g. 'ReadyUSB')
      - children: dict  parent_relpath -> list of child folder names (ordered,
                  as they appear, deduplicated)
    Only FOLDER components are used; the last component of each line (the file)
    is dropped. Paths are relative to root_name.
    """
    children = {}            # parent_rel -> [names]
    seen_under = {}          # parent_rel -> set(names)
    root_name = None

    with open(file_list_path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip().replace("\\", "/")
            if not line:
                continue
            parts = line.split("/")
            if len(parts) < 2:
                continue                       # no folder, just a bare file
            dirs = parts[:-1]                  # drop the file name
            if root_name is None:
                root_name = dirs[0]
            # register every ancestor relationship
            for i in range(1, len(dirs)):
                parent_rel = "/".join(dirs[:i])
                name = dirs[i]
                bucket = children.setdefault(parent_rel, [])
                s = seen_under.setdefault(parent_rel, set())
                if name not in s:
                    s.add(name)
                    bucket.append(name)
            # make sure leaf folders exist as keys even with no sub-folders
            children.setdefault("/".join(dirs), [])

    return root_name, children


def read_current_children(target_dir: str):
    """
    Walk the target folder and return  parent_relpath -> [child folder names].
    parent_relpath is relative to target_dir, with the target's own basename as
    the root component (to mirror file_list's 'ReadyUSB/...' layout).
    """
    root_name = os.path.basename(os.path.normpath(target_dir))
    children = {}
    for dirpath, dirnames, _files in os.walk(target_dir):
        rel = os.path.relpath(dirpath, target_dir)
        if rel == ".":
            parent_rel = root_name
        else:
            parent_rel = root_name + "/" + rel.replace(os.sep, "/")
        children.setdefault(parent_rel, [])
        for d in sorted(dirnames):
            children[parent_rel].append(d)
    return root_name, children


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------
class Plan:
    def __init__(self):
        self.renames = []   # (old_live_relpath, new_live_relpath, kind)  kind: 'letter/symbol' or 'move'
        self.creates = []   # new_live_relpath
        self.extras  = []   # current folders not present in file_list (left as-is)
        self.ambiguous = [] # (desired_relpath, [candidate origins])


def build_plan(desired_root, desired_children, target_dir):
    """
    Returns (Plan, current_root_name).
    Top-down walk of the DESIRED tree. For every desired folder we find the
    matching current folder by descriptive core, scoped to the (already matched)
    parent. We track each current folder's LIVE path so parent renames/moves are
    reflected when we reach the children.
    """
    cur_root, cur_children = read_current_children(target_dir)
    plan = Plan()

    consumed = set()        # current ORIGIN relpaths already matched

    def current_children_of(origin_parent):
        return list(cur_children.get(origin_parent, []))

    def find_match(origin_parent, desired_core):
        """Return the child NAME under origin_parent whose core matches, else None."""
        cands = [c for c in current_children_of(origin_parent)
                 if (origin_parent + "/" + c) not in consumed
                 and core_name(c) == desired_core]
        if len(cands) == 1:
            return cands[0]
        if len(cands) > 1:
            return ("AMBIG", cands)
        return None

    def find_match_global(desired_core, expected_parent_origin):
        """Global search (cross-parent move). Skip the expected parent (already tried)."""
        hits = []
        for parent_rel, names in cur_children.items():
            if parent_rel == expected_parent_origin:
                continue
            for c in names:
                origin = parent_rel + "/" + c
                if origin in consumed:
                    continue
                if core_name(c) == desired_core:
                    hits.append(origin)
        return hits

    # recurse: desired side (origin_parent = matched current parent ORIGIN path,
    # live_parent = where that parent now lives after renames)
    def walk(desired_parent_rel, origin_parent, live_parent):
        for name in desired_children.get(desired_parent_rel, []):
            desired_rel = desired_parent_rel + "/" + name
            d_core = core_name(name)
            live_target = live_parent + "/" + name

            match = find_match(origin_parent, d_core)

            if isinstance(match, tuple) and match[0] == "AMBIG":
                cand_paths = [origin_parent + "/" + c for c in match[1]]
                plan.ambiguous.append((desired_rel, cand_paths))
                # do not guess; recurse using a created path so children still sync
                plan.creates.append(live_target)
                walk(desired_rel, None, live_target)
                continue

            if match is not None:
                # matched in the expected parent (rename and/or inherited move)
                origin_child = origin_parent + "/" + match
                consumed.add(origin_child)
                # live source = live_parent + current basename (parent already moved)
                live_source = live_parent + "/" + match
                if match != name:
                    plan.renames.append((live_source, live_target, "letter/symbol"))
                walk(desired_rel, origin_child, live_target)
                continue

            # not found under the expected parent -> try a cross-parent move
            if origin_parent is not None:
                hits = find_match_global(d_core, origin_parent)
            else:
                hits = []

            if len(hits) == 1:
                origin_child = hits[0]
                consumed.add(origin_child)
                live_source = live_path_of(origin_child)
                plan.renames.append((live_source, live_target, "move"))
                walk(desired_rel, origin_child, live_target)
                continue
            elif len(hits) > 1:
                plan.ambiguous.append((desired_rel, hits))
                plan.creates.append(live_target)
                walk(desired_rel, None, live_target)
                continue

            # truly new folder
            plan.creates.append(live_target)
            walk(desired_rel, None, live_target)

    # live_path_of: resolve where an ORIGIN folder currently lives after the
    # renames recorded so far (apply the closest ancestor rename, if any).
    def live_path_of(origin):
        live = origin
        for old, new, _k in plan.renames:
            if live == old or live.startswith(old + "/"):
                live = new + live[len(old):]
        return live

    # anchor the roots together (desired root name maps to current root name)
    walk(desired_root, cur_root, cur_root)

    # report current folders never matched -> extras (left untouched)
    all_current = set()
    for parent_rel, names in cur_children.items():
        for c in names:
            all_current.add(parent_rel + "/" + c)
    plan.extras = sorted(p for p in all_current if p not in consumed)

    return plan, cur_root


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def print_report(plan: Plan):
    print(BOLD + "\n================ DRY RUN - proposed changes ================\n" + RESET)

    print(BOLD + YELLOW + f"RENAMES / MOVES ({len(plan.renames)})" + RESET)
    if not plan.renames:
        print(GREY + "  (none)" + RESET)
    for old, new, kind in plan.renames:
        tag = "MOVE  " if kind == "move" else "RENAME"
        print(f"  {YELLOW}{tag}{RESET}  {old}")
        print(f"          {GREEN}->{RESET} {new}")

    print(BOLD + CYAN + f"\nNEW FOLDERS TO CREATE ({len(plan.creates)})" + RESET)
    if not plan.creates:
        print(GREY + "  (none)" + RESET)
    for p in plan.creates:
        print(f"  {CYAN}NEW{RESET}     {p}")

    print(BOLD + GREY + f"\nLEFT UNTOUCHED - in target but not in file_list ({len(plan.extras)})" + RESET)
    if not plan.extras:
        print(GREY + "  (none)" + RESET)
    for p in plan.extras:
        print(f"  {GREY}KEEP{RESET}    {p}")

    if plan.ambiguous:
        print(BOLD + RED + f"\nAMBIGUOUS - not auto-resolved ({len(plan.ambiguous)})" + RESET)
        for desired_rel, cands in plan.ambiguous:
            print(f"  {RED}?{RESET} desired: {desired_rel}")
            for c in cands:
                print(f"      candidate: {c}")
        print(RED + "  These were NOT changed. Resolve the names and run again." + RESET)

    print(BOLD + "\n============================================================\n" + RESET)


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------
def rel_to_abs(parent_of_target: str, root_name: str, live_relpath: str) -> str:
    """live_relpath starts with root_name; map it under parent_of_target."""
    sub = live_relpath.split("/", 1)
    tail = sub[1] if len(sub) == 2 else ""
    return os.path.join(parent_of_target, root_name, *tail.split("/")) if tail \
        else os.path.join(parent_of_target, root_name)


def apply_plan(plan: Plan, target_dir: str, root_name: str):
    parent_of_target = os.path.dirname(os.path.normpath(target_dir))
    ok = err = 0

    # renames/moves are recorded top-down (parents before children) -> safe order
    for old, new, kind in plan.renames:
        src = rel_to_abs(parent_of_target, root_name, old)
        dst = rel_to_abs(parent_of_target, root_name, new)
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            print(f"  {GREEN}OK{RESET}    {kind:6s} {old} -> {new}")
            ok += 1
        except Exception as e:
            print(f"  {RED}ERR{RESET}   {kind:6s} {old} -> {new}  ({e})")
            err += 1

    for p in plan.creates:
        dst = rel_to_abs(parent_of_target, root_name, p)
        try:
            os.makedirs(dst, exist_ok=True)
            print(f"  {GREEN}OK{RESET}    NEW    {p}")
            ok += 1
        except Exception as e:
            print(f"  {RED}ERR{RESET}   NEW    {p}  ({e})")
            err += 1

    print(BOLD + f"\nDone. {GREEN}{ok} applied{RESET}, "
          + (f"{RED}{err} errors{RESET}" if err else "0 errors") + ".")
    print(GREY + "Scripts inside the folders were not touched." + RESET)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
def ask_path(prompt: str, must_be_file: bool) -> str:
    while True:
        raw = input(prompt).strip().strip('"').strip("'")
        if not raw:
            print(RED + "  Empty path. Try again." + RESET)
            continue
        path = os.path.expanduser(raw)
        if must_be_file and not os.path.isfile(path):
            print(RED + f"  Not a file: {path}" + RESET)
            continue
        if (not must_be_file) and not os.path.isdir(path):
            print(RED + f"  Not a folder: {path}" + RESET)
            continue
        return path


def main():
    banner()

    file_list_path = ask_path(BOLD + "1) Path to file_list.txt: " + RESET, must_be_file=True)
    target_dir     = ask_path(BOLD + "2) Path to the folder to update: " + RESET, must_be_file=False)

    desired_root, desired_children = read_desired_tree(file_list_path)
    if desired_root is None:
        print(RED + "file_list.txt has no folder structure to read." + RESET)
        sys.exit(1)

    target_name = os.path.basename(os.path.normpath(target_dir))
    if target_name != desired_root:
        print(YELLOW + f"\nNote: file_list root is '{desired_root}' but the target "
              f"folder is named '{target_name}'. Matching by structure under the root."
              + RESET)

    plan, cur_root = build_plan(desired_root, desired_children, target_dir)
    print_report(plan)

    if not (plan.renames or plan.creates):
        print(GREEN + "Nothing to change. The folder names already match file_list." + RESET)
        return

    answer = input(BOLD + "Apply these changes? (y/n): " + RESET).strip().lower()
    if answer != "y":
        print(GREY + "Cancelled. Nothing was changed." + RESET)
        return

    print()
    apply_plan(plan, target_dir, cur_root)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(GREY + "\nInterrupted. Nothing was changed." + RESET)
