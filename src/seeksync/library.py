"""The DJ's own music folders (roadmap step 11): an index of what is already there, recognising a wanted
track in it, and a list of duplicate files in the download folder.

The index lives in the table `library`. A scan reads tags only for new or changed files (size and
modification time decide), so a second scan of thousands of unchanged files is a quick walk."""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from .matching import aliases_of, version_conflict, version_of
from .quality import position, profile, tier_of
from .titles import ParsedTitle, parse_title, tokens

log = logging.getLogger(__name__)

AUDIO_EXTS = {"mp3", "flac", "wav", "aiff", "aif", "m4a", "ogg", "opus"}
LENGTH_SLACK = 20            # seconds that never count as a different length
LENGTH_FRACTION = 0.25       # and this share of the wanted length
_TRACK_NO = re.compile(r"^\s*\d{1,3}\s*[-._)]+\s*(?=\S)|^\s*\d{1,3}\s+(?=\D)")
_BATCH = 300


# --- one file ----------------------------------------------------------------------------------

def _first(value) -> str:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "").strip()


def _tag_text(tags, easy_key: str, id3_key: str) -> str:
    if tags is None:
        return ""
    try:
        if easy_key in tags:
            return _first(tags[easy_key])
    except Exception:
        pass
    try:
        frame = tags.get(id3_key)            # WAV keeps real ID3 frames
        return _first(getattr(frame, "text", frame)) if frame is not None else ""
    except Exception:
        return ""


def read_file(path: str, root: str = "") -> Optional[dict]:
    """Index row for one audio file (tags when there are some, else the file name), or None when
    the file can't be looked at."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    stem = _TRACK_NO.sub("", os.path.splitext(os.path.basename(path))[0])
    artist = title = ""
    duration = bitrate = bit_depth = None
    try:
        import mutagen
        f = mutagen.File(path, easy=True)
        if f is not None:
            artist, title = _tag_text(f.tags, "artist", "TPE1"), _tag_text(f.tags, "title", "TIT2")
            info = f.info
            duration = float(getattr(info, "length", 0) or 0) or None
            br = getattr(info, "bitrate", 0) or 0
            bitrate = int(br / 1000) if br > 2000 else int(br) or None      # mutagen: bits per second
            bit_depth = getattr(info, "bits_per_sample", None) or None
    except Exception:
        log.debug("couldn't read tags of %s", path, exc_info=True)
    p = parse_title(f"{artist} - {title}") if artist and title else parse_title(stem)
    if not p.title:
        p = parse_title(stem)
    return {
        "path": path, "root": root, "size": st.st_size, "mtime_ns": st.st_mtime_ns,
        "artist": p.artist, "title": p.title, "version": p.version, "stem": stem,
        "duration": duration, "ext": ext, "bitrate": bitrate, "bit_depth": bit_depth,
        "tier": tier_of(ext, bitrate, bit_depth) or "other",
        "title_key": title_key(p.title), "stem_key": " ".join(tokens(stem)),
    }


def title_key(title: str) -> str:
    return " ".join(tokens(title, drop_stop=True) or tokens(title))


# --- scanning ----------------------------------------------------------------------------------

@dataclass
class ScanResult:
    files: int = 0
    added: int = 0
    changed: int = 0
    removed: int = 0
    missing: Optional[list] = None       # configured folders that weren't there (drive unplugged?)
    seconds: float = 0.0


def clean_roots(dirs: Iterable[str]) -> list[str]:
    """Absolute, existing-or-not paths without duplicates; a folder inside another listed one is dropped."""
    out: list[str] = []
    for d in dirs:
        d = os.path.abspath(os.path.expanduser(str(d).strip())) if str(d).strip() else ""
        if d and d not in out:
            out.append(d)
    return [d for d in out if not any(o != d and (d + os.sep).startswith(o + os.sep) for o in out)]


def _walk(root: str, unreadable: Optional[list] = None):
    """(path, entry) of every audio file below root; hidden files and folders are skipped.
    Folders that couldn't be listed (no permission, a network share that dropped) are added to `unreadable`."""
    stack = [root]
    while stack:
        folder = stack.pop()
        try:
            it = os.scandir(folder)
        except OSError:
            if unreadable is not None:
                unreadable.append(folder)
            continue
        with it:
            for e in it:
                if e.name.startswith("."):
                    continue
                try:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                    elif e.is_file() and e.name.rsplit(".", 1)[-1].lower() in AUDIO_EXTS and "." in e.name:
                        yield e.path, e
                except OSError:
                    continue


