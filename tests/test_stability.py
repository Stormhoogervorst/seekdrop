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


# --- follow-ups from the review: things that didn't work as you'd expect ------------------------

def test_a_failed_start_says_why_and_where_the_log_is():
    from seeksync.__main__ import start_failed_page
    page = start_failed_page(PermissionError(13, "Permission denied"), "C:\\Users\\dj\\<log>.log")
    assert "Permission denied" in page and "&lt;log&gt;" in page and "<log>" not in page


def test_show_log_opens_the_log_file(setup, monkeypatch):
    from seeksync import server
    eng, db, sc, slsk, tmp = setup
    opened = []
    monkeypatch.setattr(server, "open_in_file_manager", opened.append)
    status, _ = _call(Api(eng, db, token="t"), "POST", "/api/open", {"log": True})
    assert status == 200 and opened and "log" in opened[0].lower()


def test_list_and_counts_go_beyond_the_newest_400(setup):
    from seeksync import server
    eng, db, sc, slsk, tmp = setup
    cid = db.add_channel("https://soundcloud.com/a", "A", False, 0)
    now = time.time()
    for i in range(450):
        db.add_track(channel_id=cid, sc_id=f"d{i}", state="done", uploaded_at=now - i)
    db.add_track(channel_id=cid, sc_id="old-waiting", state="waiting", uploaded_at=now - 10_000)
    db.add_track(channel_id=cid, sc_id="skip", state="skipped", uploaded_at=now)
    api = Api(eng, db, token="t")
    _, everything = _call(api, "GET", "/api/state")
    assert everything["counts"]["done"] == 450 and everything["counts"]["all"] == 451
    assert len(everything["tracks"]) == server.TRACK_LIMIT
    assert all(t["state"] != "skipped" for t in everything["tracks"])
    _, waiting = _call(api, "GET", "/api/state?filter=waiting")           # the old one used to be out of sight
    assert [t["sc_id"] for t in waiting["tracks"]] == ["old-waiting"]
    _, one = _call(api, "GET", f"/api/state?channel={cid}&filter=skipped")
    assert [t["sc_id"] for t in one["tracks"]] == ["skip"] and one["counts"]["skipped"] == 1


def test_uploads_missed_while_the_app_was_off_are_found(setup):
    from seeksync import engine as engine_mod
    eng, db, sc, slsk, tmp = setup
    cid = db.add_channel("https://soundcloud.com/lbl", "Label", False, backlog=1)
    asyncio.run(eng.check_channel(cid))                     # the 3 tracks of FakeSC are known now
    asked = []
    everything = [TrackStub(str(100 + i), f"https://soundcloud.com/lbl/n{i}", f"New {i} - Track {i}")
                  for i in range(40)] + list(sc.tracks)

    def latest(url, include_reposts=False, limit=25):
        asked.append(limit)
        return everything[:limit]
    sc.latest = latest
    sc.track = lambda url: None                              # details don't matter here
    asyncio.run(eng.check_channel(cid))
    assert asked == [25, engine_mod.CATCH_UP_COUNT]
    new_ids = {s.sc_id for s in everything[:40]}
    assert len([t for t in db.tracks(limit=1000) if t["sc_id"] in new_ids]) == 40


def test_search_now_gives_an_old_track_a_fresh_start(setup):
    eng, db, sc, slsk, tmp = setup
    t = _wanted(eng, db, sc, title="Nobody Knows - Unfindable")
    long_ago = time.time() - 90 * 86400
    db.update_track(t["id"], state="gave_up", created_at=long_ago, attempts=9)
    eng.retry_now(t["id"])
    t2 = db.track(t["id"])
    assert t2["state"] == "wanted" and t2["attempts"] == 0
    asyncio.run(eng._search_track(t2))                       # FakeSlsk finds nothing for this title
    t3 = db.track(t["id"])
    assert t3["state"] == "waiting", t3["state"]             # it used to stop again straight away
    assert t3["next_attempt"] - time.time() < 3700            # and the wait starts at 1 hour again


def test_a_search_that_did_not_happen_is_not_a_try(setup):
    eng, db, sc, slsk, tmp = setup
    t = _wanted(eng, db, sc)

    async def broken(q, wait=0):
        raise RuntimeError("not connected")
    slsk.search = broken
    asyncio.run(eng._search_track(t))
    assert db.track(t["id"])["attempts"] == t["attempts"]


def test_better_copies_are_searched_with_your_own_term(setup):
    from test_engine import _done_mp3, _run_upgrade
    eng, db, sc, slsk, tmp = setup
    t, _ = _done_mp3(eng, db, sc, tmp)
    db.update_track(t["id"], custom_query="my own words")
    _run_upgrade(eng, db, t["id"])
    assert slsk.searches[0] == "my own words"


def test_a_busy_peer_is_not_waited_on_for_long_when_others_are_left(setup):
    from seeksync import engine as engine_mod
    eng, db, sc, slsk, tmp = setup
    cands = [Candidate("a", "x.flac"), Candidate("b", "y.flac"), Candidate("c", "z.flac")]
    waits = [eng._queue_timeout(i, cands) for i in range(3)]
    assert waits == [engine_mod.QUEUE_TIMEOUT_NEXT, engine_mod.QUEUE_TIMEOUT_NEXT, engine_mod.QUEUE_TIMEOUT]
    assert engine_mod.QUEUE_TIMEOUT_NEXT < engine_mod.QUEUE_TIMEOUT


