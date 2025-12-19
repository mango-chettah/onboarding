#!/usr/bin/env python3

import os
import sys
import subprocess
import time
import glob
from pathlib import Path
import shutil
import signal
import json
from typing import List, Optional

# Dynamically find specstory-real, handling homebrew upgrades
def is_wrapper_script(path):
    """Check if a given path is the wrapper script (bash or Python)."""
    if not path or not os.path.exists(path):
        return False

    path_abs = os.path.abspath(path)
    wrapper_bash = os.path.abspath(os.path.expanduser("~/bin/specstory"))
    wrapper_py = os.path.abspath(os.path.expanduser("~/.specstory_wrapper/specstory_wrapper.py"))

    if path_abs in (wrapper_bash, wrapper_py):
        return True

    # Check file content for wrapper signature (errors='ignore' handles binary files gracefully)
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read(500)
        return 'specstory_wrapper.py' in content

def filter_wrapper_from_path():
    """Return PATH with wrapper directories removed."""
    wrapper_dirs = {os.path.expanduser("~/bin"), os.path.dirname(os.path.abspath(os.path.expanduser("~/bin/specstory")))}
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    return os.pathsep.join([p for p in path_parts if p not in wrapper_dirs])

def find_real_specstory():
    """Find the real specstory binary, handling homebrew version changes."""
    # Check environment variable first
    env_path = os.environ.get("SPECSTORY_ORIGINAL") or os.environ.get("SPECSTORY_REAL") or os.environ.get("ORIGINAL_SPECSTORY")
    if env_path:
        env_path = os.path.expanduser(env_path)
        if os.path.isabs(env_path) and os.path.exists(env_path) and not is_wrapper_script(env_path):
            return os.path.abspath(env_path)

    # Try homebrew installation if brew is available
    if shutil.which("brew"):
        try:
            prefix = subprocess.run(["brew", "--prefix"], capture_output=True, text=True).stdout.strip()
            if prefix:
                real_path = os.path.join(prefix, "bin", "specstory-real")

                # Check if specstory-real exists and is valid
                if os.path.exists(real_path) and not os.path.islink(real_path) and not is_wrapper_script(real_path):
                    return real_path

                # Get current specstory version and create/fix symlink
                specstory_path = subprocess.run(["brew", "--prefix", "specstory"], capture_output=True, text=True).stdout.strip()
                if specstory_path:
                    real_bin = os.path.join(specstory_path, "bin", "specstory")
                    if os.path.exists(real_bin):
                        if os.path.exists(real_path) or os.path.islink(real_path):
                            os.remove(real_path)
                        os.symlink(real_bin, real_path)
                        return real_path
        except Exception:
            pass

    # Fallback: search PATH (excluding wrapper directories)
    old_path = os.environ["PATH"]
    os.environ["PATH"] = filter_wrapper_from_path()
    resolved = shutil.which("specstory")
    os.environ["PATH"] = old_path

    if resolved and not is_wrapper_script(resolved):
        return resolved

    # Last resort: check common system locations
    for location in ["/usr/local/bin/specstory-real", "/usr/bin/specstory-real", "/bin/specstory-real",
                     "/usr/local/bin/specstory", "/usr/bin/specstory", "/bin/specstory"]:
        if os.path.exists(location) and not is_wrapper_script(location):
            return location

    return "specstory-real"

REAL = find_real_specstory()

# Final safety check: ensure REAL is never the wrapper
if is_wrapper_script(REAL):
    print(f"Error: Cannot find real specstory binary (found wrapper at {REAL})", file=sys.stderr)
    print(f"SPECSTORY_ORIGINAL={os.environ.get('SPECSTORY_ORIGINAL', 'not set')}", file=sys.stderr)

    # Try common locations as last resort
    candidates = []
    if shutil.which("brew"):
        try:
            prefix = subprocess.run(["brew", "--prefix"], capture_output=True, text=True).stdout.strip()
            if prefix:
                candidates.append(os.path.join(prefix, "bin", "specstory-real"))
                candidates.append(os.path.join(prefix, "bin", "specstory"))
        except Exception:
            pass
    
    candidates.extend([
        "/opt/homebrew/bin/specstory-real",
        "/usr/local/bin/specstory-real",
        "/usr/bin/specstory",
        "/bin/specstory"
    ])

    for candidate in candidates:
        if candidate and os.path.exists(candidate) and not is_wrapper_script(candidate):
            REAL = candidate
            print(f"Found real specstory at: {REAL}", file=sys.stderr)
            break
    else:
        print("Error: Could not find real specstory binary. Please reinstall.", file=sys.stderr)
        sys.exit(1)
