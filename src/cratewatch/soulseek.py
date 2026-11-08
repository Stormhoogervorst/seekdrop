"""Thin wrapper around aioslsk: log in, search, download."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from .matching import Candidate, file_ext

log = logging.getLogger(__name__)

LOGIN_REASONS = {
    "INVALIDPASS": "Wrong password for this Soulseek username. If the name isn't yours, pick another one.",
    "INVALIDUSERNAME": "Soulseek doesn't accept this username. Try another one (letters and numbers work best).",
    "SVRFULL": "The Soulseek server is full. Cratewatch will keep trying.",
    "SVRPRIVATE": "The Soulseek server is not accepting new accounts right now.",
}


class SoulseekService:
    """One Soulseek session. All methods must be called on the backend event loop."""

    mode = "builtin"

    def __init__(self, incoming_dir: str, cache_dir: str):
        self.incoming_dir = incoming_dir
        self.cache_dir = cache_dir
        self.client = None
        self.status = "not_configured"   # not_configured | connecting | connected | error | disconnected
        self.error = ""
        self.retryable = False           # True when a reconnect attempt makes sense
        self._search_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self.status == "connected"

    async def start(self, settings) -> None:
        await self.stop()
        if not (settings.soulseek_username and settings.soulseek_password):
            self.status, self.error = "not_configured", ""
            return

        from aioslsk.client import SoulSeekClient
        from aioslsk.events import KickedEvent, SessionDestroyedEvent, SessionInitializedEvent
        from aioslsk.exceptions import AuthenticationError
        from aioslsk.settings import CredentialsSettings, SharedDirectorySettingEntry
        from aioslsk.settings import Settings as SlskSettings
        from aioslsk.shares.cache import SharesShelveCache

        os.makedirs(self.incoming_dir, exist_ok=True)
        shares = []
        for d in _share_dirs(settings):
            if os.path.isdir(d):
                shares.append(SharedDirectorySettingEntry(path=d))

        s = SlskSettings(credentials=CredentialsSettings(
            username=settings.soulseek_username, password=settings.soulseek_password))
        s.shares.download = self.incoming_dir
        s.shares.directories = shares
        s.network.listening.port = settings.listen_port
        s.network.listening.obfuscated_port = settings.listen_port + 1
        s.network.server.reconnect.auto = True
        s.rooms.auto_join = False
        s.transfers.limits.upload_slots = 2

        client = SoulSeekClient(s, shares_cache=SharesShelveCache(self.cache_dir))

        async def on_login(_):
            self.status, self.error = "connected", ""

        async def on_logout(_):
            if self.status == "connected":
                self.status = "disconnected"
                self.error = "Lost connection to Soulseek, reconnecting…"

        async def on_kicked(_):
            self.status, self.retryable = "error", False
            self.error = ("Soulseek logged you out because this account was used somewhere else. "
                          "Use a separate account for Cratewatch.")

        client.events.register(SessionInitializedEvent, on_login)
        client.events.register(SessionDestroyedEvent, on_logout)
        client.events.register(KickedEvent, on_kicked)

        self.client = client
        self.status, self.error, self.retryable = "connecting", "", False
        try:
            await asyncio.wait_for(client.start(), 60)
            await asyncio.wait_for(client.login(), 30)
            self.status = "connected"
            log.info("Logged in to Soulseek as %s", settings.soulseek_username)
        except AuthenticationError as e:
            self.status, self.retryable = "error", e.reason in ("SVRFULL",)
            self.error = LOGIN_REASONS.get(e.reason, f"Soulseek refused the login ({e.reason}).")
            await self.stop(keep_status=True)
        except Exception as e:  # network trouble, ports in use, ...
            log.exception("Soulseek start failed")
            self.status, self.retryable = "error", True
            self.error = f"Couldn't connect to Soulseek: {e or type(e).__name__}"
            await self.stop(keep_status=True)

    async def stop(self, keep_status: bool = False) -> None:
        client, self.client = self.client, None
        if client is not None:
            try:
                await asyncio.wait_for(client.stop(), 15)
            except Exception:
                log.debug("error stopping client", exc_info=True)
        if not keep_status:
            self.status = "disconnected" if self.status != "not_configured" else self.status

    async def rescan_shares(self) -> None:
        if self.client:
            try:
                await self.client.shares.scan()
            except Exception:
                log.debug("share scan failed", exc_info=True)

    async def search(self, query: str, wait: float = 12.0) -> list[Candidate]:
        if not self.client or not self.connected:
            raise RuntimeError("not connected")
        async with self._search_lock:
            request = await self.client.searches.search(query)
            await asyncio.sleep(wait)
            results = list(request.results)
            try:
                self.client.searches.remove_request(request)
            except Exception:
                pass
        from aioslsk.protocol.primitives import AttributeKey

        out: list[Candidate] = []
        for r in results:
            for item in r.shared_items:
                attrs = item.get_attribute_map()
                out.append(Candidate(
                    username=r.username,
                    filename=item.filename,
                    size=item.filesize,
                    ext=(item.extension or file_ext(item.filename)).lower(),
                    bitrate=attrs.get(AttributeKey.BITRATE),
                    duration=attrs.get(AttributeKey.DURATION),
                    has_free_slots=r.has_free_slots,
                    queue_size=r.queue_size,
                    avg_speed=r.avg_speed,
                ))
        return out

    async def download(self, username: str, filename: str):
        if not self.client:
            raise RuntimeError("not connected")
        return await self.client.transfers.download(username, filename)

    async def abort(self, transfer) -> None:
        if self.client:
            try:
                await self.client.transfers.abort(transfer)
            except Exception:
                pass

    async def forget(self, transfer) -> None:
        if self.client:
            try:
                await self.client.transfers.remove(transfer)
            except Exception:
                pass

    @staticmethod
    def transfer_info(transfer) -> dict:
        state = transfer.state.VALUE.name if hasattr(transfer.state, "VALUE") else str(transfer.state)
        return {
            "state": state,
            "bytes": transfer.bytes_transfered,
            "size": transfer.filesize or 0,
            "local_path": transfer.local_path,
            "place_in_queue": transfer.place_in_queue,
            "fail_reason": transfer.fail_reason or transfer.abort_reason or "",
        }


def _share_dirs(settings) -> list[str]:
    dirs = list(settings.share_dirs)
    if settings.share_downloads and settings.download_dir:
        dirs.append(settings.download_dir)
    seen, out = set(), []
    for d in dirs:
        d = os.path.abspath(os.path.expanduser(d))
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out
