"""Settings and file locations."""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from typing import Optional

from platformdirs import user_data_dir, user_log_dir, user_music_dir
from . import fsutil

from .naming import DEFAULT_TEMPLATE, FLAT_TEMPLATE, template_error
from .politeness import MAX_MAX_SEARCHES, MIN_MAX_SEARCHES, MIN_SEARCH_SPACING

APP_NAME = "SeekSync"
GITHUB_REPO = "Stormhoogervorst/seeksync"


log = logging.getLogger(__name__)

# Earlier names of this app. Their data folder is taken over once, on the first start as SeekSync.
LEGACY_APP_NAMES = ("Nicotine+ Sync", "Cratewatch", "SeekDrop")
LEGACY_DB_NAMES = ("nicotine-sync.db", "cratewatch.db", "seekdrop.db")
DB_NAME = "seeksync.db"


def migrate_legacy_data(new: Optional[Path] = None, legacy: Optional[list[Path]] = None) -> Optional[Path]:
    """Move the data folder of an older app name (settings, database, channels) to SeekSync's.
    Only when SeekSync has no data yet; never merges or overwrites. Returns the folder it took over."""
    if new is None:
        if os.environ.get("SEEKSYNC_HOME"):
            return None
        new = Path(user_data_dir(APP_NAME, appauthor=False))
    if legacy is None:
        legacy = [Path(user_data_dir(n, appauthor=False)) for n in LEGACY_APP_NAMES]
    moved = None
    if not _has_data(new):
        for old in legacy:
            if _has_data(old):
                if new.exists() and any(new.iterdir()):
                    # Only the log folder is there (on Windows it lives inside the data folder and exists
                    # before this runs): take over what the old folder holds, item by item.
                    for entry in list(old.iterdir()):
                        if not (new / entry.name).exists():
                            shutil.move(str(entry), str(new / entry.name))
                    shutil.rmtree(old, ignore_errors=True)      # what is left is the old log folder
                else:
                    if new.exists():
                        new.rmdir()   # empty
                    new.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(old), str(new))
                moved = old
                log.info("Moved data from %s to %s", old, new)
                break
    if moved is not None:
        _retarget_default_download_dir(new / "settings.json")
    if new.is_dir() and not (new / DB_NAME).exists():
        for name in LEGACY_DB_NAMES:
            if (new / name).exists():
                for suffix in ("", "-wal", "-shm"):
                    src = new / (name + suffix)
                    if src.exists():
                        src.rename(new / (DB_NAME + suffix))
                break
    return moved


_NOT_DATA = {"logs", "crash.log"}      # what logging puts in the data folder on Windows before anything else


def _has_data(folder: Path) -> bool:
    """Does this app data folder hold anything besides logs?"""
    try:
        return folder.is_dir() and any(e.name.lower() not in _NOT_DATA for e in folder.iterdir())
    except OSError:
        return False


def _retarget_default_download_dir(settings_file: Path, music: Optional[Path] = None) -> None:
    """The old default download folder (Music/<old name>) becomes Music/SeekSync, but only when it
    is missing or empty. A folder that already holds music is left alone."""
    try:
        data = json.loads(settings_file.read_text("utf-8"))
    except (OSError, ValueError):
        return
    music = music or Path(default_download_dir()).parent
    current = Path(data.get("download_dir") or "")
    if current not in [music / n for n in LEGACY_APP_NAMES]:
        return
    if current.is_dir() and any(f.name != ".DS_Store" for f in current.iterdir()):
        return
    data["download_dir"] = str(music / APP_NAME)
    settings_file.write_text(json.dumps(data, indent=2), "utf-8")


def data_dir() -> Path:
    p = Path(os.environ.get("SEEKSYNC_HOME") or user_data_dir(APP_NAME, appauthor=False))
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_dir() -> Path:
    p = Path(os.environ.get("SEEKSYNC_HOME") or user_log_dir(APP_NAME, appauthor=False))
    if os.environ.get("SEEKSYNC_HOME"):
        p = p / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_download_dir() -> str:
    try:
        base = user_music_dir()
    except Exception:
        base = str(Path.home() / "Music")
    return str(Path(base) / APP_NAME)


