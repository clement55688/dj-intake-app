import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from dj_intake.core import Store, Worker, clean, route, digest, tool, track_stem, tidy_track, publish_file

class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name)/'data')
        self.output = Path(self.tmp.name)/'ready'
        self.store.save_settings({'profile':'mp3','output_dir':str(self.output)})

    def test_url_dedup_and_failure_retry(self):
        a = self.store.add('https://music.youtube.com/watch?v=BaW_jenozKc&si=tracking')
        b = self.store.add('https://youtu.be/BaW_jenozKc')
        self.assertEqual(a['id'],b['id'])
        self.store.update(a['id'],status='failed',error='Network unavailable')
        self.store.retry(a['id'])
        self.assertEqual(self.store.get(a['id'])['status'],'queued')
        self.assertEqual(self.store.get(a['id'])['error'],'')

    def test_watch_urls_inside_playlists_select_current_track(self):
        for url in [
            'https://music.youtube.com/watch?v=BmSY0FEm3PQ&list=RDAMVMBmSY0FEm3PQ&index=4',
            'https://www.youtube.com/watch?v=BmSY0FEm3PQ&list=PLexample&start_radio=1',
            'https://youtu.be/BmSY0FEm3PQ?si=tracking&list=PLexample',
        ]:
            with self.subTest(url=url):
                self.assertEqual(route(url), ('YouTube', 'https://www.youtube.com/watch?v=BmSY0FEm3PQ'))
        with self.assertRaises(ValueError):
            route('https://music.youtube.com/playlist?list=PLexample')

    def test_selection_must_be_from_search(self):
        job=self.store.add('Artist - Track Extended Mix')
        self.store.update(job['id'],status='needs_selection',candidates=json.dumps([{'title':'Track Extended Mix','url':'https://youtu.be/BaW_jenozKc'}]))
        with self.assertRaises(ValueError): self.store.choose(job['id'],'https://youtu.be/aaaaaaaaaaa')
        self.store.choose(job['id'],'https://youtu.be/BaW_jenozKc')
        self.assertEqual(self.store.get(job['id'])['source'],'YouTube')

    def test_interrupted_jobs_recover(self):
        job=self.store.add('Artist - Track')
        self.store.update(job['id'],status='downloading')
        recovered=Store(self.store.home)
        self.assertEqual(recovered.get(job['id'])['status'],'queued')

    def test_spotify_is_lookup_and_network_inputs_restricted(self):
        self.assertEqual(route('https://open.spotify.com/track/123abc')[0],'Spotify lookup')
        for url in ['http://youtube.com/watch?v=BaW_jenozKc','https://127.0.0.1/a','file:///etc/passwd','https://youtube.com.evil.test/watch?v=BaW_jenozKc','https://youtube.com/playlist?list=x']:
            with self.subTest(url=url),self.assertRaises(ValueError):route(url)
        self.assertNotIn('/',clean('蔡健雅 / 紅色高跟鞋'))
        self.assertLessEqual(len(clean('歌'*100).encode()),160)

    def test_naming_preserves_remix_and_removes_promotion(self):
        self.assertEqual(track_stem('AFROJACK & Martin Garrix','Turn Up The Speakers (Julian Jordan Remix) [Official Audio]'),
                         'AFROJACK & Martin Garrix_Turn Up The Speakers (Julian Jordan Remix)')
        self.assertEqual(tidy_track('Artist','Artist - Song (Official Music Video)'),('Artist','Song'))
        self.assertEqual(tidy_track('AFROJACK', 'Ten Feet Tall (Lyric Video) ft. Wrabel'), ('AFROJACK', 'Ten Feet Tall ft. Wrabel'))
        self.assertEqual(track_stem('', 'Track'), 'Unknown Artist_Track')
        self.assertLessEqual(len(track_stem('歌'*100,'曲'*100).encode()),160)

    def test_publication_collision_uses_number_and_recovers(self):
        self.output.mkdir(exist_ok=True)
        first=Path(self.tmp.name)/'one'; first.write_bytes(b'original')
        second=Path(self.tmp.name)/'two'; second.write_bytes(b'different recording')
        a=publish_file(first,self.output,'Artist_Song','.mp3')
        b=publish_file(second,self.output,'Artist_Song','.mp3')
        self.assertEqual(a.name,'Artist_Song.mp3')
        self.assertEqual(b.name,'Artist_Song (2).mp3')
        self.assertEqual(publish_file(second,self.output,'Artist_Song','.mp3'),b)
        self.assertEqual(a.read_bytes(),b'original')

    def test_existing_staging_names_and_history_migrate(self):
        from scripts.rename_staged import migrate
        old=self.output/'Artist - Song [123abcde].mp3'
        old.write_bytes(b'original audio bytes')
        jobs=[self.store.add('Track one'),self.store.add('Track two')]
        for job in jobs:
            self.store.update(job['id'],status='successful',title='Song',artist='Artist',output=str(old),output_hash=digest(old))
            directory=self.store.home/'jobs'/job['id'];directory.mkdir(parents=True)
            (directory/'result.json').write_text(json.dumps({'output':str(old)}))
        changes=migrate(self.store)
        self.assertEqual(len(changes),1)
        self.assertFalse(old.exists())
        new=(self.output/'Artist_Song.mp3').resolve()
        self.assertEqual(new.read_bytes(),b'original audio bytes')
        for job in jobs:
            self.assertEqual(self.store.get(job['id'])['output'],str(new))
            manifest=self.store.home/'jobs'/job['id']/'result.json'
            self.assertEqual(json.loads(manifest.read_text())['output'],str(new))
        self.assertEqual(migrate(self.store),[])

    def test_worker_errors_move_to_failed(self):
        job=self.store.add('Artist - Track')
        worker=Worker(self.store)
        def fail(_):
            worker.stop.set()
            raise RuntimeError('Example network error')
        with patch.object(worker,'process',side_effect=fail): worker.run()
        result=self.store.get(job['id'])
        self.assertEqual(result['status'],'failed')
        self.assertIn('network error',result['error'])

    @unittest.skipUnless(tool('ffmpeg') and tool('ffprobe'),'FFmpeg required')
    def test_real_audio_processing_profiles_and_recovery(self):
        import subprocess
        source=Path(self.tmp.name)/'source.wav'
        subprocess.run([tool('ffmpeg'),'-v','error','-f','lavfi','-i','sine=frequency=440:duration=1','-c:a','pcm_s16le',str(source)],check=True)
        for profile in ['mp3','aiff','original']:
            self.store.save_settings({'profile':profile,'output_dir':str(self.output)})
            job=self.store.add('Test '+profile)
            jobdir=self.store.home/'jobs'/job['id'];jobdir.mkdir(parents=True)
            Worker(self.store).finish(job,source,'Track (Test)','Artist',jobdir)
            result=self.store.get(job['id']);path=Path(result['output'])
            self.assertEqual(result['status'],'successful')
            self.assertEqual(digest(path),result['output_hash'])
            self.assertTrue((jobdir/'result.json').exists())
            self.assertTrue(source.exists())
            # Same destination on interrupted publication is reusable, never overwritten.
            Worker(self.store).finish(job,source,'Track (Test)','Artist',jobdir)
            if profile!='original':
                from mutagen import File
                tags=File(path)
                self.assertIn('Artist',str(tags.tags))
        self.assertEqual(len(list(self.output.glob('*'))),3)

if __name__=='__main__':unittest.main()
