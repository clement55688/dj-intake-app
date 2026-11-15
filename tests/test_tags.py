import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from dj_intake import tags
from dj_intake.core import Store, Worker, tool


@unittest.skipUnless(tool('ffmpeg') and tags.AudioFile, 'FFmpeg and mutagen required')
class TagTests(unittest.TestCase):
    def test_cover_and_details_are_written_for_mp3_and_aiff(self):
        with tempfile.TemporaryDirectory() as home:
            jobdir = Path(home)
            ffmpeg = tool('ffmpeg')
            # A 16:9 "video thumbnail" that should become a square cover.
            subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'color=c=red:s=1280x720', '-frames:v', '1', str(jobdir/'source.jpg')], check=True)
            (jobdir/'source.info.json').write_text(json.dumps({'album': 'Discovery', 'genre': 'House', 'upload_date': '20240102',
                                                               'webpage_url': 'https://www.youtube.com/watch?v=aaaaaaaaaaa'}))
            worker = Worker(Store(jobdir/'store'))
            for ext in ('mp3', 'aiff'):
                audio = jobdir/f'finished.{ext}'
                subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=1', str(audio)], check=True)
                worker.add_tags(audio, jobdir, jobdir/'process.log')
                found = tags.AudioFile(audio).tags
                self.assertEqual(str(found['TALB']), 'Discovery')
                self.assertEqual(str(found['TCON']), 'House')
                self.assertEqual(str(found['TDRC']), '2024')
                self.assertIn('youtube.com', str(found.getall('COMM')[0]))
                cover = found.getall('APIC')[0]
                self.assertEqual(cover.mime, 'image/jpeg')
            probe = subprocess.run([tool('ffprobe'), '-v', 'error', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', str(jobdir/'cover.jpg')],
                                   capture_output=True, text=True, check=True).stdout.strip()
            self.assertEqual(probe, '600,600')

    def test_missing_info_is_harmless(self):
        with tempfile.TemporaryDirectory() as home:
            audio = Path(home)/'finished.mp3'
            subprocess.run([tool('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=1', str(audio)], check=True)
            Worker(Store(Path(home)/'store')).add_tags(audio, Path(home), Path(home)/'process.log')
            self.assertTrue(audio.is_file())


if __name__ == '__main__':
    unittest.main()