HIST_DIR = ".specstory/history"
TS_DIR = ".specstory/timestamps"

POLL_INTERVAL = 0.1

def read_lines_text(path: str) -> List[str]:
    """Read a text file into normalized lines (LF) with UTF-8 decoding and ignore errors."""
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return text.split('\n')

def find_conversation_header_indices(lines: List[str]) -> List[int]:
    """Find indices of User/Agent header blocks."""
    indices: List[int] = []
    for i, line in enumerate(lines):
        if line.startswith('_**') and line.endswith('**_') and ('User' in line or 'Agent' in line):
            indices.append(i)
    return indices

def first_meaningful_line_after(lines: List[str], start_idx: int) -> str:
    """Return first non-empty, non-separator line following a header. Fallback to header line."""
    for j in range(start_idx + 1, len(lines)):
        content = lines[j].strip()
        if not content or content == '---':
            continue
        return content
    return lines[start_idx].strip() if start_idx < len(lines) else ''


def get_timestamp_file_for_md(md_path: str) -> str:
    """Given an absolute markdown path, return the absolute timestamps file path alongside it."""
    md_abs = os.path.abspath(md_path)
    history_dir = os.path.dirname(md_abs)  # .../.specstory/history
    specstory_dir = os.path.dirname(history_dir)  # .../.specstory
    ts_dir_for_file = os.path.join(specstory_dir, "timestamps")
    os.makedirs(ts_dir_for_file, exist_ok=True)
    base = Path(md_abs).stem
    return os.path.join(ts_dir_for_file, f"{base}.timestamps")

def get_most_recent_md_file():
    """Get the most recently created .md file in the current project's history directory."""
    md_files = glob.glob(f"{HIST_DIR}/*.md")
    if not md_files:
        return None
    latest_rel = max(md_files, key=os.path.getmtime)
    return os.path.abspath(latest_rel)

def start_watcher(before_file, before_mtime):
    """Start the background watcher that logs timestamp|first-line for new User/Agent entries."""
    # Pre-create pidfile so the parent can reliably wait for it to populate
    Path(f"/tmp/specstory_watcher_{os.getpid()}" ).touch()

    pid = os.fork()
    if pid != 0:
        # Parent process
        return

    # Child process - detach from parent
    os.setsid()

    # Determine which history file to watch by detecting any md whose mtime increases
    # since startup, or any new md that appears. This supports both new sessions and resumes.
    def list_md_files():
        files = glob.glob(f"{HIST_DIR}/*.md")
        return [os.path.abspath(p) for p in files]

    # Snapshot initial mtimes
    initial_mtimes = {}
    for p in list_md_files():
        initial_mtimes[p] = os.path.getmtime(p)

    new_file = None
    start_wait = time.time()
    while new_file is None:
        candidates = []
        for p in list_md_files():
            mt = os.path.getmtime(p)
            if p not in initial_mtimes:
                candidates.append((p, mt))
            elif mt > (initial_mtimes.get(p, 0.0) + 1e-6):
                candidates.append((p, mt))
        if candidates:
            # Choose the most recently modified candidate
            candidates.sort(key=lambda t: t[1], reverse=True)
            new_file = candidates[0][0]
            break

        time.sleep(POLL_INTERVAL)

    # Create timestamp file for the new md file (next to the md's .specstory)
    new_file = os.path.abspath(new_file)
    logfile = get_timestamp_file_for_md(new_file)
    Path(logfile).touch()

    # Write PID metadata so parent can stop this watcher
    pidfile = f"/tmp/specstory_watcher_{os.getppid()}"
    with open(pidfile, 'w') as f:
        f.write(json.dumps({"pid": os.getpid(), "target": new_file}))

    # Inline watcher loop: ensure timestamps exist for new history files and
    # append new entries for all markdown files in this history directory
    while True:
        # Detect and initialize new markdown files by creating their timestamps files
        md_files = list_md_files()
        for md_path in md_files:
            ts_path = get_timestamp_file_for_md(md_path)
            if not os.path.exists(ts_path):
                Path(ts_path).touch()

        # For each md, compute headers with meaningful content and append new timestamps
        ts_now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        for md_path in md_files:
            ts_path = get_timestamp_file_for_md(md_path)

            # Read existing entries
            existing = []
            if os.path.exists(ts_path):
                with open(ts_path, 'r') as f:
                    existing = [ln.strip() for ln in f if ln.strip()]

            # Compute snippets for headers-with-content
            lines = read_lines_text(md_path)
            hdrs = find_conversation_header_indices(lines)
            snippets = []
            for idx in hdrs:
                header_txt = lines[idx].strip() if idx < len(lines) else ''
                snippet = first_meaningful_line_after(lines, idx)
                if snippet and snippet != header_txt and snippet != '---':
                    snippets.append(snippet)

            # Append only newly appeared entries
            if len(existing) < len(snippets):
                with open(ts_path, 'a') as out:
                    for i in range(len(existing), len(snippets)):
                        out.write(f"{ts_now}|{snippets[i]}\n")

        time.sleep(POLL_INTERVAL)


