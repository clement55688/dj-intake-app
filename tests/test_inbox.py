import os
import tempfile
import unittest
from pathlib import Path

from dj_intake.core import Store
from dj_intake.inbox import Inbox, requests_in


class InboxTests(unittest.TestCase):
    def test_requests_in_shared_text(self):
        self.assertEqual(requests_in('﻿Check this out https://soundcloud.com/a/b, so good'), ['https://soundcloud.com/a/b'])
        self.assertEqual(requests_in('Fred again.. - Delilah\n'), ['Fred again.. - Delilah'])
        self.assertEqual(requests_in('  '), [])

    def test_queues_shared_files_once_and_waits_for_sync(self):
        with tempfile.TemporaryDirectory() as base:
            store = Store(Path(base) / 'home')
            shortcut = Path(base) / 'Send.shortcut'
            shortcut.write_bytes(b'AEA1')
            root = Path(base) / 'Shortcuts'
            root.mkdir()
            inbox = Inbox(store, root, shortcut)
            inbox.tick(now=1000)
            self.assertEqual(inbox.summary()['status'], 'off')
            self.assertFalse(inbox.folder.exists())  # nothing touches iCloud until turned on
            store.set_setting('phone_inbox', 'on')
            inbox.tick(now=1000)
            self.assertTrue((root / 'Send to DJ Intake.shortcut').is_file())
            shared = inbox.folder / '20261114-120000-123456.txt'
            shared.write_text('https://www.youtube.com/watch?v=aaaaaaaaaaa')
            fresh = inbox.folder / '20261114-120001-654321.txt'
            fresh.write_text('Overmono - So U Kno')
            os.utime(shared, (900, 900))
            inbox.tick(now=os.stat(fresh).st_mtime + 1)  # the newer file may still be syncing
            self.assertFalse(shared.exists())
            self.assertTrue(fresh.exists())
            inbox.tick(now=os.stat(fresh).st_mtime + 10)
            self.assertEqual(sorted(job['input'] for job in store.jobs()), ['Overmono - So U Kno', 'https://www.youtube.com/watch?v=aaaaaaaaaaa'])
            self.assertEqual(inbox.summary()['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
