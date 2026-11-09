"""Roadmap step 8: pacing, disk space, peer reputation, keeping an EP together, sharing warning.
Fake clocks, fake peers; nothing here touches the network or the real disk usage."""
import asyncio
import os
import time
from types import SimpleNamespace

import pytest

from seeksync import politeness as pol
from seeksync.config import SettingsStore
from seeksync.matching import Candidate, MatchPrefs, rank, score_candidate
from seeksync.titles import parse_title

from test_engine import FakeSC, FakeSlsk, _fresh_track, _real_sleep, setup  # noqa: F401  (fixture + fakes)


class Clock:
    """A clock that only moves when somebody sleeps."""

    def __init__(self):
        self.now = 1000.0
        self.slept = []

    def __call__(self):
        return self.now

    async def sleep(self, s):
        self.slept.append(s)
        self.now += s


# --- pacing ------------------------------------------------------------------------------------

def test_searches_are_spaced_apart():
    clock = Clock()
    th = pol.SearchThrottle(spacing=8, max_per_window=100, clock=clock, sleep=clock.sleep)

    async def go():
        for _ in range(4):
            await th.wait()
    asyncio.run(go())
    assert clock.now == 1000.0 + 3 * 8          # the first goes at once, then 8 s apart
    assert clock.slept == [8, 8, 8]


def test_maximum_per_five_minutes():
    clock = Clock()
    th = pol.SearchThrottle(spacing=8, max_per_window=5, window=300, clock=clock, sleep=clock.sleep)
    stamps = []

    async def go():
        for _ in range(12):
            await th.wait()
            stamps.append(clock.now)
    asyncio.run(go())
    # never more than 5 searches inside any 300 s window
    for i, t0 in enumerate(stamps):
        assert len([t for t in stamps if t0 <= t < t0 + 300]) <= 5
    assert stamps[5] - stamps[0] >= 300         # the 6th search had to wait for the first to age out
    # and the plain spacing still holds
    assert all(b - a >= 8 for a, b in zip(stamps, stamps[1:]))


def test_engine_throttles_both_search_paths_with_the_settings(setup):
    eng, db, sc, slsk, tmp = setup
    eng.settings.search_spacing = 10
    eng.settings.search_max_per_5min = 5
    clock = Clock()
    eng.throttle.clock, eng.throttle._sleep = clock, clock.sleep

    async def go():
        for _ in range(7):
            await eng._throttle()
    asyncio.run(go())
    assert eng.throttle.spacing == 10 and eng.throttle.max_per_window == 5
    assert clock.now - 1000.0 >= 300            # 7 searches with a limit of 5 per 5 minutes


