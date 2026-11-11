"""Use Nicotine+ (with the SeekSync Bridge plugin) instead of a built-in Soulseek login."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import shutil
import sys
from pathlib import Path
from typing import Optional

import aiohttp

from .matching import Candidate, file_ext

log = logging.getLogger(__name__)

PLUGIN_NAME = "seeksync_bridge"
PLUGIN_SRC = Path(__file__).parent / "nicotine_plugin" / PLUGIN_NAME
DEFAULT_PORT = 47820

# Nicotine+ transfer status -> the state names the engine understands.
STATUS_MAP = {
    "Finished": "COMPLETE",
    "Transferring": "DOWNLOADING",
    "Queued": "QUEUED",
    "Getting status": "QUEUED",
    "Paused": "QUEUED",
    "Cancelled": "ABORTED",
}

MSG_UNREACHABLE = ("Can't reach Nicotine+. Open Nicotine+ and turn on the SeekSync Bridge plugin "
                   "(Preferences, Plugins).")
MSG_KEY = "The Nicotine+ plugin has a different key. Install the plugin again from Settings, then turn it off and on in Nicotine+."
MSG_OFFLINE = "Nicotine+ is open but not connected to Soulseek."


def nicotine_plugins_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "nicotine" / "plugins"


def plugin_installed() -> bool:
    return (nicotine_plugins_dir() / PLUGIN_NAME / "bridge.json").exists()


def install_plugin(port: int, token: str) -> Path:
    """Copy the plugin into Nicotine+'s plugin folder and write its key."""
    dest = nicotine_plugins_dir() / PLUGIN_NAME
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("PLUGININFO", "__init__.py"):
        shutil.copyfile(PLUGIN_SRC / name, dest / name)
    cfg = dest / "bridge.json"
    cfg.write_text(json.dumps({"port": int(port), "token": token}), "utf-8")
    try:
        os.chmod(cfg, 0o600)
    except OSError:
        pass
    return dest


def _plugin_version(folder: Path) -> str:
    try:
        for line in (folder / "PLUGININFO").read_text("utf-8").splitlines():
            if line.strip().startswith("Version"):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return ""


# Earlier plugin folder names; their key is reused so the app keeps working after a rename.
LEGACY_PLUGIN_NAMES = ("nicotine_sync_bridge", "cratewatch_bridge", "seekdrop_bridge")


def migrate_legacy_plugin() -> bool:
    """If only an older-named plugin is installed, install this one with the same port and key.
    Returns True when it did; the user then switches plugins once in Nicotine+."""
    if (nicotine_plugins_dir() / PLUGIN_NAME / "bridge.json").exists():
        return False
    for old in LEGACY_PLUGIN_NAMES:
        cfg = nicotine_plugins_dir() / old / "bridge.json"
        if cfg.exists():
            try:
                d = json.loads(cfg.read_text("utf-8"))
                install_plugin(int(d["port"]), str(d["token"]))
                return True
            except (OSError, ValueError, KeyError):
                return False
    return False


def update_plugin_if_outdated() -> bool:
    """After an app update, replace an older installed plugin (keeping its key).
    Returns True if it was replaced; Nicotine+ then needs the plugin turned off and on."""
    dest = nicotine_plugins_dir() / PLUGIN_NAME
    if not (dest / "bridge.json").exists():
        return False
    if _plugin_version(dest) == _plugin_version(PLUGIN_SRC):
        return False
    for name in ("PLUGININFO", "__init__.py"):
        shutil.copyfile(PLUGIN_SRC / name, dest / name)
    return True


def new_token() -> str:
    return secrets.token_urlsafe(24)


class _Handle:
    """Stands in for an aioslsk Transfer: the engine only reads it via transfer_info()."""

    def __init__(self, username: str, path: str, folder: str):
        self.username = username
        self.path = path
        self.folder = folder
        self.info = {"state": "QUEUED", "bytes": 0, "size": 0, "local_path": None,
                     "place_in_queue": None, "fail_reason": ""}
        self.task: Optional[asyncio.Task] = None


