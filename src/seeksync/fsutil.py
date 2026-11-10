"""File operations that cope with Windows' habits.

On Windows a file that was written a moment ago is often still held by the antivirus scanner, the search
indexer or the program that downloaded it. Renaming or replacing it then fails with "access denied" or
"used by another process" (PermissionError / WinError 5, 32, 33), and succeeds a second later. These
helpers wait a little and try again. On macOS and Linux a PermissionError is a real permission problem,
so nothing is retried there.
"""
from __future__ import annotations

import errno
import logging
import os
import shutil
import sys
import time
from typing import Any, Callable

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform.startswith("win")
RETRY_DELAYS = (0.25, 0.5, 1.0, 2.0, 4.0)        # seconds between tries: about 8 s in total
_WINERRORS = (5, 32, 33)                          # access denied, sharing violation, lock violation


def _transient(e: OSError) -> bool:
    return IS_WINDOWS and (isinstance(e, PermissionError) or getattr(e, "winerror", None) in _WINERRORS)


def retry(fn: Callable[..., Any], *args: Any, delays: tuple = None, **kwargs: Any) -> Any:
    """Call fn(*args, **kwargs); on Windows, wait and try again while the file is busy."""
    delays = RETRY_DELAYS if delays is None else delays
    for i in range(len(delays) + 1):
        try:
            return fn(*args, **kwargs)
        except OSError as e:
            if i == len(delays) or not _transient(e):
                raise
            log.debug("%s is busy (%s), trying again in %.2f s", getattr(fn, "__name__", "file operation"), e, delays[i])
            time.sleep(delays[i])


def rename(src: str, dst: str) -> None:
    retry(os.rename, src, dst)


def replace(src: str, dst: str) -> None:
    retry(os.replace, src, dst)


def remove(path: str) -> None:
    retry(os.remove, path)


def move(src: str, dst: str) -> None:
    """Move a file or folder. A rename when possible (same disk), otherwise copy and delete."""
    try:
        retry(os.rename, src, dst)
        return
    except OSError as e:
        if e.errno != errno.EXDEV:
            raise
    retry(shutil.move, src, dst)
