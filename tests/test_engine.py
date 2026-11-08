"""End-to-end engine test with fake SoundCloud + fake Soulseek."""
import asyncio
import os
import time

import pytest

from seekdrop import engine as engine_mod
from seekdrop.config import SettingsStore
from seekdrop.db import Database
from seekdrop.engine import Engine
from seekdrop.matching import Candidate
from seekdrop.soundcloud import TrackInfo, TrackStub


class FakeSC:
    def __init__(self):
        self.tracks = [
            TrackStub("3", "https://soundcloud.com/lbl/c", "Old One - Gamma"),
            TrackStub("2", "https://soundcloud.com/lbl/b", "Old Two - Beta"),
            TrackStub("1", "https://soundcloud.com/lbl/a", "Old Three - Alpha"),
        ]

    def latest(self, url, include_reposts=False, limit=25):
        return list(self.tracks)

    def track(self, url):
        stub = next(t for t in self.tracks if t.url == url)
        return TrackInfo(stub.sc_id, url, stub.title, uploader="lbl", duration=300, uploaded_at=time.time())


class FakeTransfer:
    def __init__(self, path):
        self.path = path
        self.polls = 0


class FakeSlsk:
    connected = True
    status = "connected"
    error = ""
    retryable = False

    def __init__(self, incoming):
        self.incoming = incoming
        self.searches = []
        self.forgotten = []

    async def start(self, settings):
        pass

    async def stop(self):
        pass

    async def rescan_shares(self):
        pass

    async def search(self, query, wait=0):
        self.searches.append(query)
        if "fresh" in query:
            return [Candidate("peer", "@@a\\Fresh Artist\\Fresh Artist - Brand New.flac", size=30_000_000,
                              duration=301, has_free_slots=True)]
        return []

    async def download(self, user, filename):
        path = os.path.join(self.incoming, filename.split("\\")[-1])
        return FakeTransfer(path)

    def transfer_info(self, t):
        t.polls += 1
        if t.polls >= 2:
            with open(t.path, "wb") as f:
                f.write(b"x" * 10)
            return {"state": "COMPLETE", "bytes": 10, "size": 10, "local_path": t.path,
                    "place_in_queue": None, "fail_reason": ""}
        return {"state": "DOWNLOADING", "bytes": 5, "size": 10, "local_path": t.path,
                "place_in_queue": None, "fail_reason": ""}

    async def abort(self, t):
        pass

    async def forget(self, t):
        self.forgotten.append(t)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_mod, "SEARCH_SPACING", 0)
    monkeypatch.setattr(engine_mod.asyncio, "sleep", _fast_sleep)
    store = SettingsStore(tmp_path / "s.json")
    store.update({"accepted_terms": True, "soulseek_username": "u", "soulseek_password": "p",
                  "download_dir": str(tmp_path / "out")})
    db = Database(tmp_path / "db.sqlite")
    incoming = tmp_path / "in"
    incoming.mkdir()
    sc, slsk = FakeSC(), FakeSlsk(str(incoming))
    return Engine(db, store, sc, slsk, poll_tick=0.05), db, sc, slsk, tmp_path


_real_sleep = asyncio.sleep


async def _fast_sleep(s, *a, **k):
    await _real_sleep(0)


def test_backlog_then_new_release_downloaded(setup):
    eng, db, sc, slsk, tmp = setup

    async def scenario():
        cid = db.add_channel("https://soundcloud.com/lbl", "Label", False, backlog=1)
        await eng.check_channel(cid)
        states = {t["sc_id"]: t["state"] for t in db.tracks()}
        assert states == {"3": "wanted", "2": "skipped", "1": "skipped"}

        # newest backlog track isn't on Soulseek -> waiting with retry scheduled
        t3 = next(t for t in db.tracks() if t["sc_id"] == "3")
        await eng._search_track(t3)
        t3 = db.track(t3["id"])
        assert t3["state"] == "waiting" and t3["next_attempt"] > time.time() + 3000
        assert slsk.searches == ["old one gamma", "gamma"]

        # a new upload appears and is found + downloaded
        sc.tracks.insert(0, TrackStub("4", "https://soundcloud.com/lbl/d", "Fresh Artist - Brand New [FREE DL]"))
        await eng.check_channel(cid)
        t4 = next(t for t in db.tracks() if t["sc_id"] == "4")
        assert t4["state"] == "wanted" and t4["duration"] == 300
        await eng._search_track(t4)
        await eng.active[t4["id"]]["task"]
        t4 = db.track(t4["id"])
        assert t4["state"] == "done", t4
        assert t4["file_path"].endswith(os.path.join("out", "Label", "Fresh Artist - Brand New.flac"))
        assert os.path.exists(t4["file_path"])
        assert slsk.forgotten

        # user actions
        eng.retry_now(t3["id"])
        assert db.track(t3["id"])["state"] == "wanted"
        eng.skip(t3["id"])
        assert db.track(t3["id"])["state"] == "skipped"

    asyncio.run(scenario())


