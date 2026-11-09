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
    monkeypatch.setattr(engine_mod.asyncio, "sleep", _fast_sleep)
    store = SettingsStore(tmp_path / "s.json")
    store.update({"accepted_terms": True, "soulseek_username": "u", "soulseek_password": "p",
                  "download_dir": str(tmp_path / "out")})
    store.settings.search_spacing = 0        # the fake clock of real time would slow every test down
    store.settings.search_max_per_5min = 10_000
    store.settings.min_free_gb = 0           # the test machine's disk is none of our business
    db = Database(tmp_path / "db.sqlite")
    incoming = tmp_path / "in"
    incoming.mkdir()
    sc, slsk = FakeSC(), FakeSlsk(str(incoming))
    return Engine(db, store, sc, slsk, poll_tick=0.05, staging_dir=str(tmp_path / "staging")), db, sc, slsk, tmp_path


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
            info.duration = 750
        return info

    sc.track = track
    cid = db.add_channel("https://soundcloud.com/lbl", "Label", False, backlog=3)
    asyncio.run(eng.check_channel(cid))
    got = {t["sc_id"]: (t["state"], t["last_error"]) for t in db.tracks()}
    assert got == {"10": ("skipped", "Looks like a mix"), "11": ("skipped", "Longer than 12 minutes (12:30)"),
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


# --- Roadmap step 1: staging folder, publish only when everything checks out ------------------

def _files(root):
    out = []
    for d, _, names in os.walk(root):
        out += [os.path.relpath(os.path.join(d, n), root) for n in names]
    return sorted(out)


def _fresh_track(eng, db, sc):
    sc.tracks = [TrackStub("9", "https://soundcloud.com/lbl/fresh", "Fresh Artist - Brand New")]
    cid = db.add_channel("https://soundcloud.com/lbl", "Label", False, backlog=1)
    asyncio.run(eng.check_channel(cid))
    return db.tracks()[0]


def test_aborted_download_leaves_nothing_in_music_folder(setup):
    eng, db, sc, slsk, tmp = setup
    t = _fresh_track(eng, db, sc)
    slsk.incoming_dir = slsk.incoming

    def broken(tr):     # the peer sends half the file, then gives up
        with open(tr.path, "wb") as f:
            f.write(b"x" * 5)
        return {"state": "FAILED", "bytes": 5, "size": 10, "local_path": tr.path,
                "place_in_queue": None, "fail_reason": "peer went away"}
    slsk.transfer_info = broken

    db.update_track(t["id"], state="downloading")
    asyncio.run(eng._download(db.track(t["id"]), [Candidate("peer", "@@a\\Fresh Artist - Brand New.flac")]))
    assert not (tmp / "out").exists() or _files(tmp / "out") == []
    assert db.track(t["id"])["state"] == "waiting"
    # The half file is still in incoming (aioslsk/Nicotine+ may keep it); the next start removes it.
    assert _files(tmp / "in") == ["Fresh Artist - Brand New.flac"]
    eng._tidy_incoming()
    assert _files(tmp / "in") == []


def test_finished_download_goes_through_staging(setup):
    eng, db, sc, slsk, tmp = setup
    t = _fresh_track(eng, db, sc)
    seen_in_staging = []
    eng.checks.append(lambda track, path: seen_in_staging.append(path) or None)
    db.update_track(t["id"], state="downloading")
    asyncio.run(eng._download(db.track(t["id"]), [Candidate("peer", "@@a\\Fresh Artist - Brand New.flac")]))
    assert seen_in_staging and seen_in_staging[0].startswith(str(tmp / "staging"))
    assert _files(tmp / "out") == [os.path.join("Label", "Fresh Artist - Brand New.flac")]
    assert _files(tmp / "staging") == [] and _files(tmp / "in") == []


def test_rejected_file_never_reaches_music_folder(setup):
    eng, db, sc, slsk, tmp = setup
    t = _fresh_track(eng, db, sc)
    eng.checks.append(lambda track, path: "not really FLAC")
    db.update_track(t["id"], state="downloading")
    asyncio.run(eng._download(db.track(t["id"]), [Candidate("peer", "@@a\\Fresh Artist - Brand New.flac")]))
    assert not (tmp / "out").exists() or _files(tmp / "out") == []
    assert _files(tmp / "staging") == []
    t = db.track(t["id"])
    assert t["state"] == "waiting" and "not really FLAC" in t["last_error"]


def test_publish_to_other_disk_appears_in_one_go(tmp_path, monkeypatch):
    import errno
    import shutil
    src_dir, dest_dir = tmp_path / "staging", tmp_path / "music"
    src_dir.mkdir()
    dest_dir.mkdir()
    src = src_dir / "Artist - Track.flac"
    src.write_bytes(b"a" * 1000)
    dest = dest_dir / "Artist - Track.flac"

    def no_rename(a, b):    # pretend music lives on another disk
        raise OSError(errno.EXDEV, "cross-device link")
    monkeypatch.setattr(engine_mod.os, "rename", no_rename)

    real_copy = shutil.copy2
    during = []

    def watching_copy(a, b):
        real_copy(a, b)
        during.append(sorted(os.listdir(dest_dir)))   # what a watch folder could see mid-way
    monkeypatch.setattr(engine_mod.shutil, "copy2", watching_copy)

    engine_mod.publish_file(str(src), str(dest))
    assert during == [[".Artist - Track.flac.seekdrop-part"]]   # never the real name while copying
    assert sorted(os.listdir(dest_dir)) == ["Artist - Track.flac"]
    assert dest.read_bytes() == b"a" * 1000 and not src.exists()


def test_start_removes_leftovers(setup):
    eng, db, sc, slsk, tmp = setup
    (tmp / "staging" / "12").mkdir(parents=True)
    (tmp / "staging" / "12" / "half.flac").write_bytes(b"x")
    label = tmp / "out" / "Label"
    label.mkdir(parents=True)
    (label / ".Artist - Track.flac.seekdrop-part").write_bytes(b"x")
    (label / "Artist - Kept.flac").write_bytes(b"x")

    async def scenario():
        await eng.start()
        await eng.stop()
    asyncio.run(scenario())
    assert _files(tmp / "staging") == []
    assert _files(tmp / "out") == [os.path.join("Label", "Artist - Kept.flac")]


# --- Roadmap step 2: quarantine and blocklist ------------------------------------------------

def test_rejected_file_goes_to_quarantine_and_is_blocked(setup):
    eng, db, sc, slsk, tmp = setup
    t = _fresh_track(eng, db, sc)
    eng.quarantine_dir = str(tmp / "quarantine")
    eng.checks.append(lambda track, path: "Not really FLAC (it's MP3)")
    bad = Candidate("peer", "@@a\\Fresh Artist - Brand New.flac")
    db.update_track(t["id"], state="downloading")
    asyncio.run(eng._download(db.track(t["id"]), [bad]))

    rej = db.quarantined()
    assert len(rej) == 1 and rej[0]["reason"] == "Not really FLAC (it's MP3)"
    assert os.path.exists(rej[0]["path"]) and rej[0]["path"].startswith(str(tmp / "quarantine"))
    assert not (tmp / "out").exists() or _files(tmp / "out") == []
    assert db.blocked(t["id"]) == {("peer", "@@a\\Fresh Artist - Brand New.flac")}

    # The next search never offers the same peer + file again; another peer is fine.
    eng.checks.clear()
    good = Candidate("other", "@@b\\Fresh Artist\\Fresh Artist - Brand New.flac", size=30_000_000,
                     duration=301, has_free_slots=True)

    async def search(query, wait=0):
        blocked_again = Candidate("peer", "@@a\\Fresh Artist - Brand New.flac", size=30_000_000,
                                  duration=301, has_free_slots=True)
        return [blocked_again, good]
    slsk.search = search

    async def again():
        await eng._search_track(db.track(t["id"]))
        await eng.active[t["id"]]["task"]
    asyncio.run(again())
    t2 = db.track(t["id"])
    assert t2["state"] == "done" and t2["peer"] == "other"


def test_approve_and_delete_from_quarantine(setup):
    eng, db, sc, slsk, tmp = setup
    t = _fresh_track(eng, db, sc)
    eng.quarantine_dir = str(tmp / "quarantine")
    eng.checks.append(lambda track, path: "30 s of silence at the end")
    db.update_track(t["id"], state="downloading")
    asyncio.run(eng._download(db.track(t["id"]), [Candidate("peer", "@@a\\Fresh Artist - Brand New.flac")]))
    rid = db.quarantined()[0]["id"]

    path = eng.approve_reject(rid)
    assert path and path.endswith(os.path.join("Label", "Fresh Artist - Brand New.flac")) and os.path.exists(path)
    assert db.track(t["id"])["state"] == "done" and db.quarantined() == []
    assert db.reject(rid)["status"] == "approved"

    # Delete: the file goes, the block stays.
    t3 = db.track(t["id"])
    db.update_track(t3["id"], state="downloading")
    os.makedirs(tmp / "in", exist_ok=True)
    asyncio.run(eng._download(db.track(t["id"]), [Candidate("peer2", "@@c\\Fresh Artist - Brand New.flac")]))
    r2 = db.quarantined()[0]
    eng.delete_reject(r2["id"])
    assert not os.path.exists(r2["path"]) and db.quarantined() == []
    assert ("peer2", "@@c\\Fresh Artist - Brand New.flac") in db.blocked(t["id"])


def test_measured_quality_is_stored_on_the_track(setup):
    eng, db, sc, slsk, tmp = setup
    t = _fresh_track(eng, db, sc)

    def fake_spectrum_check(track, path):
        track.setdefault("_meta", {}).update(cutoff_hz=20300, quality="suspect")
        return None
    eng.checks.append(fake_spectrum_check)
    db.update_track(t["id"], state="downloading")
    asyncio.run(eng._download(db.track(t["id"]), [Candidate("peer", "@@a\\Fresh Artist - Brand New.flac")]))
    t = db.track(t["id"])
    assert t["state"] == "done" and t["cutoff_hz"] == 20300 and t["quality"] == "suspect"


# --- Roadmap step 4: quality profiles and upgrades -------------------------------------------

def _done_mp3(eng, db, sc, tmp):
    t = _fresh_track(eng, db, sc)
    label = tmp / "out" / "Label"
    label.mkdir(parents=True, exist_ok=True)
    mp3 = label / "Fresh Artist - Brand New.mp3"
    mp3.write_bytes(b"old mp3")
    db.update_track(t["id"], state="done", file_path=str(mp3), tier="mp3_320", next_upgrade=time.time() - 1,
                    peer="first", remote_file="@@x\\Fresh Artist - Brand New.mp3")
    return db.track(t["id"]), mp3


def _results(*cands):
    async def search(query, wait=0):
        return list(cands)
    return search


FLAC = Candidate("goodpeer", "@@a\\Fresh Artist\\Fresh Artist - Brand New.flac", size=30_000_000,
                 duration=301, has_free_slots=True)


def _measured(tier):
    def check(track, path):
        track.setdefault("_meta", {}).update(tier=tier, cutoff_hz=22050, quality="genuine")
        return None
    return check


def _run_upgrade(eng, db, tid):
    async def go():
        await eng._upgrade_search(db.track(tid))
        if tid in eng.active:
            await eng.active[tid]["task"]
    asyncio.run(go())


def test_mp3_320_is_replaced_by_flac_and_old_file_goes_to_trash(setup):
    eng, db, sc, slsk, tmp = setup
    eng.store.update({"upgrade_mode": "auto"})
    t, mp3 = _done_mp3(eng, db, sc, tmp)
    assert [r["id"] for r in db.due_upgrades(time.time(), time.time() - 30 * 86400)] == [t["id"]]
    slsk.search = _results(FLAC)
    eng.checks.append(_measured("flac16"))
    _run_upgrade(eng, db, t["id"])

    t = db.track(t["id"])
    assert t["file_path"].endswith("Fresh Artist - Brand New.flac") and os.path.exists(t["file_path"])
    assert t["tier"] == "flac16" and t["next_upgrade"] == 0 and t["state"] == "done"
    assert not mp3.exists()
    trashed = [f for f in _files(eng.trash_dir)]
    assert len(trashed) == 1 and trashed[0].endswith("Fresh Artist - Brand New.mp3")


def test_worse_or_fake_never_replaces(setup):
    eng, db, sc, slsk, tmp = setup
    eng.store.update({"upgrade_mode": "auto"})
    t, mp3 = _done_mp3(eng, db, sc, tmp)

    # Only an MP3 256 around: not better, nothing is even downloaded.
    worse = Candidate("w", "@@w\\Fresh Artist - Brand New.mp3", size=9_000_000, bitrate=256, duration=301)
    slsk.search = _results(worse)
    _run_upgrade(eng, db, t["id"])
    assert db.track(t["id"])["file_path"] == str(mp3) and mp3.read_bytes() == b"old mp3"

    # A "FLAC" that the spectrum check calls fake: quarantined, file untouched.
    db.update_track(t["id"], next_upgrade=time.time() - 1)
    slsk.search = _results(FLAC)
    eng.checks.append(lambda track, path: "Fake lossless: audio stops at 16.4 kHz (MP3 at about 128 kbps)")
    _run_upgrade(eng, db, t["id"])
    assert db.track(t["id"])["file_path"] == str(mp3) and mp3.exists()
    assert ("goodpeer", FLAC.filename) in db.blocked(t["id"])

    # A "FLAC" that measures as MP3 320 (suspect): no better than what we have.
    eng.checks.clear()
    eng.checks.append(_measured("mp3_320"))
    other = Candidate("peer3", "@@c\\Fresh Artist\\Fresh Artist - Brand New.flac", size=30_000_000, duration=301)
    db.update_track(t["id"], next_upgrade=time.time() - 1)
    slsk.search = _results(other)
    _run_upgrade(eng, db, t["id"])
    t2 = db.track(t["id"])
    assert t2["file_path"] == str(mp3) and t2["tier"] == "mp3_320" and mp3.exists()
    assert ("peer3", other.filename) in db.blocked(t["id"])
    assert _files(eng.trash_dir) == []


def test_ask_first_then_replace_or_keep(setup):
    eng, db, sc, slsk, tmp = setup
    assert eng.settings.upgrade_mode == "ask"          # the default
    t, mp3 = _done_mp3(eng, db, sc, tmp)
    slsk.search = _results(FLAC)
    eng.checks.append(_measured("flac16"))
    _run_upgrade(eng, db, t["id"])
    t = db.track(t["id"])
    assert t["upgrade_path"] and os.path.exists(t["upgrade_path"]) and t["upgrade_tier"] == "flac16"
    assert t["file_path"] == str(mp3) and mp3.exists()              # nothing replaced yet

    path = eng.replace_upgrade(t["id"])
    assert path.endswith(".flac") and os.path.exists(path) and not mp3.exists()
    assert db.track(t["id"])["upgrade_path"] == "" and db.track(t["id"])["tier"] == "flac16"

    # Keep: the waiting copy goes, the user's file stays, no more searching.
    db.update_track(t["id"], tier="mp3_320", next_upgrade=time.time() - 1)
    slsk.search = _results(Candidate("peer4", "@@d\\Fresh Artist\\Fresh Artist - Brand New.flac", size=30_000_000, duration=301))
    _run_upgrade(eng, db, t["id"])
    pending = db.track(t["id"])["upgrade_path"]
    assert pending and os.path.exists(pending)
    eng.keep_current(t["id"])
    t3 = db.track(t["id"])
    assert t3["upgrade_path"] == "" and t3["next_upgrade"] == 0 and not os.path.exists(pending)
    assert os.path.exists(t3["file_path"])


def test_upgrades_stop_after_30_days(setup):
    eng, db, sc, slsk, tmp = setup
    t, _ = _done_mp3(eng, db, sc, tmp)
    db.update_track(t["id"], created_at=time.time() - 31 * 86400)
    assert db.due_upgrades(time.time(), time.time() - 30 * 86400) == []


def test_new_download_gets_tier_and_upgrade_date(setup):
    eng, db, sc, slsk, tmp = setup
    t = _fresh_track(eng, db, sc)
    eng.checks.append(_measured("mp3_320"))
    db.update_track(t["id"], state="downloading")
    asyncio.run(eng._download(db.track(t["id"]), [Candidate("peer", "@@a\\Fresh Artist - Brand New.mp3", bitrate=320)]))
    t = db.track(t["id"])
    assert t["state"] == "done" and t["tier"] == "mp3_320" and t["next_upgrade"] > time.time()


# --- Roadmap step 5: "Why not?" ---------------------------------------------------------------

def test_search_attempts_are_kept_with_reasons(setup):
    eng, db, sc, slsk, tmp = setup
    t = _fresh_track(eng, db, sc)
    low = Candidate("lowpeer", "@@a\\Fresh Artist - Brand New.mp3", size=8_000_000, bitrate=192, duration=301)
    wrong = Candidate("w", "@@b\\Fresh Artist - Other Thing.flac", size=30_000_000, duration=301)
    slsk.search = _results(low, wrong)
    for _ in range(4):
        asyncio.run(eng._search_track(db.track(t["id"])))
    t = db.track(t["id"])
    assert t["state"] == "waiting"
    assert t["last_error"] == "2 results, none matched: closest was 192 kbps, under your minimum (MP3 320)"
    attempts = db.searches(t["id"])
    assert len(attempts) == 3                                     # only the last 3 are kept
    a = attempts[0]
    assert a["queries"][0] == {"query": "fresh artist brand new", "results": 2}
    assert [c["username"] for c in a["candidates"]] == ["lowpeer", "w"]
    assert a["candidates"][0]["rejected"].startswith("192 kbps")


def test_no_results_still_gives_a_reason(setup):
    eng, db, sc, slsk, tmp = setup
    t = _fresh_track(eng, db, sc)
    slsk.search = _results()
    asyncio.run(eng._search_track(db.track(t["id"])))
    assert db.track(t["id"])["last_error"] == "No results for 'fresh artist brand new', 'brand new'"


def test_pick_a_file_anyway_is_still_checked(setup):
    eng, db, sc, slsk, tmp = setup
    t = _fresh_track(eng, db, sc)
    db.update_track(t["id"], state="waiting")
    picked = {"username": "lowpeer", "filename": "@@a\\Fresh Artist - Brand New.mp3", "bitrate": 192, "ext": "mp3"}

    # A picked file that fails the checks still ends up in quarantine, not in the music folder.
    eng.checks.append(lambda track, path: "Fake 320 kbps: audio stops at 16.7 kHz (about 128 kbps)")

    async def go():
        assert eng.pick(t["id"], picked)
        await eng.active[t["id"]]["task"]
    asyncio.run(go())
    assert db.quarantined()[0]["peer"] == "lowpeer"
    assert not (tmp / "out").exists() or _files(tmp / "out") == []

    # Without a failing check it is downloaded.
    eng.checks.clear()
    db.update_track(t["id"], state="waiting")
    picked2 = dict(picked, username="other")
    asyncio.run(_pick_and_wait(eng, t["id"], picked2))
    t = db.track(t["id"])
    assert t["state"] == "done" and t["peer"] == "other" and os.path.exists(t["file_path"])


async def _pick_and_wait(eng, tid, cand):
    assert eng.pick(tid, cand)
    await eng.active[tid]["task"]


def test_own_search_term_is_kept_and_used_first(setup):
    eng, db, sc, slsk, tmp = setup
    t = _fresh_track(eng, db, sc)
    db.update_track(t["id"], state="waiting")
    eng.set_query(t["id"], "  fresh   artist alias  brand new ")
    t = db.track(t["id"])
    assert t["custom_query"] == "fresh artist alias brand new" and t["state"] == "wanted"
    slsk.search = _results()
    asyncio.run(eng._search_track(db.track(t["id"])))
    asyncio.run(eng._search_track(db.track(t["id"])))     # next attempt: still first
    attempts = db.searches(t["id"])
    assert all(a["queries"][0]["query"] == "fresh artist alias brand new" for a in attempts)
    eng.set_query(t["id"], "")                             # back to the automatic terms
    assert db.track(t["id"])["custom_query"] == ""


def test_stop_looking(setup):
    eng, db, sc, slsk, tmp = setup
    t = _fresh_track(eng, db, sc)
    db.update_track(t["id"], state="waiting")
    eng.stop_looking(t["id"])
    t = db.track(t["id"])
    assert t["state"] == "skipped" and t["last_error"] == "Stopped by you"


# --- Roadmap step 6: aliases and manual corrections, end to end --------------------------------

def test_alias_is_searched_and_matched(setup):
    eng, db, sc, slsk, tmp = setup
    eng.store.update({"artist_aliases": "Kieran Hebden = Four Tet"})
    sc.tracks = [TrackStub("50", "https://soundcloud.com/lbl/ms", "Kieran Hebden - Morning Side")]
    cid = db.add_channel("https://soundcloud.com/lbl", "Label", False, backlog=1)
    asyncio.run(eng.check_channel(cid))
    t = db.tracks()[0]
    found = Candidate("p", "@@m\\Four Tet\\Four Tet - Morning Side.flac", size=30_000_000, duration=300, has_free_slots=True)
    queries = []

    async def search(q, wait=0):
        queries.append(q)
        return [found] if q.startswith("four tet") else []
    slsk.search = search

    async def go():
        await eng._search_track(db.track(t["id"]))
        await eng.active[t["id"]]["task"]
    asyncio.run(go())
    assert queries[:2] == ["kieran hebden morning side", "four tet morning side"]
    t = db.track(t["id"])
    assert t["state"] == "done" and t["peer"] == "p"


def test_manual_correction_wins(setup):
    eng, db, sc, slsk, tmp = setup
    # Uploaded by a label without the artist in the title: read as the uploader's track.
    sc.tracks = [TrackStub("60", "https://soundcloud.com/lbl/idg", "In Da Game")]
    cid = db.add_channel("https://soundcloud.com/lbl", "Label", False, backlog=1)
    asyncio.run(eng.check_channel(cid))
    t = db.tracks()[0]
    badstar = Candidate("p", "@@m\\Badstar\\Badstar - In Da Game (Dub).flac", size=30_000_000, duration=300, has_free_slots=True)
    slsk.search = _results(badstar)
    asyncio.run(eng._search_track(db.track(t["id"])))
    assert db.track(t["id"])["state"] == "waiting"              # a dub: not the original

    eng.set_fix(t["id"], "Badstar", "In Da Game", "Dub")
    t = db.track(t["id"])
    assert (t["artist"], t["title"], t["version"], t["state"]) == ("Badstar", "In Da Game", "Dub", "wanted")

    async def go():
        await eng._search_track(db.track(t["id"]))
        await eng.active[t["id"]]["task"]
    asyncio.run(go())
    t = db.track(t["id"])
    assert t["state"] == "done" and t["file_path"].endswith("Badstar - In Da Game (Dub).flac")
