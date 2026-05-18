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

# ----------------------------- ANSI colors ----------------------------------

class C:
    """ANSI color codes for terminal output."""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    CYAN    = "\033[96m"    # section headers / scan user
    GREEN   = "\033[92m"    # success / OK
    YELLOW  = "\033[93m"    # warnings / info / cache ops
    RED     = "\033[91m"    # errors
    MAGENTA = "\033[95m"    # scan path
    BLUE    = "\033[94m"    # result file location

def c(color, text):
    """Wrap text in an ANSI color code."""
    return "{}{}{}".format(color, text, C.RESET)

def _find_pip_for_bootstrap():
    """
    Find a working pip binary to install pexpect at startup.
    Tries the pip binary that matches the running Python first,
    then falls back to other known locations.
    """
    py = sys.executable
    py_dir = os.path.dirname(py)
    ver = "{}.{}".format(sys.version_info.major, sys.version_info.minor)

    candidates = [
        os.path.join(py_dir, "pip{}".format(ver)),
        os.path.join(py_dir, "pip3"),
        "/opt/alt/python38/bin/pip3.8",
        "/opt/alt/python39/bin/pip3.9",
        "/usr/bin/pip3.9",
        "/usr/bin/pip3.8",
        "/usr/bin/pip3",
        "/usr/local/bin/pip3.8",
        "/usr/local/bin/pip3.9",
        "/usr/local/bin/pip3",
    ]

    for pip in candidates:
        # os.path.exists() follows symlinks, so it returns True even if pip
        # is a symlink -- unlike os.path.isfile() which can fail on broken links
        if os.path.exists(pip) and os.access(pip, os.X_OK):
            return pip
    return None


try:
    import pexpect
except ImportError:
    print("pexpect not found. Installing via pip ...")
    _pip = _find_pip_for_bootstrap()
    if _pip is None:
        print("  [ERROR] Could not find a pip binary to install pexpect.")
        print("          Please install pexpect manually:")
        print("          /opt/alt/python38/bin/pip3.8 install pexpect --user")
        sys.exit(1)
    print("  [INFO] Using pip binary for bootstrap: {}".format(_pip))

    # Determine the user site-packages path for the running Python and
    # install pexpect there so the correct interpreter can import it.
    import site
    user_site = site.getusersitepackages()
    os.makedirs(user_site, exist_ok=True)

    subprocess.check_call([_pip, "install", "pexpect", "--target", user_site, "-q"])

    # Add the install location to sys.path so we can import it immediately
    if user_site not in sys.path:
        sys.path.insert(0, user_site)

    import pexpect


# ----------------------------- pip detection --------------------------------

