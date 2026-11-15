"""Cover art and extra tags, so tracks don't show up blank in Serato or rekordbox.

Artist and title are written by FFmpeg during conversion; this adds album,
genre, year, a comment with the source link, and the cover picture.
"""
from __future__ import annotations
import re
from pathlib import Path

try:  # installed with yt-dlp
    from mutagen import File as AudioFile
    from mutagen.id3 import APIC, COMM, ID3, TALB, TCON, TDRC, ID3NoHeaderError
    from mutagen.mp4 import MP4, MP4Cover
except ImportError:  # pragma: no cover
    AudioFile = None


def details(info):
    """Album, genre, year and source link from yt-dlp's info JSON."""
    year = info.get('release_year') or str(info.get('release_date') or info.get('upload_date') or '')[:4]
    return {
        'album': str(info.get('album') or '').strip(),
        'genre': str(info.get('genre') or (info.get('genres') or [''])[0] or '').strip(),
        'year': str(year) if re.fullmatch(r'(19|20)\d\d', str(year)) else '',
        'comment': 'DJ Intake · ' + str(info.get('webpage_url') or info.get('original_url') or '').strip(),
    }


def write(path, meta, cover=None):
    """Add tags and cover art in place. Returns False when the format isn't supported."""
    if AudioFile is None:
        return False
    path = Path(path)
    picture = Path(cover).read_bytes() if cover and Path(cover).is_file() else None
    suffix = path.suffix.lower()
    if suffix == '.m4a':
        audio = MP4(path)
        for key, value in (('\xa9alb', meta['album']), ('\xa9gen', meta['genre']), ('\xa9day', meta['year']), ('\xa9cmt', meta['comment'])):
            if value:
                audio[key] = [value]
        if picture:
            audio['covr'] = [MP4Cover(picture, imageformat=MP4Cover.FORMAT_JPEG)]
        audio.save()
        return True
    if suffix == '.mp3':
        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            tags = ID3()
        save = lambda: tags.save(path, v2_version=3)
    elif suffix in ('.aiff', '.aif', '.wav'):
        audio = AudioFile(path)
        if audio is None:
            return False
        if audio.tags is None:
            audio.add_tags()
        tags = audio.tags
        save = lambda: audio.save(v2_version=3)
    else:
        return False
    for frame, value in ((TALB, meta['album']), (TCON, meta['genre']), (TDRC, meta['year'])):
        if value:
            tags.setall(frame.__name__, [frame(encoding=3, text=value)])
    if meta['comment']:
        tags.setall('COMM', [COMM(encoding=3, lang='eng', desc='', text=meta['comment'])])
    if picture:
        tags.setall('APIC', [APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=picture)])
    save()
    return True
