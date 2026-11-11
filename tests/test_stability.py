"""Weak spots found in the 0.6.4 review: things that could stop a background job, lose a file,
quarantine a good download or keep the app from starting."""
import asyncio
import json
import logging
import os
import sqlite3
import time

import pytest

from seeksync import checks, config, fsutil, library, matching
from seeksync import rekordbox as rb
from seeksync.app import open_database
from seeksync.config import Settings, SettingsStore, migrate_legacy_data
from seeksync.db import Database
from seeksync.matching import Candidate, MatchPrefs
from seeksync.server import Api
from seeksync.soundcloud import TrackStub
from seeksync.titles import parse_title

from test_engine import FakeTransfer, setup  # noqa: F401  (the fixture)


def _wanted(eng, db, sc, title="Fresh Artist - Brand New"):
    sc.tracks.insert(0, TrackStub("9", "https://soundcloud.com/lbl/z", title))
    cid = db.add_channel("https://soundcloud.com/lbl", "Label", False, backlog=1)
    asyncio.run(eng.check_channel(cid))
    return next(t for t in db.tracks() if t["sc_id"] == "9")


# --- the engine -------------------------------------------------------------------------------

def test_a_track_skipped_while_another_was_searched_is_not_searched(setup):
    eng, db, sc, slsk, tmp = setup
    t = _wanted(eng, db, sc)
    stale = dict(t)                         # what the search loop read a moment ago
    eng.skip(t["id"])
    asyncio.run(eng._search_track(stale))
    assert db.track(t["id"])["state"] == "skipped"
    assert slsk.searches == []


def test_a_track_whose_channel_was_removed_is_not_searched(setup):
    eng, db, sc, slsk, tmp = setup
    t = _wanted(eng, db, sc)
    eng.remove_channel(t["channel_id"])
    asyncio.run(eng._search_track(dict(t)))
    assert slsk.searches == []


def test_skip_leaves_a_finished_download_alone(setup):
    eng, db, sc, slsk, tmp = setup
    t = _wanted(eng, db, sc)
    db.update_track(t["id"], state="done", file_path="/music/x.flac")
    eng.skip(t["id"])                       # the click came just after the download finished
    assert db.track(t["id"])["state"] == "done"
    eng.skip(987654)                        # a track that no longer exists


def test_a_peer_that_cannot_be_asked_does_not_end_the_attempt(setup):
    eng, db, sc, slsk, tmp = setup
    t = _wanted(eng, db, sc)
    calls = []

    async def download(user, filename):
        calls.append(user)
        if user == "broken":
            raise RuntimeError("peer refused")
        return FakeTransfer(os.path.join(slsk.incoming, filename.split("\\")[-1]))
    slsk.download = download

    async def scenario():
        db.update_track(t["id"], state="downloading")
        eng.active[t["id"]] = {"task": None, "transfer": None, "candidate": None}
        await eng._download(db.track(t["id"]), [Candidate("broken", "a\\Fresh Artist - Brand New.flac"),
                                                Candidate("fine", "b\\Fresh Artist - Brand New.flac")])
    asyncio.run(scenario())
    assert calls == ["broken", "fine"]
    assert db.track(t["id"])["state"] == "done"


