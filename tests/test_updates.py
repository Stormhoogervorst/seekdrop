import asyncio

from seeksync import updates
from seeksync.updates import UpdateChecker, is_newer, parse_version


def test_version_compare():
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert is_newer("v0.3.0", "0.2.0")
    assert is_newer("0.2.1", "0.2")
    assert not is_newer("v0.2.0", "0.2.0")
    assert not is_newer("v0.1.9", "0.2.0")
    assert not is_newer("nightly", "0.2.0")


class _Store:
    class settings:
        check_updates = True


def test_check_sets_latest(monkeypatch):
    class Resp:
        status = 200
        async def json(self): return {"tag_name": "v9.0.0", "html_url": "https://github.com/x/y/releases/tag/v9.0.0"}
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    class Sess:
        def __init__(self, **kw): pass
        def get(self, url, timeout=None):
            assert url.endswith("/releases/latest")
            return Resp()
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    monkeypatch.setattr(updates.aiohttp, "ClientSession", Sess)
    c = UpdateChecker(_Store(), repo="x/y")
    asyncio.run(c.check())
    assert c.latest == {"version": "9.0.0", "url": "https://github.com/x/y/releases/tag/v9.0.0", "asset": None}


# --- roadmap-less feature: the "Check now" and "Install" buttons ----------------------------------------

import hashlib
import os
import plistlib
import subprocess
import sys

import pytest

from seeksync import __version__

DMG = {"name": "SeekSync-9.0.0-macos-arm64.dmg", "browser_download_url": "https://github.com/x/y/releases/download/v9.0.0/SeekSync-9.0.0-macos-arm64.dmg",
       "size": 1234, "digest": "sha256:ABCDEF"}


def test_pick_asset():
    a = updates.pick_asset([{"name": "SeekSync-9-windows.zip", "browser_download_url": "u"}, DMG], "darwin")
    assert a == {"name": DMG["name"], "url": DMG["browser_download_url"], "size": 1234, "sha256": "abcdef"}
    assert updates.pick_asset([DMG], "win32") is None
    assert updates.pick_asset([{"name": "notes.txt", "browser_download_url": "u"}], "darwin") is None
    assert updates.pick_asset([], "darwin") is None
    no_digest = dict(DMG, digest=None)
    assert updates.pick_asset([no_digest], "darwin")["sha256"] == ""


class _Fake(UpdateChecker):
    def __init__(self, data=None, error=None):
        super().__init__(_Store(), repo="x/y")
        self.data, self.error = data, error

    async def _fetch(self):
        if self.error:
            raise self.error
        return self.data


def test_check_now_says_what_it_found(monkeypatch):
    monkeypatch.setattr(updates, "pick_asset", lambda assets, platform=None: {"name": "n", "url": "u", "size": 1, "sha256": ""})
    c = _Fake({"tag_name": "v9.0.0", "html_url": "page", "assets": [DMG]})
    r = asyncio.run(c.check_now())
    assert r["status"] == "update" and r["version"] == "9.0.0" and "9.0.0 is available" in r["message"]
    assert c.latest["asset"]["name"] == "n" and c.checked_at

    r = asyncio.run(_Fake({"tag_name": "v" + __version__}).check_now())
    assert r["status"] == "current" and "latest version" in r["message"]

    r = asyncio.run(_Fake(None).check_now())
    assert r["status"] == "current" and "No published release" in r["message"]

    r = asyncio.run(_Fake(error=OSError("down")).check_now())
    assert r["status"] == "error" and "Can't reach GitHub" in r["message"]


def test_a_newer_release_that_is_gone_clears_the_banner():
    c = _Fake({"tag_name": "v9.0.0", "html_url": "p"})
    asyncio.run(c.check_now())
    assert c.latest
    c.data = {"tag_name": "v" + __version__}
    asyncio.run(c.check_now())
    assert c.latest is None


def test_source_run_can_not_install_itself():
    assert updates.bundle_path() is None
    assert "only work in the installed SeekSync app" in updates.install_problem()
    c = _Fake({"tag_name": "v9.0.0"})
    asyncio.run(c.check_now())
    with pytest.raises(RuntimeError):
        c.start_install(lambda: None)


def test_download_is_checked(tmp_path):
    from aiohttp import web
    from aiohttp.test_utils import TestServer

    body = os.urandom(300_000)

    async def scenario():
        app = web.Application()
        async def f(r): return web.Response(body=body)
        async def gone(r): return web.Response(status=404)
        app.router.add_get("/f", f)
        app.router.add_get("/gone", gone)
        async with TestServer(app) as srv:
            base = f"http://127.0.0.1:{srv.port}"
            c = UpdateChecker(_Store())
            good = {"url": base + "/f", "size": len(body), "sha256": hashlib.sha256(body).hexdigest()}
            await c.download(good, tmp_path / "ok.dmg")
            assert (tmp_path / "ok.dmg").read_bytes() == body
            assert c.progress["done"] == len(body)
            for bad, word in ((dict(good, size=len(body) + 1), "incomplete"), (dict(good, sha256="0" * 64), "checksum"),
                              (dict(good, url=base + "/gone"), "404")):
                with pytest.raises(RuntimeError) as e:
                    await c.download(bad, tmp_path / "bad.dmg")
                assert word in str(e.value)
            await c.download(dict(good, sha256=""), tmp_path / "nosum.dmg")      # no checksum from GitHub: size only

    asyncio.run(scenario())