class NicotineBridge:
    """Same interface as SoulseekService, but talks to the Nicotine+ plugin."""

    mode = "nicotine"

    def __init__(self, incoming_dir: str):
        self.incoming_dir = incoming_dir
        self.status = "not_configured"
        self.error = ""
        self.retryable = False      # the monitor below reconnects by itself
        self.username = ""
        self.shared_folders: Optional[int] = None   # reported by plugin 0.5+ (None = unknown)
        self.shared_files: Optional[int] = None
        self._base = ""
        self._token = ""
        self._session: Optional[aiohttp.ClientSession] = None
        self._monitor: Optional[asyncio.Task] = None

    @property
    def connected(self) -> bool:
        return self.status == "connected"

    async def start(self, settings) -> None:
        await self.stop()
        if not settings.nicotine_token:
            self.status, self.error = "not_configured", ""
            return
        os.makedirs(self.incoming_dir, exist_ok=True)
        self._base = f"http://127.0.0.1:{settings.nicotine_port}"
        self._token = settings.nicotine_token
        self._session = aiohttp.ClientSession(headers={"X-Token": self._token})
        self.status = "connecting"
        await self._check()
        self._monitor = asyncio.create_task(self._watch())

    async def stop(self, keep_status: bool = False) -> None:
        if self._monitor:
            self._monitor.cancel()
            self._monitor = None
        if self._session:
            await self._session.close()
            self._session = None
        if not keep_status and self.status != "not_configured":
            self.status = "disconnected"

    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(5)
            try:
                await self._check()
            except asyncio.CancelledError:
                raise
            except Exception:           # the watcher must survive anything, or the status never changes again
                log.debug("Nicotine+ status check failed", exc_info=True)
                self.status, self.error = "error", MSG_UNREACHABLE

    async def _check(self) -> None:
        try:
            data = await self._get("/status", timeout=8)
        except PermissionError:
            self.status, self.error = "error", MSG_KEY
            return
        except Exception:
            self.status, self.error = "error", MSG_UNREACHABLE
            return
        if data.get("logged_in"):
            if self.status != "connected":
                log.info("Nicotine+ bridge connected (%s)", data.get("username"))
            self.status, self.error, self.username = "connected", "", data.get("username", "")
            self.shared_folders, self.shared_files = data.get("shared_folders"), data.get("shared_files")
        else:
            self.status, self.error = "error", MSG_OFFLINE

    async def _get(self, path: str, params: Optional[dict] = None, timeout: float = 15) -> dict:
        assert self._session is not None
        async with self._session.get(self._base + path, params=params,
                                     timeout=aiohttp.ClientTimeout(total=timeout)) as r:
            return await self._json(r)

    async def _post(self, path: str, body: dict, timeout: float = 15) -> dict:
        assert self._session is not None
        async with self._session.post(self._base + path, json=body,
                                      timeout=aiohttp.ClientTimeout(total=timeout)) as r:
            return await self._json(r)

    @staticmethod
    async def _json(r: aiohttp.ClientResponse) -> dict:
        if r.status == 401:
            raise PermissionError("bad key")
        try:
            data = await r.json(content_type=None)
        except ValueError:
            data = None
        if not isinstance(data, dict):      # not the plugin answering (another program on this port?)
            if r.status >= 400:
                raise RuntimeError(f"HTTP {r.status}")
            raise RuntimeError("unexpected answer from Nicotine+")
        if r.status >= 400:
            raise RuntimeError(data.get("error") or f"HTTP {r.status}")
        return data

    # ---------------------------------------------------------------- engine interface
    async def rescan_shares(self) -> None:
        pass  # Nicotine+ manages its own shares

    async def search(self, query: str, wait: float = 12.0) -> list[Candidate]:
        if not self.connected:
            raise RuntimeError("not connected")
        data = await self._post("/search", {"query": query, "wait": wait}, timeout=wait + 30)
        out = []
        for r in data.get("results") or []:
            if not isinstance(r, dict) or not r.get("username") or not r.get("path"):
                continue
            out.append(Candidate(
                username=r["username"], filename=r["path"], size=int(r.get("size") or 0),
                ext=(r.get("ext") or file_ext(r["path"])).lower(), bitrate=r.get("bitrate"),
                sample_rate=r.get("sample_rate"), bit_depth=r.get("bit_depth"),
                duration=r.get("duration"), has_free_slots=bool(r.get("free_slots")),
                queue_size=int(r.get("queue") or 0), avg_speed=int(r.get("speed") or 0)))
        return out

    async def download(self, username: str, filename: str):
        await self._post("/download", {"username": username, "path": filename, "folder": self.incoming_dir})
        h = _Handle(username, filename, self.incoming_dir)
        h.task = asyncio.create_task(self._poll(h))
        return h

    async def _poll(self, h: _Handle) -> None:
        misses = 0
        while True:
            try:
                d = await self._get("/transfer", {"username": h.username, "path": h.path}, timeout=10)
                misses = 0
            except asyncio.CancelledError:
                raise
            except Exception:
                misses += 1
                if misses >= 30:   # ~1 minute without Nicotine+
                    h.info.update(state="FAILED", fail_reason="Nicotine+ stopped responding")
                    return
                await asyncio.sleep(2)
                continue
            status = d.get("status", "")
            state = STATUS_MAP.get(status, "FAILED")
            local = d.get("local_path")
            if state == "COMPLETE" and not local:
                guess = os.path.join(h.folder, h.path.replace("\\", "/").rsplit("/", 1)[-1])
                local = guess if os.path.exists(guess) else None
                if local is None:
                    state = "DOWNLOADING"   # wait for the finished notification
            h.info = {
                "state": state,
                "bytes": int(d.get("bytes") or 0),
                "size": int(d.get("size") or 0),
                "local_path": local,
                "place_in_queue": d.get("queue_position") or None,
                "fail_reason": "" if state != "FAILED" else (status or "failed"),
            }
            if state in ("COMPLETE", "FAILED", "ABORTED"):
                return
            await asyncio.sleep(2)

    @staticmethod
    def transfer_info(h: _Handle) -> dict:
        return dict(h.info)

    async def abort(self, h: _Handle) -> None:
        try:
            await self._post("/abort", {"username": h.username, "path": h.path, "clear": False})
        except Exception:
            pass

    async def lookup(self, username: str, path: str) -> Optional[dict]:
        """State of a transfer left over from an earlier session, or None if Nicotine+ has none."""
        d = await self._get("/transfer", {"username": username, "path": path}, timeout=10)
        status = d.get("status", "")
        if status == "Missing":
            return None
        state, local = STATUS_MAP.get(status, "FAILED"), d.get("local_path")
        if state == "COMPLETE" and not local:
            # Nicotine+ was restarted too, so the plugin lost the path; look in our incoming folder.
            guess = os.path.join(self.incoming_dir, path.replace("\\", "/").rsplit("/", 1)[-1])
            local = guess if os.path.exists(guess) else None
        return {"state": state, "local_path": local}

    async def cancel(self, username: str, path: str) -> None:
        """Stop and remove a leftover transfer so it can't land in the incoming folder later."""
        await self._post("/abort", {"username": username, "path": path, "clear": True})

    async def forget(self, h: _Handle) -> None:
        if h.task:
            h.task.cancel()
        if h.info.get("state") != "COMPLETE":
            try:
                await self._post("/abort", {"username": h.username, "path": h.path, "clear": True})
            except Exception:
                pass