def scan(db, dirs: Iterable[str], progress: Optional[Callable[[int, int], None]] = None,
         should_stop: Optional[Callable[[], bool]] = None) -> ScanResult:
    """Bring the index in line with the folders. Only new and changed files are read.
    A folder that isn't there (an unplugged drive) keeps its rows; folders no longer listed lose them."""
    t0 = time.time()
    roots = clean_roots(dirs)
    res = ScanResult(missing=[])
    known = db.library_stats()                      # path -> (size, mtime_ns, root)
    seen: set[str] = set()
    todo: list[tuple[str, str, os.DirEntry]] = []
    for root in roots:
        if not os.path.isdir(root):
            res.missing.append(root)
            seen.update(p for p, r in db.library_paths_of(root))      # keep what we knew about it
            continue
        unreadable: list[str] = []
        for path, e in _walk(root, unreadable):
            seen.add(path)
            try:
                st = e.stat()
            except OSError:
                continue
            if known.get(path) != (st.st_size, st.st_mtime_ns, root):
                todo.append((path, root, e))
        for folder in unreadable:
            # Not the same as "the files are gone": keep what we knew, or tracks would be fetched again.
            prefix = folder.rstrip("/\\") + os.sep
            seen.update(p for p in known if p.startswith(prefix))
            log.warning("couldn't read the folder %s; what was known about it is kept", folder)
        if should_stop and should_stop():
            return res
    batch: list[dict] = []
    for n, (path, root, _e) in enumerate(todo, 1):
        if should_stop and should_stop():
            break
        row = read_file(path, root)
        if row:
            batch.append(row)
            res.added += path not in known
            res.changed += path in known
        if len(batch) >= _BATCH:
            db.library_upsert(batch)
            batch = []
        if progress:
            progress(n, len(todo))
    if batch:
        db.library_upsert(batch)
    res.removed = db.library_delete([p for p in known if p not in seen])     # deleted, or its folder isn't listed any more
    res.files = db.library_count()
    res.seconds = round(time.time() - t0, 2)
    return res


def index_file(db, path: str, root: str = "") -> None:
    """Put one freshly published file in the index right away (so a second upload of the same track
    in another channel is recognised before the next scan)."""
    row = read_file(path, root)
    if row:
        db.library_upsert([row])


# --- recognising a track -----------------------------------------------------------------------

def _main_artist_tokens(artist: str) -> list[str]:
    first = (artist or "").split(",")[0]
    first = re.split(r"\s+(?:x|&|and|vs\.?|with)\s+", first, flags=re.I)[0]
    return tokens(first, drop_stop=True)


def _same_artist(want: ParsedTitle, entry: dict, aliases: dict) -> bool:
    entry_artist = set(tokens(entry["artist"], drop_stop=True))
    everything = entry_artist | set(tokens(entry["stem"], drop_stop=True))
    names = [want.artist, *aliases_of(want.artist.split(",")[0], aliases)]
    for name in names:
        main = _main_artist_tokens(name)
        if main and set(main) <= everything:
            return True
        all_names = set(tokens(name, drop_stop=True))
        if entry_artist and entry_artist <= all_names:      # the file lists fewer artists than SoundCloud
            return True
    return False


_NOISE = {"original", "mix", "extended", "version", "edit", "club", "radio", "remix", "feat", "ft", "featuring"}


