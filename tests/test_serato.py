import os
import tempfile
import unittest
from pathlib import Path

from dj_intake.core import Store
from dj_intake import serato


class CrateFormatTests(unittest.TestCase):
    def test_round_trip_keeps_order_unicode_and_drops_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            crate = os.path.join(folder, 'Subcrates', 'Test.crate')
            paths = ['/Users/me/Music/蛋堡_關鍵字.mp3', '/Users/me/Music/Rósalía_x.mp3', '/Users/me/Music/a 🎧.mp3', '/Users/me/Music/蛋堡_關鍵字.mp3']
            serato.write_crate(crate, paths, volume_root='/')
            self.assertEqual(serato.read_crate(crate, volume_root='/'), ['/Users/me/Music/蛋堡_關鍵字.mp3', '/Users/me/Music/R\u00f3salía_x.mp3', '/Users/me/Music/a 🎧.mp3'])
            data = Path(crate).read_bytes()
            self.assertTrue(data.startswith(b'vrsn'))
            self.assertEqual(serato.parse_tags(data)[0][1].decode('utf-16-be'), serato.CRATE_VERSION)
            self.assertEqual(serato.serialize_tags(serato.parse_tags(data)), data)

    def test_paths_are_stored_relative_to_the_volume(self):
        self.assertEqual(serato.serato_location('/Users/me/Music/x.mp3')[1], 'Users/me/Music/x.mp3')


class CrateSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.store = Store(base / 'home')
        self.folder = base / '_Serato_'
        (self.folder / 'Subcrates').mkdir(parents=True)
        self.serato_open = False
        self.sync = serato.CrateSync(self.store, self.folder, running=lambda: self.serato_open)
        self.files = []
        for name in ('A_One.mp3', 'B_Two.mp3'):
            path = base / name
            path.write_bytes(b'x')
            job = self.store.add('https://www.youtube.com/watch?v=' + name[0] * 11)
            self.store.update(job['id'], status='successful', output=str(path))
            self.files.append(str(path))

    def tearDown(self):
        self.tmp.cleanup()

    def test_nothing_happens_until_turned_on(self):
        self.sync.tick(now=1000)
        self.assertFalse(os.path.exists(self.sync.crate_path()))
        self.assertFalse(self.sync.summary()['decided'])

    def test_waits_for_serato_to_close_then_writes_and_keeps_user_edits(self):
        self.store.set_setting('serato_crate', 'on')
        self.serato_open = True
        self.sync.tick(now=1000)
        self.assertFalse(os.path.exists(self.sync.crate_path()))
        self.assertEqual(self.sync.summary()['status'], 'waiting')
        self.serato_open = False
        self.sync.tick(now=1005)  # Serato may still be saving on quit
        self.assertFalse(os.path.exists(self.sync.crate_path()))
        self.sync.tick(now=1020)
        self.assertEqual(sorted(serato.read_crate(self.sync.crate_path(), volume_root='/')), sorted(self.files))
        # A track the DJ dragged into the crate inside Serato stays, and the old crate is backed up.
        extra = '/Users/me/Music/Mine.mp3'
        serato.write_crate(self.sync.crate_path(), [extra] + self.files, volume_root='/')
        newer = Path(self.tmp.name) / 'C_Three.mp3'
        newer.write_bytes(b'x')
        job = self.store.add('https://www.youtube.com/watch?v=' + 'C' * 11)
        self.store.update(job['id'], status='successful', output=str(newer))
        self.sync.tick(now=2000)
        self.assertEqual(serato.read_crate(self.sync.crate_path(), volume_root='/'), [extra] + self.files + [str(newer)])
        self.assertEqual(len(os.listdir(self.store.home / 'serato-backups')), 1)


if __name__ == '__main__':
    unittest.main()
