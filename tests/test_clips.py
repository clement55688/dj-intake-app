import array
import json
import math
import sqlite3
import struct
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from dj_intake.core import Store, Worker, clip_range, digest, timestamp, tool


class ClipTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'catalog')
        self.output=Path(self.tmp.name)/'ready'
        self.store.save_settings({'profile':'mp3','output_dir':str(self.output)})

    def test_time_formats_and_invalid_ranges(self):
        self.assertEqual(clip_range('00:50','2:30'),(50,150))
        self.assertEqual(clip_range('','02:30'),(0,150))
        self.assertEqual(clip_range('',''),(None,None))
        self.assertEqual(timestamp('1:02:03.500'),3723.5)
        for a,b in [('2:30','00:50'),('00:50','00:50'),('-1','10'),('1:99','3:00'),('50',''),('nan','100'),('1:60:00','2:00:00')]:
            with self.subTest(a=a,b=b),self.assertRaises(ValueError):clip_range(a,b)

    def test_clips_and_profiles_are_distinct_from_full_tracks(self):
        url='https://youtu.be/BaW_jenozKc'
        full=self.store.add(url)
        first=self.store.add(url,'00:50','02:30')
        again=self.store.add(url,'50','150')
        other=self.store.add(url,'00:51','02:30')
        self.assertNotEqual(full['id'],first['id'])
        self.assertEqual(first['id'],again['id'])
        self.assertNotEqual(other['id'],first['id'])
        self.store.save_settings({'profile':'aiff','output_dir':str(self.output)})
        self.assertNotEqual(self.store.add(url,'50','150')['id'],first['id'])
        self.assertEqual(self.store.get(first['id'])['clip_start'],50)

    def test_existing_schema_gets_nullable_clip_columns(self):
        home=Path(self.tmp.name)/'old';home.mkdir()
        with sqlite3.connect(home/'queue.sqlite3') as c:
            c.execute('CREATE TABLE jobs (id TEXT PRIMARY KEY, input TEXT, source TEXT, url TEXT, status TEXT, title TEXT, artist TEXT, error TEXT, candidates TEXT, output TEXT, source_key TEXT, source_hash TEXT, output_hash TEXT, profile TEXT, created REAL, updated REAL)')
            c.execute("INSERT INTO jobs (id,status,title) VALUES ('existing','successful','Existing track')")
        store=Store(home)
        self.assertEqual(store.get('existing')['title'],'Existing track')
        self.assertIsNone(store.get('existing')['clip_start'])
        self.assertIsNone(store.get('existing')['clip_end'])

    @unittest.skipUnless(tool('ffmpeg') and tool('ffprobe'),'FFmpeg required')
    def test_real_cut_has_correct_duration_and_contains_selected_audio(self):
        source=Path(self.tmp.name)/'tones.wav'
        rate=44100
        with wave.open(str(source),'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(rate)
            wav.writeframes(b''.join(struct.pack('<h',int(10000*math.sin(2*math.pi*(440*(i//rate+1))*i/rate))) for i in range(rate*4)))
        original_hash=digest(source)
        for profile in ('mp3','aiff','original'):
            self.store.save_settings({'profile':profile,'output_dir':str(self.output)})
            job=self.store.add('Clip test '+profile,'0:01','0:03')
            directory=self.store.home/'jobs'/job['id'];directory.mkdir(parents=True)
            Worker(self.store).finish(job,source,'Track','Artist',directory)
            output=Path(self.store.get(job['id'])['output'])
            self.assertIn('Artist_Track (00m01s-00m03s)',output.name)
            result=json.loads(subprocess.check_output([tool('ffprobe'),'-v','error','-show_format','-of','json',str(output)]))
            self.assertAlmostEqual(float(result['format']['duration']),2,delta=.1)
            decoded=subprocess.check_output([tool('ffmpeg'),'-v','error','-i',str(output),'-ac','1','-ar',str(rate),'-f','f32le','-'])
            samples=array.array('f');samples.frombytes(decoded)
            # Each middle half-second should contain the chosen second/third tones.
            for begin,frequency in ((.25,880),(1.25,1320)):
                segment=samples[int(begin*rate):int((begin+.5)*rate)]
                crossings=sum(a<=0<b for a,b in zip(segment,segment[1:]))
                self.assertAlmostEqual(crossings/.5,frequency,delta=5)
            manifest=json.loads((directory/'result.json').read_text())
            self.assertEqual(manifest['original'],str(source))
            self.assertEqual(manifest['clip_start'],1)
        self.assertEqual(digest(source),original_hash)
        invalid=self.store.add('Past the end','1','10')
        directory=self.store.home/'jobs'/invalid['id'];directory.mkdir(parents=True)
        with self.assertRaisesRegex(RuntimeError,'outside this recording'):
            Worker(self.store).finish(invalid,source,'Track','Artist',directory)


if __name__=='__main__':unittest.main()
