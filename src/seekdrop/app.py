"""Start the backend (engine + local web server) in a background thread."""
from __future__ import annotations

import asyncio
import logging
import socket
import threading
from logging.handlers import RotatingFileHandler
from typing import Optional

from aiohttp import web

from .config import DB_NAME, SettingsStore, data_dir, log_dir
from .db import Database
from .engine import Engine
from .server import Api
from .nicotine import NicotineBridge
from .updates import UpdateChecker
from .soulseek import SoulseekService
from .soundcloud import SoundCloudClient

log = logging.getLogger("seekdrop")

INSTANCE_PORT = 47811  # localhost-only lock so two copies don't fight over one Soulseek account


def setup_logging(verbose: bool = False) -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fh = RotatingFileHandler(log_dir() / "seekdrop.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(fh)
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


class Backend:
    def __init__(self, port: int = 0, slsk=None, sc=None, token: Optional[str] = None, updates=None):
        self.port = port
        self.url = ""
        self.token = token or ""      # fixed key only for the demo/dev server; normally random
        self._updates = updates
        self._slsk = slsk
        self._sc = sc
        self._ready = threading.Event()
        self._error: Optional[BaseException] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop: Optional[asyncio.Event] = None
        self._thread = threading.Thread(target=self._run, name="backend", daemon=True)

    def start(self, timeout: float = 30) -> str:
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
        home = data_dir()
        db = Database(home / DB_NAME)
        store = SettingsStore()
        sc = self._sc or SoundCloudClient(cache_dir=str(home / "cache"))
        def make_slsk(mode: str):
            if mode == "nicotine":
                return NicotineBridge(incoming_dir=str(home / "incoming-nicotine"))
            return SoulseekService(incoming_dir=str(home / "incoming"), cache_dir=str(home))

        factory = None if self._slsk else make_slsk
        slsk = self._slsk or make_slsk(store.settings.soulseek_mode)
        engine = Engine(db, store, sc, slsk, slsk_factory=factory)
        updates = self._updates or UpdateChecker(store)
        api = Api(engine, db, token=self.token or None, updates=updates)
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
            await updates.stop()
            await engine.stop()
            await runner.cleanup()
