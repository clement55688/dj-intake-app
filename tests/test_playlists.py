import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from dj_intake.core import Store, Worker, playlist_link, split_title
from dj_intake.library import LibraryIndex


class PlaylistTests(unittest.TestCase):
    def test_playlist_links(self):
        self.assertEqual(playlist_link('https://www.youtube.com/playlist?list=PL123'), 'youtube')
        self.assertEqual(playlist_link('music.youtube.com/playlist?list=PL123'), 'youtube')
        self.assertEqual(playlist_link('https://soundcloud.com/artist/sets/my-set'), 'soundcloud')
        self.assertEqual(playlist_link('https://c418.bandcamp.com/album/alpha'), 'bandcamp')
        self.assertIsNone(playlist_link('https://www.youtube.com/watch?v=aaaaaaaaaaa&list=PL123'))
        self.assertIsNone(playlist_link('https://soundcloud.com/artist/track'))

    def test_split_title(self):
        self.assertEqual(split_title('', 'Eminem - Without Me (Official Video)'), ('Eminem', 'Without Me'))
        self.assertEqual(split_title('Daft Punk', 'One More Time'), ('Daft Punk', 'One More Time'))

    def test_listing_skips_unusable_entries_and_marks_tracks_you_have(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as music:
            open(music + '/Eminem_Without Me.mp3', 'wb').close()
            worker = Worker(Store(home), LibraryIndex(lambda: [music]))
            worker.library.refresh(wait=True)
            listing = {'title': 'Mix', 'entries': [
                {'id': 'aaaaaaaaaaa', 'title': 'Eminem - Without Me (Official Video)'},
                {'id': 'bbbbbbbbbbb', 'title': '[Private video]'},
                {'id': 'ccccccccccc', 'title': 'Song', 'channel': 'X', 'duration': 200},
                None]}
            done = SimpleNamespace(returncode=0, stdout=json.dumps(listing))
            with patch('dj_intake.core.subprocess.run', return_value=done) as run:
                result = worker.playlist('https://www.youtube.com/playlist?list=PL1')
            args = run.call_args[0][0]
            self.assertIn('--yes-playlist', args)
            self.assertNotIn('--no-playlist', args)
            self.assertEqual([t['url'][-11:] for t in result['tracks']], ['aaaaaaaaaaa', 'ccccccccccc'])
            self.assertEqual([t['have'] for t in result['tracks']], [True, False])
            with self.assertRaises(ValueError):
                worker.playlist('https://www.youtube.com/watch?v=aaaaaaaaaaa')


if __name__ == '__main__':
    unittest.main()
