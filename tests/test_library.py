import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dj_intake.core import Store, Worker, describe_quality, download_problem
from dj_intake.library import LibraryIndex, artist_names, name_guesses, title_key


class MatchingTests(unittest.TestCase):
    def test_title_key_drops_featuring_and_promo_but_keeps_remix(self):
        self.assertEqual(title_key('Let Me Love You (feat. Justin Bieber) [Official Video]'), 'let me love you')
        self.assertEqual(title_key('Let Me Love You ft. Justin Bieber'), 'let me love you')
        self.assertEqual(title_key('Piece Of Your Heart (Alok Remix)'), 'piece of your heart alok remix')

    def test_file_name_guesses(self):
        self.assertIn(('DJ Snake', 'Let Me Love You'), name_guesses('/m/DJ Snake_Let Me Love You.mp3'))
        self.assertIn(('Jay-Z', 'Empire State Of Mind'), name_guesses('/m/Jay-Z-Empire State Of Mind.mp3'))
        self.assertIn(('Eminem', 'Without Me'), name_guesses('/m/Eminem - Without Me (2).mp3'))
        self.assertEqual(name_guesses('/Music/Daft Punk/Discovery/01 One More Time.m4a'), [('Daft Punk', 'One More Time')])

    def test_artist_names_split_collaborations(self):
        self.assertEqual(artist_names('Martin Garrix & Brooks'), {'martin garrix', 'brooks'})

    def test_index_finds_same_song_not_remix_or_other_artist(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ('DJ Snake-Let Me Love You ft. Justin Bieber.mp3', 'Meduza_Piece Of Your Heart.mp3', 'Someone_Intro.mp3'):
                Path(folder, name).write_bytes(b'x')
            index = LibraryIndex(lambda: [folder])
            index.refresh(wait=True)
            self.assertTrue(index.find('DJ Snake', 'Let Me Love You (feat. Justin Bieber)').endswith('Justin Bieber.mp3'))
            self.assertIsNone(index.find('Meduza', 'Piece Of Your Heart (Alok Remix)'))
            self.assertIsNone(index.find('Other Artist', 'Intro'))
            self.assertIsNone(index.find('', 'Let Me Love You'))


class WorkerFlowTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.music = tempfile.TemporaryDirectory()
        self.store = Store(self.home.name)
        self.library = LibraryIndex(lambda: [self.music.name])
        self.library.refresh(wait=True)
        self.worker = Worker(self.store, self.library)
        self.candidates = [{'title': 'DJ Snake - Let Me Love You', 'artist': 'DJ Snake', 'duration': 205, 'url': 'https://www.youtube.com/watch?v=aaaaaaaaaaa'}]

    def tearDown(self):
        self.home.cleanup()
        self.music.cleanup()

    def run_job(self, info):
        job = self.store.add('https://soundcloud.com/djsnake/let-me-love-you')
        with patch.object(self.worker, 'metadata', return_value=info), patch.object(self.worker, 'search', return_value=self.candidates):
            self.worker.process(job)
        return self.store.get(job['id'])

    def test_locked_track_offers_youtube_versions(self):
        job = self.run_job({'id': '1', 'extractor_key': 'Soundcloud', 'title': 'Let Me Love You', 'uploader': 'DJ Snake',
                            'formats': [], '_warnings': 'WARNING: This video is DRM protected'})
        self.assertEqual((job['status'], job['hint']), ('needs_selection', 'locked'))
        self.assertEqual(json.loads(job['candidates'])[0]['url'], self.candidates[0]['url'])

    def test_preview_only_track_offers_youtube_versions(self):
        job = self.run_job({'id': '2', 'extractor_key': 'Soundcloud', 'title': 'Let Me Love You', 'artist': 'DJ Snake',
                            'formats': [{'format_id': 'http_mp3_1_0_preview'}, {'format_id': 'hls_mp3_1_0_preview'}]})
        self.assertEqual((job['status'], job['hint']), ('needs_selection', 'preview'))
        self.store.choose(job['id'], self.candidates[0]['url'])
        self.assertEqual(self.store.get(job['id'])['hint'], '')

    def test_already_have_pauses_until_download_anyway(self):
        Path(self.music.name, 'DJ Snake-Let Me Love You ft. Justin Bieber.mp3').write_bytes(b'x')
        self.library.refresh(wait=True)
        job = self.run_job({'id': '3', 'extractor_key': 'Soundcloud', 'title': 'Let Me Love You (feat. Justin Bieber)', 'artist': 'DJ Snake',
                            'formats': [{'format_id': 'hls_aac_160k'}]})
        self.assertEqual(job['status'], 'already_have')
        self.assertTrue(job['match_path'].endswith('Justin Bieber.mp3'))
        self.store.keep_duplicate(job['id'])
        again = self.store.get(job['id'])
        self.assertEqual((again['status'], again['allow_duplicate']), ('queued', 1))
        self.assertIsNone(self.worker.already_have(again, 'DJ Snake', 'Let Me Love You'))
        self.assertEqual(self.store.remove_job(job['id']), 'queued')


class HelperTests(unittest.TestCase):
    def test_download_problem(self):
        self.assertEqual(download_problem({'formats': [{'format_id': 'x', 'has_drm': True}]}), 'locked')
        self.assertEqual(download_problem({'formats': []}, 'This video is DRM protected'), 'locked')
        self.assertIsNone(download_problem({'formats': []}))
        self.assertIsNone(download_problem({'formats': [{'format_id': 'http_mp3_1_0_preview'}, {'format_id': 'hls_aac_160k'}]}))

    def test_quality_labels(self):
        self.assertEqual(describe_quality({'codec_name': 'aac', 'bit_rate': '160000'}, {}), {'label': 'AAC 160 kbps', 'tier': 'streaming'})
        self.assertEqual(describe_quality({'codec_name': 'opus'}, {'bit_rate': '134813'}), {'label': 'Opus ~130 kbps', 'tier': 'streaming'})
        self.assertEqual(describe_quality({'codec_name': 'flac'}, {})['tier'], 'lossless')


if __name__ == '__main__':
    unittest.main()