def test_gives_up_after_limit(setup):
    eng, db, sc, slsk, tmp = setup
    cid = db.add_channel("https://soundcloud.com/lbl", "Label", False, backlog=3)
    asyncio.run(eng.check_channel(cid))
    t = db.tracks()[0]
    db.update_track(t["id"], created_at=time.time() - 40 * 86400)
    eng._schedule_retry(db.track(t["id"]), "nope")
    assert db.track(t["id"])["state"] == "gave_up"


def test_switching_to_nicotine_swaps_service(setup):
    eng, db, sc, slsk, tmp = setup
    made = []

    class Svc(FakeSlsk):
        def __init__(self, mode):
            super().__init__(str(tmp))
            self.mode = mode
            made.append(mode)

    eng.slsk_factory = Svc
    eng.slsk = Svc("builtin")
    eng.store.update({"soulseek_mode": "nicotine", "nicotine_token": "k"})
    asyncio.run(eng.apply_settings({"soulseek_mode", "nicotine_token"}))
    assert eng.slsk.mode == "nicotine" and made == ["builtin", "nicotine"]
    assert eng.settings.configured


def test_mixes_and_long_uploads_skipped(setup):
    eng, db, sc, slsk, tmp = setup
    sc.tracks = [
        TrackStub("10", "https://soundcloud.com/lbl/show", "Label Radio Show 042"),
        TrackStub("11", "https://soundcloud.com/lbl/long", "Artist - Long Journey"),
        TrackStub("12", "https://soundcloud.com/lbl/ok", "Artist - Normal (Extended Mix)"),
    ]
    orig = sc.track

    def track(url):
        info = orig(url)
        if url.endswith("/long"):
            info.duration = 601
        return info

    sc.track = track
    cid = db.add_channel("https://soundcloud.com/lbl", "Label", False, backlog=3)
    asyncio.run(eng.check_channel(cid))
    got = {t["sc_id"]: (t["state"], t["last_error"]) for t in db.tracks()}
    assert got == {"10": ("skipped", "Looks like a mix"), "11": ("skipped", "Longer than 10 minutes"),
                   "12": ("wanted", "")}
    # The user can still fetch a skipped one on purpose.
    tid = next(t["id"] for t in db.tracks() if t["sc_id"] == "11")
    eng.retry_now(tid)
    assert db.track(tid)["state"] == "wanted"