def test_a_long_queue_does_not_count_against_the_peer(setup, monkeypatch):
    from seeksync import engine as engine_mod
    eng, db, sc, slsk, tmp = setup
    t = _wanted(eng, db, sc)
    slsk.transfer_info = lambda tr: {"state": "QUEUED", "bytes": 0, "size": 0, "local_path": None,
                                     "place_in_queue": 40, "fail_reason": ""}
    clock = iter(range(0, 10**7, 600))                       # ten minutes pass at every look
    monkeypatch.setattr(engine_mod.time, "time", lambda: float(next(clock)))
    ok, info = asyncio.run(eng._try_candidate(db.track(t["id"]), Candidate("busy", "a\\Fresh Artist - Brand New.flac"),
                                              queue_timeout=1800))
    assert not ok and info["fail_reason"] == "peer queue too long"
    assert db.peer_stats(["busy"]) == {}                     # no "failed" towards a 30-day block


def test_old_quarantine_files_are_deleted_but_stay_blocked(setup):
    from seeksync import engine as engine_mod
    eng, db, sc, slsk, tmp = setup
    t = _wanted(eng, db, sc)
    q = tmp / "q" / "a.flac"
    q.parent.mkdir()
    q.write_bytes(b"x")
    fresh = tmp / "q" / "b.flac"
    fresh.write_bytes(b"x")
    old_id = db.add_reject(t["id"], "peer", "a.flac", "Fake lossless", str(q))
    db.add_reject(t["id"], "peer", "b.flac", "Fake lossless", str(fresh))
    with db.lock:
        db.conn.execute("UPDATE rejects SET created_at=? WHERE id=?",
                        (time.time() - (engine_mod.QUARANTINE_DAYS + 1) * 86400, old_id))
    assert eng._tidy_quarantine() == 1
    assert not q.exists() and fresh.exists()
    assert db.reject(old_id)["status"] == "deleted"
    assert ("peer", "a.flac") in db.blocked(t["id"])          # never tried again


# --- secrets in settings.json --------------------------------------------------------------------

def test_secrets_are_stored_through_protect(tmp_path, monkeypatch):
    from seeksync import secret
    monkeypatch.setattr(secret, "protect", lambda v: "dpapi:" + v[::-1] if v else v)
    monkeypatch.setattr(secret, "unprotect", lambda v: v[6:][::-1] if v.startswith("dpapi:") else v)
    store = SettingsStore(tmp_path / "s.json")
    store.update({"soulseek_password": "hunter2", "nicotine_token": "key", "soulseek_username": "dj"})
    raw = json.loads((tmp_path / "s.json").read_text())
    assert raw["soulseek_password"] == "dpapi:2retnuh" and raw["nicotine_token"] == "dpapi:yek"
    assert raw["soulseek_username"] == "dj"
    again = SettingsStore(tmp_path / "s.json").settings
    assert again.soulseek_password == "hunter2" and again.nicotine_token == "key"


def test_plain_secrets_from_older_versions_still_work(tmp_path):
    from seeksync import secret
    assert secret.unprotect("hunter2") == "hunter2"
    if not secret.IS_WINDOWS:
        assert secret.protect("hunter2") == "hunter2"          # macOS/Linux: the file itself is private (chmod 600)
        assert secret.unprotect("dpapi:AAAA") == ""             # made on Windows: enter it again


@pytest.mark.skipif(os.name != "nt", reason="Windows Data Protection API")
def test_windows_encrypts_the_password(tmp_path):
    from seeksync import secret
    stored = secret.protect("pässwörd 🎧")
    assert stored.startswith("dpapi:") and "pässwörd" not in stored
    assert secret.unprotect(stored) == "pässwörd 🎧"
    assert secret.unprotect("dpapi:bm90IGVuY3J5cHRlZA==") == ""   # garbage: entered again, no crash
    store = SettingsStore(tmp_path / "s.json")
    store.update({"soulseek_password": "hunter2"})
    assert "hunter2" not in (tmp_path / "s.json").read_text()
    assert SettingsStore(tmp_path / "s.json").settings.soulseek_password == "hunter2"


# --- SeekDrop data that wasn't taken over on Windows ----------------------------------------------

def _db_with_channels(path, n):
    db = Database(path)
    for i in range(n):
        db.add_channel(f"https://soundcloud.com/c{i}", f"C{i}", False, 0)
    db.conn.close()


def test_seekdrop_data_is_taken_over_when_seeksync_started_empty(tmp_path):
    old, new = tmp_path / "SeekDrop", tmp_path / "SeekSync"
    old.mkdir()
    (old / "settings.json").write_text('{"soulseek_username": "old"}')
    _db_with_channels(old / "seekdrop.db", 3)
    (new / "Logs").mkdir(parents=True)
    (new / "settings.json").write_text('{"soulseek_username": "typed again"}')
    _db_with_channels(new / "seeksync.db", 0)
    assert migrate_legacy_data(new, [old]) == old
    assert json.loads((new / "settings.json").read_text())["soulseek_username"] == "old"
    assert len(Database(new / "seeksync.db").channels()) == 3
    kept = [p for p in new.iterdir() if p.name.startswith("before-takeover-")]
    assert len(kept) == 1 and (kept[0] / "settings.json").exists()      # nothing SeekSync made is lost
    assert migrate_legacy_data(new, [old]) is None                       # and only once


def test_seeksync_with_channels_is_never_replaced(tmp_path):
    old, new = tmp_path / "SeekDrop", tmp_path / "SeekSync"
    old.mkdir()
    _db_with_channels(old / "seekdrop.db", 3)
    new.mkdir()
    _db_with_channels(new / "seeksync.db", 1)
    assert migrate_legacy_data(new, [old]) is None
    assert len(Database(new / "seeksync.db").channels()) == 1 and (old / "seekdrop.db").exists()