def test_settings_can_slow_down_but_never_remove_the_limits(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    store.update({"search_spacing": 0, "search_max_per_5min": 10_000, "min_free_gb": -3})
    s = store.settings
    assert s.search_spacing == pol.MIN_SEARCH_SPACING
    assert s.search_max_per_5min == pol.MAX_MAX_SEARCHES
    assert s.min_free_gb == 0
    store.update({"search_spacing": 20, "search_max_per_5min": 1})
    assert (s.search_spacing, s.search_max_per_5min) == (20, pol.MIN_MAX_SEARCHES)
    assert (store.settings.search_spacing, store.settings.search_max_per_5min) == (20, 5)   # safe defaults are 8 and 20


def test_safe_defaults():
    from seeksync.config import Settings
    s = Settings()
    assert (s.search_spacing, s.search_max_per_5min, s.min_free_gb) == (8, 20, 5)


# --- disk space --------------------------------------------------------------------------------

def _usage(free_gb):
    return lambda path: SimpleNamespace(free=int(free_gb * pol.GB), total=10**12, used=0)


def test_low_disk_space_message_and_limit_zero(tmp_path):
    assert pol.low_disk_space([str(tmp_path)], 5, usage=_usage(50)) is None
    why = pol.low_disk_space([str(tmp_path)], 5, usage=_usage(1.5))
    assert why and "1.5 GB" in why and "paused" in why
    assert pol.low_disk_space([str(tmp_path)], 0, usage=_usage(0.1)) is None      # 0 = off
    # a music folder that doesn't exist yet is judged by the nearest existing parent
    assert pol.low_disk_space([str(tmp_path / "no" / "such")], 5, usage=_usage(1)) is not None


def test_downloads_pause_below_the_limit_and_resume(setup, monkeypatch):
    eng, db, sc, slsk, tmp = setup
    cid = db.add_channel("https://soundcloud.com/lbl", "Label", False, backlog=1)
    sc.tracks = sc.tracks[:1]
    asyncio.run(eng.check_channel(cid))
    eng.settings.min_free_gb = 5
    from seeksync import engine as engine_mod
    free = {"gb": 1.0}
    monkeypatch.setattr(engine_mod, "low_disk_space",
                        lambda paths, limit: pol.low_disk_space(paths, limit, usage=_usage(free["gb"])))

    async def go():
        task = asyncio.create_task(eng._search_loop())
        await _real_sleep(0.3)
        assert slsk.searches == []                              # paused: nothing searched, nothing downloaded
        assert "paused" in eng.paused_reason
        assert any("paused" in a["msg"] for a in eng.activity)
        free["gb"] = 50.0                                       # the user cleaned up
        eng.wake()
        await _real_sleep(0.3)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    asyncio.run(go())
    assert slsk.searches                                        # searching resumed by itself
    assert eng.paused_reason == ""


# --- peer reputation ---------------------------------------------------------------------------

ARTIST_TRACK = parse_title("Artist - Track")


def _c(user, name="Artist - Track.flac", folder="@@m\\Artist", **kw):
    base = dict(username=user, filename=f"{folder}\\{name}", size=30_000_000, duration=300, has_free_slots=True)
    base.update(kw)
    return Candidate(**base)


def test_two_fakes_put_a_peer_at_the_bottom(setup):
    eng, db, sc, slsk, tmp = setup
    eng._record_peer("liar", "fake")
    eng._record_peer("liar", "fake")
    cands = [_c("liar"), _c("newbie"), _c("honest", has_free_slots=False)]
    for _ in range(4):
        eng._record_peer("honest", "ok")
    ranked = rank(ARTIST_TRACK, 300, cands, eng._prefs(None, cands))
    assert [c.username for c in ranked][-1] == "liar"           # bottom, though it has a free slot
    assert "liar" in {c.username for c in ranked}                # two fakes: still listed, not yet blocked
    assert db.blocked_peers(time.time()) == []


def test_repeat_offenders_are_blocked_and_the_reason_is_shown(setup):
    eng, db, sc, slsk, tmp = setup
    for _ in range(3):
        eng._record_peer("liar", "fake")
    blocked = db.blocked_peers(time.time())
    assert [b["username"] for b in blocked] == ["liar"] and "fake" in blocked[0]["block_reason"]
    cands = [_c("liar"), _c("honest")]
    ranked = rank(ARTIST_TRACK, 300, cands, eng._prefs(None, cands))
    assert [c.username for c in ranked] == ["honest"]
    assert cands[0].rejected.startswith("Peer blocked:")        # "Why not?" says so

    # five failures and no success blocks too; one success earlier keeps the peer
    for _ in range(5):
        eng._record_peer("flaky", "failed")
    eng._record_peer("mostly-ok", "ok")
    for _ in range(5):
        eng._record_peer("mostly-ok", "failed")
    names = {b["username"] for b in db.blocked_peers(time.time())}
    assert names == {"liar", "flaky"}


def test_block_ends_after_30_days_and_can_be_lifted(setup):
    eng, db, sc, slsk, tmp = setup
    for _ in range(3):
        eng._record_peer("liar", "fake")
    assert db.blocked_peers(time.time() + 29 * 86400)
    assert not db.blocked_peers(time.time() + 31 * 86400)
    eng.unblock_peer("liar")
    assert db.blocked_peers(time.time()) == []
    cands = [_c("liar")]
    assert rank(ARTIST_TRACK, 300, cands, eng._prefs(None, cands))   # back in the results
    eng._record_peer("liar", "fake")                                  # one slip is not a block again
    assert db.blocked_peers(time.time()) == []


def test_reliable_peer_is_preferred_all_else_equal():
    prefs = MatchPrefs(peer_scores={"good": pol.peer_score(5, 0, 0), "bad": pol.peer_score(0, 3, 0)})
    ranked = rank(ARTIST_TRACK, 300, [_c("bad"), _c("unknown"), _c("good")], prefs)
    assert [c.username for c in ranked] == ["good", "unknown", "bad"]


def test_download_outcomes_are_counted_per_peer(setup):
    eng, db, sc, slsk, tmp = setup
    t = _fresh_track(eng, db, sc)
    eng.quarantine_dir = str(tmp / "quarantine")

    def fake_check(track, path):                # what checks.FileChecker does for a converted MP3
        track.setdefault("_meta", {})["quality"] = "fake"
        return "Fake lossless: audio stops at 16 kHz"
    eng.checks.append(fake_check)
    db.update_track(t["id"], state="downloading")
    asyncio.run(eng._download(db.track(t["id"]), [Candidate("liar", "@@a\\Fresh Artist - Brand New.flac")]))
    assert db.peer_stats(["liar"])["liar"]["fake"] == 1

    # a peer that fails or goes quiet
    eng.checks.clear()
    slsk.transfer_info = lambda tr: {"state": "FAILED", "bytes": 0, "size": 10, "local_path": None,
                                     "place_in_queue": None, "fail_reason": "peer went away"}
    db.update_track(t["id"], state="downloading")
    asyncio.run(eng._download(db.track(t["id"]), [Candidate("flaky", "@@a\\Fresh Artist - Brand New.flac")]))
    assert db.peer_stats(["flaky"])["flaky"]["failed"] == 1

    # and one that delivers
    def good(tr):
        with open(tr.path, "wb") as f:
            f.write(b"x" * 10)
        return {"state": "COMPLETE", "bytes": 10, "size": 10, "local_path": tr.path,
                "place_in_queue": None, "fail_reason": ""}
    slsk.transfer_info = good
    db.update_track(t["id"], state="downloading")
    asyncio.run(eng._download(db.track(t["id"]), [Candidate("honest", "@@a\\Fresh Artist - Brand New.flac")]))
    assert db.peer_stats(["honest"])["honest"]["ok"] == 1
    assert db.track(t["id"])["state"] == "done"


def test_peer_stats_table_is_added_to_an_old_database(tmp_path):
    import sqlite3
    from seeksync.db import Database
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE channels (id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE, name TEXT NOT NULL DEFAULT '',"
                " avatar TEXT NOT NULL DEFAULT '', include_reposts INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1,"
                " initialized INTEGER NOT NULL DEFAULT 0, backlog INTEGER NOT NULL DEFAULT 0, kind TEXT NOT NULL DEFAULT 'profile',"
                " last_checked REAL, last_error TEXT NOT NULL DEFAULT '', added_at REAL NOT NULL)")
    con.commit()
    con.close()
    db = Database(path)
    assert db.peer_stats() == {}
    assert db.bump_peer("x", "ok")["ok"] == 1


# --- EP / album from one user ------------------------------------------------------------------

def test_tracks_of_one_release_prefer_the_same_folder(setup):
    eng, db, sc, slsk, tmp = setup
    cid = db.add_channel("https://soundcloud.com/lbl/sets/ep", "My EP", False, backlog=0, kind="playlist")
    # track 1 of the EP already came from peer "album-guy", folder "@@m\\Artist - The EP"
    db.add_track(channel_id=cid, sc_id="1", raw_title="Artist - One", artist="Artist", title="One", state="done",
                 peer="album-guy", remote_file="@@m\\Artist - The EP\\01 Artist - One.flac")
    t2 = db.add_track(channel_id=cid, sc_id="2", raw_title="Artist - Track", artist="Artist", title="Track",
                      state="wanted", duration=300)
    t2 = db.track(t2)
    cands = [_c("other", folder="@@x\\Artist"),                    # nothing in common
             _c("album-guy", folder="@@m\\Artist - Singles"),      # same peer, other folder
             _c("album-guy", folder="@@m\\Artist - The EP"),       # same folder
             ]
    ranked = rank(ARTIST_TRACK, 300, cands, eng._prefs(t2, cands))
    assert [(c.username, c.parent) for c in ranked] == [
        ("album-guy", "Artist - The EP"), ("album-guy", "Artist - Singles"), ("other", "Artist")]
    assert "same folder as earlier tracks" in ranked[0].reasons
    assert "same peer as earlier tracks" in ranked[1].reasons
    # a preference, not a demand: a clearly better file elsewhere still wins when the match is poor
    worse = _c("album-guy", folder="@@m\\Artist - The EP", name="Artist - Track.mp3", bitrate=320, has_free_slots=False)
    best = _c("other", folder="@@x\\Artist", has_free_slots=True)
    ranked = rank(ARTIST_TRACK, 300, [worse, best], eng._prefs(t2, [worse, best]))
    assert ranked[0] is best                    # FLAC with a free slot beats an MP3 from the same folder


def test_no_earlier_tracks_means_no_preference(setup):
    eng, db, sc, slsk, tmp = setup
    cid = db.add_channel("https://soundcloud.com/x", "X", False, backlog=0)
    t = db.track(db.add_track(channel_id=cid, sc_id="1", raw_title="a", artist="Artist", title="Track"))
    prefs = eng._prefs(t, [_c("p")])
    assert not prefs.same_folder and not prefs.same_peers


# --- sharing -----------------------------------------------------------------------------------

def test_warns_when_nothing_is_shared(tmp_path):
    assert "not sharing" in pol.sharing_warning([])
    assert "not sharing" in pol.sharing_warning([str(tmp_path / "gone")])
    assert "still empty" in pol.sharing_warning([str(tmp_path)])
    (tmp_path / "a.flac").write_bytes(b"x")
    assert pol.sharing_warning([str(tmp_path)]) == ""


def test_nicotine_reports_what_it_shares():
    assert "Nicotine+" in pol.sharing_warning(None, folders=0, files=0)
    assert "empty" in pol.sharing_warning(None, folders=2, files=0)
    assert pol.sharing_warning(None, folders=2, files=1200) == ""
    assert pol.sharing_warning(None, folders=None, files=None) == ""    # an older plugin can't tell: no false alarm


def test_engine_picks_the_right_source_for_the_warning(setup, tmp_path):
    eng, db, sc, slsk, tmp = setup
    eng.settings.share_downloads, eng.settings.share_dirs = False, []
    assert "not sharing" in eng.share_warning()
    eng.slsk = SimpleNamespace(mode="nicotine", shared_folders=3, shared_files=900)
    assert eng.share_warning() == ""
    eng.slsk = SimpleNamespace(mode="nicotine", shared_folders=0, shared_files=0)
    assert "Nicotine+" in eng.share_warning()


def test_state_api_carries_the_notices(setup):
    from seeksync.server import Api
    eng, db, sc, slsk, tmp = setup
    eng.settings.share_downloads, eng.settings.share_dirs = False, []
    eng.paused_reason = "Only 1.0 GB free"
    srv = Api(eng, db, token="t")

    class Req:
        query = {}
    resp = asyncio.run(srv.state(Req()))
    import json
    body = json.loads(resp.text)
    assert body["politeness"]["paused"] == "Only 1.0 GB free"
    assert "not sharing" in body["politeness"]["share_warning"]
    assert body["politeness"]["blocked_peers"] == []