def test_only_github_downloads_are_used(monkeypatch):
    c = UpdateChecker(_Store(), repo="x/y")
    c._check_url("https://github.com/x/y/releases/download/v1/a.dmg")
    for bad in ("https://evil.example/a.dmg", "https://github.com/other/repo/releases/download/v1/a.dmg", "http://github.com/x/y/releases/download/v1/a.dmg"):
        with pytest.raises(RuntimeError):
            c._check_url(bad)


def test_downloaded_app_is_verified(tmp_path):
    app = tmp_path / "SeekSync.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="incomplete"):
        UpdateChecker.verify_app(app, "9.0.0")
    (app / "Contents" / "MacOS" / "SeekSync").write_text("x")
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleShortVersionString": "8.0.0"}))
    with pytest.raises(RuntimeError, match="not 9.0.0"):
        UpdateChecker.verify_app(app, "9.0.0")
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleShortVersionString": "9.0.0"}))
    UpdateChecker.verify_app(app, "9.0.0")


def _swap(tmp_path, *, with_new=True, old_backups=0):
    """Run the swap script on fake apps. Returns (target, backup dir, file the fake `open` wrote)."""
    target, new, backup = tmp_path / "SeekSync.app", tmp_path / ".stage" / "SeekSync.app", tmp_path / "prev"
    target.mkdir()
    (target / "v").write_text("old")
    if with_new:
        new.mkdir(parents=True)
        (new / "v").write_text("new")
    backup.mkdir()
    for i in range(old_backups):
        (backup / f"SeekSync-2020010{i + 1}-000000.app").mkdir()
        os.utime(backup / f"SeekSync-2020010{i + 1}-000000.app", (1_000_000 + i, 1_000_000 + i))
    opened = tmp_path / "opened.txt"
    fake_open = tmp_path / "fakeopen.sh"
    fake_open.write_text(f'#!/bin/sh\necho "$1" >> "{opened}"\n')
    fake_open.chmod(0o755)
    script = tmp_path / "swap.sh"
    script.write_text(updates.SWAP_SCRIPT)
    done = subprocess.Popen([sys.executable, "-c", "pass"])
    done.wait()
    r = subprocess.run(["/bin/sh", str(script), str(done.pid), str(new), str(target), str(backup)],
                       env={**os.environ, "OPEN_CMD": str(fake_open)}, timeout=30)
    return target, backup, opened, r.returncode


@pytest.mark.skipif(sys.platform == "win32", reason="shell script")
def test_swap_replaces_the_app_keeps_a_backup_and_reopens(tmp_path):
    target, backup, opened, code = _swap(tmp_path, old_backups=3)
    assert code == 0
    assert (target / "v").read_text() == "new"
    backups = sorted(p.name for p in backup.iterdir())
    assert len(backups) == updates.KEEP_BACKUPS                      # the newest ones stay, older ones go
    assert any((backup / b / "v").exists() and (backup / b / "v").read_text() == "old" for b in backups)
    assert opened.read_text().strip() == str(target)


@pytest.mark.skipif(sys.platform == "win32", reason="shell script")
def test_swap_puts_the_old_app_back_when_the_new_one_is_missing(tmp_path):
    target, backup, opened, code = _swap(tmp_path, with_new=False)
    assert code == 1
    assert (target / "v").read_text() == "old"
    assert opened.read_text().strip() == str(target)


# --- the routes -------------------------------------------------------------------------------------

def test_update_routes(setup):
    from aiohttp.test_utils import TestClient, TestServer
    from seeksync.server import Api

    eng, db, _sc, slsk, tmp = setup
    up = _Fake({"tag_name": "v9.0.0", "html_url": "page", "assets": [DMG]})
    quits = []
    api = Api(eng, db, token="t", updates=up, quit_app=lambda: quits.append(1))
    h = {"X-Token": "t"}

    async def scenario():
        async with TestClient(TestServer(api.app())) as c:
            r = await (await c.post("/api/update/check", headers=h)).json()
            assert r["status"] == "update" and "9.0.0" in r["message"]
            state = await (await c.get("/api/state", headers=h)).json()
            assert state["update"]["version"] == "9.0.0"
            assert state["updating"]["can_install"] is False and "Mac" in state["updating"]["problem"]
            bad = await c.post("/api/update/install", headers=h)
            assert bad.status == 400 and "Mac" in (await bad.json())["error"]
        assert quits == []                                           # nothing quits when nothing was installed

    asyncio.run(scenario())

