"""Roadmap step 11: recognising tracks the DJ already has, and listing duplicates. Files are generated here
(tiny fake MP3s with tags, empty files for the big-folder test); nothing touches the network."""
import asyncio
import json
import os
import struct
import time

import pytest

from seeksync import library
from seeksync.db import Database
from seeksync.matching import Candidate, parse_aliases
from seeksync.soundcloud import TrackInfo, TrackStub
from seeksync.titles import parse_title

from test_engine import _fresh_track, _real_sleep, setup  # noqa: F401  (fixture + fakes)


# --- generated files ---------------------------------------------------------------------------

def mp3(path, artist=None, title=None, seconds=0, kbps=32):
    """A fake MP3 of about `seconds` long. Tags only when artist and title are given."""
    path = str(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    idx = {32: 1, 128: 9, 320: 14}[kbps]
    size = int(144 * kbps * 1000 / 44100)
    frames = max(10, int(seconds * 44100 / 1152))
    with open(path, "wb") as f:
        f.write((b"\xff\xfb" + bytes([idx << 4, 0]) + b"\x00" * (size - 4)) * frames)
    if artist:
        from mutagen.id3 import ID3, TIT2, TPE1
        tags = ID3()
        tags.add(TPE1(encoding=1, text=artist))
        tags.add(TIT2(encoding=1, text=title))
        tags.save(path, v2_version=3)
    return path


def flac(path, artist=None, title=None):
    path = str(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    info = struct.pack(">HH", 4096, 4096) + b"\0\0\0" + b"\0\0\0"
    info += struct.pack(">Q", (44100 << 44) | (1 << 41) | (15 << 36) | 441000 * 21) + b"\0" * 16
    with open(path, "wb") as f:
        f.write(b"fLaC" + bytes([0x80]) + struct.pack(">I", 34)[1:] + info)
    if artist:
        from mutagen.flac import FLAC
        t = FLAC(path)
        t["artist"], t["title"] = artist, title
        t.save()
    return path


def scanned(tmp_path, *dirs):
    db = Database(tmp_path / "lib.db")
    res = library.scan(db, [str(d) for d in dirs])
    return db, res


def want(raw, db, duration=None, aliases=None):
    return library.find(db, parse_title(raw), duration, parse_aliases(aliases or ""))


# --- reading files -----------------------------------------------------------------------------

def test_scan_reads_tags_and_file_names(tmp_path):
    music = tmp_path / "music"
    mp3(music / "a.mp3", "Fresh Artist", "Brand New (Extended Mix)", seconds=300)
    mp3(music / "sub" / "01 - Other Artist - Second Track.mp3")
    mp3(music / ".hidden.mp3")
    (music / "notes.txt").write_text("not audio")
    (music / "cover.jpg").write_bytes(b"x")
    db, res = scanned(tmp_path, music)
    rows = {os.path.basename(r["path"]): r for r in db.library_under(str(music))}
    assert sorted(rows) == ["01 - Other Artist - Second Track.mp3", "a.mp3"] and res.files == 2 and res.added == 2
    a = rows["a.mp3"]
    assert (a["artist"], a["title"], a["version"]) == ("Fresh Artist", "Brand New", "Extended Mix")
    assert a["ext"] == "mp3" and 240 < a["duration"] < 360
    b = rows["01 - Other Artist - Second Track.mp3"]
    assert (b["artist"], b["title"]) == ("Other Artist", "Second Track")        # track number dropped, name parsed


# --- recognising a track -----------------------------------------------------------------------

def test_a_track_under_a_slightly_different_name_is_found(tmp_path):
    music = tmp_path / "music"
    mp3(music / "Brand New - Fresh Artist (Original Mix).mp3")                  # no tags, words the other way round
    mp3(music / "b" / "x.mp3", "Fresh Artist", "Second One (Extended Mix)")      # tags only
    mp3(music / "c" / "Cafe Del Mar - Sunset Track.mp3")
    db, _ = scanned(tmp_path, music)
    assert want("Fresh Artist - Brand New", db)["path"].endswith("Brand New - Fresh Artist (Original Mix).mp3")
    assert want("Fresh Artist - Brand New [FREE DL]", db)
    assert want("Fresh Artist - Second One", db)["path"].endswith("x.mp3")      # Extended goes with the original
    assert want("Café Del Mar - Sunset Track", db)                               # accents don't matter


def test_other_tracks_and_versions_are_not_mistaken_for_it(tmp_path):
    music = tmp_path / "music"
    mp3(music / "Artist - Track (Bob Remix).mp3")
    mp3(music / "Artist - Track Of Doom.mp3")
    mp3(music / "Other Guy - Track.mp3")
    mp3(music / "Artist - Track (Radio Edit).mp3")
    mp3(music / "Artist - Other Song.mp3")
    db, _ = scanned(tmp_path, music)
    assert want("Artist - Track", db) is None                       # a remix, a longer title, another artist, a radio edit
    assert want("Artist - Track (Bob Remix)", db)["path"].endswith("(Bob Remix).mp3")
    assert want("Artist - Track (Alice Remix)", db) is None         # somebody else's remix
    assert want("Artist - Track (Radio Edit)", db)
    assert want("Artist - Missing Song", db) is None


def test_length_must_be_about_right_except_between_original_and_extended(tmp_path):
    music = tmp_path / "music"
    mp3(music / "m" / "Artist - Long Thing.mp3", seconds=1800)                   # a half hour mix with the same name
    mp3(music / "e" / "Artist - Fine Track (Extended Mix).mp3", seconds=420)
    mp3(music / "u" / "Artist - Fine Two.mp3", seconds=215)
    db, _ = scanned(tmp_path, music)
    assert want("Artist - Long Thing", db, duration=215) is None
    assert want("Artist - Fine Track", db, duration=215)                         # 7:00 extended for a 3:35 original
    assert want("Artist - Fine Two", db, duration=215) and want("Artist - Fine Two", db, duration=230)
    assert want("Artist - Fine Two", db, duration=100) is None                   # far too short
    assert want("Artist - Fine Two", db, duration=None)                          # unknown length: no objection


def test_an_alias_counts_as_the_artist(tmp_path):
    music = tmp_path / "music"
    mp3(music / "Kieran Hebden - Track.mp3")
    db, _ = scanned(tmp_path, music)
    assert want("Four Tet - Track", db) is None
    assert want("Four Tet - Track", db, aliases="Four Tet = Kieran Hebden")


def test_the_best_copy_is_the_one_reported(tmp_path):
    music = tmp_path / "music"
    mp3(music / "a" / "Artist - Same.mp3", kbps=128)
    flac(music / "b" / "Artist - Same.flac")
    mp3(music / "c" / "Artist - Same.mp3", kbps=320)
    db, _ = scanned(tmp_path, music)
    assert want("Artist - Same", db)["path"].endswith("Same.flac")


# --- scanning: speed, changes, missing folders -------------------------------------------------

def test_second_scan_of_10000_files_reads_nothing_and_takes_seconds(tmp_path, monkeypatch):
    music = tmp_path / "music"
    for i in range(10_000):
        d = music / f"folder {i // 500}"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"Artist {i} - Track {i}.mp3").write_bytes(b"")
    db = Database(tmp_path / "lib.db")
    first = library.scan(db, [str(music)])
    assert first.files == 10_000 and first.added == 10_000

    reads = []
    real = library.read_file
    monkeypatch.setattr(library, "read_file", lambda *a, **k: reads.append(a[0]) or real(*a, **k))
    t0 = time.time()
    second = library.scan(db, [str(music)])
    took = time.time() - t0
    assert reads == [] and (second.added, second.changed, second.removed) == (0, 0, 0)
    assert second.files == 10_000 and took < 5, took

    # a new file, a changed file and a removed file are picked up, and only those are read
    (music / "folder 0" / "New Artist - New Track.mp3").write_bytes(b"")
    changed = music / "folder 1" / "Artist 500 - Track 500.mp3"
    changed.write_bytes(b"abc")
    os.remove(music / "folder 2" / "Artist 1000 - Track 1000.mp3")
    third = library.scan(db, [str(music)])
    assert (third.added, third.changed, third.removed, third.files) == (1, 1, 1, 10_000)
    assert len(reads) == 2


def test_a_folder_that_is_gone_keeps_its_rows_but_an_unlisted_one_loses_them(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    mp3(a / "Artist - One.mp3")
    mp3(b / "Artist - Two.mp3")
    db, _ = scanned(tmp_path, a, b)
    assert db.library_count() == 2
    os.rename(b, tmp_path / "b-unplugged")                         # a drive that isn't connected right now
    res = library.scan(db, [str(a), str(b)])
    assert db.library_count() == 2 and res.missing == [str(b)]
    library.scan(db, [str(a)])                                     # the user took it off the list
    assert [os.path.basename(r["path"]) for r in db.library_under(str(tmp_path))] == ["Artist - One.mp3"]


def test_overlapping_folders_are_scanned_once():
    assert library.clean_roots(["/m/dj", "/m/dj/sub", "/m/dj/", "/m/other", "/m/dj2"]) == ["/m/dj", "/m/other", "/m/dj2"]


def test_old_database_gets_the_library_table(tmp_path):
    path = tmp_path / "old.db"
    db = Database(path)
    db.conn.execute("DROP TABLE library")
    db.conn.close()
    db = Database(path)
    assert db.library_count() == 0


# --- in the engine -----------------------------------------------------------------------------

def _setup_library(eng, tmp, files=()):
    music = tmp / "music"
    music.mkdir(exist_ok=True)
    eng.settings.library_dirs = [str(music)]
    for name in files:
        mp3(music / name, seconds=300)            # as long as the SoundCloud upload of the engine tests
    return music


def test_a_track_you_already_have_is_not_searched_or_downloaded(setup):
    eng, db, sc, slsk, tmp = setup
    _setup_library(eng, tmp, ["Fresh Artist - Brand New (Original Mix).mp3"])
    asyncio.run(eng.scan_library())
    t = _fresh_track(eng, db, sc)
    assert t["state"] == "collected" and t["file_path"].endswith("Brand New (Original Mix).mp3")
    assert any("already in your collection" in a["msg"] for a in eng.activity)
    assert slsk.searches == [] and not eng.active
    # the search loop leaves it alone too
    assert db.due_tracks(time.time()) == []


def test_waiting_tracks_are_found_after_a_scan_and_come_back_when_the_file_goes(setup):
    eng, db, sc, slsk, tmp = setup
    music = _setup_library(eng, tmp)
    t = _fresh_track(eng, db, sc)
    assert t["state"] == "wanted"
    db.update_track(t["id"], state="waiting", attempts=2)                      # searched without luck
    f = mp3(music / "Fresh Artist - Brand New.mp3", seconds=300)
    asyncio.run(eng.scan_library())
    assert db.track(t["id"])["state"] == "collected"
    os.remove(f)
    asyncio.run(eng.scan_library())
    again = db.track(t["id"])
    assert again["state"] == "wanted" and again["file_path"] == ""
    assert any("no longer in your folders" in a["msg"] for a in eng.activity)


def test_get_it_anyway_is_respected_and_other_states_are_left_alone(setup):
    eng, db, sc, slsk, tmp = setup
    music = _setup_library(eng, tmp, ["Fresh Artist - Brand New.mp3"])
    asyncio.run(eng.scan_library())
    t = _fresh_track(eng, db, sc)
    assert t["state"] == "collected"
    eng.retry_now(t["id"])
    mine = db.track(t["id"])
    assert mine["state"] == "wanted" and mine["skip_rule"] == "overridden" and mine["file_path"] == ""
    asyncio.run(eng.scan_library())                                            # a new scan must not take it back
    assert db.track(t["id"])["state"] == "wanted"
    asyncio.run(eng._search_track(db.track(t["id"])))                          # and the search really happens
    assert slsk.searches

    # tracks that are being downloaded, finished or skipped by the user are never turned into "collected"
    for state in ("downloading", "done", "skipped"):
        db.update_track(t["id"], state=state, skip_rule="")
        asyncio.run(eng.scan_library())
        assert db.track(t["id"])["state"] == state


def test_searching_waits_while_the_folders_are_read(setup):
    eng, db, sc, slsk, tmp = setup
    _fresh_track(eng, db, sc)
    eng.library_state["scanning"] = True

    async def go():
        task = asyncio.create_task(eng._search_loop())
        await _real_sleep(0.3)
        assert slsk.searches == []
        eng.library_state["scanning"] = False
        eng.wake()
        await _real_sleep(0.3)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    asyncio.run(go())
    assert slsk.searches


def test_a_new_download_is_known_at_once_so_the_same_track_in_another_channel_is_not_fetched_twice(setup, monkeypatch):
    from seeksync import tagging
    eng, db, sc, slsk, tmp = setup
    t = _fresh_track(eng, db, sc)
    monkeypatch.setattr(tagging, "fetch_cover", lambda *a, **k: None)

    def deliver(tr):
        with open(tr.path, "wb") as f:
            f.write(b"x" * 10)
        return {"state": "COMPLETE", "bytes": 10, "size": 10, "local_path": tr.path, "place_in_queue": None, "fail_reason": ""}
    slsk.transfer_info = deliver
    db.update_track(t["id"], state="downloading")
    asyncio.run(eng._download(db.track(t["id"]), [Candidate("peer", "@@a\\Fresh Artist - Brand New.flac")]))
    first = db.track(t["id"])
    assert first["state"] == "done" and db.library_has(first["file_path"])

    # the same song is uploaded by a second channel
    sc.tracks = [TrackStub("77", "https://soundcloud.com/other/x", "Fresh Artist - Brand New")]
    sc.track = lambda url: TrackInfo("77", url, "Fresh Artist - Brand New", duration=300, uploaded_at=1.0)
    other = db.add_channel("https://soundcloud.com/other", "Other", False, backlog=5)
    asyncio.run(eng.check_channel(other))
    dup = next(x for x in db.tracks() if x["sc_id"] == "77")
    assert dup["state"] == "collected" and dup["file_path"] == first["file_path"]


def test_settings_keep_a_clean_list_of_folders(setup):
    eng, db, sc, slsk, tmp = setup
    eng.store.update({"library_dirs": ["/a", "  ", "/b "]})
    assert eng.settings.library_dirs == ["/a", "/b"]
    assert eng.library_roots()[0] == os.path.abspath(eng.settings.download_dir)         # the download folder always counts


# --- duplicates --------------------------------------------------------------------------------

def test_duplicates_are_listed_with_the_best_copy_marked_and_nothing_is_touched(tmp_path):
    out = tmp_path / "out"
    keep = [
        flac(out / "Chan" / "Artist - Same.flac"),
        mp3(out / "Chan" / "Artist - Same.mp3", kbps=320),
        mp3(out / "Other" / "Artist - Same (2).mp3", "Artist", "Same", kbps=128),
        mp3(out / "Chan" / "Artist - Same (Extended Mix).mp3", kbps=320),           # another version: not a duplicate
        mp3(out / "Chan" / "Artist - Alone.mp3"),
        mp3(out / "Chan" / "Artist - Pair (Bob Remix).mp3"),
        mp3(out / "Chan" / "Artist - Pair (Bob Remix) copy.mp3", "Artist", "Pair (Bob Remix)"),
    ]
    elsewhere = mp3(tmp_path / "dj" / "Artist - Same.mp3", kbps=320)                # in your own folder, not in downloads
    db, _ = scanned(tmp_path, out, tmp_path / "dj")
    groups = library.duplicates(db.library_under(str(out)), "club")
    by_title = {(g["title"], g["version"]): g for g in groups}
    assert set(by_title) == {("Same", ""), ("Pair", "Bob Remix")}
    same = by_title[("Same", "")]["files"]
    assert [os.path.basename(f["path"]) for f in same] == ["Artist - Same.flac", "Artist - Same.mp3", "Artist - Same (2).mp3"]
    assert [f["best"] for f in same] == [True, False, False]
    assert elsewhere not in {f["path"] for g in groups for f in g["files"]}
    assert all(os.path.exists(p) for p in keep + [elsewhere])                       # nothing was moved or deleted


def test_api_state_scan_duplicates_and_open(setup, monkeypatch):
    from seeksync import server
    eng, db, sc, slsk, tmp = setup
    out = tmp / "out"
    flac(out / "A" / "Artist - Same.flac")
    mp3(out / "B" / "Artist - Same.mp3", kbps=320)
    music = _setup_library(eng, tmp, ["Other - Thing.mp3"])
    api = server.Api(eng, db, token="t")

    class Req:
        def __init__(self, data=None):
            self._d, self.query, self.match_info = data or {}, {}, {}

        async def json(self):
            return self._d

    async def go():
        await api.scan_library(Req())
        await eng.scan_library()                                     # let the scan that was started finish
        state = json.loads((await api.state(Req())).text)
        dups = json.loads((await api.duplicates(Req())).text)
        return state, dups
    state, dups = asyncio.run(go())
    assert state["library"]["files"] == 3 and not state["library"]["scanning"]
    assert str(music) in state["library"]["dirs"] and state["library"]["own"] == str(out)
    assert len(dups["groups"]) == 1 and dups["groups"][0]["files"][0]["best"] is True

    opened = []
    monkeypatch.setattr(server, "open_in_file_manager", opened.append)
    inside = str(out / "A" / "Artist - Same.flac")
    assert asyncio.run(api.open_path(Req({"path": inside}))).status == 200 and opened == [inside]
    assert asyncio.run(api.open_path(Req({"path": "/etc/passwd"}))).status == 404       # never outside your music folders
    assert asyncio.run(api.open_path(Req({"path": str(out) + "-evil/x.mp3"}))).status == 404
    assert opened == [inside]
