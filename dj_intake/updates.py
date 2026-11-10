"""Check GitHub for a newer DJ Intake release and run the update script on request.

The check sends one anonymous request to GitHub's public releases API, at most every
few hours, and can be turned off in Preferences. Installing runs the same
scripts/update.command a user would run by hand, then reopens the Desktop app.
"""
from __future__ import annotations
import json
import re
import shlex
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

VERSION = '0.4.2'
REPO = 'clement55688/dj-intake-app'
API = f'https://api.github.com/repos/{REPO}/releases/latest'
CHECK_EVERY = 6 * 3600


def parse_version(value):
    """'v0.4.10' -> (0, 4, 10); None if it isn't a plain version tag."""
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', str(value or '').strip())
    return tuple(int(part) for part in match.groups()) if match else None


def latest_release():
    """Return {'version', 'url'} for the newest published release, or None if unavailable."""
    request = Request(API, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'DJ-Intake-update-check'})
    with urlopen(request, timeout=8) as response:
        data = json.load(response)
    version = parse_version(data.get('tag_name'))
    if not version or data.get('draft') or data.get('prerelease'):
        return None
    return {'version': '.'.join(map(str, version)), 'url': data.get('html_url') or f'https://github.com/{REPO}/releases/latest'}


class UpdateChecker:
    def __init__(self, fetch=latest_release, current=VERSION):
        self.fetch, self.current = fetch, current
        self.latest, self.checked_at, self.lock = None, 0.0, threading.Lock()

    def refresh(self, force=False):
        with self.lock:
            if not force and time.time() - self.checked_at < CHECK_EVERY:
                return
            self.checked_at = time.time()
        try:
            latest = self.fetch()
        except Exception:  # offline, rate limited, GitHub down: try again later
            return
        with self.lock:
            self.latest = latest

    def status(self, enabled=True):
        """What the page shows. Never blocks: refreshes in the background when stale."""
        if not enabled:
            return None
        if time.time() - self.checked_at >= CHECK_EVERY:
            threading.Thread(target=self.refresh, daemon=True).start()
        latest = self.latest
        if latest and (parse_version(latest['version']) or ()) > (parse_version(self.current) or ()):
            return {'current': self.current, **latest}
        return None


def installed_copy(root):
    """True when running from the public installer's checkout, which update.command can pull."""
    try:
        remote = subprocess.run(['git', '-C', str(root), 'remote', 'get-url', 'origin'],
                                capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False
    return (root / 'scripts/update.command').is_file() and remote.rstrip('/').removesuffix('.git').endswith(REPO)


def start_install(root):
    """Run the update in a detached shell that outlives this server, then reopen the app."""
    log = Path.home() / 'Library/Logs/dj-intake-update.log'
    script = f'''#!/bin/bash
sleep 2
osascript -e 'tell application id "local.djintake.launcher" to quit' >/dev/null 2>&1
sleep 1
if bash {shlex.quote(str(root / 'scripts/update.command'))} >{shlex.quote(str(log))} 2>&1; then
  open "$HOME/Desktop/DJ Intake.app"
else
  osascript -e 'display alert "DJ Intake update didn’t finish" message "Your library is safe. Details are in ~/Library/Logs/dj-intake-update.log. Reopening the current version."' >/dev/null 2>&1
  open "$HOME/Desktop/DJ Intake.app"
fi
'''
    with tempfile.NamedTemporaryFile('w', suffix='.sh', delete=False) as handle:
        handle.write(script)
    subprocess.Popen(['/bin/bash', handle.name], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
