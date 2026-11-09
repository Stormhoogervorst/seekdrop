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
    assert "only work in the SeekSync app" in updates.install_problem()
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
