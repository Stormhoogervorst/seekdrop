"""Diagnostics for freezes and crashes, written to the log folder.

The packaged Windows app has no console, so an error that nobody catches would vanish. This module makes
sure it ends up in `seeksync.log` (uncaught errors in any thread) or `crash.log` (the process itself dies),
and a watchdog writes the stack of every thread to the log when the app's event loop stops answering. With
that, a "SeekSync froze" report comes with the line of code it was stuck on.
"""
from __future__ import annotations

import asyncio
import faulthandler
import logging
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Optional

log = logging.getLogger("seeksync.diag")

_crash_file = None          # kept open for faulthandler


def install(log_folder: Path) -> None:
    """Route uncaught errors to the log and let a hard crash write its traceback to crash.log."""
    global _crash_file
    try:
        _crash_file = open(Path(log_folder) / "crash.log", "a", encoding="utf-8")
        faulthandler.enable(file=_crash_file, all_threads=True)
    except Exception:
        log.debug("couldn't enable faulthandler", exc_info=True)

    def on_exception(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            return
        log.critical("uncaught error", exc_info=(exc_type, exc, tb))

    def on_thread_exception(args):
        if args.exc_type is SystemExit:
            return
        log.critical("uncaught error in thread %s", getattr(args.thread, "name", "?"),
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = on_exception
    threading.excepthook = on_thread_exception


def thread_stacks() -> str:
    names = {t.ident: t.name for t in threading.enumerate()}
    parts = []
    for ident, frame in sys._current_frames().items():
        parts.append(f"--- thread {names.get(ident, ident)}\n" + "".join(traceback.format_stack(frame)))
    return "\n".join(parts)


class LoopWatchdog:
    """Pings the asyncio loop every few seconds. When it doesn't answer within `warn_after` seconds, the stack
    of every thread goes to the log (once per freeze), and the log says how long the freeze lasted."""

    def __init__(self, loop: asyncio.AbstractEventLoop, interval: float = 5.0, warn_after: float = 10.0):
        self.loop = loop
        self.interval = interval
        self.warn_after = warn_after
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="loop-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            answered = threading.Event()
            try:
                self.loop.call_soon_threadsafe(answered.set)
            except RuntimeError:       # the loop is closed
                return
            started = time.monotonic()
            if answered.wait(self.warn_after):
                continue
            log.warning("the app's event loop hasn't answered for %.0f s; what every thread is doing:\n%s",
                        self.warn_after, thread_stacks())
            while not answered.wait(1.0):
                if self._stop.is_set():
                    return
            log.warning("the event loop answers again after %.1f s", time.monotonic() - started)