def _same_title(want_title_tokens: list[str], want: ParsedTitle, entry: dict) -> bool:
    key = " ".join(want_title_tokens)
    if entry["title_key"] == key:
        return True
    # The tags are missing or odd: the title may still be all that's left of the file name.
    stem = set(tokens(entry["stem"], drop_stop=True))
    if not set(want_title_tokens) <= stem:
        return False
    rest = stem - set(want_title_tokens) - set(tokens(want.artist, drop_stop=True)) \
        - set(tokens(entry["artist"], drop_stop=True)) - set(tokens(entry["version"] or want.version)) - _NOISE
    return not [t for t in rest if not t.isdigit()]


def _same_length(want: ParsedTitle, entry: dict, duration: Optional[float]) -> bool:
    have = entry.get("duration")
    if not duration or not have:
        return True
    allowed = max(LENGTH_SLACK, LENGTH_FRACTION * duration)
    if abs(have - duration) <= allowed:
        return True
    # An extended mix is legitimately longer than the original upload (and the other way round).
    stem = set(tokens(entry["stem"] + " " + (entry["version"] or "")))
    return version_of(want.version).kind in ("original", "extended") and "extended" in (stem | set(tokens(want.version)))


def matches(want: ParsedTitle, duration: Optional[float], entry: dict, aliases: Optional[dict] = None) -> bool:
    """True when this file is the wanted track: same title, artist and version, and not a very different length."""
    title_t = tokens(want.title, drop_stop=True) or tokens(want.title)
    if not title_t or not tokens(want.artist, drop_stop=True):
        return False
    if not _same_title(title_t, want, entry) or not _same_artist(want, entry, aliases or {}):
        return False
    name_tokens = set(tokens(entry["stem"] + " " + (entry["version"] or "")))
    if version_conflict(want, name_tokens, set(title_t)):
        return False
    return _same_length(want, entry, duration)


def find(db, want: ParsedTitle, duration: Optional[float] = None, aliases: Optional[dict] = None,
         exclude: Optional[str] = None) -> Optional[dict]:
    """The best file in the index that is the wanted track, or None."""
    title_t = tokens(want.title, drop_stop=True) or tokens(want.title)
    if not title_t:
        return None
    best = None
    for entry in db.library_candidates(" ".join(title_t)):
        if exclude and entry["path"] == exclude:
            continue
        if matches(want, duration, entry, aliases):
            rank = _quality_rank(entry)
            if best is None or rank < best[0]:
                best = (rank, entry)
    return best[1] if best else None


# --- duplicates --------------------------------------------------------------------------------

_TIER_RANK = {"flac24": 0, "flac16": 1, "wav": 2, "mp3_320": 3, "mp3_256": 4, "mp3_192": 5, "mp3_low": 6, "other": 7}


def _quality_rank(entry: dict, prof: Optional[dict] = None) -> tuple:
    """Lower is better: the position in the user's profile, then the general ladder, bitrate, size."""
    pos = position(prof, entry["tier"]) if prof else None
    return (pos if pos is not None else 99, _TIER_RANK.get(entry["tier"], 7), -(entry["bitrate"] or 0), -entry["size"])


def duplicates(entries: list[dict], quality_profile: str = "club") -> list[dict]:
    """Groups of files that are the same track (same artist, title and version), best copy first.
    Nothing is judged beyond that: the app never deletes or moves a file."""
    prof = profile(quality_profile)
    groups: dict[tuple, list[dict]] = {}
    for e in entries:
        v = version_of(e["version"])
        main = " ".join(_main_artist_tokens(e["artist"])) or e["stem_key"]
        groups.setdefault((main, e["title_key"], v.kind, tuple(sorted(v.names))), []).append(e)
    out = []
    for (_artist, _title, _kind, _names), files in groups.items():
        if len(files) < 2:
            continue
        files.sort(key=lambda e: _quality_rank(e, prof))
        first = files[0]
        out.append({
            "artist": first["artist"], "title": first["title"], "version": first["version"],
            "files": [{"path": f["path"], "tier": f["tier"], "bitrate": f["bitrate"], "size": f["size"],
                       "duration": f["duration"], "ext": f["ext"], "best": i == 0} for i, f in enumerate(files)],
        })
    out.sort(key=lambda g: ((g["artist"] or "").lower(), (g["title"] or "").lower()))
    return out
