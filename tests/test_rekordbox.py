"""Roadmap step 12 (Rekordbox only): the XML SeekDrop writes for Rekordbox. Written, read back with
independent XML parsing, and driven from the engine with fake downloads. Rekordbox itself is not needed
(and not available here): the format is checked against its published structure."""
import asyncio
import json
import os
import xml.etree.ElementTree as ET

import pytest

from seekdrop import engine as engine_mod
from seekdrop import rekordbox as rb
from seekdrop.matching import Candidate

from test_engine import _real_sleep, setup  # noqa: F401  (fixture)
from test_library import mp3
from test_tagging import _download_as, _ready, _run_download, fake_flac, make_wav


def mk_flac(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fake_flac(path)


def track(i, path, **kw):
    base = dict(track_id=i, path=str(path), name=f"Title {i}", artist="Artist", size=1000, seconds=300,
                kind="FLAC File", added=1767225600.0)
    base.update(kw)
    return rb.Track(**base)


# --- paths -------------------------------------------------------------------------------------

def test_location_is_a_percent_encoded_file_url_and_goes_back_to_the_same_path():
    for path in ["/Users/dj/Music/SeekDrop/Label/Artist - Title (Extended Mix).flac",
                 "/Users/dj/Music/Café Del Mar/Sinéad & Björk - 100% #1 [live].mp3",
                 "/Users/dj/Music/夜/Дельфин - Привет.wav", "/Users/dj/Music/it's here/x.aiff"]:
        url = rb.location(path)
        assert url.startswith("file://localhost/Users/dj/Music/") and " " not in url and "&" not in url
        assert rb.path_from_location(url) == path
    assert rb.location("/a/b c/d.mp3") == "file://localhost/a/b%20c/d.mp3"
    # the same characters stay as they are that Rekordbox leaves alone in its own exports; the rest is encoded
    assert rb.location("/a/Track (1) #2, x+y=z; w@h $!*?.mp3") == "file://localhost/a/Track%20(1)%20#2,%20x+y=z;%20w@h%20$!*?.mp3"
    assert rb.location("/a/R&B [v2] 50%'s.mp3") == "file://localhost/a/R%26B%20%5Bv2%5D%2050%25%27s.mp3"
    assert rb.path_from_location(rb.location("/a/Track (1) #2, x+y=z; w@h $!*?.mp3")) == "/a/Track (1) #2, x+y=z; w@h $!*?.mp3"


def test_windows_paths_get_the_drive_form_rekordbox_uses():
    url = rb.location("C:\\Users\\Dj\\Music\\Day One\\x y.mp3")
    assert url == "file://localhost/C:/Users/Dj/Music/Day%20One/x%20y.mp3"
    assert rb.path_from_location(url) == "C:/Users/Dj/Music/Day One/x y.mp3"


def test_locations_written_by_rekordbox_itself_are_understood():
    assert rb.path_from_location("file://localhost/Users/me/Music/a%20b.mp3") == "/Users/me/Music/a b.mp3"
    assert rb.path_from_location("file:///Users/me/Music/a%20b.mp3") == "/Users/me/Music/a b.mp3"
    assert rb.path_from_location("file://localhost/D:/Music/x.flac") == "D:/Music/x.flac"


def test_text_is_made_safe_for_xml():
    assert rb.clean("a\x00b\x1fc\x0bd") == "abcd"
    assert rb.clean("ok \ud800 lone surrogate") == "ok  lone surrogate"
    assert rb.clean(None) == "" and rb.clean("Ça va 夜 🎧") == "Ça va 夜 🎧"


def test_playlist_names_are_made_unique():
    assert rb.unique_names(["Label", "Other", "label", "", "Label"]) == ["Label", "Other", "label (2)", "Untitled", "Label (3)"]


# --- the file ----------------------------------------------------------------------------------

def test_written_file_is_read_back_with_the_same_content(tmp_path):
    out = tmp_path / "rb.xml"
    tracks = [
        track(1, tmp_path / "Label" / "Artist - Title 1.flac", name="Night Signal (Extended Mix)", artist="Mira Kova & Delen",
              genre="Techno", year="2026", label="Nightshift Records", comment="https://soundcloud.com/x/y?a=1&b=2",
              bitrate=0, sample_rate=44100),
        track(2, tmp_path / "Label" / "Sinéad - \"Quoted\" <Title>.mp3", name='"Quoted" <Title> & more', artist="Sinéad",
              kind="MP3 File", bitrate=320, sample_rate=44100),
        track(7, tmp_path / "夜" / "Дельфин - Привет 🎧.wav", name="Привет 🎧", artist="Дельфин", kind="WAV File"),
    ]
    playlists = [rb.Playlist("Label", [1, 2]), rb.Playlist("Friday & Warm-up", [7, 1])]
    rb.write(str(out), tracks, playlists, "0.4.0")

    # an XML parser that doesn't know SeekDrop agrees on what is in the file
    root = ET.parse(out).getroot()
    assert root.tag == "DJ_PLAYLISTS" and root.get("Version") == "1.0.0"
    assert out.read_text("utf-8").startswith('<?xml version="1.0" encoding="UTF-8"?>\n<DJ_PLAYLISTS Version="1.0.0">')
    product = root.find("PRODUCT")
    assert (product.get("Name"), product.get("Version")) == ("SeekDrop", "0.4.0")
    coll = root.find("COLLECTION")
    assert coll.get("Entries") == "3" and len(coll.findall("TRACK")) == 3
    node = root.find("PLAYLISTS/NODE")
    assert (node.get("Type"), node.get("Name")) == ("0", "ROOT")
    folder = node.find("NODE")
    assert (folder.get("Type"), folder.get("Name"), folder.get("Count")) == ("0", "SeekDrop", "2")
    pls = folder.findall("NODE")
    assert [(p.get("Name"), p.get("Type"), p.get("KeyType"), p.get("Entries")) for p in pls] == \
        [("Label", "1", "0", "2"), ("Friday & Warm-up", "1", "0", "2")]

    got = rb.read(str(out))
    assert sorted(got["tracks"]) == [1, 2, 7]
    t1, t2, t7 = got["tracks"][1], got["tracks"][2], got["tracks"][7]
    assert t1["Name"] == "Night Signal (Extended Mix)" and t1["Artist"] == "Mira Kova & Delen"
    assert (t1["Genre"], t1["Year"], t1["Label"], t1["Kind"], t1["Size"], t1["TotalTime"]) == \
        ("Techno", "2026", "Nightshift Records", "FLAC File", "1000", "300")
    assert t1["Comments"] == "https://soundcloud.com/x/y?a=1&b=2" and t1["DateAdded"] == "2026-01-01"
    assert "BitRate" not in t1 and t1["SampleRate"] == "44100"
    assert (t2["Name"], t2["BitRate"], t2["Kind"]) == ('"Quoted" <Title> & more', "320", "MP3 File")
    assert t7["Name"] == "Привет 🎧" and t7["Artist"] == "Дельфин"
    for t in tracks:
        assert rb.path_from_location(got["tracks"][t.track_id]["Location"]) == t.path
    assert got["playlists"] == [("Label", [1, 2]), ("Friday & Warm-up", [7, 1])]      # same order as given


def test_an_empty_library_is_still_a_valid_file(tmp_path):
    out = tmp_path / "sub" / "dir" / "rb.xml"                       # folders are created
    rb.write(str(out), [], [])
    root = ET.parse(out).getroot()
    assert root.find("COLLECTION").get("Entries") == "0"
    assert root.find("PLAYLISTS/NODE/NODE").get("Count") == "0"
    assert rb.read(str(out)) == {"tracks": {}, "playlists": []}


def test_the_file_appears_in_one_go_and_a_failure_keeps_the_old_one(tmp_path, monkeypatch):
    out = tmp_path / "rb.xml"
    rb.write(str(out), [track(1, tmp_path / "a.flac")], [rb.Playlist("A", [1])])
    first = out.read_bytes()
    assert sorted(os.listdir(tmp_path)) == ["rb.xml"]               # no temporary file left behind

    real_replace = os.replace

    def boom(src, dst):
        assert os.path.exists(src) and os.path.basename(src).startswith(".")      # written to a hidden file first
        raise OSError("disk full")                                  # dies right before the file would appear
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        rb.write(str(out), [track(2, tmp_path / "b.flac")], [])
    monkeypatch.setattr(os, "replace", real_replace)
    assert out.read_bytes() == first                                # what Rekordbox sees is the last good file
    assert sorted(os.listdir(tmp_path)) == ["rb.xml"]


def test_file_facts_read_the_audio_once(tmp_path, monkeypatch):
    f, w = mp3(tmp_path / "a.mp3", seconds=120, kbps=128), tmp_path / "b.wav"
    make_wav(w, bits=16, rate=48000, frames=48000 * 3)
    cache = {}
    a, b = rb.file_facts(f, cache), rb.file_facts(str(w), cache)
    assert (a["kind"], a["bitrate"], a["sample_rate"]) == ("MP3 File", 128, 44100) and 115 <= a["seconds"] <= 125
    assert (b["kind"], b["sample_rate"], b["seconds"]) == ("WAV File", 48000, 3) and b["size"] == os.path.getsize(w)
    import mutagen
    calls = []
    monkeypatch.setattr(mutagen, "File", lambda *x, **k: calls.append(x))
    assert rb.file_facts(f, cache) == a and calls == []             # unchanged file: not read again


# --- the engine --------------------------------------------------------------------------------

def _enable(eng, tmp):
    eng.settings.rekordbox_export = True
    eng.settings.rekordbox_xml_path = str(tmp / "rekordbox" / "export.xml")


def test_default_settings_and_location(setup):
    eng, db, sc, slsk, tmp = setup
    assert eng.settings.rekordbox_export is False                   # off until asked for
    assert eng.rekordbox_path() == str(tmp / "out" / "SeekDrop for Rekordbox.xml")
    eng.settings.rekordbox_xml_path = str(tmp)                      # a folder: the file goes inside
    assert eng.rekordbox_path() == str(tmp / "SeekDrop for Rekordbox.xml")


def test_a_finished_download_ends_up_in_the_xml(setup, monkeypatch):
    eng, db, sc, slsk, tmp = setup
    t = _ready(eng, db, sc, monkeypatch)
    _enable(eng, tmp)
    _download_as(slsk, fake_flac)

    async def go():
        db.update_track(t["id"], state="downloading")
        await eng._download(db.track(t["id"]), [Candidate("peer", "@@a\\Fresh Artist - Brand New.flac")])
        await _real_sleep(0.05)
        await eng._rb_task                                          # the delayed write
    asyncio.run(go())
    done = db.track(t["id"])
    got = rb.read(eng.rekordbox_path())
    assert list(got["tracks"]) == [t["id"]]
    x = got["tracks"][t["id"]]
    assert (x["Name"], x["Artist"], x["Genre"], x["Year"]) == ("Brand New", "Fresh Artist", "Techno", "2025")
    assert x["Comments"] == "https://soundcloud.com/lbl/fresh" and x["Kind"] == "FLAC File"
    assert rb.path_from_location(x["Location"]) == done["file_path"] and os.path.exists(done["file_path"])
    assert int(x["Size"]) == os.path.getsize(done["file_path"]) and "Label" not in x
    assert got["playlists"] == [("Label", [t["id"]])]               # one playlist for the channel
    assert eng.rekordbox_state["tracks"] == 1 and eng.rekordbox_state["playlists"] == 1 and not eng.rekordbox_state["error"]


def test_only_finished_files_that_still_exist_are_included(setup, monkeypatch):
    eng, db, sc, slsk, tmp = setup
    _enable(eng, tmp)
    a = db.add_channel("https://soundcloud.com/a", "Alpha", False, 0)
    b = db.add_channel("https://soundcloud.com/b", "Beta", False, 0)
    empty = db.add_channel("https://soundcloud.com/c", "Gamma", False, 0)
    music = tmp / "out"

    def add(cid, sid, state, name, exists=True):
        f = str(music / name)
        if exists:
            mk_flac(f)
        return db.add_track(channel_id=cid, sc_id=sid, artist="Art", title=name[:-5], state=state,
                            file_path=f if state in ("done", "collected") else "")
    first = add(a, "1", "done", "One.flac")
    gone = add(a, "2", "done", "Two.flac", exists=False)            # deleted by the user
    add(a, "3", "wanted", "Three.flac")
    add(a, "4", "collected", "Four.flac")                           # already yours: not for this file
    add(a, "5", "skipped", "Five.flac")
    third = add(b, "6", "done", "Six.flac")
    second = add(a, "7", "done", "Seven.flac")
    state = eng.write_rekordbox_sync()
    got = rb.read(eng.rekordbox_path())
    assert sorted(got["tracks"]) == sorted([first, second, third]) and gone not in got["tracks"]
    assert got["playlists"] == [("Alpha", [first, second]), ("Beta", [third])]      # in the order they came in, none for Gamma
    assert state["tracks"] == 3 and state["playlists"] == 2


def test_two_channels_with_the_same_name_get_different_playlist_names(setup):
    eng, db, sc, slsk, tmp = setup
    _enable(eng, tmp)
    for i, url in enumerate(("https://soundcloud.com/x", "https://soundcloud.com/x/sets/y")):
        cid = db.add_channel(url, "Same Name", False, 0)
        f = str(tmp / "out" / f"t{i}.flac")
        mk_flac(f)
        db.add_track(channel_id=cid, sc_id=str(i), artist="A", title=f"T{i}", state="done", file_path=f)
    eng.write_rekordbox_sync()
    assert [n for n, _ in rb.read(eng.rekordbox_path())["playlists"]] == ["Same Name", "Same Name (2)"]


def test_label_only_when_it_is_switched_on_for_the_tags(setup, monkeypatch):
    eng, db, sc, slsk, tmp = setup
    t = _ready(eng, db, sc, monkeypatch)
    _enable(eng, tmp)
    f = str(tmp / "out" / "x.flac")
    mk_flac(f)
    db.update_track(t["id"], state="done", file_path=f)
    eng.write_rekordbox_sync()
    assert "Label" not in rb.read(eng.rekordbox_path())["tracks"][t["id"]]
    eng.settings.label_from_channel = True
    eng.write_rekordbox_sync()
    assert rb.read(eng.rekordbox_path())["tracks"][t["id"]]["Label"] == "Label"


def test_a_burst_of_downloads_writes_the_file_once(setup, monkeypatch):
    eng, db, sc, slsk, tmp = setup
    _enable(eng, tmp)
    writes = []
    real = eng.write_rekordbox_sync
    monkeypatch.setattr(eng, "write_rekordbox_sync", lambda: writes.append(1) or real())

    async def go():
        for _ in range(6):
            eng.schedule_rekordbox()
        await _real_sleep(0.05)
        await eng._rb_task
        eng.schedule_rekordbox()                                    # later downloads schedule a new write
        await _real_sleep(0.05)
        await eng._rb_task
    asyncio.run(go())
    assert len(writes) == 2


def test_nothing_is_written_while_the_export_is_off(setup):
    eng, db, sc, slsk, tmp = setup

    async def go():
        eng.schedule_rekordbox()
        await _real_sleep(0.05)
        await eng.write_rekordbox()
    asyncio.run(go())
    assert eng._rb_task is None and not os.path.exists(eng.rekordbox_path())


def test_a_better_copy_changes_the_location(setup, monkeypatch):
    eng, db, sc, slsk, tmp = setup
    t = _ready(eng, db, sc, monkeypatch)
    eng.settings.tag_files = False
    eng.settings.filename_template = "{artist} - {title}"
    _enable(eng, tmp)
    mp3_file = mp3(tmp / "out" / "Fresh Artist - Brand New.mp3", seconds=300, kbps=320)
    db.update_track(t["id"], state="done", file_path=mp3_file, tier="mp3_320")
    eng.write_rekordbox_sync()
    old = rb.path_from_location(rb.read(eng.rekordbox_path())["tracks"][t["id"]]["Location"])
    assert old.endswith(".mp3")

    better = str(tmp / "better.flac")
    mk_flac(better)
    scheduled = []
    monkeypatch.setattr(eng, "schedule_rekordbox", lambda: scheduled.append(1))
    path = eng._replace(db.track(t["id"]), better, Candidate("peer", "x.flac"), {}, "flac16")
    assert scheduled == [1] and path.endswith(".flac")             # the replacement asks for a new write
    eng.write_rekordbox_sync()
    new = rb.path_from_location(rb.read(eng.rekordbox_path())["tracks"][t["id"]]["Location"])
    assert new == path and new != old and not os.path.exists(old)


def test_removing_a_channel_updates_the_file_too(setup, monkeypatch):
    eng, db, sc, slsk, tmp = setup
    _enable(eng, tmp)
    cid = db.add_channel("https://soundcloud.com/x", "X", False, 0)
    scheduled = []
    monkeypatch.setattr(eng, "schedule_rekordbox", lambda: scheduled.append(1))
    eng.remove_channel(cid)
    assert scheduled == [1]


def test_a_file_that_cant_be_written_is_reported_and_nothing_crashes(setup):
    eng, db, sc, slsk, tmp = setup
    blocker = tmp / "blocker"
    blocker.write_text("a file where a folder should be")
    eng.settings.rekordbox_export = True
    eng.settings.rekordbox_xml_path = str(blocker / "export.xml")
    asyncio.run(eng.write_rekordbox())
    assert eng.rekordbox_state["error"]
    assert any("Couldn't write the Rekordbox file" in a["msg"] for a in eng.activity)


def test_the_xml_in_the_download_folder_is_not_mistaken_for_music(setup):
    from seekdrop import library
    eng, db, sc, slsk, tmp = setup
    eng.settings.rekordbox_export = True                            # default place: the download folder
    f = str(tmp / "out" / "Artist - Song.flac")
    mk_flac(f)
    eng.write_rekordbox_sync()
    assert os.path.exists(eng.rekordbox_path())
    res = library.scan(db, [str(tmp / "out")])
    assert res.files == 1


def test_settings_and_api(setup, monkeypatch):
    from seekdrop import server
    eng, db, sc, slsk, tmp = setup
    api = server.Api(eng, db, token="t")

    class Req:
        def __init__(self, data=None):
            self._d, self.query, self.match_info = data or {}, {}, {}

        async def json(self):
            return self._d

    off = asyncio.run(api.update_rekordbox(Req()))
    assert off.status == 400 and "Turn on" in json.loads(off.text)["error"]

    async def turn_on():
        await api.put_settings(Req({"rekordbox_export": True, "rekordbox_xml_path": f"  {tmp}/rb/out.xml  "}))
        await _real_sleep(0.1)                                      # the write that saving the settings starts
        return await api.update_rekordbox(Req())
    ok = asyncio.run(turn_on())
    body = json.loads(ok.text)
    assert ok.status == 200 and body["ok"] and body["tracks"] == 0
    assert eng.settings.rekordbox_xml_path == f"{tmp}/rb/out.xml" and os.path.exists(f"{tmp}/rb/out.xml")

    state = json.loads(asyncio.run(api.state(Req())).text)["rekordbox"]
    assert state["enabled"] and state["path"] == f"{tmp}/rb/out.xml" and state["written_at"] > 0

    opened = []
    monkeypatch.setattr(server, "open_in_file_manager", opened.append)
    assert asyncio.run(api.open_path(Req({"rekordbox": True}))).status == 200
    assert opened == [f"{tmp}/rb/out.xml"]
