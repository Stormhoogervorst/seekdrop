"""Settings and file locations."""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from platformdirs import user_data_dir, user_log_dir, user_music_dir

APP_NAME = "Cratewatch"


def data_dir() -> Path:
    p = Path(os.environ.get("CRATEWATCH_HOME") or user_data_dir(APP_NAME, appauthor=False))
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_dir() -> Path:
    p = Path(os.environ.get("CRATEWATCH_HOME") or user_log_dir(APP_NAME, appauthor=False))
    if os.environ.get("CRATEWATCH_HOME"):
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
    organize_by_channel: bool = True
    preferred_format: str = "lossless"      # "lossless" | "mp3"
    min_bitrate: int = 320
    check_interval_minutes: int = 60
    max_parallel_downloads: int = 3
    give_up_days: int = 30
    listen_port: int = 60000

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


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "settings.json"
        self._lock = threading.Lock()
        self.settings = self._load()

    def _load(self) -> Settings:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text("utf-8"))
                known = {f.name for f in fields(Settings)}
                return Settings(**{k: v for k, v in raw.items() if k in known})
            except Exception:
                pass
        return Settings()

    def save(self) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(self.settings), indent=2), "utf-8")
            os.replace(tmp, self.path)
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
            if key in ("min_bitrate", "check_interval_minutes", "max_parallel_downloads", "give_up_days", "listen_port", "nicotine_port"):
                value = int(value)
            if key in ("accepted_terms", "share_downloads", "organize_by_channel"):
                value = bool(value)
            if key == "share_dirs":
                value = [str(v).strip() for v in (value or []) if str(v).strip()]
            if key in ("soulseek_username", "download_dir"):
                value = str(value).strip()
            if key == "preferred_format" and value not in ("lossless", "mp3"):
                continue
            if key == "soulseek_mode" and value not in ("builtin", "nicotine"):
                continue
            if getattr(s, key) != value:
                setattr(s, key, value)
                changed.add(key)
        s.check_interval_minutes = max(15, s.check_interval_minutes)
        s.max_parallel_downloads = min(max(1, s.max_parallel_downloads), 10)
        s.give_up_days = min(max(1, s.give_up_days), 365)
        if changed:
            self.save()
        return s, changed
