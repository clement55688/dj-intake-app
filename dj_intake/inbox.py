"""Send from iPhone: links shared with the "Send to DJ Intake" shortcut land in iCloud Drive
(Shortcuts › DJ Intake Inbox) as small text files; DJ Intake queues them and deletes them.

macOS asks once before an app can read iCloud Drive, and the read waits until that is
answered, so everything here runs on a background thread and only after the person turns
the feature on.
"""
from __future__ import annotations
import os
import re
import shutil
import time
from pathlib import Path

SHORTCUTS_DRIVE = Path.home() / 'Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents'
FOLDER_NAME = 'DJ Intake Inbox'
SHORTCUT_NAME = 'Send to DJ Intake.shortcut'
DATALESS = 0x40000000  # stat flag for an iCloud file that hasn't downloaded yet
URL = re.compile(r'https?://\S+')


def requests_in(text):
    """Links in shared text (apps often add words around them), else the text as a song name."""
    text = text.lstrip('﻿').strip()
    links = [link.rstrip('.,)>"\'') for link in URL.findall(text)]
    if links:
        return links[:20]
    first = text.splitlines()[0].strip() if text else ''
    return [first] if first else []


class Inbox:
    def __init__(self, store, root=SHORTCUTS_DRIVE, shortcut=None):
        self.store = store
        self.root = Path(root)
        self.folder = self.root / FOLDER_NAME
        self.shortcut = Path(shortcut) if shortcut else Path(__file__).resolve().parent.parent / 'assets' / SHORTCUT_NAME
        self.state = {'status': 'off', 'added': 0, 'checked': None, 'since': None}
        self.done = set()

    def enabled(self):
        return self.store.setting('phone_inbox', '') == 'on'

    def summary(self):
        state = dict(self.state, enabled=self.enabled(), icloud=self.root.is_dir())
        # A check that hasn't come back is almost always the macOS permission prompt.
        if state['status'] == 'checking' and state['since'] and time.time() - state['since'] > 6:
            state['status'] = 'permission'
        return state

    def tick(self, now=None):
        now = time.time() if now is None else now
        if not self.enabled():
            self.state['status'] = 'off'
            return
        if not self.root.is_dir():
            self.state['status'] = 'no-icloud'
            return
        self.state.update(status='checking', since=now)
        self.folder.mkdir(exist_ok=True)
        copy = self.root / SHORTCUT_NAME
        if self.shortcut.is_file() and not copy.exists():
            shutil.copyfile(self.shortcut, copy)  # so the iPhone can open it from the Files app
        for path in sorted(self.folder.iterdir()):
            if path.name.startswith('.') or path.suffix.lower() != '.txt' or path.name in self.done:
                continue
            info = path.stat()
            if info.st_flags & DATALESS or now - info.st_mtime < 3 or info.st_size > 4096:
                continue  # still syncing, or not a shared link
            for value in requests_in(path.read_text(errors='replace')):
                try:
                    self.store.add(value)
                    self.state['added'] += 1
                except ValueError:
                    pass
            self.done.add(path.name)
            path.unlink(missing_ok=True)
        self.state.update(status='ok', checked=now, since=None)

    def loop(self, stop):
        while not stop.wait(8):
            try:
                self.tick()
            except Exception as error:
                self.state.update(status='error', error=str(error)[:200], since=None)
