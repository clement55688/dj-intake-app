"""Run an explicitly configured Apple Shortcut and return its text match."""
import subprocess
import sys
import tempfile
from pathlib import Path

SHORTCUT = 'DJ Intake Recognize'
HEARING_HELP = ('Shazam couldn\u2019t hear a song. Play it out loud through your speakers \u2014 it can\u2019t hear headphones \u2014 '
                'and make sure your Mac\u2019s microphone is the input in Sound settings.')


def shortcut_is_installed():
    if sys.platform != 'darwin':
        raise ValueError('Music recognition requires Apple Shortcuts on macOS.')
    result = subprocess.run(
        ['/usr/bin/shortcuts', 'list'], capture_output=True, text=True,
        timeout=10, check=True,
    )
    return SHORTCUT in result.stdout.splitlines()


def open_setup():
    from .core import ROOT

    try:
        installed = shortcut_is_installed()
        if installed:
            command = ['/usr/bin/shortcuts', 'view', SHORTCUT]
        else:
            template = ROOT / 'assets' / f'{SHORTCUT}.shortcut'
            if not template.is_file():
                raise ValueError('The setup file is missing. Reinstall DJ Intake and try again.')
            command = ['/usr/bin/open', '-a', 'Shortcuts', str(template)]
        subprocess.run(command, capture_output=True, timeout=15, check=True)
        return installed
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError('Could not open Apple Shortcuts. Try opening the app and clicking Set up recognition again.') from error


def identify():
    try:
        if not shortcut_is_installed():
            raise ValueError('Click Set up recognition, then Add Shortcut in Apple Shortcuts.')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'match.txt'
            result = subprocess.run(
                ['/usr/bin/shortcuts', 'run', SHORTCUT, '--output-path', str(output),
                 '--output-type', 'public.plain-text'],
                capture_output=True, timeout=60,
            )
            if result.returncode or not output.is_file():
                detail = result.stderr.decode('utf-8', 'replace').casefold()
                # Shazam reports silence (e.g. music only in headphones) as a network problem.
                if 'network' in detail or 'no match' in detail or 'couldn' in detail:
                    raise ValueError(HEARING_HELP)
                raise ValueError('No song was returned. Check the shortcut permissions or try again during a clearer part of the track.')
            with output.open('rb') as stream:
                match = ' '.join(stream.read(4097).decode('utf-8').split())
            if not match or len(match) > 512:
                raise ValueError('No usable match. Configure the shortcut to return one line with the artist and song title.')
            return match
    except subprocess.TimeoutExpired as error:
        raise ValueError('Recognition timed out. Check for a permission prompt in Shortcuts.') from error
    except (OSError, UnicodeError, subprocess.CalledProcessError) as error:
        raise ValueError('Could not read a match from Apple Shortcuts.') from error
