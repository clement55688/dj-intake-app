"""Read/write Serato DJ "DBv2" library files (database V2, .crate) -- stdlib only.

File format (verified on files written by Serato DJ Pro 4.0.7):
  * A file is a flat sequence of tags: 4-byte ASCII id, 4-byte big-endian
    payload length, payload.  Some tags (otrk, ovct, osrt, and the r* rule
    containers in .scrate files) hold a nested tag sequence.
  * Type is given by the first letter of the id:
      t*/p* = UTF-16BE text (no BOM, no NUL), b* = 1-byte bool,
      u* = uint32 BE, s* = uint16 BE, o*/r* = nested container.
  * vrsn is UTF-16BE text but is written raw (8-byte header + text).
  * Crate:  vrsn '1.0/Serato ScratchLive Crate', optional osrt (sort),
            ovct{tvcn name, tvcw width} column definitions, then one
            otrk{ptrk path} per track.
  * database V2: vrsn '2.0/Serato Scratch LIVE Database', then one
            otrk per track (ttyp, pfil, tsng, tart, talb, tlen, tbit, ...).
  * Paths are relative to the volume root, no leading slash, NFC-normalised.
"""
from __future__ import annotations

import os
import struct
import subprocess
import tempfile
import unicodedata
from typing import Iterable, Iterator, Union

CRATE_VERSION = "1.0/Serato ScratchLive Crate"
DATABASE_VERSION = "2.0/Serato Scratch LIVE Database"

# Column set Serato DJ Pro 4.0.7 writes for user-created crates (verified).
DEFAULT_COLUMNS = (
    ("song", "250"), ("artist", "250"), ("bpm", "30"), ("key", "30"),
    ("album", "250"), ("length", "250"), ("comment", "250"),
)

# Serato file-name encoding of crate names (verified on this Mac):
SUBCRATE_SEPARATOR = "%%"          # 'Parent%%Child.crate'
SMART_SUBCRATE_SEPARATOR = "≫≫"  # '≫≫' used in SmartCrates names
_ESCAPES = {"/": "␛␛2f"}  # a crate named '11/6' -> '11␛␛2f6.crate'

SERATO_PROCESS_NAMES = ("Serato DJ Pro", "Serato DJ Lite", "Serato DJ")

Tag = tuple  # (tag: str, value: bytes | list[Tag])
Value = Union[bytes, list]

_CONTAINERS = {"otrk", "ovct", "osrt", "rart", "rlut", "rurt"}


# --------------------------------------------------------------------- tags
def _is_container(tag: str) -> bool:
    return tag in _CONTAINERS or tag[0] in "or"


def parse_tags(data: bytes) -> list:
    """Parse bytes into a list of (tag, value). Containers -> nested lists,
    everything else -> raw payload bytes (lossless)."""
    out, off, n = [], 0, len(data)
    while off < n:
        if n - off < 8:
            raise ValueError(f"truncated tag header at offset {off}")
        tag = data[off:off + 4].decode("ascii")
        (length,) = struct.unpack(">I", data[off + 4:off + 8])
        end = off + 8 + length
        if end > n:
            raise ValueError(f"tag {tag!r} at {off} overruns file")
        payload = data[off + 8:end]
        out.append((tag, parse_tags(payload) if _is_container(tag) else payload))
        off = end
    return out


def serialize_tags(tags: Iterable) -> bytes:
    parts = []
    for tag, value in tags:
        body = serialize_tags(value) if isinstance(value, list) else bytes(value)
        raw = tag.encode("ascii")
        if len(raw) != 4:
            raise ValueError(f"bad tag id {tag!r}")
        parts.append(raw + struct.pack(">I", len(body)) + body)
    return b"".join(parts)


def text(s: str) -> bytes:
    return s.encode("utf-16-be")


def decode_text(b: bytes) -> str:
    return b.decode("utf-16-be")


def decode_value(tag: str, b: bytes):
    c = tag[0]
    if c in "tp" or tag == "vrsn":
        return decode_text(b)
    if c == "b":
        return b != b"\x00"
    if c == "u" and len(b) == 4:
        return struct.unpack(">I", b)[0]
    if c == "s" and len(b) == 2:
        return struct.unpack(">H", b)[0]
    return b


