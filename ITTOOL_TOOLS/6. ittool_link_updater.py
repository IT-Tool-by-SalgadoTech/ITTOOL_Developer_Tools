#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
#  SalgadoTech  -  IT-Tool  ReadyUSB Link Updater
# ----------------------------------------------------------------------------
#  Asks three things:
#    1) the folder (or .zip) with the scripts to correct
#    2) where to save the corrected copy
#    3) the updated repository link  (the source of the real files)
#
#  Matching is done by the FILE NUMBER. Every script starts with a unique
#  number (e.g. 55.BIOS.txt); the tool finds the repository file with that
#  same number and rewrites the embedded GitHub link to point to it. Files
#  that have no number (special runners) keep the target their link already
#  names, validated against the repository.
#
#  Only the URL changes; every other byte of each script is preserved
#  (encoding and line endings). The original folder is never modified.
#
#  Standard library only. No third party dependencies.
# ============================================================================

import os
import re
import shutil
import tarfile
import tempfile
import urllib.parse
import urllib.request

EXEC_EXTS = (".ps1", ".py", ".sh")

BANNER = r"""
  ____        _                       _____         _
 / ___|  __ _| | __ _  __ _  __| | ___|_   _|__  ___| |__
 \___ \ / _` | |/ _` |/ _` |/ _` |/ _ \ | |/ _ \/ __| '_ \
  ___) | (_| | | (_| | (_| | (_| | (_) || |  __/ (__| | | |
 |____/ \__,_|_|\__, |\__,_|\__,_|\___/ |_|\___|\___|_| |_|
                |___/      IT-Tool  -  ReadyUSB Link Updater
"""


# ----------------------------------------------------------------------------
# Parse the repository link the user provides (any GitHub URL form works)
# ----------------------------------------------------------------------------
def parse_repo_link(link):
    """Return (owner, repo, ref). Accepts plain repo URLs and tree/blob URLs
    like .../owner/repo/tree/<branch-or-commit>/path."""
    m = re.search(r"github\.com/([^/]+)/([^/]+)", link)
    if not m:
        raise ValueError("That does not look like a GitHub link.")
    owner = m.group(1)
    repo = m.group(2).rstrip("/")
    ref_m = re.search(r"/(?:tree|blob|raw)/([^/]+)", link)
    ref = ref_m.group(1) if ref_m else "main"
    return owner, repo, ref


def lead_number(name):
    """Leading number of a file name, e.g. '55.BIOS.ps1' -> '55'. None if it
    does not start with a number."""
    m = re.match(r"^(\d+)", name)
    return m.group(1) if m else None


def _dec(text):
    return urllib.parse.unquote(text)


# ----------------------------------------------------------------------------
# Repository download + catalog (indexed by number + extension)
# ----------------------------------------------------------------------------
def _repo_root(base):
    if os.path.isdir(os.path.join(base, "ReadyUSB")):
        return base
    for root, dirs, _ in os.walk(base):
        if "ReadyUSB" in dirs:
            return root
    return base


