# Wordfence CLI Manager for cPanel

A Python script to automate the installation and scanning operations of [Wordfence CLI](https://github.com/wordfence/wordfence-cli) across cPanel accounts on a shared hosting server.

---

## Features

- Install Wordfence CLI on one or multiple cPanel accounts in a single run
- Automates the interactive first-run configuration wizard using a PTY session (via `pexpect`), so no manual input is needed per user
- Run malware or vulnerability scans on any cPanel account's `public_html`
- All scans run in the background and write output to a log file in the user's home directory
- User switching is handled via `su - <user> -s /bin/bash` — no need to log in separately to each account

---

## Requirements

- Must be run as **root** on the server
- Python 3.6 or higher (tested on Python 3.6 — compatible with CloudLinux/cPanel environments)
- `/opt/alt/python38/bin/pip3.8` must be available (standard on CloudLinux with Python Selector)
- Wordfence CLI must already be installed (or will be installed by this script) at `~/.local/bin/wordfence` for each cPanel user
- A valid [Wordfence CLI license](https://www.wordfence.com/products/wordfence-cli/) — free licenses are available
- `pexpect` Python package — **auto-installed** by the script if not present

---

## Installation

Clone or download the script to your server:

```bash
wget https://raw.githubusercontent.com/your-username/your-repo/main/wordfence_manager.py
chmod +x wordfence_manager.py
```

---

## Usage

Always run as root:

```bash
python3 wordfence_manager.py
```

The script will present a menu with two options:

```
+----------------------------------------------+
|     Wordfence CLI Manager for cPanel        |
+----------------------------------------------+

What would you like to do?
  1. Install Wordfence CLI on cPanel account(s)
  2. Run a Wordfence scan on a cPanel account
```

---

## Option 1 — Install Wordfence CLI

Select option `1` to install and configure Wordfence CLI on one or more cPanel accounts.

**You will be prompted for:**
- cPanel usernames (comma-separated if multiple)
- Your Wordfence CLI license key

**What the script does for each user:**

1. Runs `pip3.8 install wordfence --user` as that cPanel user
2. Launches the Wordfence CLI first-run configuration wizard through a PTY session and automatically answers the prompts:

| Prompt | Answer |
|---|---|
| Would you like to configure it now? | `y` |
| Cache directory | Enter (use default) |
| Automatically request a free license? | `n` |
| License | *(your provided license key)* |
| Number of worker processes | Enter (use default) |

**Example:**

```
Enter cPanel username(s) where Wordfence CLI should be installed (comma-separated): user1, user2, user3

Enter your Wordfence CLI license key
(will be supplied during the configuration wizard): xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

---

## Option 2 — Run a Wordfence Scan

Select option `2` to run a scan on a cPanel account's `public_html` directory.

**You will be prompted for:**
- The cPanel username to scan
- The type of scan to run

**Available scan types:**

| Scan | Command run as user | Output file |
|---|---|---|
| Malware scan (files) | `wordfence malware-scan /home/<user>/public_html -a` | `~/file_scan.txt` |
| Vulnerability scan | `wordfence vuln-scan /home/<user>/public_html -a` | `~/vuln_scan.txt` |

All scans run **in the background** (`&`) so the script returns immediately. Results are written to the respective output file inside the cPanel user's home directory.

**To monitor a running scan:**

```bash
# Check if the scan process is still running
su - username -s /bin/bash -c "ps aux | grep wordfence"

# View results once complete
su - username -s /bin/bash -c "cat ~/file_scan.txt"
su - username -s /bin/bash -c "cat ~/vuln_scan.txt"
```

---

## Notes

- The `pexpect` package is required for the installation flow. It will be installed automatically via `pip` if not already present on the system.
- The configuration wizard is driven through a real PTY (pseudo-terminal) session. This is necessary because Wordfence CLI checks for an interactive terminal (`isatty()`) and refuses piped input.
- Scans are launched as background processes. If the Wordfence Intelligence API request fails intermittently during a scan, this is a transient issue — simply re-run the scan.
- User switching uses `su - <username> -s /bin/bash` to ensure a full login shell with the correct `PATH` and environment variables, including `~/.local/bin`.

---

## File Structure

```
wordfence_manager.py   # Main script
README.md              # This file
```

---

## License

MIT — free to use and modify.