def test_the_old_file_comes_back_when_a_better_copy_cannot_be_placed(setup, monkeypatch):
    eng, db, sc, slsk, tmp = setup
    t = _wanted(eng, db, sc)
    old = tmp / "out" / "Label" / "old.mp3"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_bytes(b"old")
    new = tmp / "better.flac"
    new.write_bytes(b"new")
    db.update_track(t["id"], state="done", file_path=str(old), tier="mp3_320")

    def full_disk(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(eng, "_finalize", full_disk)
    with pytest.raises(OSError):
        eng._replace(db.track(t["id"]), str(new), Candidate("peer", "x.flac"), {}, "flac16")
    assert old.read_bytes() == b"old"                       # back where it was
    assert db.track(t["id"])["file_path"] == str(old)


def test_downloads_pause_while_the_music_folder_is_unreachable(setup):
    eng, db, sc, slsk, tmp = setup
    blocker = tmp / "not-a-folder"
    blocker.write_text("x")
    eng.settings.download_dir = str(blocker / "Music")      # can't be made: its parent is a file
    assert "Can't reach your music folder" in eng._check_disk()
    assert eng.activity[0]["level"] == "warn"
    eng.settings.download_dir = str(tmp / "out")
    assert eng._check_disk() == ""
    assert "continue" in eng.activity[0]["msg"]


def test_start_survives_a_folder_it_cannot_read(setup, monkeypatch):
    eng, db, sc, slsk, tmp = setup
    (tmp / "out").mkdir(exist_ok=True)
    real = os.listdir

    def listdir(path):
        if str(path) == str(tmp / "out"):
            raise PermissionError(1, "Operation not permitted")
        return real(path)
    monkeypatch.setattr(os, "listdir", listdir)
    eng._tidy_files()                                       # used to raise, and the app didn't start


def test_background_jobs_are_kept_and_their_errors_logged(setup, caplog):
    eng, db, sc, slsk, tmp = setup

    async def boom():
        raise RuntimeError("nope")

    async def scenario():
        task = eng.spawn(boom(), "test-job")
        assert task in eng._spawned
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert task not in eng._spawned
    with caplog.at_level(logging.ERROR):
        asyncio.run(scenario())
    assert any("test-job" in r.getMessage() for r in caplog.records)


def test_the_watchdog_survives_a_failed_connection(setup):
    eng, db, sc, slsk, tmp = setup

    async def start(settings):
        raise OSError("network is down")
    slsk.start = start
    asyncio.run(eng._connect_safely())
    assert "Couldn't connect" in eng.activity[0]["msg"]


def test_covers_button_is_never_stuck(setup, monkeypatch):
    eng, db, sc, slsk, tmp = setup

    def broken():
        raise sqlite3.OperationalError("disk I/O error")
    monkeypatch.setattr(db, "tracks_for_rekordbox", broken)
    with pytest.raises(sqlite3.OperationalError):
        eng.fill_missing_covers()
    assert eng.covers_state["running"] is False


# --- settings ---------------------------------------------------------------------------------

def test_an_emptied_number_box_keeps_the_old_value(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    store.update({"give_up_days": 20})
    _, changed = store.update({"give_up_days": "", "max_parallel_downloads": "abc", "search_spacing": None,
                               "check_interval_minutes": "90"})
    assert changed == {"check_interval_minutes"}
    assert store.settings.give_up_days == 20 and store.settings.check_interval_minutes == 90


def test_ports_and_margins_stay_usable(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    store.update({"listen_port": 99999, "nicotine_port": 5, "check_length_margin": -4, "check_silence_seconds": -1})
    s = store.settings
    assert (s.listen_port, s.nicotine_port, s.check_length_margin, s.check_silence_seconds) == (65534, 1024, 0, 0)


def test_wrong_kinds_of_values_in_the_settings_file(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"soulseek_username": "dj", "library_dirs": None, "give_up_days": "soon",
                                "max_parallel_downloads": "4", "tag_files": "yes", "quality_profile": "best",
                                "share_dirs": ["/a", 3, None], "soulseek_password": 12345}))
    s = SettingsStore(path).settings
    d = Settings()
    assert s.soulseek_username == "dj"                      # the good fields are kept
    assert s.library_dirs == [] and s.give_up_days == d.give_up_days and s.max_parallel_downloads == 4
    assert s.tag_files is d.tag_files and s.quality_profile == d.quality_profile
    assert s.share_dirs == ["/a", "3"] and s.soulseek_password == ""


def test_an_unreadable_settings_file_is_kept(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"soulseek_username": "dj", ')         # cut off
    store = SettingsStore(path)
    assert store.settings.soulseek_username == ""
    store.update({"give_up_days": 9})                       # overwrites settings.json
    assert (tmp_path / "settings.json.unreadable").read_text() == '{"soulseek_username": "dj", '


def test_windows_log_folder_does_not_stop_the_takeover(tmp_path):
    """On Windows the logs live inside the data folder and exist before the old data is looked for."""
    old = tmp_path / "SeekDrop"
    (old / "Logs").mkdir(parents=True)
    (old / "Logs" / "seekdrop.log").write_text("old log")
    (old / "settings.json").write_text('{"accepted_terms": true}')
    (old / "seekdrop.db").write_text("x")
    new = tmp_path / "SeekSync"
    (new / "Logs").mkdir(parents=True)
    (new / "Logs" / "seeksync.log").write_text("new log")
    (new / "crash.log").write_text("")
    assert migrate_legacy_data(new, [old]) == old
    assert (new / "settings.json").exists() and (new / "seeksync.db").read_text() == "x"
    assert (new / "Logs" / "seeksync.log").read_text() == "new log"
    assert not old.exists()
    # A SeekSync folder with real data is still never touched.
    other = tmp_path / "Cratewatch"
    other.mkdir()
    (other / "settings.json").write_text("{}")
    assert migrate_legacy_data(new, [other]) is None and other.exists()


# --- the database -----------------------------------------------------------------------------

def test_a_damaged_database_is_set_aside(tmp_path):
    path = tmp_path / "seeksync.db"
    path.write_bytes(b"this is not a database at all" * 200)
    db = open_database(path)
    assert db.channels() == []
    kept = [p for p in tmp_path.iterdir() if ".damaged-" in p.name]
    assert len(kept) == 1 and kept[0].read_bytes().startswith(b"this is not")


def test_a_healthy_database_is_opened_as_it_is(tmp_path):
    path = tmp_path / "seeksync.db"
    Database(path).add_channel("https://soundcloud.com/a", "A", False, 0)
    assert [c["name"] for c in open_database(path).channels()] == ["A"]
    assert not [p for p in tmp_path.iterdir() if ".damaged-" in p.name]


def test_very_long_lists_of_ids(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    cid = db.add_channel("https://soundcloud.com/a", "A", False, 0)
    for i in range(1200):
        db.add_track(channel_id=cid, sc_id=str(i))
    ids = [str(i) for i in range(40_000)]
    assert len(db.tracks_by_sc_ids(ids)) == 1200 and len(db.known_sc_ids(ids)) == 1200
    assert db.peer_stats([f"user{i}" for i in range(40_000)]) == {}


# --- the music folders ------------------------------------------------------------------------

def test_a_folder_that_cannot_be_listed_keeps_its_files(tmp_path, monkeypatch):
    db = Database(tmp_path / "db.sqlite")
    root = tmp_path / "music"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir()
    (root / "a" / "Artist - One.mp3").write_bytes(b"x")
    (root / "b" / "Artist - Two.mp3").write_bytes(b"x")
    assert library.scan(db, [str(root)]).files == 2

    real = os.scandir

    def scandir(path):
        if str(path) == str(root / "b"):
            raise PermissionError(13, "Permission denied")
        return real(path)
    monkeypatch.setattr(os, "scandir", scandir)
    res = library.scan(db, [str(root)])
    assert res.removed == 0 and res.files == 2              # not "gone": tracks aren't fetched again
    monkeypatch.setattr(os, "scandir", real)
    os.remove(root / "b" / "Artist - Two.mp3")
    assert library.scan(db, [str(root)]).removed == 1       # really gone is still noticed


# --- matching ---------------------------------------------------------------------------------

def test_one_odd_search_result_does_not_sink_the_search():
    want = parse_title("Fresh Artist - Brand New")
    good = Candidate("peer", "x\\Fresh Artist - Brand New.flac", size=30_000_000, has_free_slots=True)
    odd = Candidate(None, "x\\Fresh Artist - Brand New.flac", size=30_000_000)       # type: ignore[arg-type]
    ranked = matching.rank(want, 300, [odd, good], MatchPrefs())
    assert ranked == [good]
    assert odd.rejected


# --- file checks ------------------------------------------------------------------------------

def test_missing_ffmpeg_never_sends_a_file_to_quarantine(tmp_path):
    """ffmpeg was there when the app started and is gone now (an update moved it)."""
    gone = checks.Tools(ffmpeg=str(tmp_path / "ffmpeg"), ffprobe=str(tmp_path / "ffprobe"))
    checker = checks.FileChecker(lambda: Settings(), gone)
    f = tmp_path / "a.flac"
    f.write_bytes(b"x")
    real_find = checks.Tools.find
    checks.Tools.find = classmethod(lambda cls: checks.Tools())          # not found anywhere either
    try:
        assert checker({"duration": 300}, str(f)) is None
    finally:
        checks.Tools.find = real_find
    assert not checker.tools.available


def test_a_broken_spectrum_measurement_is_not_a_bad_file(tmp_path, monkeypatch):
    a = checks.Analysis(container="flac", codec="flac", header_duration=300, decoded_duration=300, decoded=True)
    monkeypatch.setattr(checks, "analyse", lambda *x, **k: a)

    def broken(*x, **k):
        raise ValueError("buffer size must be a multiple of element size")
    monkeypatch.setattr(checks, "measure_cutoff", broken)
    checker = checks.FileChecker(lambda: Settings(), checks.Tools("ffmpeg", "ffprobe"))
    track = {"duration": 300}
    assert checker(track, str(tmp_path / "a.flac")) is None
    assert track["_meta"]["tier"] == "flac16" and "quality" not in track["_meta"]


# --- Rekordbox --------------------------------------------------------------------------------

def test_collection_export_with_ids_that_are_not_numbers(tmp_path):
    xml = tmp_path / "rekordbox.xml"
    xml.write_text('<?xml version="1.0" encoding="UTF-8"?><DJ_PLAYLISTS Version="1.0.0"><COLLECTION Entries="2">'
                   '<TRACK TrackID="A-1" Location="file://localhost/Music/One.mp3"/>'
                   '<TRACK TrackID="" Location="file://localhost/Music/Two.mp3"/>'
                   '</COLLECTION></DJ_PLAYLISTS>', "utf-8")
    assert rb.collection_paths(str(xml)) == {"/music/one.mp3", "/music/two.mp3"}


def test_a_file_without_a_collection_is_not_an_empty_rekordbox(tmp_path):
    """An empty set would mean "nothing is in Rekordbox", and files would be replaced without asking."""
    xml = tmp_path / "other.xml"
    xml.write_text("<playlist><track/></playlist>", "utf-8")
    with pytest.raises(ValueError):
        rb.collection_paths(str(xml))


# --- the local API ----------------------------------------------------------------------------

def _call(api, method, path, body=None):
    from aiohttp.test_utils import TestClient, TestServer

    async def run():
        async with TestClient(TestServer(api.app())) as client:
            r = await client.request(method, path, json=body, headers={"X-Token": "t"})
            return r.status, await r.json()
    return asyncio.run(run())


def test_api_answers_with_a_message_instead_of_a_crash(setup):
    eng, db, sc, slsk, tmp = setup
    api = Api(eng, db, token="t")
    status, body = _call(api, "POST", "/api/tracks/abc/skip")
    assert status == 400 and body["error"]
    status, body = _call(api, "GET", "/api/state?channel=x")
    assert status == 400 and body["error"]

    def boom(tid):
        raise RuntimeError("unexpected")
    eng.retry_now = boom
    status, body = _call(api, "POST", "/api/tracks/1/retry")
    assert status == 500 and "unexpected" in body["error"]


def test_saving_settings_with_an_empty_number(setup):
    eng, db, sc, slsk, tmp = setup
    api = Api(eng, db, token="t")
    before = eng.settings.give_up_days
    status, body = _call(api, "PUT", "/api/settings", {"give_up_days": "", "check_length_margin": "12"})
    assert status == 200 and body["changed"] == ["check_length_margin"]
    assert eng.settings.give_up_days == before


# --- the app must keep answering (Windows reports of "not responding") --------------------------

def test_the_screen_is_served_while_the_shared_thread_pool_is_full(setup):
    """Long jobs (file checks, scans) fill asyncio's shared pool; the state for the screen has its own threads."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    eng, db, sc, slsk, tmp = setup
    api = Api(eng, db, token="t")
    release = threading.Event()

    class Req:
        query = {}

    async def scenario():
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        busy = asyncio.ensure_future(asyncio.to_thread(release.wait))      # the only shared thread is taken
        await asyncio.sleep(0.05)
        try:
            resp = await asyncio.wait_for(api.state(Req()), 5)
        finally:
            release.set()
            await busy
        return json.loads(resp.text)
    assert asyncio.run(scenario())["version"]


def test_the_disk_is_not_asked_on_the_event_loop(setup, monkeypatch):
    """A drive that is asleep answers slowly; that may never hold up the loop that runs everything."""
    import threading
    eng, db, sc, slsk, tmp = setup
    api = Api(eng, db, token="t")
    asked_on = []
    real = eng._check_disk
    monkeypatch.setattr(eng, "_check_disk", lambda: asked_on.append(threading.current_thread().name) or real())
    real_path = eng.rekordbox_path
    monkeypatch.setattr(eng, "rekordbox_path", lambda: asked_on.append(threading.current_thread().name) or real_path())

    class Req:
        query = {}

    async def scenario():
        loop_thread = threading.current_thread().name
        task = asyncio.ensure_future(eng._search_loop())
        await api.state(Req())
        for _ in range(50):
            await asyncio.sleep(0.01)
        task.cancel()
        return loop_thread
    loop_thread = asyncio.run(scenario())
    assert len(asked_on) >= 2 and loop_thread not in asked_on


def test_the_window_does_not_wait_for_the_login(setup):
    eng, db, sc, slsk, tmp = setup
    gate = asyncio.Event

    async def scenario():
        hold = gate()

        async def slow_start(settings):
            await hold.wait()                       # a login that takes a minute
        slsk.start = slow_start
        await asyncio.wait_for(eng.start(), 2)      # returns at once: the window can open
        assert eng._connecting
        hold.set()
        await asyncio.gather(*eng._spawned)
        assert not eng._connecting
        await eng.stop()
    asyncio.run(scenario())


def test_share_scans_get_their_own_threads():
    """aioslsk queues one job per shared file; they must not land in the pool the rest of the app uses."""
    from seeksync.soulseek import _SharesPool
    import threading
    pool = _SharesPool()
    release = threading.Event()
    futures = [pool.submit(release.wait) for _ in range(50)]
    t0 = time.time()
    pool.shutdown()                                 # what aioslsk calls when the app closes: must not wait
    assert time.time() - t0 < 1
    release.set()
    assert sum(f.cancelled() for f in futures) >= 40
