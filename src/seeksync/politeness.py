"""Being a good Soulseek citizen (roadmap step 8): search pacing, disk space, peer reputation.

Pure logic with no network and no engine, so it is easy to test with a fake clock."""
from __future__ import annotations

import asyncio
import os
import shutil
import time
from collections import deque
from typing import Callable, Optional

# Pacing -------------------------------------------------------------------------------------
DEFAULT_SEARCH_SPACING = 8.0       # seconds between two searches
MIN_SEARCH_SPACING = 4.0           # the user can slow down, never speed up past this
DEFAULT_MAX_SEARCHES = 20          # per WINDOW
MIN_MAX_SEARCHES, MAX_MAX_SEARCHES = 5, 60
WINDOW = 300.0                     # seconds ("a few minutes")


class SearchThrottle:
    """Waits before a search so that there is a fixed gap between searches and never more than
    `max_per_window` searches in any window of `window` seconds."""

    def __init__(self, spacing: float = DEFAULT_SEARCH_SPACING, max_per_window: int = DEFAULT_MAX_SEARCHES,
                 window: float = WINDOW, clock: Callable[[], float] = time.time,
                 sleep: Optional[Callable] = None):
        self.spacing = spacing
        self.max_per_window = max_per_window
        self.window = window
        self.clock = clock
        self._sleep = sleep
        self._stamps: deque[float] = deque()

    def configure(self, spacing: float, max_per_window: int) -> None:
        self.spacing, self.max_per_window = spacing, max_per_window

    def delay(self) -> float:
        """Seconds to wait before the next search is allowed (0 = go now)."""
        now = self.clock()
        while self._stamps and now - self._stamps[0] >= self.window:
            self._stamps.popleft()
        wait = 0.0
        if self._stamps:
            wait = self.spacing - (now - self._stamps[-1])
        if self.max_per_window > 0 and len(self._stamps) >= self.max_per_window:
            # the search that has to age out of the window before another one fits
            oldest_blocking = self._stamps[len(self._stamps) - self.max_per_window]
            wait = max(wait, oldest_blocking + self.window - now)
        return max(0.0, wait)

    async def wait(self) -> None:
        """Wait until a search is allowed, then count it."""
        while True:
            d = self.delay()
            if d <= 0:
                break
            await (self._sleep or asyncio.sleep)(d)
        self._stamps.append(self.clock())


# Disk space ---------------------------------------------------------------------------------
DEFAULT_MIN_FREE_GB = 5
GB = 1024 ** 3


def _existing(path: str) -> str:
    """Nearest folder that exists (disk_usage needs one; the music folder may not exist yet)."""
    path = os.path.abspath(path or ".")
    while path and not os.path.exists(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return path


def low_disk_space(paths: list[str], min_free_gb: float,
                   usage: Callable = shutil.disk_usage) -> Optional[str]:
    """A message when any of the folders is on a disk with less than `min_free_gb` GB free
    (the app data holds incoming + staging, the music folder is where files end up); else None.
    A limit of 0 turns the check off."""
    if min_free_gb <= 0:
        return None
    seen = set()
    for p in paths:
        if not p:
            continue
        p = _existing(p)
        try:
            free = usage(p).free
        except OSError:
            continue
        key = (os.stat(p).st_dev if os.path.exists(p) else p)
        if key in seen:
            continue
        seen.add(key)
        if free < min_free_gb * GB:
            return (f"Only {free / GB:.1f} GB free on the disk with {p}. Downloads are paused until there are "
                    f"{min_free_gb:g} GB free (change this in Settings).")
    return None


# Peer reputation ----------------------------------------------------------------------------
FAKE_PENALTY = 30.0          # per fake lossless / fake 320 a peer delivered
FAIL_PENALTY = 8.0           # per failed download (capped, see score)
FAIL_CAP = 5
RELIABLE_BONUS = 10.0        # at most, for a peer that delivered good files again and again
BLOCK_AFTER_FAKES = 3
BLOCK_AFTER_FAILS = 5        # failures without a single success
BLOCK_DAYS = 30


def peer_score(ok: int, failed: int, fake: int) -> float:
    """Added to a candidate's score: bonus for reliable peers, penalty for failing or faking ones."""
    score = -FAKE_PENALTY * fake - FAIL_PENALTY * min(failed, FAIL_CAP)
    if ok:
        score += min(ok, 5) / 5 * RELIABLE_BONUS * ok / (ok + failed + fake)
    return round(score, 1)


def block_reason(ok: int, failed: int, fake: int) -> str:
    """Why a peer should be blocked now ('' = not (yet))."""
    if fake >= BLOCK_AFTER_FAKES:
        return f"Delivered fake lossless or fake 320 files {fake} times"
    if failed >= BLOCK_AFTER_FAILS and ok == 0:
        return f"{failed} downloads failed and none ever worked"
    return ""


# Sharing ------------------------------------------------------------------------------------
def _has_files(folder: str, limit: int = 2000) -> bool:
    """True as soon as one file is found; looks at most `limit` entries so it stays cheap."""
    seen = 0
    for _root, _dirs, files in os.walk(folder):
        if files:
            return True
        seen += 1
        if seen >= limit:
            return True   # a big tree: assume it has music
    return False


def sharing_warning(dirs: Optional[list[str]], folders: Optional[int] = None, files: Optional[int] = None) -> str:
    """A message when nothing is shared on Soulseek, '' when fine or unknown.
    Own login: `dirs` are the folders we share. Nicotine+: its plugin reports `folders` / `files`
    (None = it couldn't tell, then no warning)."""
    nothing = ("You're not sharing any folders on Soulseek. Many users block people who share nothing, "
               "so downloads fail more often. Turn on sharing of the download folder in Settings.")
    empty = ("The folders you share on Soulseek are still empty. Many users block people who share nothing; "
             "downloaded tracks are shared automatically, so this fixes itself once a few have arrived.")
    if dirs is not None:
        existing = [d for d in dirs if os.path.isdir(d)]
        if not existing:
            return nothing
        return "" if any(_has_files(d) for d in existing) else empty
    if folders is not None and folders == 0:
        return "You're not sharing any folders in Nicotine+. Many users block people who share nothing. Add one in Nicotine+ (Preferences, Shares)."
    if files is not None and files == 0:
        return empty.replace("downloaded tracks are shared automatically, so this fixes itself once a few have arrived",
                             "add your music folder in Nicotine+ (Preferences, Shares)")
    return ""
