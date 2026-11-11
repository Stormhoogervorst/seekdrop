"""Start the backend (engine + local web server) in a background thread."""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import RotatingFileHandler
from typing import Callable, Optional

from aiohttp import web

from . import fsutil
from .checks import FileChecker
from .config import DB_NAME, SettingsStore, data_dir, log_dir
from .db import Database
from .diag import LoopWatchdog
from .engine import Engine
from .server import Api
from .nicotine import NicotineBridge
from .updates import UpdateChecker
from .soulseek import SoulseekService
from .soundcloud import SoundCloudClient
from .sources import Sources

log = logging.getLogger("seeksync")

INSTANCE_PORT = int(os.environ.get("SEEKSYNC_LOCK_PORT") or 47811)  # localhost-only lock so two copies don't fight over one Soulseek account (the variable is for tests)


def setup_logging(verbose: bool = False) -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fh = RotatingFileHandler(log_dir() / "seeksync.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(fh)
    if sys.stderr is not None:     # the windowed Windows app has no console: only the log file then
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(sh)
    for noisy in ("aioslsk", "aiohttp.access", "async_upnp_client"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def acquire_instance_lock() -> Optional[socket.socket]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", INSTANCE_PORT))
        s.listen(1)
        return s
    except OSError:
        s.close()
        return None


def open_database(path) -> Database:
    """Open the database. A file that is damaged beyond reading (a crash or a full disk at the wrong moment)
    would keep the app from ever starting again: it is set aside under another name, never deleted, and the
    app starts with a new one."""
    try:
        return Database(path)
    except sqlite3.DatabaseError as e:
        msg = str(e).lower()
        if "malformed" not in msg and "not a database" not in msg:
            raise                       # locked, read-only folder, ...: not a damaged file
        aside = f"{path}.damaged-{time.strftime('%Y%m%d-%H%M%S')}"
        log.error("the database %s can't be read (%s); it is kept as %s and a new one is started", path, e, aside)
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(str(path) + suffix):
                fsutil.replace(str(path) + suffix, aside + suffix)
        return Database(path)


class Backend:
    def __init__(self, port: int = 0, slsk=None, sc=None, token: Optional[str] = None, updates=None):
        self.port = port
        self.url = ""
        self.token = token or ""      # fixed key only for the demo/dev server; normally random
        self._updates = updates
        self.on_quit: Optional[Callable[[], None]] = None      # set by the window: how to close the app
        self._slsk = slsk
        self._sc = sc
        self._ready = threading.Event()
        self._error: Optional[BaseException] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop: Optional[asyncio.Event] = None
        self._thread = threading.Thread(target=self._run, name="backend", daemon=True)

    def start(self, timeout: float = 60) -> str:
        self._thread.start()
        if not self._ready.wait(timeout):
            raise RuntimeError("backend did not start in time")
        if self._error:
            raise self._error
        return self.url

    def stop(self, timeout: float = 20) -> None:
        if self._loop and self._stop:
            self._loop.call_soon_threadsafe(self._stop.set)
        self._thread.join(timeout)

    def _run(self) -> None:
        try:
            asyncio.run(self._main())
        except BaseException as e:  # surface startup errors to the caller
            log.exception("backend crashed")
            self._error = e
            self._ready.set()

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        # The standard pool has (processors + 4) threads: 6 on a small laptop. A library scan, a few file checks
        # and a channel check fill that up, and then a running download can't write to disk (aioslsk writes
        # through the same pool). These jobs mostly wait for the disk or the network, so more threads cost nothing.
        self._loop.set_default_executor(ThreadPoolExecutor(max_workers=32, thread_name_prefix="work"))
        watchdog = LoopWatchdog(self._loop)        # logs what every thread is doing when the app freezes
        watchdog.start()
        home = data_dir()
        db = open_database(home / DB_NAME)
        store = SettingsStore()
        sc = self._sc or Sources(SoundCloudClient(cache_dir=str(home / "cache")))
        def make_slsk(mode: str):
            if mode == "nicotine":
                return NicotineBridge(incoming_dir=str(home / "incoming-nicotine"))
            return SoulseekService(incoming_dir=str(home / "incoming"), cache_dir=str(home))

        factory = None if self._slsk else make_slsk
        slsk = self._slsk or make_slsk(store.settings.soulseek_mode)
        engine = Engine(db, store, sc, slsk, slsk_factory=factory, staging_dir=str(home / "staging"),
                        quarantine_dir=str(home / "quarantine"))
        engine.file_checker = FileChecker(lambda: store.settings)
        engine.checks.append(engine.file_checker)
        updates = self._updates or UpdateChecker(store)
        api = Api(engine, db, token=self.token or None, updates=updates, quit_app=lambda: self.on_quit and self.on_quit())
        self.token = api.token

        runner = web.AppRunner(api.app(), access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", self.port)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        self.url = f"http://127.0.0.1:{self.port}/#token={self.token}"
        log.info("UI at http://127.0.0.1:%s", self.port)

        await engine.start()
        updates.start()
        self._ready.set()
        try:
            await self._stop.wait()
        finally:
            watchdog.stop()
            try:
                await updates.stop()
            except Exception:
                log.exception("couldn't stop the update check")
            try:
                await asyncio.wait_for(engine.stop(), 25)    # a connection that won't close must not keep the app alive
            except asyncio.TimeoutError:
                log.warning("the engine didn't stop in time")
            except Exception:
                log.exception("the engine didn't stop cleanly")
            await runner.cleanup()