# ------------------------------------------------------------------- paths
def serato_location(abs_path: str) -> tuple[str, str]:
    """Return (serato_dir, stored_relative_path) for an absolute file path.

    Boot volume:  /Users/me/Music/x.mp3 -> (~/Music/_Serato_, 'Users/me/Music/x.mp3')
    External:     /Volumes/X/DJ/x.mp3   -> ('/Volumes/X/_Serato_', 'DJ/x.mp3')
    Serato keeps one _Serato_ folder per volume; a crate on the boot volume may
    only reference boot-volume files and vice versa.  (External drive handling
    follows the documented convention; not verified on this Mac.)
    """
    p = unicodedata.normalize("NFC", os.path.abspath(abs_path))
    parts = p.split("/")
    if len(parts) > 3 and parts[1] == "Volumes":
        root = "/".join(parts[:3])
        # /Volumes/Macintosh HD is a symlink to '/': treat as boot volume.
        is_boot = os.path.exists(root) and os.path.samefile(root, "/")
        if not is_boot:
            return os.path.join(root, "_Serato_"), "/".join(parts[3:])
        p = "/" + "/".join(parts[3:])
    return os.path.expanduser("~/Music/_Serato_"), p.lstrip("/")


def to_stored_path(abs_path: str, volume_root: str = "/") -> str:
    p = unicodedata.normalize("NFC", os.path.abspath(abs_path))
    root = volume_root.rstrip("/") + "/"
    if not p.startswith(root) and volume_root != "/":
        raise ValueError(f"{abs_path} is not on volume {volume_root}")
    return p[len(root):] if volume_root != "/" else p.lstrip("/")


def from_stored_path(rel: str, volume_root: str = "/") -> str:
    return os.path.join(volume_root, rel.lstrip("/"))


def crate_filename(*names: str) -> str:
    """crate_filename('Parent', 'Child') -> 'Parent%%Child.crate'."""
    def esc(n: str) -> str:
        for k, v in _ESCAPES.items():
            n = n.replace(k, v)
        return n
    return SUBCRATE_SEPARATOR.join(esc(n) for n in names) + ".crate"


# ------------------------------------------------------------------ crates
def read_crate(path: str, volume_root: str | None = None) -> list[str]:
    """Absolute paths listed in a .crate (or .scrate) file, in order."""
    if volume_root is None:
        volume_root = _volume_root_for_serato_file(path)
    with open(path, "rb") as f:
        tags = parse_tags(f.read())
    out = []
    for tag, value in tags:
        if tag == "otrk":
            for t, v in value:
                if t == "ptrk":
                    out.append(from_stored_path(decode_text(v), volume_root))
    return out


def build_crate(abs_paths: Iterable[str], volume_root: str = "/",
                columns=DEFAULT_COLUMNS) -> bytes:
    tags: list = [("vrsn", text(CRATE_VERSION))]
    for name, width in columns:
        tags.append(("ovct", [("tvcn", text(name)), ("tvcw", text(width))]))
    seen = set()
    for p in abs_paths:
        rel = to_stored_path(p, volume_root)
        key = rel.casefold()  # APFS/HFS+ default volumes are case-insensitive
        if key in seen:
            continue
        seen.add(key)
        tags.append(("otrk", [("ptrk", text(rel))]))
    return serialize_tags(tags)


def write_crate(path: str, abs_paths: Iterable[str],
                volume_root: str | None = None, columns=DEFAULT_COLUMNS) -> None:
    """Atomically write a crate: order preserved, duplicates dropped."""
    if volume_root is None:
        volume_root = _volume_root_for_serato_file(path)
    data = build_crate(abs_paths, volume_root, columns)
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".djintake-", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _volume_root_for_serato_file(path: str) -> str:
    """_Serato_ under /Volumes/X -> '/Volumes/X', otherwise '/'."""
    parts = os.path.abspath(path).split("/")
    if len(parts) > 3 and parts[1] == "Volumes" and "_Serato_" in parts[3:4]:
        return "/".join(parts[:3])
    return "/"


# ---------------------------------------------------------------- database
def _length_seconds(s: str | None) -> float | None:
    """tlen is 'mm:ss.cc' (also seen 'h:mm:ss.cc')."""
    if not s:
        return None
    try:
        secs = 0.0
        for part in s.split(":"):
            secs = secs * 60 + float(part)
        return secs
    except ValueError:
        return None


