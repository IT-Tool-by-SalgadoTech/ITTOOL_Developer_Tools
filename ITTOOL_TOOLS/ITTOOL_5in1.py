#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
#  IT-Tool by SalgadoTech
#  Script: ITTOOL_5in1.py
#  ScriptID: (pending)
#  Version: 1.0
#  Date: 2026-06-18
#  Category: Tools > Maintenance > 5-in-1 Launcher
#  Description: Menu launcher for the 5 ITTOOL maintenance scripts. It only
#               asks which one to run and runs it as-is. No logic is changed
#               in any of the launched scripts.
#  (c) 2025 SalgadoTech - All Rights Reserved
#  Unauthorized distribution prohibited
#  Encoding: UTF-8 (no BOM), ASCII content only.
# ============================================================================

import os
import sys
import subprocess

# ---------------------------------------------------------------------------
# ANSI color codes
# ---------------------------------------------------------------------------
CYAN    = "\033[96m"
DCYAN   = "\033[36m"
WHITE   = "\033[97m"
GREEN   = "\033[92m"
RED     = "\033[91m"
YELLOW  = "\033[93m"
RESET   = "\033[0m"


def enable_ansi():
    """Enable ANSI escape codes on Windows terminal."""
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)


# ---------------------------------------------------------------------------
# Output helpers (green = ok, red = fail, yellow = warning, cyan = info)
# ---------------------------------------------------------------------------
def write_ok(msg):
    print(f"{GREEN}[ OK ] {msg}{RESET}")

def write_err(msg):
    print(f"{RED}[FAIL] {msg}{RESET}")

def write_warn(msg):
    print(f"{YELLOW}[WARN] {msg}{RESET}")

def write_info(msg):
    print(f"{CYAN}[INFO] {msg}{RESET}")


# ---------------------------------------------------------------------------
# Base directory: the folder where THIS launcher lives.
# The 5 scripts must sit next to it (same folder).
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Menu order matches the 5 files as provided. (file name, short description)
SCRIPTS = [
    ("ITTOOL_Manual_Renumber.py", "Renumber the Word manual (.docx) to match file_list.txt"),
    ("ittool_ps1_renumber.py",    "Renumber .ps1 scripts to match file_list.txt"),
    ("delete_numbering.py",       "Remove leading numbers from files and folders"),
    ("fl.py",                     "Generate file_list.txt from the ReadyUSB folder"),
    ("numbering.py",              "Add sequential numbering to files (deep-first)"),
]


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
def show_header():
    print()
    print(f"{CYAN} _____ _____  _______ ____   ____  _     {RESET}")
    print(f"{CYAN}|_   _|_   _||__   __/ __ \\ / __ \\| |    {RESET}")
    print(f"{CYAN}  | |   | |     | | | |  | | |  | | |    {RESET}")
    print(f"{CYAN}  | |   | |     | | | |  | | |  | | |    {RESET}")
    print(f"{CYAN} _| |_  | |     | | | |__| | |__| | |___ {RESET}")
    print(f"{CYAN}|_____| |_|     |_|  \\____/ \\____/|_____|{RESET}")
    print()
    print(f"  {WHITE}=================================================================={RESET}")
    print(f"  {CYAN}IT-Tool by SalgadoTech{RESET}")
    print(f"  {DCYAN}Script: ITTOOL_5in1.py{RESET}")
    print(f"  {DCYAN}Version: 1.0{RESET}")
    print(f"  {DCYAN}Date: 2026-06-18{RESET}")
    print(f"  {DCYAN}Category: Tools > Maintenance > 5-in-1 Launcher{RESET}")
    print(f"  {DCYAN}Description: 5-in-1 launcher for the ITTOOL maintenance scripts{RESET}")
    print(f"  {DCYAN}(c) 2025 SalgadoTech - All Rights Reserved{RESET}")
    print(f"  {WHITE}=================================================================={RESET}")
    print()


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
def show_menu():
    print()
    print(f"  {WHITE}================================================={RESET}")
    print(f"  {WHITE}  ITTOOL Tools - 5 in 1{RESET}")
    print(f"  {WHITE}================================================={RESET}")
    for i, (name, desc) in enumerate(SCRIPTS, start=1):
        print(f"  [{i}] {name}")
        print(f"      {DCYAN}{desc}{RESET}")
    print("  [0] Exit")
    print(f"  {WHITE}================================================={RESET}")


# ---------------------------------------------------------------------------
# Launch one script: runs it as-is with the same Python interpreter,
# sharing this console so its own prompts work normally.
# ---------------------------------------------------------------------------
def launch(name):
    path = os.path.join(BASE_DIR, name)
    if not os.path.isfile(path):
        write_err(f"Not found next to this launcher: {name}")
        write_info(f"Expected at: {path}")
        return
    print()
    write_info(f"Launching {name} ...")
    print()
    subprocess.run([sys.executable, path])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    enable_ansi()
    show_header()

    while True:
        show_menu()
        choice = input("  Select an option: ").strip()

        if choice == "0":
            write_info("Exiting.")
            break
        elif choice in {"1", "2", "3", "4", "5"}:
            launch(SCRIPTS[int(choice) - 1][0])
        else:
            write_warn("Invalid option.")
            continue

        print()
        input("Press ENTER to return to the menu...")


if __name__ == "__main__":
    main()