@dataclass
class Settings:
    accepted_terms: bool = False
    soulseek_mode: str = "builtin"          # "builtin" | "nicotine"
    nicotine_port: int = 47820
    nicotine_token: str = ""
    soulseek_username: str = ""
    soulseek_password: str = ""
    download_dir: str = field(default_factory=default_download_dir)
    share_dirs: list[str] = field(default_factory=list)
    share_downloads: bool = True
    filename_template: str = DEFAULT_TEMPLATE   # folders and file name of a finished track (naming.py, step 10)
    tag_files: bool = True                  # write artist, title, genre, year, cover ... into the file
    wav_to_aiff: bool = False               # convert WAV to AIFF (same audio, better tags in DJ software)
    label_from_channel: bool = False        # use the channel name of a profile as the label tag
    quality_profile: str = "club"           # club | balanced | space (quality.PROFILES)
    upgrade_mode: str = "ask"               # better copy found later: "ask" | "auto" | "auto_unless_dj" | "off"
    rekordbox_library_xml: str = ""         # step 12: a collection export made in Rekordbox (read only); tracks in it count as "in Rekordbox"
    artist_aliases: str = ""                # one line per artist: "Name = Alias 1, Alias 2" (step 6)
    check_interval_minutes: int = 60
    max_parallel_downloads: int = 3
    give_up_days: int = 30
    listen_port: int = 60000
    check_updates: bool = True              # look for a newer release on GitHub twice a day
    check_length_margin: int = 10           # file may differ this many seconds from SoundCloud
    check_silence_seconds: int = 10         # longer silence at the start or end rejects the file
    suspect_quality: str = "label"          # suspect lossless / 320: "label" (let through) or "reject"
    search_spacing: int = 8                 # seconds between Soulseek searches (step 8; at least 4)
    search_max_per_5min: int = 20           # most searches in any 5 minutes (5 to 60)
    rekordbox_export: bool = False          # step 12: keep a Rekordbox XML of the downloads up to date
    rekordbox_xml_path: str = ""            # '' = "SeekSync for Rekordbox.xml" in the download folder
    library_dirs: list[str] = field(default_factory=list)     # step 11: music folders you already have (the download folder is always included)
    block_keywords: list[str] = field(default_factory=list)   # step 9: words that skip an upload, every channel
    block_artists: list[str] = field(default_factory=list)    # step 9: artists that are never fetched
    min_free_gb: int = 5                    # below this much free disk space no new downloads start (0 = off)

    @property
    def configured(self) -> bool:
        if not (self.accepted_terms and self.download_dir):
            return False
        if self.soulseek_mode == "nicotine":
            return bool(self.nicotine_token)
        return bool(self.soulseek_username and self.soulseek_password)

    def public(self) -> dict:
        d = asdict(self)
        d["soulseek_password"] = ""
        d["nicotine_token"] = ""
        d["has_password"] = bool(self.soulseek_password)
        d["configured"] = self.configured
        return d


_INT_FIELDS = ("check_interval_minutes", "max_parallel_downloads", "give_up_days", "listen_port", "nicotine_port",
               "check_length_margin", "check_silence_seconds", "search_spacing", "search_max_per_5min", "min_free_gb")


def _clamp(s: Settings) -> Settings:
    """Keep the numbers inside what the app can work with."""
    s.check_interval_minutes = max(15, s.check_interval_minutes)
    s.max_parallel_downloads = min(max(1, s.max_parallel_downloads), 10)
    s.give_up_days = min(max(1, s.give_up_days), 365)
    s.search_spacing = min(max(int(MIN_SEARCH_SPACING), s.search_spacing), 120)
    s.search_max_per_5min = min(max(MIN_MAX_SEARCHES, s.search_max_per_5min), MAX_MAX_SEARCHES)
    s.min_free_gb = min(max(0, s.min_free_gb), 1000)
    s.listen_port = min(max(1024, s.listen_port), 65534)        # the port after it is used too
    s.nicotine_port = min(max(1024, s.nicotine_port), 65535)
    s.check_length_margin = min(max(0, s.check_length_margin), 3600)
    s.check_silence_seconds = min(max(0, s.check_silence_seconds), 3600)
    return s


