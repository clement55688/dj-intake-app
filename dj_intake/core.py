from __future__ import annotations
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen, Request

ROOT = Path(__file__).resolve().parent.parent


def clean(text, limit=160):
    text = unicodedata.normalize('NFC', str(text))
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip(' .') or 'Unknown'
    return text.encode('utf-8')[:limit].decode('utf-8', 'ignore').rstrip(' .')



def tidy_track(artist, title):
    artist = unicodedata.normalize('NFC', str(artist or '')).strip()
    title = unicodedata.normalize('NFC', str(title or 'Untitled')).strip()
    if artist and title.casefold().startswith((artist + ' - ').casefold()):
        title = title[len(artist) + 3:]
    # Remove only explicit promotional suffixes; keep remix/edit and content labels.
    promo = r'(?:official\s+(?:music\s+)?(?:video|audio|visuali[sz]er)|lyrics?\s+video|official\s+lyrics?)'
    title = re.sub(r'\s*(?:\(' + promo + r'\)|\[' + promo + r'\])\s*', ' ', title, flags=re.I).strip()
    pattern = r'\s*(?:\(' + promo + r'\)|\[' + promo + r'\]|[-|–—]\s*' + promo + r')\s*$'
    while True:
        updated = re.sub(pattern, '', title, flags=re.I).strip()
        if updated == title:
            break
        title = updated
    return artist, title or 'Untitled'


def track_stem(artist, title):
    artist, title = tidy_track(artist, title)
    artist = clean(artist or 'Unknown Artist', 70)
    return artist + '_' + clean(title, 160 - len(artist.encode('utf-8')) - 1)


def publish_file(staged, folder, stem, extension):
    """Publish atomically without overwriting; numeric suffixes only on collisions."""
    expected = digest(staged)
    for number in range(1, 10001):
        output = Path(folder) / (stem + (f' ({number})' if number > 1 else '') + extension)
        try:
            os.link(staged, output)
            return output
        except FileExistsError:
            if output.is_file() and digest(output) == expected:
                return output
    raise RuntimeError('Too many files share this name. Choose a more specific title.')


def timestamp(value):
    text = str(value).strip()
    if not re.fullmatch(r'\d+(?::\d{1,2}){0,2}(?:\.\d{1,3})?', text):
        raise ValueError('Use seconds, MM:SS, or HH:MM:SS, for example 00:50.')
    parts = [float(part) for part in text.split(':')]
    if any(part >= 60 for part in parts[1:]):
        raise ValueError('Seconds and hour-format minutes must be below 60.')
    result = 0.0
    for part in parts:
        result = result * 60 + part
    if not math.isfinite(result) or result > 86400:
        raise ValueError('Timestamps must be between 0 and 24 hours.')
    return result


def clip_range(start='', end=''):
    if str(start or '').strip() == '' and str(end or '').strip() == '':
        return None, None
    if str(end or '').strip() == '':
        raise ValueError('Enter an end time for the clip, or clear both times for the full track.')
    a = timestamp(start) if str(start or '').strip() else 0.0
    b = timestamp(end)
    if b <= a:
        raise ValueError('End time must be later than start time.')
    return a, b


def clip_label(seconds):
    minutes, remainder = divmod(seconds, 60)
    sec = f'{remainder:06.3f}'.rstrip('0').rstrip('.')
    return f'{int(minutes):02d}m{sec}s'


