#!/usr/bin/env python3
"""
Wordfence CLI Manager for cPanel Accounts
Handles installation and scanning operations via cPanel user switching.
Requires: pexpect  (auto-installed if missing)
Compatible with: CloudLinux (Python 3.8 via /opt/alt) and AlmaLinux/standard servers (Python 3.8+)
Minimum requirement: Python 3.8 / pip 3.8
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


# ─────────────────────────── pip detection ──────────────────────────────────

# Candidates in order of preference — must be 3.8 or higher
PIP_CANDIDATES = [
    ("/opt/alt/python38/bin/pip3.8", (3, 8)),   # CloudLinux Python Selector 3.8
    ("/opt/alt/python39/bin/pip3.9", (3, 9)),   # CloudLinux Python Selector 3.9
    ("/opt/alt/python310/bin/pip3.10", (3, 10)),# CloudLinux Python Selector 3.10
    ("/opt/alt/python311/bin/pip3.11", (3, 11)),# CloudLinux Python Selector 3.11
    ("/usr/bin/pip3.9",  (3, 9)),               # AlmaLinux 9 / standard
    ("/usr/bin/pip3.8",  (3, 8)),               # Standard 3.8
    ("/usr/bin/pip3.10", (3, 10)),              # Standard 3.10
    ("/usr/bin/pip3.11", (3, 11)),              # Standard 3.11
    ("/usr/bin/pip3",    None),                 # Generic — version checked at runtime
    ("/usr/local/bin/pip3", None),              # Custom installs
]

MIN_VERSION = (3, 8)


def get_pip_version(pip_bin):
    """
    Return the (major, minor) tuple of the given pip binary,
    or None if it cannot be determined.
    """
    try:
        out = subprocess.check_output(
            [pip_bin, "--version"],
            stderr=subprocess.DEVNULL,
            text=True
        )
        # Output looks like: pip 21.3.1 from ... (python 3.9)
        for part in out.split():
            if part.startswith("(python"):
                # part = "(python" and next token is "3.9)"
                continue
            if part.replace(".", "").isdigit() and "." in part:
                major, minor = int(part.split(".")[0]), int(part.split(".")[1])
                if major == 3:
                    return (major, minor)
        # Fallback: parse "python X.Y" at the end of the version string
        if "python" in out:
            token = out.split("python")[-1].strip().rstrip(")")
            parts = token.split(".")
            if len(parts) >= 2:
                return (int(parts[0]), int(parts[1]))
    except Exception:
        pass
    return None


def detect_pip():
    """
    Return the first pip binary on this server that is >= 3.8.
    If a pip is found but is below 3.8, print an error and exit.
    If no pip is found at all, print an error and exit.
    """
    found_but_too_old = []

    for pip_bin, known_version in PIP_CANDIDATES:
        if not os.path.isfile(pip_bin):
            continue

        # Use the known version if hardcoded, otherwise detect at runtime
        version = known_version if known_version else get_pip_version(pip_bin)

        if version is None:
            # Could not determine version — skip this candidate
            continue

        if version >= MIN_VERSION:
            return pip_bin, version
        else:
            found_but_too_old.append((pip_bin, version))

    # No suitable pip found — give a helpful error
    if found_but_too_old:
        print("\n  [ERROR] pip version is less than 3.8.")
        print("          The following pip binaries were found but do not meet the minimum requirement (3.8):")
        for pip_bin, version in found_but_too_old:
            print("            {} (python {}.{})".format(pip_bin, version[0], version[1]))
        print("          Please install Python 3.8 or higher and try again.")
    else:
        print("\n  [ERROR] No pip binary (3.8 or higher) was found on this server.")
        print("          Please install Python 3.8+ and ensure pip is available.")

    sys.exit(1)


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

def install_wordfence(users, license_key, pip_bin):
    """Install Wordfence CLI for each cPanel user and run initial config."""
    for user in users:
        section("Installing Wordfence CLI for user: {}".format(user))

        # Step 1: pip install
        print("\n[1/2] Running pip install for '{}' ...".format(user))
        rc = run_as_user(
            user,
            "{} install wordfence --user".format(pip_bin)
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
    # Check that the script itself is running on Python 3.8+
    if sys.version_info < MIN_VERSION:
        print("\n  [ERROR] This script requires Python 3.8 or higher.")
        print("          Current Python version: {}.{}.{}".format(*sys.version_info[:3]))
        print("          Please run using python3.8 or higher.")
        sys.exit(1)

    print("\n+----------------------------------------------+")
    print("|     Wordfence CLI Manager for cPanel        |")
    print("+----------------------------------------------+")

    # Detect pip early — exits with a clear error if none >= 3.8 is found
    pip_bin, pip_version = detect_pip()
    print("  [INFO] Using pip binary : {}".format(pip_bin))
    print("  [INFO] pip Python version: {}.{}".format(*pip_version))

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
        install_wordfence(users, license_key, pip_bin)

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
