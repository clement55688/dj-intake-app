"""What's already in your music folders.

Used to say "you already have this" before downloading, and to flag 30-second
previews that slipped into a library. Only file names are read for matching;
durations come from audio headers. Nothing here changes or moves files.
"""
from __future__ import annotations
import os
import re
import threading
import time
import unicodedata
from pathlib import Path

try:  # installed with yt-dlp; the preview check is skipped without it
    import mutagen
except ImportError:  # pragma: no cover
    mutagen = None

AUDIO = {'.mp3', '.m4a', '.aac', '.aif', '.aiff', '.wav', '.flac', '.alac', '.ogg', '.opus'}
MAX_FILES = 50000
REFRESH_EVERY = 600
PREVIEW_SECONDS = (27.0, 31.5)  # store previews are 30 seconds long

FEAT = re.compile(r'\s*[(\[]\s*(?:feat\.?|ft\.?|featuring|with)\s[^)\]]*[)\]]'
                  r'|\s+(?:feat\.?|ft\.?|featuring)\s.*$', re.I)
PROMO = re.compile(r'\s*[(\[][^)\]]*\b(?:official|lyrics?|visuali[sz]er|audio|video|hq|hd)\b[^)\]]*[)\]]', re.I)
ARTIST_SPLIT = re.compile(r'\s*(?:,|&|\+|;|/|\bx\b|\band\b|\bvs\.?\b|\bfeat\.?\b|\bft\.?\b|\bfeaturing\b)\s*', re.I)
TRACK_NUMBER = re.compile(r'^\d{1,3}(?:\s*[-.]\s*|\s+)')
COPY_SUFFIX = re.compile(r'\s\(\d+\)$')


def _plain(text):
    text = unicodedata.normalize('NFKC', str(text or '')).casefold()
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', text)).strip()


def title_key(title):
    """'Let Me Love You (feat. Justin Bieber) [Official Video]' -> 'let me love you'. Remix names stay."""
    title = unicodedata.normalize('NFKC', str(title or ''))
    title = PROMO.sub('', FEAT.sub('', title))
    return _plain(title)


def artist_names(artist):
    names = {_plain(name) for name in ARTIST_SPLIT.split(unicodedata.normalize('NFKC', str(artist or '')))}
    return {name for name in names if name and name not in ('unknown artist', 'various artists')}


def name_guesses(path):
    """Possible (artist, title) pairs for a file name such as 'Artist_Title', 'Artist - Title' or 'Artist-Title'."""
    path = Path(path)
    stem = COPY_SUFFIX.sub('', unicodedata.normalize('NFC', path.stem)).strip()

    def splits(separator):
        # Every split point, so 'Jay-Z-Empire State Of Mind' and "LET_S GO" still find the right pair.
        return [(stem[:i], stem[i + len(separator):]) for i in range(1, len(stem) - len(separator))
                if stem.startswith(separator, i)]

    if ' - ' in stem:
        artist, title = stem.split(' - ', 1)
        if TRACK_NUMBER.match(artist + ' ') and ' - ' in title:  # '01 - Artist - Title'
            artist, title = title.split(' - ', 1)
        return [(artist, title)] + splits('_')
    if '_' in stem:  # DJ Intake's own naming: Artist_Title
        return splits('_')
    if '-' in stem:
        return splits('-')
    if TRACK_NUMBER.match(stem):  # Apple Music style: Artist/Album/03 Title.m4a
        return [(path.parent.parent.name, TRACK_NUMBER.sub('', stem))]
    return []


def audio_seconds(path):
    if mutagen is None:
        return None
    try:
        audio = mutagen.File(path)
        return float(audio.info.length) if audio is not None and audio.info else None
    except Exception:
        return None


class LibraryIndex:
    """A cached map of the music you already have, rebuilt in the background."""

    def __init__(self, folders):
        self.folders = folders  # callable returning a list of folders to look in
        self.lock = threading.Lock()
        self.titles = {}
        self.files = []
        self.short = []
        self.built_at = 0.0
        self.building = False
        self.durations = {}

    def refresh(self, wait=False):
        with self.lock:
            if self.building:
                return
            self.building = True
        thread = threading.Thread(target=self._build, daemon=True)
        thread.start()
        if wait:
            thread.join()

    def ensure_fresh(self):
        if time.time() - self.built_at > REFRESH_EVERY:
            self.refresh()

    def _walk(self):
        seen, found = set(), []
        for folder in self.folders():
            folder = Path(folder).expanduser()
            if not folder.is_dir():
                continue
            for root, dirs, names in os.walk(folder):
                # Skip hidden folders and app data such as _Serato_.
                dirs[:] = [d for d in dirs if not d.startswith(('.', '_'))]
                for name in names:
                    path = os.path.join(root, name)
                    if name.startswith('.') or os.path.splitext(name)[1].lower() not in AUDIO or path in seen:
                        continue
                    seen.add(path)
                    found.append(path)
                    if len(found) >= MAX_FILES:
                        return found
        return found

    def _build(self):
        try:
            files = self._walk()
            titles, short, durations = {}, [], {}
            for path in files:
                for artist, title in name_guesses(path):
                    key = title_key(title)
                    if key:
                        titles.setdefault(key, []).append((artist_names(artist), path))
                try:
                    info = os.stat(path)
                except OSError:
                    continue
                stamp = (info.st_size, info.st_mtime)
                cached = self.durations.get(path)
                seconds = cached[1] if cached and cached[0] == stamp else audio_seconds(path)
                durations[path] = (stamp, seconds)
                if seconds is not None and PREVIEW_SECONDS[0] <= seconds <= PREVIEW_SECONDS[1]:
                    short.append({'path': path, 'name': os.path.basename(path), 'seconds': round(seconds, 1)})
            with self.lock:
                self.titles, self.files, self.short, self.durations = titles, files, short, durations
                self.built_at = time.time()
        finally:
            with self.lock:
                self.building = False

    def add(self, path):
        """Count a file we just saved without waiting for the next scan."""
        with self.lock:
            for artist, title in name_guesses(path):
                key = title_key(title)
                if key:
                    self.titles.setdefault(key, []).append((artist_names(artist), str(path)))

    def find(self, artist, title, ignore=()):
        """Path of a file that looks like the same recording, or None.

        Needs the same title (ignoring featured artists and promo labels, but not
        remix names) and at least one artist in common, so 'Intro' by two different
        artists never matches.
        """
        key, names = title_key(title), artist_names(artist)
        if not key or not names:
            return None
        with self.lock:
            entries = list(self.titles.get(key, ()))
            previews = {item['path'] for item in self.short}  # a 30-second preview doesn't count as having it
        for others, path in entries:
            if names & others and path not in ignore and path not in previews and os.path.exists(path):
                return path
        return None

    def previews(self, dismissed=()):
        with self.lock:
            return [item for item in self.short if item['path'] not in dismissed and os.path.exists(item['path'])]

    def summary(self, dismissed=()):
        with self.lock:
            ready, count = self.built_at > 0, len(self.files)
        return {'ready': ready, 'files': count, 'previews': self.previews(dismissed)}
