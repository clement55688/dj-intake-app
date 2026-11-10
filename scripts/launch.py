#!/usr/bin/env python3
"""Start DJ Intake if necessary, then explicitly open its page on macOS."""
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
URL = 'http://127.0.0.1:8765/'


def ready():
    try:
        with urlopen(URL, timeout=1) as response:
            return response.status == 200 and b'<title>DJ Intake</title>' in response.read(64000)
    except OSError:
        return False


def launch(open_browser=True):
    if not ready():
        log = Path.home() / 'Library/Logs/dj-intake-app.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open('ab') as stream:
            subprocess.Popen(
                [str(ROOT / '.venv/bin/python'), '-m', 'dj_intake.server', '--no-browser'],
                cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stream, stderr=stream,
                close_fds=True, start_new_session=True,
            )
        for _ in range(60):
            if ready():
                break
            time.sleep(.25)
        else:
            raise RuntimeError('The server did not start. See ~/Library/Logs/dj-intake-app.log.')
    # Explicit Launch Services request instead of Python's browser detection.
    if open_browser:
        subprocess.run(['/usr/bin/open', URL], check=True, timeout=15)


if __name__ == '__main__':
    try:
        launch(open_browser="--no-browser" not in sys.argv[1:])
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
