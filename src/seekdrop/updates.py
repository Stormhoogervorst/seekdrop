"""Tell the user when a newer release is on GitHub (no auto-update, just a link)."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

import aiohttp

from . import __version__
from .config import GITHUB_REPO

log = logging.getLogger(__name__)

CHECK_EVERY = 12 * 3600


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


class UpdateChecker:
    def __init__(self, store, repo: str = GITHUB_REPO):
        self.store = store
        self.repo = repo
        self.latest: Optional[dict] = None   # {"version": "0.4.0", "url": "https://github.com/..."}
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="updates")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _loop(self) -> None:
        await asyncio.sleep(5)   # don't slow down startup
        while True:
            if self.store.settings.check_updates:
                await self.check()
            await asyncio.sleep(CHECK_EVERY)

    async def check(self) -> None:
        url = f"https://api.github.com/repos/{self.repo}/releases/latest"   # skips drafts and pre-releases
        headers = {"Accept": "application/vnd.github+json", "User-Agent": f"SeekDrop/{__version__}"}
        try:
            async with aiohttp.ClientSession(headers=headers) as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status != 200:      # 404 = no published release yet
                        return
                    data = await r.json()
        except Exception as e:
            log.debug("update check failed: %s", e)
            return
        tag = data.get("tag_name") or ""
        if is_newer(tag):
            self.latest = {"version": tag.lstrip("v"), "url": data.get("html_url") or f"https://github.com/{self.repo}/releases/latest"}
            log.info("Update available: %s", tag)
        else:
            self.latest = None
