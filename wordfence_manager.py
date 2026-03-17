#!/usr/bin/env python3
"""
Wordfence CLI Manager for cPanel Accounts
Handles installation and scanning operations via cPanel user switching.
Requires: pexpect  (auto-installed if missing)
"""

import subprocess
import sys
import os
from typing import List

try:
    import pexpect
except ImportError:
    print("pexpect not found. Installing via pip ...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pexpect", "-q"])
    import pexpect


# ─────────────────────────── helpers ────────────────────────────────────────

def run_as_user(user, command):
    """Run a non-interactive shell command as a cPanel user via su."""
    full_cmd = ["su", "-", user, "-s", "/bin/bash", "-c", command]
    result = subprocess.run(full_cmd, text=True)
    return result.returncode


def prompt_choice(question, options):
    """Display a numbered menu and return the chosen option string."""
    print("\n" + question)
    for i, opt in enumerate(options, 1):
        print("  {}. {}".format(i, opt))
    while True:
        raw = input("Enter choice number: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("  Please enter a number between 1 and {}.".format(len(options)))


def ask_users(prompt_text, multiple=True):
    """Ask for one or more cPanel usernames."""
    if multiple:
        raw = input("\n{} (comma-separated): ".format(prompt_text)).strip()
        users = [u.strip() for u in raw.split(",") if u.strip()]
    else:
        raw = input("\n{}: ".format(prompt_text)).strip()
        users = [raw] if raw else []
    if not users:
        print("  No users entered. Exiting.")
        sys.exit(1)
    return users


def section(title):
    """Print a section divider."""
    print("\n" + "-" * 60)
    print("  " + title)
    print("-" * 60)


# ─────────────────────────── pexpect config ─────────────────────────────────

def configure_wordfence_pexpect(user, license_key):
    """
    Drive the interactive Wordfence CLI first-run wizard through a real PTY
    so Wordfence cannot detect a non-interactive pipe.

    Prompt sequence:
      1. "Would you like to configure it now? [y/n]"   -> y
      2. "Cache directory (default: ...)"              -> <Enter>
      3. "automatically request a free ... [y/n]"      -> n
      4. "License:"                                     -> <license_key>
      5. "Number of worker processes ... (default: 1)" -> <Enter>
    """
    cmd = "su - {u} -s /bin/bash -c '/home/{u}/.local/bin/wordfence malware-scan'".format(u=user)
    print("      Spawning PTY session for '{}' ...".format(user))

    try:
        child = pexpect.spawn(
            "/bin/bash", ["-c", cmd],
            encoding="utf-8",
            timeout=120
        )
        # Mirror all output to stdout so the operator can see what is happening
        child.logfile_read = sys.stdout

        # 1. Configure now?
        child.expect(r"\[y/n\].*:")
        child.sendline("y")

        # 2. Cache directory - accept default
        child.expect(r"Cache directory.*:")
        child.sendline("")

        # 3. Auto-request free license?
        child.expect(r"\[y/n\].*:")
        child.sendline("n")

        # 4. License key
        child.expect(r"License.*:")
        child.sendline(license_key)

        # 5. Worker processes - accept default
        child.expect(r"Number of worker processes.*:")
        child.sendline("")

        # Wait for the process to exit
        child.expect(pexpect.EOF)
        child.close()

        exit_ok = child.exitstatus in (0, None)
        return exit_ok

    except pexpect.TIMEOUT:
        print("\n  [!] Timed out waiting for a prompt while configuring '{}'.".format(user))
        return False
    except pexpect.EOF:
        print("\n  [!] Process ended unexpectedly while configuring '{}'.".format(user))
        return False


# ─────────────────────────── install flow ───────────────────────────────────

def install_wordfence(users, license_key):
    """Install Wordfence CLI for each cPanel user and run initial config."""
    for user in users:
        section("Installing Wordfence CLI for user: {}".format(user))

        # Step 1: pip install
        print("\n[1/2] Running pip install for '{}' ...".format(user))
        rc = run_as_user(
            user,
            "/opt/alt/python38/bin/pip3.8 install wordfence --user"
        )
        if rc != 0:
            print("  [!] pip install returned exit code {} for '{}'. Continuing anyway.".format(rc, user))
        else:
            print("  [OK] pip install completed for '{}'.".format(user))

        # Step 2: interactive config via pexpect PTY
        print("\n[2/2] Running initial Wordfence CLI configuration for '{}' ...".format(user))
        print("      (Driving prompts via PTY - output mirrored below)\n")

        success = configure_wordfence_pexpect(user, license_key)
        if not success:
            print("\n  [!] Configuration may not have completed cleanly for '{}'.".format(user))
        else:
            print("\n  [OK] Wordfence CLI configured successfully for '{}'.".format(user))

    section("Installation complete")
    print("  All specified users have been processed.")


# ─────────────────────────── scan flow ──────────────────────────────────────

SCAN_MAP = {
    "Malware scan (files)": {
        "cmd_tpl": ".local/bin/wordfence malware-scan /home/{user}/public_html -a > ~/file_scan.txt &",
        "out_file": "~/file_scan.txt",
    },
    "Vulnerability scan": {
        "cmd_tpl": ".local/bin/wordfence vuln-scan /home/{user}/public_html -a > ~/vuln_scan.txt &",
        "out_file": "~/vuln_scan.txt",
    },
}


def run_scan(user, scan_type):
    """Launch the chosen Wordfence scan as the given cPanel user."""
    meta = SCAN_MAP[scan_type]
    cmd = meta["cmd_tpl"].format(user=user)
    out = meta["out_file"]

    section("Running {} for user: {}".format(scan_type, user))
    print("  Command : {}".format(cmd))
    print("  Output  : {}  (inside {}'s home directory)".format(out, user))
    print("\n  Launching scan in background ...")

    rc = run_as_user(user, cmd)
    if rc != 0:
        print("  [!] Scan command returned exit code {}.".format(rc))
    else:
        print("  [OK] Scan launched successfully.")
        print("       Results will be written to {} under /home/{}/".format(out, user))


# ─────────────────────────── entry point ────────────────────────────────────

def main():
    print("\n+----------------------------------------------+")
    print("|     Wordfence CLI Manager for cPanel        |")
    print("+----------------------------------------------+")

    action = prompt_choice(
        "What would you like to do?",
        [
            "Install Wordfence CLI on cPanel account(s)",
            "Run a Wordfence scan on a cPanel account",
        ],
    )

    # Install branch
    if action.startswith("Install"):
        users = ask_users(
            "Enter cPanel username(s) where Wordfence CLI should be installed",
            multiple=True,
        )
        license_key = input(
            "\nEnter your Wordfence CLI license key\n"
            "(will be supplied during the configuration wizard): "
        ).strip()
        if not license_key:
            print("  No license key provided. Exiting.")
            sys.exit(1)
        install_wordfence(users, license_key)

    # Scan branch
    else:
        users = ask_users("Enter the cPanel username to scan", multiple=False)
        user = users[0]
        scan_type = prompt_choice(
            "Which type of scan would you like to run?",
            list(SCAN_MAP.keys()),
        )
        run_scan(user, scan_type)

    print("\n  Done. Goodbye!\n")


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("\n  [!] This script must be run as root (e.g. sudo python3 wordfence_manager.py).")
        sys.exit(1)
    main()