from test_engine import setup  # noqa: E402,F401  (fixture)


# --- installing on Windows ----------------------------------------------------------------------------------------------

SETUP = {"name": "SeekSync-9.0.0-windows-setup.exe",
         "browser_download_url": "https://github.com/x/y/releases/download/v9.0.0/SeekSync-9.0.0-windows-setup.exe",
         "size": 99, "digest": "sha256:ABCDEF"}


def test_pick_asset_for_windows():
    a = updates.pick_asset([DMG, {"name": "notes.txt", "browser_download_url": "u"}, SETUP], "win32")
    assert a == {"name": SETUP["name"], "url": SETUP["browser_download_url"], "size": 99, "sha256": "abcdef"}
    assert updates.pick_asset([DMG], "win32") is None
    assert updates.pick_asset([SETUP], "darwin") is None             # the Mac never picks the Windows installer
    assert updates.pick_asset([SETUP], "linux") is None


@pytest.fixture
def windows_app(monkeypatch, tmp_path):
    """This process pretends to be the installed SeekSync.exe on Windows."""
    app = tmp_path / "Programs" / "SeekSync"
    app.mkdir(parents=True)
    exe = app / "SeekSync.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    return exe


def test_windows_copy_that_is_installed_can_update(windows_app):
    assert updates.install_problem() == ""


def test_windows_source_run_can_not_update(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert "only work in the installed SeekSync app" in updates.install_problem()


def test_windows_folder_without_write_access_can_not_update(windows_app, monkeypatch):
    monkeypatch.setattr(updates.os, "access", lambda p, mode: False)
    assert "can't change" in updates.install_problem()


def test_windows_install_downloads_checks_and_hands_over_to_a_script(windows_app, monkeypatch):
    from aiohttp import web
    from aiohttp.test_utils import TestServer

    body = b"MZ" + os.urandom(50_000)
    started = []
    monkeypatch.setenv("SEEKSYNC_RELEASE_API", "http://127.0.0.1:1/x")          # allows a download from this computer

    class FakeProc:
        def __init__(self, args, **kw):
            # read the files now: a later install attempt clears the update folder
            started.append((args, kw, open(args[0], "rb").read().decode(), open(args[2], "rb").read()))
    monkeypatch.setattr(updates.subprocess, "Popen", FakeProc)

    async def scenario():
        app = web.Application()
        async def f(r): return web.Response(body=body)
        app.router.add_get("/setup.exe", f)
        async with TestServer(app) as srv:
            c = UpdateChecker(_Store(), repo="x/y")
            asset = {"name": SETUP["name"], "url": f"http://127.0.0.1:{srv.port}/setup.exe", "size": len(body),
                     "sha256": hashlib.sha256(body).hexdigest()}
            await c.install({"version": "9.0.0", "asset": asset})
            for bad, word in ((dict(asset, sha256=""), "no checksum"), (dict(asset, name="SeekSync-8.0.0-windows-setup.exe"), "not version"),
                              (dict(asset, sha256="0" * 64), "checksum")):
                with pytest.raises(RuntimeError) as e:
                    await c.install({"version": "9.0.0", "asset": bad})
                assert word in str(e.value)
            assert len(started) == 1                                              # a refused download starts nothing

    asyncio.run(scenario())
    args, kw, text, saved = started[0]
    script, pid, setup, exe = args
    assert pid == str(os.getpid()) and exe == str(windows_app)
    assert saved == body and setup.endswith("SeekSync-9.0.0-windows-setup.exe")
    assert text.startswith("@echo off") and "\r\n" in text and text.count("\n") == text.count("\r\n")
    assert "/VERYSILENT" in text and "/NORESTART" in text and 'start "" "%APP%"' in text
    assert kw["creationflags"] & 0x08000000                                       # no console window


def test_windows_download_that_is_not_a_program_is_refused(windows_app, monkeypatch):
    from aiohttp import web
    from aiohttp.test_utils import TestServer

    body = b"<html>not an installer</html>"
    monkeypatch.setenv("SEEKSYNC_RELEASE_API", "http://127.0.0.1:1/x")
    monkeypatch.setattr(updates.subprocess, "Popen", lambda *a, **k: pytest.fail("must not start"))

    async def scenario():
        app = web.Application()
        async def f(r): return web.Response(body=body)
        app.router.add_get("/s.exe", f)
        async with TestServer(app) as srv:
            asset = {"name": SETUP["name"], "url": f"http://127.0.0.1:{srv.port}/s.exe", "size": len(body),
                     "sha256": hashlib.sha256(body).hexdigest()}
            with pytest.raises(RuntimeError, match="not a Windows program"):
                await UpdateChecker(_Store(), repo="x/y").install({"version": "9.0.0", "asset": asset})

    asyncio.run(scenario())
