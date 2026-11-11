"""Find out whether a newer release is on GitHub, and (packaged apps for Mac and Windows) install it.

Mac: download the .dmg of the release, check size and checksum, copy the new SeekSync.app next to the
current one, then a small shell script waits until this app has quit, moves the old app to
`previous-versions/` in the app data (a back-up) and puts the new one in its place.

Windows: download the installer (`SeekSync-x.y.z-windows-setup.exe`), check size and checksum (the checksum is
required, because the file is run), then a small batch file waits until this app has quit, runs the installer
quietly (it installs over the old version, no administrator rights needed) and starts the app again.

Nothing is installed without the user pressing the button."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

import aiohttp

from . import __version__
from .config import GITHUB_REPO, data_dir

log = logging.getLogger(__name__)

CHECK_EVERY = 12 * 3600
KEEP_BACKUPS = 2

SWAP_SCRIPT = """#!/bin/sh
# SeekSync update: wait until the app has quit, keep the old app as a back-up, put the new one in its place.
PID="$1"; NEW="$2"; TARGET="$3"; BACKUP="$4"
OPEN="${OPEN_CMD:-open}"
i=0
while kill -0 "$PID" 2>/dev/null; do
  i=$((i+1))
  [ "$i" -gt 120 ] && exit 1
  sleep 0.5
done
mkdir -p "$BACKUP" || { $OPEN "$TARGET"; exit 1; }
OLD="$BACKUP/SeekSync-$(date +%Y%m%d-%H%M%S).app"
if mv "$TARGET" "$OLD"; then
  if mv "$NEW" "$TARGET"; then
    xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null
    rmdir "$(dirname "$NEW")" 2>/dev/null
    ls -1dt "$BACKUP"/SeekSync-*.app 2>/dev/null | tail -n +@KEEP@ | while read -r old; do rm -rf "$old"; done
    $OPEN "$TARGET"
    exit 0
  fi
  mv "$OLD" "$TARGET"
fi
$OPEN "$TARGET"
exit 1
""".replace("@KEEP@", str(KEEP_BACKUPS + 1))


WINDOWS_SCRIPT = """@echo off
rem SeekSync update: wait until the app has quit, run the installer quietly, start the app again.
set "PID=%~1"
set "SETUP=%~2"
set "APP=%~3"
set /a WAITED=0
:wait
tasklist /FI "PID eq %PID%" /NH 2>nul | find "%PID%" >nul
if errorlevel 1 goto install
set /a WAITED+=1
if %WAITED% gtr 120 goto failed
ping -n 2 127.0.0.1 >nul
goto wait
:install
"%SETUP%" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /LOG="%~dp0setup.log"
start "" "%APP%"
exit /b 0
:failed
start "" "%APP%"
exit /b 1
"""


def parse_version(v: str) -> tuple[int, ...]:
    """'v1.2.3' -> (1, 2, 3). Anything after the numbers (e.g. '-beta') is ignored."""
    m = re.match(r"^v?(\d+(?:\.\d+)*)", (v or "").strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def is_newer(latest: str, current: str = __version__) -> bool:
    a, b = parse_version(latest), parse_version(current)
    if not a or not b:
        return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def pick_asset(assets: list, platform: str = sys.platform) -> Optional[dict]:
    """The download for this computer from a release's asset list: {"name", "url", "size", "sha256"}."""
    if platform == "darwin":
        wanted = lambda n: n.endswith(".dmg") and "macos" in n
    elif platform.startswith("win"):
        wanted = lambda n: n.endswith("-windows-setup.exe")
    else:
        return None
    for a in assets or []:
        name = str(a.get("name") or "")
        if wanted(name.lower()) and a.get("browser_download_url"):
            digest = str(a.get("digest") or "")
            return {"name": name, "url": a["browser_download_url"], "size": int(a.get("size") or 0),
                    "sha256": digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else ""}
    return None


def bundle_path() -> Optional[Path]:
    """The SeekSync.app this process runs from, or None (running from the source, or not a Mac app)."""
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return None
    p = Path(sys.executable).resolve()
    return p.parents[2] if len(p.parents) > 2 and p.parents[2].suffix == ".app" else None


def windows_app_dir() -> Optional[Path]:
    """The folder of the installed SeekSync.exe this process runs from, or None (source run, or not Windows)."""
    if not sys.platform.startswith("win") or not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve().parent


def install_problem() -> str:
    """Why this copy can't update itself ('' = it can)."""
    if sys.platform.startswith("win"):
        folder = windows_app_dir()
        if folder is None:
            return "Automatic updates only work in the installed SeekSync app for Mac and Windows."
        if not os.access(folder, os.W_OK):
            return (f"SeekSync can't change {folder}. Download the installer from the release page and run it yourself.")
        return ""
    app = bundle_path()
    if app is None:
        return "Automatic updates only work in the installed SeekSync app for Mac and Windows."
    if not os.access(app.parent, os.W_OK) or not os.access(app, os.W_OK):
        return f"SeekSync can't change {app.parent}. Move the app to a folder you own (or drag it to Applications yourself)."
    return ""