def download_repo(owner, repo, ref, dest):
    url = "https://codeload.github.com/%s/%s/tar.gz/%s" % (owner, repo, ref)
    tar_path = os.path.join(dest, "repo.tar.gz")
    print("[*] Downloading repository: %s/%s  (%s)" % (owner, repo, ref))
    req = urllib.request.Request(url, headers={"User-Agent": "ittool-link-updater"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(tar_path, "wb") as out:
        shutil.copyfileobj(resp, out)
    extract_dir = os.path.join(dest, "repo")
    os.makedirs(extract_dir, exist_ok=True)
    with tarfile.open(tar_path, "r:gz") as tf:
        tf.extractall(extract_dir)
    return _repo_root(extract_dir)


def build_catalog(repo_root):
    """Index repo executables by (number, ext). Returns (by_numext, real_paths).
    real_paths is the set of relative paths (used for numberless runners)."""
    by_numext = {}
    real_paths = set()
    for root, _, files in os.walk(repo_root):
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in EXEC_EXTS:
                continue
            rel = os.path.relpath(os.path.join(root, fname), repo_root).replace(os.sep, "/")
            real_paths.add(rel)
            num = lead_number(fname)
            if num is not None:
                by_numext.setdefault((num, ext), []).append(rel)
    return by_numext, real_paths


# ----------------------------------------------------------------------------
# URL handling
# ----------------------------------------------------------------------------
URL_RE = re.compile(rb"https://github\.com[^\s'\"\\]+")


def build_raw_url(owner, repo, ref, real_path):
    quoted = urllib.parse.quote(real_path, safe="/")
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", ref):          # commit SHA
        return "https://github.com/%s/%s/raw/%s/%s" % (owner, repo, ref, quoted)
    return "https://github.com/%s/%s/raw/refs/heads/%s/%s" % (owner, repo, ref, quoted)


def target_path_from_url(url, owner, repo):
    if not url.startswith("https://github.com/%s/%s/" % (owner, repo)):
        return None
    m = re.search(r"raw/refs/heads/[^/]+/(.+)$", url)
    return _dec(m.group(1)) if m else None


# ----------------------------------------------------------------------------
# Save-name handling (the number inside the launcher's $dst path)
# ----------------------------------------------------------------------------
def name_stem(name):
    """File name without its leading number: '48.BIOS.ps1' -> '.BIOS.ps1'."""
    return re.sub(r"^\d+", "", name)


def renumber_save_name(data, new_name):
    """Rewrite the local save-name so its leading number matches the repository
    file. Any occurrence of the same descriptive name carrying a different
    number is updated (this is the launcher's $dst save name). The copy inside
    the GitHub URL already equals new_name after the link update, so it stays a
    no-op. Returns (new_data, old_name or None)."""
    stem = name_stem(new_name)
    if not stem or stem == new_name:        # repo file has no leading number
        return data, None
    pat = re.compile(rb"\d+" + re.escape(stem.encode("ascii")))
    new_b = new_name.encode("ascii")
    old_name = None
    for mm in pat.finditer(data):
        if mm.group(0) != new_b:
            old_name = mm.group(0).decode("ascii", "replace")
            break
    if old_name is None:
        return data, None
    return pat.sub(new_b, data), old_name


class Result:
    def __init__(self):
        self.changed = []
        self.unchanged = []
        self.runners = []
        self.external = []
        self.no_link = 0
        self.unresolved = []
        self.dst_fixed = []


def process_file(abs_path, rel_path, owner, repo, ref, by_numext, real_paths, result):
    with open(abs_path, "rb") as fh:
        data = fh.read()
    m = URL_RE.search(data)
    if not m:
        result.no_link += 1
        return
    old_bytes = m.group(0)
    old_url = old_bytes.decode("ascii", "replace")

    if not old_url.startswith("https://github.com/%s/%s/" % (owner, repo)):
        result.external.append((rel_path, old_url))
        return

    link_ext = os.path.splitext(target_path_from_url(old_url, owner, repo) or "")[1].lower()
    num = lead_number(os.path.basename(rel_path))   # the script's OWN number

    real_path = None
    if num is not None and link_ext in EXEC_EXTS:
        cands = by_numext.get((num, link_ext), [])
        if len(cands) == 1:
            real_path = cands[0]
    if real_path is None and num is not None:
        # extension in the link may be wrong/missing; match by number only
        all_ext = [c for e in EXEC_EXTS for c in by_numext.get((num, e), [])]
        if len(all_ext) == 1:
            real_path = all_ext[0]

    if real_path is None:
        # Numberless runner: keep the file the link already names, validated.
        stale = target_path_from_url(old_url, owner, repo)
        if stale and stale in real_paths:
            real_path = stale
            new_url = build_raw_url(owner, repo, ref, real_path)
            if new_url != old_url:
                data = data.replace(old_bytes, new_url.encode("ascii"), 1)
            data, dst_old = renumber_save_name(data, os.path.basename(real_path))
            if new_url != old_url or dst_old is not None:
                with open(abs_path, "wb") as fh:
                    fh.write(data)
            if dst_old is not None:
                result.dst_fixed.append((rel_path, dst_old, os.path.basename(real_path)))
            result.runners.append((rel_path, real_path))
            return
        result.unresolved.append((rel_path, old_url))
        return

    new_url = build_raw_url(owner, repo, ref, real_path)
    new_name = os.path.basename(real_path)
    url_changed = new_url != old_url
    if url_changed:
        data = data.replace(old_bytes, new_url.encode("ascii"), 1)
    data, dst_old = renumber_save_name(data, new_name)
    if url_changed or dst_old is not None:
        with open(abs_path, "wb") as fh:
            fh.write(data)
    if dst_old is not None:
        result.dst_fixed.append((rel_path, dst_old, new_name))
    if url_changed:
        result.changed.append((rel_path, old_url, new_url))
    else:
        result.unchanged.append((rel_path, old_url))


# ----------------------------------------------------------------------------
# Output copy (never deletes; overwrites files in place)
# ----------------------------------------------------------------------------
def prepare_output(scripts_path, out_dir):
    if os.path.isdir(scripts_path):
        shutil.copytree(scripts_path, out_dir, dirs_exist_ok=True)
    elif scripts_path.lower().endswith(".zip"):
        import zipfile
        os.makedirs(out_dir, exist_ok=True)
        with zipfile.ZipFile(scripts_path) as zf:
            zf.extractall(out_dir)
    else:
        raise ValueError("The scripts path must be a folder or a .zip file")
    return out_dir


def write_report(out_dir, result, owner, repo, ref):
    path = os.path.join(out_dir, "link_update_report.txt")
    L = ["IT-Tool ReadyUSB Link Updater - report",
         "Repository: %s/%s  ref=%s" % (owner, repo, ref), "=" * 70,
         "Updated links:        %d" % len(result.changed),
         "Already correct:      %d" % len(result.unchanged),
         "Runners validated:    %d" % len(result.runners),
         "External (skipped):   %d" % len(result.external),
         "Unresolved (review):  %d" % len(result.unresolved),
         "Names re-numbered:    %d" % len(result.dst_fixed),
         "Files without a link: %d" % result.no_link, "", "--- UPDATED ---"]
    for rel, old, new in result.changed:
        L += [rel, "    old: %s" % old, "    new: %s" % new]
    L += ["", "--- RUNNERS (no number, target validated) ---"]
    L += ["%s  ->  %s" % (rel, tgt) for rel, tgt in result.runners]
    L += ["", "--- SAVE-NAMES RE-NUMBERED ---"]
    L += ["%s  ->  %s  (was %s)" % (rel, new, old) for rel, old, new in result.dst_fixed]
    L += ["", "--- EXTERNAL (left untouched) ---"]
    L += ["%s  ->  %s" % (rel, url) for rel, url in result.external]
    if result.unresolved:
        L += ["", "--- UNRESOLVED (needs review) ---"]
        for rel, url in result.unresolved:
            L += [rel, "    %s" % url]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    return path


# ----------------------------------------------------------------------------
# Main: three questions, then do the work
# ----------------------------------------------------------------------------
def ask(prompt, default=None):
    while True:
        suffix = " [%s]" % default if default else ""
        ans = input("%s%s: " % (prompt, suffix)).strip().strip('"').strip("'")
        if not ans and default:
            ans = default
        if ans:
            return ans
        print("    Required.")


def main():
    print(BANNER)

    scripts = ask("Folder or .zip to correct")
    while not (os.path.isdir(scripts) or
               (scripts.lower().endswith(".zip") and os.path.isfile(scripts))):
        print("    Not found: %s" % scripts)
        scripts = ask("Folder or .zip to correct")

    out = os.path.abspath(ask("Folder to save the corrected copy", "ReadyUSB_corrected"))

    while True:
        link = ask("Updated repository link (GitHub URL)")
        try:
            owner, repo, ref = parse_repo_link(link)
            break
        except ValueError as e:
            print("    %s" % e)

    print("")
    tmp = tempfile.mkdtemp(prefix="ittool_repo_")
    try:
        repo_root = download_repo(owner, repo, ref, tmp)
        by_numext, real_paths = build_catalog(repo_root)
        print("[*] Repository catalog: %d files" % len(real_paths))

        prepare_output(scripts, out)
        result = Result()
        for root, _, files in os.walk(out):
            for fname in files:
                if fname == "link_update_report.txt":
                    continue
                abs_path = os.path.join(root, fname)
                rel = os.path.relpath(abs_path, out).replace(os.sep, "/")
                process_file(abs_path, rel, owner, repo, ref, by_numext, real_paths, result)
        report = write_report(out, result, owner, repo, ref)

        print("")
        print("[OK] Updated:    %d" % len(result.changed))
        print("     Already ok: %d" % len(result.unchanged))
        print("     Runners:    %d" % len(result.runners))
        print("     External:   %d" % len(result.external))
        print("     Unresolved: %d" % len(result.unresolved))
        print("     Names fixed: %d" % len(result.dst_fixed))
        print("")
        print("[*] Corrected copy: %s" % out)
        print("[*] Report:         %s" % report)
    except Exception as exc:
        print("[ERROR] %s" % exc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    try:
        input("\nPress Enter to exit...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()