def test_playlist_gets_every_track_in_order(setup):
    eng, db, sc, slsk, tmp = setup
    # A profile already knows track "2" (skipped: older than its backlog) and "1" (user wants it).
    pid = db.add_channel("https://soundcloud.com/lbl", "Label", False, backlog=1)
    asyncio.run(eng.check_channel(pid))
    assert {t["sc_id"]: t["state"] for t in db.tracks()} == {"3": "wanted", "2": "skipped", "1": "skipped"}

    playlist = [
        TrackStub("20", "https://soundcloud.com/other/first", ""),          # flat playlist entries have no title
        TrackStub("2", "https://soundcloud.com/lbl/b", ""),
        TrackStub("21", "https://soundcloud.com/other/show", "Other Radio Show 12"),
        TrackStub("22", "https://soundcloud.com/other/broken", ""),
    ]
    titles = {"https://soundcloud.com/other/first": "Other - First Song", "https://soundcloud.com/lbl/b": "Old Two - Beta",
              "https://soundcloud.com/other/show": "Other Radio Show 12"}

    def track(url):
        if url not in titles:
            raise RuntimeError("SoundCloud hiccup")
        return TrackInfo(url.rsplit("/", 1)[-1], url, titles[url], uploader="other", duration=280)

    sc.latest = lambda url, include_reposts=False, limit=25: list(playlist)
    sc.track = track
    cid = db.add_channel("https://soundcloud.com/other/sets/mine", "Mine", False, 0, kind="playlist")
    asyncio.run(eng.check_channel(cid))

    mine = [(t["sc_id"], t["state"]) for t in sorted(db.tracks(channel_id=cid), key=lambda t: t["id"])]
    # "2" moved over from the profile and is wanted now; the radio show is skipped; "22" isn't stored yet.
    assert sorted(mine) == [("2", "wanted"), ("20", "wanted"), ("21", "skipped")]
    assert db.track(next(t["id"] for t in db.tracks() if t["sc_id"] == "20"))["title"] == "First Song"

    # Next check: the hiccup is gone, the missing track gets added; a track the user skips stays skipped.
    titles["https://soundcloud.com/other/broken"] = "Other - Third"
    eng.skip(next(t["id"] for t in db.tracks() if t["sc_id"] == "20"))
    asyncio.run(eng.check_channel(cid))
    got = {t["sc_id"]: t["state"] for t in db.tracks(channel_id=cid)}
    assert got == {"2": "wanted", "20": "skipped", "21": "skipped", "22": "wanted"}


def test_old_database_gets_kind_column(tmp_path):
    import sqlite3
    path = tmp_path / "old.sqlite"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE channels (id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE, name TEXT NOT NULL DEFAULT '', "
                "avatar TEXT NOT NULL DEFAULT '', include_reposts INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1, "
                "initialized INTEGER NOT NULL DEFAULT 0, backlog INTEGER NOT NULL DEFAULT 0, last_checked REAL, "
                "last_error TEXT NOT NULL DEFAULT '', added_at REAL NOT NULL)")
    con.execute("INSERT INTO channels(url, name, added_at) VALUES ('https://soundcloud.com/x', 'X', 0)")
    con.commit()
    con.close()
    db = Database(path)
    assert db.channels()[0]["kind"] == "profile"


def test_leftover_transfers_are_tidied_up_after_restart(setup):
    eng, db, sc, slsk, tmp = setup
    cid = db.add_channel("https://soundcloud.com/lbl", "Label", False, backlog=3)
    asyncio.run(eng.check_channel(cid))
    finished, queued, gone = sorted(db.tracks(), key=lambda t: t["id"])
    for t, f in ((finished, "Old Three - Alpha.flac"), (queued, "Old Two - Beta.mp3"), (gone, "x.mp3")):
        db.update_track(t["id"], state="downloading", peer="p", remote_file="@@a\\" + f)
    landed = tmp / "in" / "Old Three - Alpha.flac"
    landed.write_bytes(b"x")

    cancelled = []

    async def lookup(user, path):
        if path.endswith("Alpha.flac"):
            return {"state": "COMPLETE", "local_path": str(landed)}
        if path.endswith("Beta.mp3"):
            return {"state": "QUEUED", "local_path": None}
        return None

    async def cancel(user, path):
        cancelled.append(path)

    slsk.lookup, slsk.cancel = lookup, cancel

    async def scenario():
        await eng.start()          # what a restart does
        await eng._recover_stale()
        await eng.stop()

    asyncio.run(scenario())
    got = {t["id"]: t["state"] for t in db.tracks()}
    assert got[finished["id"]] == "done" and os.path.exists(db.track(finished["id"])["file_path"])
    assert got[queued["id"]] == "wanted" and got[gone["id"]] == "wanted"
    assert sorted(cancelled) == ["@@a\\Old Three - Alpha.flac", "@@a\\Old Two - Beta.mp3"]
    assert eng._stale == []


def test_outdated_plugin_is_replaced(tmp_path, monkeypatch):
    from seekdrop import nicotine
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    dest = nicotine.install_plugin(47820, "key")
    assert not nicotine.update_plugin_if_outdated()            # same version: nothing to do
    (dest / "PLUGININFO").write_text('Name = "x"\nVersion = "0.0.1"\n')
    assert nicotine.update_plugin_if_outdated()
    assert nicotine._plugin_version(dest) == nicotine._plugin_version(nicotine.PLUGIN_SRC)
    assert '"token": "key"' in (dest / "bridge.json").read_text()