# Candidates in order of preference -- must be 3.8 or higher
PIP_CANDIDATES = [
    ("/opt/alt/python38/bin/pip3.8",   (3, 8)),    # CloudLinux Python Selector 3.8
    ("/opt/alt/python39/bin/pip3.9",   (3, 9)),    # CloudLinux Python Selector 3.9
    ("/opt/alt/python310/bin/pip3.10", (3, 10)),   # CloudLinux Python Selector 3.10
    ("/opt/alt/python311/bin/pip3.11", (3, 11)),   # CloudLinux Python Selector 3.11
    ("/usr/bin/pip3.9",                (3, 9)),    # AlmaLinux 9 / standard
    ("/usr/bin/pip3.8",                (3, 8)),    # Standard 3.8
    ("/usr/bin/pip3.10",               (3, 10)),   # Standard 3.10
    ("/usr/bin/pip3.11",               (3, 11)),   # Standard 3.11
    ("/usr/bin/pip3",                  None),      # Generic -- version checked at runtime
    ("/usr/local/bin/pip3.8",          (3, 8)),    # Custom installs (also symlink target on CloudLinux)
    ("/usr/local/bin/pip3.9",          (3, 9)),
    ("/usr/local/bin/pip3.10",         (3, 10)),
    ("/usr/local/bin/pip3",            None),
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
        if "python" in out:
            token = out.split("python")[-1].strip().rstrip(")")
            parts = token.split(".")
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
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
        if not (os.path.exists(pip_bin) and os.access(pip_bin, os.X_OK)):
            continue

        # Use the known version if hardcoded, otherwise detect at runtime
        version = known_version if known_version else get_pip_version(pip_bin)

        if version is None:
            continue

        if version >= MIN_VERSION:
            return pip_bin, version
        else:
            found_but_too_old.append((pip_bin, version))

    # No suitable pip found -- give a helpful error
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


# ----------------------------- helpers -------------------------------------

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


def ask_wp_path(user):
    """
    Prompt for the WordPress installation path.
    Defaults to /home/<user>/public_html if left blank.
    """
    default_path = "/home/{}/public_html".format(user)
    raw = input(
        "\nEnter WordPress installation path\n"
        "(press Enter to use default: {}): ".format(default_path)
    ).strip()
    path = raw if raw else default_path
    print("  [INFO] Scan path set to: {}".format(path))
    return path


def section(title):
    """Print a section divider."""
    print("")
    print(c(C.CYAN, C.BOLD + "-" * 60))
    print(c(C.CYAN, C.BOLD + "  " + title))
    print(c(C.CYAN, C.BOLD + "-" * 60))


# ----------------------------- pexpect config -------------------------------

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


# ----------------------------- install flow ---------------------------------

def install_wordfence(users, license_key, pip_bin):
    """Install Wordfence CLI for each cPanel user and run initial config."""
    for user in users:
        section("Installing Wordfence CLI for user: {}".format(user))

        # Step 1: pip install
        # Pin urllib3 to v1.x to avoid OpenSSL 1.0.2 incompatibility with urllib3 v2.
        # urllib3 v2 requires OpenSSL 1.1.1+; older servers (e.g. CentOS 7) ship 1.0.2k.
        print("\n[1/2] Running pip install for '{}' ...".format(user))
        rc = run_as_user(
            user,
            '{} install wordfence "urllib3<2" --user'.format(pip_bin)
        )
        if rc != 0:
            print(c(C.YELLOW, "  [!] pip install returned exit code {} for '{}'. Continuing anyway.".format(rc, user)))
        else:
            print(c(C.GREEN, "  [OK] pip install completed for '{}'.".format(user)))

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


# ----------------------------- scan flow ------------------------------------

SCAN_MAP = {
    "Malware scan (files)": {
        "cmd_tpl": ".local/bin/wordfence malware-scan {wp_path} -a > ~/file_scan.txt",
        "out_file": "~/file_scan.txt",
    },
    "Vulnerability scan": {
        "cmd_tpl": ".local/bin/wordfence vuln-scan {wp_path} -a > ~/vuln_scan.txt",
        "out_file": "~/vuln_scan.txt",
    },
}

MAX_RETRIES = 3    # Number of retry attempts if the API request fails
RETRY_DELAY = 30   # Seconds to wait between retries

# The vulnerability index cache file — hex encoding of "vulnerability_index_production"
VULN_CACHE_FILE = "76756C6E65726162696C6974795F696E6465785F70726F64756374696F6E"


def get_cache_dir(user):
    """Return the Wordfence cache directory path for a cPanel user."""
    return "/home/{}/.cache/wordfence".format(user)


def get_vuln_cache_path(user):
    """Return the full path to the vulnerability index cache file for a user."""
    return "{}/{}".format(get_cache_dir(user), VULN_CACHE_FILE)


def copy_vuln_cache(source_user, target_user):
    """
    Copy the vulnerability index cache file from source_user to target_user.
    This avoids the target user needing to re-download the ~90MB file from
    the Wordfence API, which is the main cause of rate limiting errors.
    """
    import shutil
    import pwd

    src      = get_vuln_cache_path(source_user)
    dst_dir  = get_cache_dir(target_user)
    dst_file = get_vuln_cache_path(target_user)

    if not os.path.isfile(src):
        print(c(C.YELLOW, "  [!] Vulnerability cache not found for '{}' at {}.".format(source_user, src)))
        print(c(C.YELLOW, "      Skipping cache copy -- target user will download from API."))
        return False

    os.makedirs(dst_dir, exist_ok=True)

    try:
        shutil.copy2(src, dst_file)
        pw = pwd.getpwnam(target_user)
        os.chown(dst_file, pw.pw_uid, pw.pw_gid)
        os.chmod(dst_file, 0o664)
        size_mb = os.path.getsize(dst_file) / (1024 * 1024)
        print(c(C.GREEN, "  [OK] Vulnerability cache copied from '{}' to '{}' ({:.1f} MB).".format(
            source_user, target_user, size_mb)))
        return True
    except Exception as e:
        print(c(C.RED, "  [!] Failed to copy vulnerability cache to '{}': {}".format(target_user, e)))
        return False


def remove_vuln_cache(user):
    """
    Remove the copied vulnerability index cache file from the user's cache
    directory after their scan completes, to keep things clean.
    """
    path = get_vuln_cache_path(user)
    try:
        if os.path.isfile(path):
            os.remove(path)
            print(c(C.GREEN, "  [OK] Vulnerability cache cleaned up from '{}'.".format(user)))
        else:
            print("  [INFO] No vulnerability cache file found to remove for '{}'.".format(user))
    except Exception as e:
        print("  [!] Failed to remove vulnerability cache for '{}': {}".format(user, e))


def run_scan_with_retry(user, cmd, out):
    """
    Run a scan command as the given user, retrying up to MAX_RETRIES times
    if the scan fails. Runs in the foreground to capture the exit code.
    """
    import time

    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            print(c(C.YELLOW, "  [RETRY] Attempt {}/{} after {}s delay ...".format(
                attempt, MAX_RETRIES, RETRY_DELAY)))
            time.sleep(RETRY_DELAY)

        rc = run_as_user(user, cmd)

        if rc == 0:
            print(c(C.GREEN, C.BOLD + "  [OK] Scan completed successfully."))
            print(c(C.BLUE,  "       Results written to {} under /home/{}/".format(out, user)))
            return True
        else:
            print(c(C.YELLOW, "  [!] Scan failed (exit code {}) on attempt {}/{}.".format(
                rc, attempt, MAX_RETRIES)))

    print(c(C.RED, C.BOLD + "  [ERROR] Scan failed after {} attempts for user '{}'.".format(MAX_RETRIES, user)))
    print(c(C.RED, "          This is likely due to Wordfence API rate limiting."))
    print(c(C.RED, "          Try running the scan again after a few minutes."))
    return False


def run_scan(users, scan_type):
    """
    Launch the chosen Wordfence scan for each cPanel user.

    Strategy for multiple users:
      1. Run the first user normally -- Wordfence downloads the vulnerability
         index (~90MB) from the API and caches it in ~/.cache/wordfence/
      2. For each subsequent user, copy that cached file directly from user 1
         before running their scan -- no extra API calls needed.
      3. After each subsequent user's scan completes, remove the copied cache
         file from their home directory to keep things tidy.
    """
    meta       = SCAN_MAP[scan_type]
    total      = len(users)
    first_user = users[0]

    for index, user in enumerate(users, 1):
        wp_path = ask_wp_path(user)
        cmd     = meta["cmd_tpl"].format(wp_path=wp_path)
        out     = meta["out_file"]

        section("[{}/{}] Running {} for user: {}".format(index, total, scan_type, user))
        print("  Scan user        : " + c(C.CYAN,    C.BOLD + user))
        print("  Scan path        : " + c(C.MAGENTA, wp_path))
        print("  Command          : " + cmd)
        print("  Results saved to : " + c(C.BLUE,    C.BOLD + "/home/{}/{}".format(user, out.replace("~/", ""))))
        print("  Max retries      : {}".format(MAX_RETRIES))
        print("")

        is_first = (index == 1)
        cache_was_copied = False

        if is_first:
            print(c(C.YELLOW, "  [CACHE] First user -- vulnerability index will be downloaded from Wordfence API."))
            print(c(C.YELLOW, "          This will be shared with subsequent users to avoid rate limiting."))
        else:
            print(c(C.YELLOW, "  [CACHE] Copying vulnerability index from '{}' to avoid API re-download ...".format(first_user)))
            cache_was_copied = copy_vuln_cache(first_user, user)

        print("")
        run_scan_with_retry(user, cmd, out)

        # Clean up the copied cache file after the scan to keep the user's home tidy
        if cache_was_copied:
            print("")
            print(c(C.YELLOW, "  [CACHE] Cleaning up copied vulnerability cache from '{}' ...".format(user)))
            remove_vuln_cache(user)

    section("All scans complete")
    print(c(C.GREEN, C.BOLD + "  All {} user(s) processed successfully.".format(total)))

# ----------------------------- entry point ----------------------------------

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

    # Detect pip early -- exits with a clear error if none >= 3.8 is found
    pip_bin, pip_version = detect_pip()
    print("  [INFO] Using pip binary    : {}".format(pip_bin))
    print("  [INFO] pip Python version  : {}.{}".format(*pip_version))

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
        raw_users = input("\nEnter cPanel username(s) to scan (comma-separated): ").strip()
        users = [u.strip() for u in raw_users.split(",") if u.strip()]
        if not users:
            print("  No users entered. Exiting.")
            sys.exit(1)

        scan_type = prompt_choice(
            "Which type of scan would you like to run?",
            list(SCAN_MAP.keys()),
        )
        if len(users) > 1:
            print("\n  [INFO] {} users queued.".format(len(users)))
            print("  [INFO] Vulnerability index will be downloaded once for the first")
            print("         user and copied to subsequent users to avoid API rate limiting.")
        run_scan(users, scan_type)

    print("\n  Done. Goodbye!\n")


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("\n  [!] This script must be run as root (e.g. sudo python3 wordfence_manager.py).")
        sys.exit(1)
    main()