def job_stem(artist, title, job):
    stem = track_stem(artist, title)
    if job.get('clip_end') is not None:
        stem += f" ({clip_label(job['clip_start'])}-{clip_label(job['clip_end'])})"
    return stem


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def route(value):
    value = value.strip()
    if not value or len(value) > 2000:
        raise ValueError('Enter a track URL or artist and song name (up to 2,000 characters).')
    if '://' not in value:
        if value.startswith(('www.', 'youtube.com/', 'youtu.be/', 'soundcloud.com/', 'open.spotify.com/')):
            value = 'https://' + value
        else:
            return 'Search', value
    u = urlparse(value)
    if u.scheme != 'https' or u.username or u.password:
        raise ValueError('Use an HTTPS track URL without embedded credentials.')
    host = (u.hostname or '').lower()
    if u.port not in (None, 443):
        raise ValueError('Custom network ports are not supported.')
    if host in ('youtube.com', 'www.youtube.com', 'music.youtube.com', 'm.youtube.com', 'youtu.be'):
        vid = u.path.strip('/') if host == 'youtu.be' else parse_qs(u.query).get('v', [''])[0]
        if not vid and u.path.startswith(('/shorts/', '/embed/')):
            vid = u.path.split('/')[2]
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', vid):
            raise ValueError('Paste an individual YouTube track/video URL, rather than a playlist.')
        return 'YouTube', 'https://www.youtube.com/watch?v=' + vid
    if host in ('soundcloud.com', 'www.soundcloud.com', 'on.soundcloud.com'):
        return 'SoundCloud', value
    if host == 'open.spotify.com':
        if not re.search(r'/track/[A-Za-z0-9]+', u.path):
            raise ValueError('Paste an individual Spotify track link.')
        return 'Spotify lookup', value
    if host.endswith('.bandcamp.com'):
        if not u.path.startswith('/track/'):
            raise ValueError('Paste an individual Bandcamp track link.')
        return 'Bandcamp', value
    raise ValueError('Supported: YouTube, SoundCloud, Bandcamp track URLs, Spotify track references, or song names.')