def _coerce(s: Settings) -> Settings:
    """A settings file that was edited by hand or written by an older version can hold the wrong kind of
    value (a text where a number belongs, null for a list). Such a field falls back to its default."""
    default = Settings()
    for f in fields(Settings):
        want, v = getattr(default, f.name), getattr(s, f.name)
        if isinstance(want, bool):
            ok = isinstance(v, bool) or v in (0, 1)
            v = bool(v) if ok else want
        elif isinstance(want, int):
            try:
                v = int(float(v)) if not isinstance(v, bool) else want
            except (TypeError, ValueError, OverflowError):
                v = want
        elif isinstance(want, str):
            v = v if isinstance(v, str) else want
        elif isinstance(want, list):
            v = [str(x) for x in v if isinstance(x, (str, int, float))] if isinstance(v, list) else want
        setattr(s, f.name, v)
    if s.quality_profile not in ("club", "balanced", "space"):
        s.quality_profile = default.quality_profile
    if s.upgrade_mode not in ("ask", "auto", "auto_unless_dj", "off"):
        s.upgrade_mode = default.upgrade_mode
    if s.soulseek_mode not in ("builtin", "nicotine"):
        s.soulseek_mode = default.soulseek_mode
    if s.suspect_quality not in ("label", "reject"):
        s.suspect_quality = default.suspect_quality
    if template_error(s.filename_template):
        s.filename_template = default.filename_template
    return s


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "settings.json"
        self._lock = threading.Lock()
        self.settings = self._load()

    def _load(self) -> Settings:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text("utf-8"))
                if "quality_profile" not in raw and "preferred_format" in raw:   # from before profiles
                    from .quality import profile_from_old_settings
                    raw["quality_profile"] = profile_from_old_settings(raw.get("preferred_format", "lossless"),
                                                                       int(raw.get("min_bitrate") or 320))
                if "filename_template" not in raw and raw.get("organize_by_channel") is False:
                    raw["filename_template"] = FLAT_TEMPLATE      # the old "no folder per channel" checkbox
                for key in ("share_dirs", "library_dirs"):
                    v = raw.get(key)
                    if isinstance(v, str):
                        raw[key] = [x.strip() for x in v.splitlines() if x.strip()]
                    elif isinstance(v, list) and len(v) > 1 and all(isinstance(x, str) and len(x) == 1 for x in v):
                        raw[key] = []                # one letter per entry: an earlier version split a path into characters
                known = {f.name for f in fields(Settings)}
                return _clamp(_coerce(Settings(**{k: v for k, v in raw.items() if k in known})))
            except Exception:
                # Starting with the defaults would overwrite this file at the first change: keep a copy.
                log.exception("couldn't read %s, starting with the default settings", self.path)
                try:
                    shutil.copyfile(self.path, self.path.with_name(self.path.name + ".unreadable"))
                except OSError:
                    pass
        return Settings()

    def save(self) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(self.settings), indent=2), "utf-8")
            fsutil.replace(tmp, self.path)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass

    def update(self, changes: dict) -> tuple[Settings, set[str]]:
        """Apply validated changes; returns settings and the names that changed."""
        s = self.settings
        changed: set[str] = set()
        types = {f.name: f.type for f in fields(Settings)}
        for key, value in changes.items():
            if key not in types:
                continue
            if key == "soulseek_password" and not value:
                continue  # empty means "keep current"
            if key in _INT_FIELDS:
                try:
                    value = int(float(value))
                except (TypeError, ValueError, OverflowError):
                    continue                       # an emptied number box: keep what it was
            if key in ("accepted_terms", "share_downloads", "tag_files", "wav_to_aiff", "label_from_channel", "rekordbox_export",
                       "check_updates"):
                value = bool(value)
            if key in ("share_dirs", "library_dirs"):
                if isinstance(value, str):
                    value = value.splitlines()       # a text box that was sent as one string
                value = [str(v).strip() for v in (value or []) if str(v).strip()]
            if key in ("block_keywords", "block_artists"):
                from .rules import clean_words
                value = clean_words(value)
            if key == "artist_aliases":
                value = "\n".join(line.strip() for line in str(value or "").splitlines() if line.strip())[:5000]
            if key in ("soulseek_username", "download_dir", "rekordbox_xml_path", "rekordbox_library_xml"):
                value = str(value).strip()
            if key == "filename_template":
                value = str(value or "").strip()
                if template_error(value):
                    continue                       # the API reports the reason before it gets here
            if key == "quality_profile" and value not in ("club", "balanced", "space"):
                continue
            if key == "upgrade_mode" and value not in ("ask", "auto", "auto_unless_dj", "off"):
                continue
            if key == "soulseek_mode" and value not in ("builtin", "nicotine"):
                continue
            if key == "suspect_quality" and value not in ("label", "reject"):
                continue
            if getattr(s, key) != value:
                setattr(s, key, value)
                changed.add(key)
        _clamp(s)
        if changed:
            self.save()
        return s, changed
