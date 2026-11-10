"""Things that made the Windows build freeze or misbehave (0.6.3). They run everywhere: the Windows-only
behaviour is switched on in the test."""
import asyncio
import errno
import logging
import os
import subprocess
import sys
import threading
import time

import pytest

from seeksync import __main__ as entry
from seeksync import checks, diag, fsutil, naming
from seeksync.engine import publish_file


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(fsutil, "IS_WINDOWS", True)
    monkeypatch.setattr(fsutil, "RETRY_DELAYS", (0.01, 0.01, 0.01))
    monkeypatch.setattr(fsutil.time, "sleep", lambda s: None)


def busy_then_ok(times):
    calls = {"n": 0}

    def fn(*a):
        calls["n"] += 1
        if calls["n"] <= times:
            raise PermissionError(13, "used by another process")
        return "done"
    return fn, calls


def test_busy_file_is_tried_again_on_windows(windows):
    fn, calls = busy_then_ok(2)
    assert fsutil.retry(fn) == "done"
    assert calls["n"] == 3


def test_gives_up_after_the_last_try(windows):
    fn, calls = busy_then_ok(99)
    with pytest.raises(PermissionError):
        fsutil.retry(fn)
    assert calls["n"] == 4                      # first try plus three waits


def test_permission_error_is_final_elsewhere(monkeypatch):
    monkeypatch.setattr(fsutil, "IS_WINDOWS", False)
    fn, calls = busy_then_ok(1)
    with pytest.raises(PermissionError):
        fsutil.retry(fn)
    assert calls["n"] == 1                      # a real permission problem, not worth waiting for


def test_other_errors_are_not_retried(windows):
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise FileNotFoundError(errno.ENOENT, "gone")
    with pytest.raises(FileNotFoundError):
        fsutil.retry(fn)
    assert calls["n"] == 1


def test_publish_waits_for_a_file_the_scanner_holds(windows, tmp_path, monkeypatch):
    src, dest = tmp_path / "a.flac", tmp_path / "out.flac"
    src.write_bytes(b"x")
    real, calls = os.rename, {"n": 0}

    def flaky(a, b):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(13, "Access is denied")
        return real(a, b)
    monkeypatch.setattr(os, "rename", flaky)
    publish_file(str(src), str(dest))
    assert dest.read_bytes() == b"x" and not src.exists() and calls["n"] == 3


def test_move_copies_across_disks(monkeypatch, tmp_path):
    src, dest = tmp_path / "a", tmp_path / "b"
    src.write_bytes(b"x")

    def other_disk(a, b):
        raise OSError(errno.EXDEV, "cross-device")
    monkeypatch.setattr(os, "rename", other_disk)
    fsutil.move(str(src), str(dest))
    assert dest.read_bytes() == b"x" and not src.exists()


def test_long_names_are_cut_to_fit_windows():
    folder = "C:\\Users\\someone\\Music\\SeekSync\\" + "Channel " * 10
    base = "Artist - " + "Very Long Title " * 20
    short = naming.fit_name(folder, base, ".flac", limit=250)
    assert len(os.path.join(folder, short + ".flac")) + 5 <= 250
    assert short.startswith("Artist - ") and not short.endswith((" ", "."))
    assert naming.fit_name(folder, "Short", ".flac", limit=250) == "Short"
    assert naming.fit_name(folder, base, ".flac", limit=0) == base      # no limit off Windows


def test_names_windows_cannot_create_are_changed():
    assert naming.render("{title}", {"title": "NUL"}) == ["_NUL"]
    assert naming.render("{channel}/{title}", {"channel": "COM1", "title": "x"}) == ["_COM1", "x"]
    assert naming.render("{title}", {"title": "Console"}) == ["Console"]


def test_ffmpeg_runs_without_window_or_stdin(monkeypatch):
    assert checks._spawn_options()["stdin"] == subprocess.DEVNULL
    monkeypatch.setattr(sys, "platform", "win32")
    assert checks._spawn_options()["creationflags"] == 0x08000000      # CREATE_NO_WINDOW


def test_ffmpeg_is_found_in_the_windows_places(monkeypatch, tmp_path):
    (tmp_path / "ffmpeg.exe").write_bytes(b"")
    (tmp_path / "ffmpeg.exe").chmod(0o755)          # Windows has no execute bit; here the check needs one
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(checks, "_EXTRA_DIRS", (str(tmp_path),))
    monkeypatch.setattr(checks.shutil, "which", lambda n: None)
    assert checks.find_tool("ffmpeg") == str(tmp_path / "ffmpeg.exe")


def test_watchdog_reports_a_frozen_loop(caplog):
    caplog.set_level(logging.WARNING, logger="seeksync.diag")
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    dog = diag.LoopWatchdog(loop, interval=0.05, warn_after=0.2)
    dog.start()
    try:
        loop.call_soon_threadsafe(time.sleep, 0.8)          # the loop is stuck for a while
        deadline = time.time() + 5
        while time.time() < deadline and "answers again" not in caplog.text:
            time.sleep(0.05)
    finally:
        dog.stop()
        loop.call_soon_threadsafe(loop.stop)
        t.join(2)
    assert "hasn't answered" in caplog.text and "answers again" in caplog.text
    assert "time.sleep" in caplog.text or "sleep" in caplog.text      # the stack shows what it was stuck on


def test_quitting_is_forced_when_it_takes_too_long(monkeypatch):
    ended = []
    monkeypatch.setattr(entry.os, "_exit", lambda code: ended.append(code))
    monkeypatch.setattr(entry.logging, "shutdown", lambda: None)
    entry._force_exit_later(0.05)
    deadline = time.time() + 3
    while not ended and time.time() < deadline:
        time.sleep(0.02)
    assert ended == [0]


def test_window_is_fine_off_windows():
    if not sys.platform.startswith("win"):
        assert entry.webview_unavailable() == ""