class Store:
    def __init__(self, home):
        self.home = Path(home).expanduser().resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.db = self.home / 'queue.sqlite3'
        with self.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, input TEXT, source TEXT, url TEXT, status TEXT, title TEXT, artist TEXT, error TEXT, candidates TEXT, output TEXT, source_key TEXT, source_hash TEXT, output_hash TEXT, profile TEXT, created REAL, updated REAL)')
            columns = {row[1] for row in c.execute('PRAGMA table_info(jobs)')}
            for column in ('clip_start', 'clip_end'):
                if column not in columns:
                    c.execute(f'ALTER TABLE jobs ADD COLUMN {column} REAL')
            if 'find_identity' not in columns:
                c.execute('ALTER TABLE jobs ADD COLUMN find_identity TEXT')
            c.execute('CREATE TABLE IF NOT EXISTS finds (identity TEXT PRIMARY KEY, name TEXT NOT NULL, found_at REAL NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
            c.execute("UPDATE jobs SET status='queued', error='Resumed after app restart' WHERE status IN ('resolving','downloading','processing')")
        self.wake = threading.Event()

    def connect(self):
        c = sqlite3.connect(self.db, timeout=20)
        c.row_factory = sqlite3.Row
        return c

    def remember_find(self, name):
        found_at = time.time()
        identity = unicodedata.normalize('NFC', name).casefold()
        with self.connect() as connection:
            connection.execute(
                'INSERT INTO finds VALUES (?, ?, ?) ON CONFLICT(identity) DO UPDATE SET found_at=excluded.found_at',
                (identity, name, found_at),
            )
            return dict(connection.execute('SELECT * FROM finds WHERE identity=?', (identity,)).fetchone())

    def finds(self):
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                'SELECT identity, name, found_at FROM finds ORDER BY found_at DESC'
            )]

    def rename_find(self, identity, name):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 240 or any(ord(ch) < 32 for ch in name):
            raise ValueError('Enter a song name of up to 240 characters on one line.')
        with self.connect() as c:
            if not c.execute('UPDATE finds SET name=? WHERE identity=?',
                             (unicodedata.normalize('NFC', name.strip()), identity)).rowcount:
                raise ValueError('Saved find not found.')

    def delete_find(self, identity):
        """Remove a saved find and cancel its pending version search. Downloads already queued keep going."""
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM finds WHERE identity=?', (identity,)).fetchone()
            if not row:
                raise ValueError('Saved find not found.')
            c.execute('DELETE FROM finds WHERE identity=?', (identity,))
            c.execute("UPDATE jobs SET status='cancelled', updated=? WHERE find_identity=? AND source='Search' AND status IN ('queued','needs_selection')",
                      (time.time(), identity))
            return dict(row)

    def restore_find(self, identity, name, found_at):
        """Undo for delete_find: put the find back with its original time."""
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 240 or any(ord(ch) < 32 for ch in name):
            raise ValueError('Enter a song name of up to 240 characters on one line.')
        if not isinstance(found_at, (int, float)) or not 0 < found_at <= time.time() + 60:
            raise ValueError('Invalid saved find time.')
        if not isinstance(identity, str) or not 1 <= len(identity) <= 1000:
            raise ValueError('Saved find not found.')
        name = unicodedata.normalize('NFC', name.strip())
        with self.connect() as c:
            c.execute('INSERT OR IGNORE INTO finds VALUES (?, ?, ?)', (identity, name, float(found_at)))
            return dict(c.execute('SELECT * FROM finds WHERE identity=?', (identity,)).fetchone())

    def request_find(self, identity, source_url=None):
        if source_url is not None:
            if not isinstance(source_url, str):
                raise ValueError('Paste a track link.')
            source, url = route(source_url)
            if source not in ('YouTube', 'SoundCloud', 'Bandcamp'):
                raise ValueError('Paste an individual YouTube, SoundCloud or Bandcamp track link.')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            found = c.execute('SELECT name FROM finds WHERE identity=?', (identity,)).fetchone()
            if not found:
                raise ValueError('Saved find not found.')
            if source_url is None:
                source, url = 'Search', found['name']
            old = c.execute("SELECT * FROM jobs WHERE find_identity=? AND status!='cancelled' ORDER BY created DESC LIMIT 1", (identity,)).fetchone()
            if old and old['status'] in ('queued', 'resolving', 'downloading', 'processing'):
                raise ValueError('This find already has a request in progress.')
            if old and old['source'] == 'Search':
                c.execute("UPDATE jobs SET status='cancelled', updated=? WHERE id=?", (time.time(), old['id']))
            ident = uuid.uuid4().hex
            now = time.time()
            profile = c.execute("SELECT value FROM settings WHERE key='profile'").fetchone()
            c.execute('INSERT INTO jobs (id,input,source,url,status,title,artist,error,candidates,profile,created,updated,find_identity) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (ident, found['name'], source, url, 'queued', '', '', '', '[]', profile[0] if profile else 'mp3', now, now, identity))
        self.wake.set()
        return self.get(ident)

    def setting(self, key, default):
        with self.connect() as c:
            row = c.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return row[0] if row else default

    def save_settings(self, values):
        if values.get('profile') not in ('mp3', 'aiff', 'original'):
            raise ValueError('Unknown audio profile.')
        folder = self.set_output_dir(values['output_dir'], profile=values['profile'])
        return folder

    def set_output_dir(self, value, *, profile=None):
        folder = Path(value).expanduser()
        if not folder.is_absolute():
            raise ValueError('Choose an absolute folder path.')
        folder = folder.resolve()
        folder.mkdir(parents=True, exist_ok=True)
        if not os.access(folder, os.W_OK | os.X_OK):
            raise ValueError('Choose a folder you can write to.')
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('output_dir', str(folder)))
            if profile is not None:
                c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('profile', profile))
        return str(folder)

    def add(self, value, start='', end=''):
        source, value_normal = route(value)
        clip_start, clip_end = clip_range(start, end)
        with self.connect() as c:
            existing = c.execute("SELECT * FROM jobs WHERE url=? AND clip_start IS ? AND clip_end IS ? AND profile=? AND status NOT IN ('failed','cancelled')", (value_normal, clip_start, clip_end, self.setting('profile','mp3'))).fetchone()
            if existing:
                return dict(existing)
            ident = uuid.uuid4().hex
            now = time.time()
            c.execute('INSERT INTO jobs (id,input,source,url,status,title,artist,error,candidates,profile,created,updated,clip_start,clip_end) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (ident, value.strip(), source, value_normal, 'queued', '', '', '', '[]', self.setting('profile','mp3'), now, now, clip_start, clip_end))
        self.wake.set()
        return self.get(ident)

    def get(self, ident):
        with self.connect() as c:
            row = c.execute('SELECT * FROM jobs WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('Request not found.')
        return dict(row)

    def update(self, ident, **values):
        allowed = {'status','title','artist','error','candidates','output','source_key','source_hash','output_hash','url','source'}
        if not values.keys() <= allowed:
            raise ValueError('Unknown job field')
        values['updated'] = time.time()
        with self.connect() as c:
            c.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?', (*values.values(), ident))

    def jobs(self):
        with self.connect() as c:
            return [dict(r) for r in c.execute('SELECT * FROM jobs ORDER BY created DESC')]

    def retry(self, ident):
        row = self.get(ident)
        if row['status'] != 'failed':
            raise ValueError('Only failed requests can be retried.')
        self.update(ident, status='queued', error='')
        self.wake.set()

    def choose(self, ident, url):
        row = self.get(ident)
        if row['status'] != 'needs_selection':
            raise ValueError('This request is not waiting for a selection.')
        candidates = json.loads(row['candidates'])
        chosen = next((x for x in candidates if x['url'] == url), None)
        if not chosen:
            raise ValueError('Choose a listed recording.')
        source, url = route(url)
        with self.connect() as c:
            if not c.execute("UPDATE jobs SET source=?,url=?,title=?,status='queued',error='',updated=? WHERE id=? AND status='needs_selection'",
                             (source, url, chosen['title'], time.time(), ident)).rowcount:
                raise ValueError('This request is no longer waiting for a selection.')
        self.wake.set()


def tool(name):
    if name == 'yt-dlp' and (ROOT / '.venv/bin/yt-dlp').exists():
        return str(ROOT / '.venv/bin/yt-dlp')
    for candidate in (shutil.which(name), '/opt/homebrew/bin/'+name, '/usr/local/bin/'+name, str(Path.home()/'.stacher'/name)):
        if candidate and Path(candidate).is_file() and os.access(candidate,os.X_OK):
            return candidate
    return None


def execute(args, log, timeout=1200):
    env = os.environ.copy()
    env['PATH'] = os.pathsep.join([str(ROOT/'.venv/bin'), str(Path.home()/'.stacher'), '/opt/homebrew/bin', env.get('PATH','')])
    with Path(log).open('a') as f:
        result = subprocess.run(args, stdout=f, stderr=f, timeout=timeout, env=env, stdin=subprocess.DEVNULL)
    if result.returncode:
        tail = Path(log).read_text(errors='replace')[-2500:]
        raise RuntimeError(tail.strip() or f'Command failed ({result.returncode}).')


class Worker:
    def __init__(self, store):
        self.store = store
        self.stop = threading.Event()

    def run(self):
        while not self.stop.is_set():
            jobs = [j for j in reversed(self.store.jobs()) if j['status'] == 'queued']
            if not jobs:
                self.store.wake.wait(2); self.store.wake.clear(); continue
            job = jobs[0]
            try:
                self.process(job)
            except Exception as exc:
                self.store.update(job['id'], status='failed', error=str(exc)[-3000:])

    def yt(self):
        binary = tool('yt-dlp')
        if not binary:
            raise RuntimeError('yt-dlp is missing. Run scripts/setup.command, then Retry.')
        args = [binary,'--ignore-config','--no-plugin-dirs','--use-extractors','^(youtube|youtube:search|soundcloud|Bandcamp)$','--no-playlist','--socket-timeout','25','--retries','2']
        deno = tool('deno')
        if deno:
            args += ['--js-runtimes', 'deno:'+deno]
        return args

    def metadata(self, value, jobdir, flat=False):
        target = jobdir / 'metadata.json'
        errors = jobdir / 'metadata.log'
        env = os.environ.copy()
        env['PATH'] = str(Path.home()/'.stacher') + os.pathsep + env.get('PATH','')
        args = self.yt()+['--dump-single-json','--skip-download']+(['--flat-playlist'] if flat else [])+['--',value]
        with target.open('w') as out, errors.open('w') as err:
            result = subprocess.run(args, stdout=out, stderr=err, timeout=180, stdin=subprocess.DEVNULL, env=env)
        if result.returncode:
            raise RuntimeError(errors.read_text(errors='replace')[-2500:])
        return json.loads(target.read_text())

    def process(self, job):
        s, ident = self.store, job['id']
        jobdir = s.home / 'jobs' / ident
        jobdir.mkdir(parents=True, exist_ok=True)
        s.update(ident, status='resolving', error='')
        if job['source'] in ('Search','Spotify lookup'):
            query = job['url']
            if job['source'] == 'Spotify lookup':
                from urllib.parse import urlencode
                endpoint = 'https://open.spotify.com/oembed?'+urlencode({'url':query})
                with urlopen(Request(endpoint, headers={'User-Agent':'DJ-Intake/0.1'}), timeout=25) as response:
                    data = json.loads(response.read(100000))
                query = data.get('title','')
                if not query:
                    raise RuntimeError('Spotify metadata is unavailable. Enter Artist - Title instead.')
                s.update(ident, title=query)
            data = self.metadata('ytsearch5:'+query, jobdir, flat=True)
            candidates = []
            for entry in data.get('entries', []):
                if not entry or not re.fullmatch(r'[A-Za-z0-9_-]{11}', str(entry.get('id', ''))):
                    continue
                candidates.append({'title':entry.get('title','Untitled'), 'artist':entry.get('channel') or entry.get('uploader') or '',
                                   'duration':entry.get('duration'), 'url':'https://www.youtube.com/watch?v='+entry['id']})
            if not candidates:
                raise RuntimeError('No recordings found. Try Artist - Title, including the remix name.')
            s.update(ident,status='needs_selection',candidates=json.dumps(candidates),error='Choose the recording and version to download.')
            return
        info = self.metadata(job['url'],jobdir)
        if info.get('is_live') or info.get('live_status') == 'is_live':
            raise RuntimeError('Live streams are not supported. Paste a finished track URL.')
        if float(info.get('duration') or 0) > 3600:
            raise RuntimeError('This item exceeds the one-hour track limit.')
        if job.get('clip_end') is not None and info.get('duration') is not None and job['clip_end'] > float(info['duration']) + .05:
            raise RuntimeError('The requested end time is past the end of this recording.')
        artist = info.get('artist') or info.get('creator') or ''
        title = info.get('track') or info.get('title') or job['title'] or 'Untitled'
        if not artist and ' - ' in title:
            artist,title = title.split(' - ',1)
        artist, title = tidy_track(artist, title)
        source_key = str(info.get('extractor_key') or info.get('extractor'))+':'+str(info.get('id'))
        s.update(ident,title=title,artist=artist,source_key=source_key)
        for other in s.jobs():
            if other['id'] != ident and other['source_key'] == source_key and (other.get('clip_start'),other.get('clip_end'),other['profile']) == (job.get('clip_start'),job.get('clip_end'),job['profile']) and other['status'] == 'successful' and other['output'] and Path(other['output']).exists():
                if digest(other['output']) == other['output_hash']:
                    s.update(ident,status='successful',output=other['output'],output_hash=other['output_hash'],source_hash=other['source_hash'],error='Already in your successful library; existing file reused.')
                    return
        for name in ('ffmpeg','ffprobe'):
            if not tool(name):
                raise RuntimeError(name+' is missing. Run scripts/setup.command, then Retry.')
        s.update(ident,status='downloading')
        paths = jobdir/'download-path.txt'
        paths.unlink(missing_ok=True)
        args = self.yt()+['-f','bestaudio/best','-x','--audio-format','best','--ffmpeg-location',str(Path(tool('ffmpeg')).parent),
                         '--max-filesize','500M','--no-overwrites','--write-info-json','--newline',
                         '--print-to-file','after_move:%(filepath)s',str(paths),'-o',str(jobdir/'source.%(ext)s'),'--',job['url']]
        execute(args,jobdir/'download.log')
        if not paths.exists():
            raise RuntimeError('The downloader did not produce an audio file.')
        source = Path(paths.read_text().strip().splitlines()[-1]).resolve()
        if source.parent != jobdir.resolve() or not source.is_file():
            raise RuntimeError('Invalid downloader output path.')
        s.update(ident,status='processing')
        self.finish(job,source,title,artist,jobdir)

    def finish(self,job,source,title,artist,jobdir):
        s,ident = self.store,job['id']
        artist, title = tidy_track(artist, title)
        log = jobdir/'process.log'
        probe = subprocess.run([tool('ffprobe'),'-v','error','-show_format','-show_streams','-of','json',str(source)],capture_output=True,text=True,check=True,timeout=30)
        data = json.loads(probe.stdout)
        if not any(stream.get('codec_type') == 'audio' for stream in data.get('streams',[])):
            raise RuntimeError('The file has no audio stream.')
        execute([tool('ffmpeg'),'-v','error','-xerror','-i',str(source),'-map','0:a:0','-f','null','-'],log)
        original_hash = digest(source)
        cutting = job.get('clip_end') is not None
        trim_args = []
        if cutting:
            duration = float(data.get('format',{}).get('duration') or 0)
            if job['clip_start'] < 0 or job['clip_end'] <= job['clip_start'] or not duration or job['clip_end'] > duration + .05:
                raise RuntimeError('The requested range is outside this recording. Check the start and end times.')
            trim_args = ['-ss',str(job['clip_start']),'-t',str(job['clip_end']-job['clip_start'])]
        folder = Path(s.setting('output_dir',str(Path.home()/'Music/DJ Intake Staging'))).expanduser()
        folder.mkdir(parents=True,exist_ok=True)
        profile = job['profile']
        ext = ('.wav' if cutting else source.suffix) if profile == 'original' else ('.mp3' if profile == 'mp3' else '.aiff')
        base = job_stem(artist, title, job)
        temp = jobdir/('finished'+ext)
        if profile == 'original' and not cutting:
            shutil.copyfile(source,temp)
        else:
            codec = ['-c:a','copy'] if profile == 'mp3' and source.suffix == '.mp3' and not cutting else (['-c:a','libmp3lame','-b:a','320k','-ar','44100'] if profile == 'mp3' else (['-c:a','pcm_s16be','-ar','44100'] if profile == 'aiff' else ['-c:a','pcm_s24le']))
            execute([tool('ffmpeg'),'-v','error','-y','-i',str(source),*trim_args,'-map','0:a:0','-vn',*codec,'-metadata','artist='+artist,'-metadata','title='+title,*(['-write_id3v2','1'] if profile == 'aiff' else []),str(temp)],log)
        output_hash = digest(temp)
        # Link a completed temporary file on the destination filesystem, never overwrite.
        staged = folder/('.'+ident+'.partial')
        shutil.copyfile(temp,staged)
        if digest(staged) != output_hash:
            raise RuntimeError('Output verification failed.')
        try:
            output = publish_file(staged,folder,base,ext)
        finally:
            staged.unlink(missing_ok=True)
        manifest = {'request_id':ident,'source_url':job['url'],'original':str(source),'source_sha256':original_hash,'output':str(output),'sha256':output_hash,'artist':artist,'title':title,'profile':profile,'clip_start':job.get('clip_start'),'clip_end':job.get('clip_end'),'probe':data,'quality_note':'Successful means downloaded and checked. Audition before a live set. Transcoding cannot restore stream quality.'}
        (jobdir/'result.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
        s.update(ident,status='successful',title=title,artist=artist,output=str(output),output_hash=output_hash,source_hash=original_hash,error='')