def merge_timestamps(target_md=None):
    """Insert timestamps into the markdown headers from the corresponding timestamps file.
    If target_md is provided, that file is used; otherwise the latest md in history is used.
    """
    if target_md:
        latest_md = os.path.abspath(target_md)
    else:
        latest_md = get_most_recent_md_file()
    if not latest_md:
        return

    latest_md = os.path.abspath(latest_md)
    timestamp_file = get_timestamp_file_for_md(latest_md)

    # Ensure timestamp file exists; do not early-return on empty as we may need to backfill
    os.makedirs(os.path.dirname(timestamp_file), exist_ok=True)
    if not os.path.exists(timestamp_file):
        Path(timestamp_file).touch()

    # Consider interactive only if there is at least one User block with content
    has_user_content = False
    in_user_block = False
    with open(latest_md, 'r') as md_in:
        for raw_line in md_in:
            line = raw_line.rstrip('\n')
            if line.startswith('_**') and line.endswith('**_'):
                in_user_block = line.startswith('_**User')
                continue
            if in_user_block:
                if line.strip() and line.strip() != '---':
                    has_user_content = True
                    break

    # If no user content, don't merge timestamps; clear any noise
    if not has_user_content:
        # Clear any noise written by the watcher during startup/shutdown
        with open(timestamp_file, 'w'):
            pass
        return

    # Backfill any missing timestamps for headers that have content but weren't logged (e.g., watcher stopped early)
    md_lines = read_lines_text(latest_md)
    header_idxs = find_conversation_header_indices(md_lines)
    # Only count headers which have meaningful content following
    headers_with_content = []
    for h in header_idxs:
        header_txt = md_lines[h].strip() if h < len(md_lines) else ''
        snippet = first_meaningful_line_after(md_lines, h)
        if snippet and snippet != header_txt and snippet != '---':
            headers_with_content.append((h, snippet))

    with open(timestamp_file, 'r') as f:
        existing = [ln.strip() for ln in f if ln.strip()]

    if len(existing) < len(headers_with_content):
        # Append missing timestamps with the corresponding snippets
        now_ts = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        with open(timestamp_file, 'a') as f:
            for i in range(len(existing), len(headers_with_content)):
                _, snippet = headers_with_content[i]
                f.write(f"{now_ts}|{snippet}\n")

    # Read timestamps
    with open(timestamp_file, 'r') as f:
        raw = [line.strip() for line in f if line.strip()]
    timestamps = []
    last = None
    for ts in raw:
        if ts != last:
            timestamps.append(ts)
            last = ts

    # Process the markdown file
    temp_file = f"{latest_md}.tmp"
    timestamp_index = 0

    with open(latest_md, 'r') as md_in, open(temp_file, 'w') as md_out:
        for line in md_in:
            line = line.rstrip('\n')
            # Check if this line is a User or Agent header
            if line.startswith('_**') and ('User' in line or 'Agent' in line) and line.endswith('**_'):
                # Extract the role (User or Agent...)
                role = line[3:-3]  # Remove _** and **_

                # Get the next timestamp if available
                if timestamp_index < len(timestamps) and timestamps[timestamp_index]:
                    ts_line = timestamps[timestamp_index]
                    ts_display = ts_line.split('|', 1)[0].strip()
                    md_out.write(f"_**{role} ({ts_display})**_\n")
                    timestamp_index += 1
                else:
                    md_out.write(line + '\n')
            else:
                md_out.write(line + '\n')

    # Replace original with updated file
    shutil.move(temp_file, latest_md)