def iter_database(db_path: str) -> Iterator[dict]:
    """Yield one {tag: decoded value} dict per otrk in database V2."""
    with open(db_path, "rb") as f:
        tags = parse_tags(f.read())
    for tag, value in tags:
        if tag == "otrk":
            yield {t: decode_value(t, v) for t, v in value}


def library_tracks(db_path: str, volume_root: str | None = None) -> list[dict]:
    """[{path, title, artist, length, missing}] from database V2.

    length is seconds (float) or None; missing is the bmis flag (Serato only
    refreshes it when it touches the file -- check os.path.exists yourself).
    """
    if volume_root is None:
        volume_root = _volume_root_for_serato_file(db_path)
    out = []
    for t in iter_database(db_path):
        if "pfil" not in t:
            continue
        out.append({
            "path": from_stored_path(t["pfil"], volume_root),
            "title": t.get("tsng") or "",
            "artist": t.get("tart") or "",
            "length": _length_seconds(t.get("tlen")),
            "missing": bool(t.get("bmis", False)),
        })
    return out


# ------------------------------------------------------------------ process
def serato_running() -> bool:
    """True if Serato DJ Pro/Lite is running (exact process-name match)."""
    for name in SERATO_PROCESS_NAMES:
        r = subprocess.run(["/usr/bin/pgrep", "-x", name],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode == 0:
            return True
    return False


# ---------------------------------------------------------------- DJ Intake
CRATE_NAME = "DJ Intake.crate"
QUIET_SECONDS = 10  # Serato rewrites its crates when it quits; wait until it has finished


class CrateSync:
    """Keeps a 'DJ Intake' crate in Serato listing every finished download.

    Serato DJ Pro rewrites its crate files while it runs (and on quit), so the crate is
    only written while Serato is closed; Serato picks it up the next time it opens.
    Only this one crate file is ever written, and the previous copy is backed up first.
    """

    def __init__(self, store, folder=None, running=serato_running):
        self.store = store
        self.folder = os.path.expanduser(folder or "~/Music/_Serato_")
        self.running = running
        self.last_running = 0.0
        self.written = None
        self.state = {"status": "idle", "tracks": 0, "updated": None}

    def available(self):
        return os.path.isdir(os.path.join(self.folder, "Subcrates")) or os.path.isfile(os.path.join(self.folder, "database V2"))

    def enabled(self):
        return self.store.setting("serato_crate", "") == "on"

    def crate_path(self):
        return os.path.join(self.folder, "Subcrates", CRATE_NAME)

    def downloads(self):
        """Finished files on the startup disk, oldest first (an external drive has its own _Serato_ folder)."""
        jobs = [j for j in reversed(self.store.jobs()) if j["status"] == "successful" and j.get("output")]
        return [j["output"] for j in jobs if not j["output"].startswith("/Volumes/") and os.path.isfile(j["output"])]

    def summary(self):
        return {"available": self.available(), "enabled": self.enabled(),
                "decided": self.store.setting("serato_crate", "") != "", **self.state}

    def tick(self, now=None):
        import time
        now = time.time() if now is None else now
        if not (self.enabled() and self.available()):
            return
        wanted = self.downloads()
        if self.written is not None and set(wanted) <= self.written:
            return
        if self.running():
            self.last_running = now
            self.state["status"] = "waiting"
            return
        if now - self.last_running < QUIET_SECONDS:
            return
        self.write(wanted, now)

    def write(self, wanted, now):
        import shutil
        crate = self.crate_path()
        existing = read_crate(crate) if os.path.isfile(crate) else []
        merged = existing + [p for p in wanted if p not in set(existing)]
        if merged != existing or not os.path.isfile(crate):
            if os.path.isfile(crate):
                backups = os.path.join(self.store.home, "serato-backups")
                os.makedirs(backups, exist_ok=True)
                shutil.copy2(crate, os.path.join(backups, f"DJ Intake {int(now)}.crate"))
                for old in sorted(os.listdir(backups))[:-10]:
                    os.unlink(os.path.join(backups, old))
            write_crate(crate, merged, volume_root="/")
            self.state.update(status="updated", updated=now)
        self.state["tracks"] = len(merged)
        self.written = set(merged)

    def loop(self, stop):
        while not stop.wait(5):
            try:
                self.tick()
            except Exception as error:  # never take the app down over Serato
                self.state.update(status="error", error=str(error)[:200])