class UpdateChecker:
    def __init__(self, store, repo: str = GITHUB_REPO):
        self.store = store
        self.repo = repo
        self.latest: Optional[dict] = None   # {"version", "url", "asset": {name, url, size, sha256} | None}
        self.progress: dict = {"stage": "", "done": 0, "total": 0, "error": ""}
        self.checked_at: float = 0.0
        self._task: Optional[asyncio.Task] = None
        self._install: Optional[asyncio.Task] = None

    # -- the background check
    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="updates")

    async def stop(self) -> None:
        for t in (self._task, self._install):
            if t:
                t.cancel()
        await asyncio.gather(*[t for t in (self._task, self._install) if t], return_exceptions=True)

    async def _loop(self) -> None:
        await asyncio.sleep(5)   # don't slow down startup
        while True:
            if self.store.settings.check_updates:
                await self.check()
            await asyncio.sleep(CHECK_EVERY)

    @property
    def api_url(self) -> str:
        # SEEKSYNC_RELEASE_API lets a test point at a fake GitHub (never set it otherwise).
        return os.environ.get("SEEKSYNC_RELEASE_API") or f"https://api.github.com/repos/{self.repo}/releases/latest"

    async def _fetch(self) -> Optional[dict]:
        """The latest published release (drafts and pre-releases are skipped by GitHub), None when there is none.
        Raises OSError / aiohttp errors when GitHub can't be reached."""
        headers = {"Accept": "application/vnd.github+json", "User-Agent": f"SeekSync/{__version__}"}
        async with aiohttp.ClientSession(headers=headers) as s:
            async with s.get(self.api_url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 404:
                    return None
                if r.status != 200:
                    raise OSError(f"GitHub answered {r.status}")
                return await r.json()

    def _apply(self, data: Optional[dict]) -> None:
        tag = (data or {}).get("tag_name") or ""
        if data and is_newer(tag):
            self.latest = {"version": tag.lstrip("v"),
                           "url": data.get("html_url") or f"https://github.com/{self.repo}/releases/latest",
                           "asset": pick_asset(data.get("assets") or [])}
            log.info("Update available: %s", tag)
        else:
            self.latest = None

    async def check(self) -> None:
        """The quiet check in the background: failures are only logged."""
        try:
            self._apply(await self._fetch())
            self.checked_at = time.time()
        except Exception as e:
            log.debug("update check failed: %s", e)

    async def check_now(self) -> dict:
        """The button: look now, and say in words what was found."""
        try:
            data = await self._fetch()
        except Exception as e:
            log.debug("update check failed: %s", e)
            return {"status": "error", "message": "Can't reach GitHub. Check your internet connection."}
        try:
            self._apply(data)
        except Exception as e:
            log.debug("couldn't read GitHub's answer: %s", e)
            return {"status": "error", "message": "GitHub's answer couldn't be read. Try again later."}
        self.checked_at = time.time()
        if data is None:
            return {"status": "current", "version": __version__,
                    "message": f"No published release found. You have {__version__}."}
        if self.latest:
            return {"status": "update", "version": self.latest["version"],
                    "message": f"Version {self.latest['version']} is available (you have {__version__})."}
        return {"status": "current", "version": __version__, "message": f"You have the latest version ({__version__})."}

    # -- installing
    def installing(self) -> bool:
        return bool(self._install and not self._install.done())

    def start_install(self, quit_app: Callable[[], None]) -> None:
        """Download and prepare the update in the background; then quit so the swap script can run."""
        if self.installing():
            return
        problem = install_problem()
        if problem:
            raise RuntimeError(problem)
        if not self.latest or not self.latest.get("asset"):
            raise RuntimeError("There is no download for this version. Use the release page instead.")
        self.progress = {"stage": "downloading", "done": 0, "total": self.latest["asset"]["size"], "error": ""}
        self._install = asyncio.create_task(self._run_install(dict(self.latest), quit_app), name="install-update")

    async def _run_install(self, release: dict, quit_app: Callable[[], None]) -> None:
        try:
            await self.install(release)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("update failed")
            self.progress = {"stage": "", "done": 0, "total": 0, "error": str(e) or "The update failed."}
            return
        self.progress["stage"] = "restarting"
        await asyncio.sleep(1.5)                  # let the page show "Restarting"
        quit_app()

    async def install(self, release: dict) -> None:
        problem = install_problem()
        if problem:
            raise RuntimeError(problem)
        if sys.platform.startswith("win"):
            await self._install_windows(release)
        else:
            await self._install_mac(release)

    async def _install_windows(self, release: dict) -> None:
        folder = windows_app_dir()
        asset, version = release["asset"], release["version"]
        if folder is None:
            raise RuntimeError("Automatic updates only work in the installed SeekSync app for Mac and Windows.")
        self._check_url(asset["url"])
        if not asset.get("sha256"):      # this file is going to be run: without a checksum from GitHub it isn't
            raise RuntimeError("GitHub gave no checksum for this download, so it was not installed. Use the release page instead.")
        if f"-{version}-" not in asset["name"]:
            raise RuntimeError(f"The download is not version {version}.")
        work = data_dir() / "update"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)
        setup = work / asset["name"]
        await self.download(asset, setup)

        self.progress["stage"] = "installing"
        with open(setup, "rb") as f:
            if f.read(2) != b"MZ":
                raise RuntimeError("The download is not a Windows program.")
        script = work / "update.bat"
        script.write_text(WINDOWS_SCRIPT, "utf-8", newline="\r\n")
        subprocess.Popen([str(script), str(os.getpid()), str(setup), str(folder / Path(sys.executable).name)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                         | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))

    async def _install_mac(self, release: dict) -> None:
        app = bundle_path()
        asset, version = release["asset"], release["version"]
        if app is None:
            raise RuntimeError("Automatic updates only work in the installed SeekSync app for Mac and Windows.")
        self._check_url(asset["url"])
        work = data_dir() / "update"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)
        dmg = work / asset["name"]
        await self.download(asset, dmg)

        self.progress["stage"] = "installing"
        stage = app.parent / f".SeekSync-update-{version}"
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir()
        try:
            new_app = await self.extract(dmg, stage, work)
            self.verify_app(new_app, version)
            dmg.unlink(missing_ok=True)
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        script = work / "swap.sh"
        script.write_text(SWAP_SCRIPT, "utf-8")
        script.chmod(0o755)
        backup = data_dir() / "previous-versions"
        subprocess.Popen(["/bin/sh", str(script), str(os.getpid()), str(new_app), str(app), str(backup)],
                         start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)

    def _check_url(self, url: str) -> None:
        ok = url.startswith(f"https://github.com/{self.repo}/releases/download/") or \
            (os.environ.get("SEEKSYNC_RELEASE_API") and url.startswith("http://127.0.0.1:"))
        if not ok:
            raise RuntimeError("The download link is not on GitHub, so SeekSync won't use it.")

    async def download(self, asset: dict, dest: Path) -> None:
        """Stream the file to `dest`; the size and (when GitHub gave one) the SHA-256 must match."""
        sha = hashlib.sha256()
        done = 0
        headers = {"User-Agent": f"SeekSync/{__version__}"}
        async with aiohttp.ClientSession(headers=headers) as s:
            async with s.get(asset["url"], timeout=aiohttp.ClientTimeout(total=None, sock_connect=20, sock_read=60)) as r:
                if r.status != 200:
                    raise RuntimeError(f"The download failed (GitHub answered {r.status}).")
                with open(dest, "wb") as f:
                    async for chunk in r.content.iter_chunked(256 * 1024):
                        f.write(chunk)
                        sha.update(chunk)
                        done += len(chunk)
                        self.progress.update(stage="downloading", done=done)
        self.progress["stage"] = "checking"
        if asset.get("size") and done != asset["size"]:
            raise RuntimeError("The download is incomplete. Try again.")
        if asset.get("sha256") and sha.hexdigest() != asset["sha256"]:
            raise RuntimeError("The download doesn't match its checksum, so it was not installed.")

    @staticmethod
    async def _run(*cmd: str) -> str:
        p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await p.communicate()
        if p.returncode:
            raise RuntimeError(f"{cmd[0]} failed: {out.decode('utf-8', 'replace').strip()[:200]}")
        return out.decode("utf-8", "replace")

    async def extract(self, dmg: Path, stage: Path, work: Path) -> Path:
        """Copy SeekSync.app out of the disk image into `stage` (on the same disk as the current app)."""
        mnt = work / "mnt"
        mnt.mkdir(exist_ok=True)
        await self._run("hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", str(mnt), str(dmg))
        try:
            src = mnt / "SeekSync.app"
            if not src.is_dir():
                raise RuntimeError("The download doesn't contain SeekSync.app.")
            dst = stage / "SeekSync.app"
            await self._run("ditto", str(src), str(dst))
            return dst
        finally:
            try:
                await self._run("hdiutil", "detach", str(mnt), "-force")
            except Exception:
                log.debug("couldn't unmount the update image", exc_info=True)

    @staticmethod
    def verify_app(new_app: Path, version: str) -> None:
        plist = new_app / "Contents" / "Info.plist"
        exe = new_app / "Contents" / "MacOS" / "SeekSync"
        if not plist.is_file() or not exe.is_file():
            raise RuntimeError("The downloaded app is incomplete.")
        info = plistlib.loads(plist.read_bytes())
        got = str(info.get("CFBundleShortVersionString") or "")
        if parse_version(got) != parse_version(version):
            raise RuntimeError(f"The download is version {got or '?'}, not {version}.")