def merge_all_timestamps():
    """Merge timestamps into all markdown files in the history directory."""
    md_files = glob.glob(f"{HIST_DIR}/*.md")
    for md_path in md_files:
        merge_timestamps(md_path)


def stop_watcher():
    """Stop the background watcher started by this process and remove its pidfile."""
    pidfile = f"/tmp/specstory_watcher_{os.getpid()}"

    # Wait briefly for the pidfile to be populated
    deadline = time.time() + 2.0
    pid_text = None
    while time.time() < deadline:
        if os.path.exists(pidfile):
            with open(pidfile, 'r') as f:
                pid_text = f.read().strip()
            if pid_text:
                break
        time.sleep(0.1)

    if not pid_text:
        if os.path.exists(pidfile):
            os.remove(pidfile)
        return

    # Parse PID from JSON or plain text
    pid = json.loads(pid_text).get("pid") if pid_text.startswith('{') else int(pid_text)

    # Kill process group or individual process
    for sig in [signal.SIGTERM, signal.SIGKILL]:
        try:
            os.killpg(pid, sig)
        except (OSError, ProcessLookupError):
            try:
                os.kill(pid, sig)
            except (OSError, ProcessLookupError):
                break
        if sig == signal.SIGTERM:
            time.sleep(0.2)

    if os.path.exists(pidfile):
        os.remove(pidfile)


def print_specstory_banner():
    """Print a banner indicating specstory recording is active."""
    # ANSI color codes
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    # Print to stderr so it doesn't interfere with tool output
    print(f"{CYAN}╭{'─' * 50}╮{RESET}", file=sys.stderr)
    print(f"{CYAN}│{RESET} {GREEN}{BOLD}📝 SpecStory Recording Active{RESET}{'':>20}{CYAN}│{RESET}", file=sys.stderr)
    print(f"{CYAN}│{RESET}    Session will be logged to .specstory/{'':>9}{CYAN}│{RESET}", file=sys.stderr)
    print(f"{CYAN}╰{'─' * 50}╯{RESET}", file=sys.stderr)
    print(file=sys.stderr)
    sys.stderr.flush()  # Ensure banner is displayed immediately


def main():
    """Entry point: start watcher, run real tool, then merge timestamps."""
    # Debug: print to stderr to verify execution
    # print(f"DEBUG: specstory_wrapper.py called with {sys.argv}", file=sys.stderr)
    
    os.makedirs(TS_DIR, exist_ok=True)

    if len(sys.argv) > 1 and sys.argv[1] == 'run':
        print_specstory_banner()

    before_file = get_most_recent_md_file()
    before_mtime = os.path.getmtime(before_file) if before_file else None

    start_watcher(before_file, before_mtime)

    # Run SpecStory
    result = subprocess.run([REAL] + sys.argv[1:])

    # Give watcher time to finish, then stop it
    time.sleep(POLL_INTERVAL * 5)
    stop_watcher()
    time.sleep(POLL_INTERVAL * 2)

    # Merge timestamps into all markdown files
    merge_all_timestamps()

    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
