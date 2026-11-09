"""Roadmap step 16: Spotify playlists, read from the public embed page. A fake page, no network."""
import asyncio
import json

import pytest

from seeksync import spotify as sp
from seeksync.soundcloud import ChannelError
from seeksync.sources import Sources, is_playlist_url, normalize_channel_url, source_name

from test_engine import _fresh_track, setup  # noqa: F401  (fixture)

PID = "37i9dQZF1DXcBWIGoYBM5M"
URL = f"https://open.spotify.com/playlist/{PID}"


def track(tid, title, artists, ms=300_000, kind="track"):
    return {"uri": f"spotify:{kind}:{tid}", "uid": "x", "title": title, "subtitle": artists, "duration": ms,
            "isPlayable": True, "entityType": kind}


def page(tracks, name="Late Night Techno", status=None):
    if status:
        props = {"status": status, "title": "Page not found"}
    else:
        props = {"state": {"data": {"entity": {"type": "playlist", "name": name, "id": PID, "trackList": tracks}}}}
    data = {"props": {"pageProps": props}}
    return f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></body></html>'


T1 = "3zOYmiNOuyDL0ClxJcEJ0T"
T2 = "4uLU6hMCjMI75M1A2tKUQC"
T3 = "1301WleyT98MSxVHPZCA6M"


def client(html):
    return sp.SpotifyClient(fetch=lambda url: html)


# --- links ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    URL, URL + "?si=abc123", f"open.spotify.com/intl-nl/playlist/{PID}?si=1", f"https://open.spotify.com/embed/playlist/{PID}",
    f"spotify:playlist:{PID}", f"  {URL}/  ",
])
def test_playlist_links_are_normalised(text):
    assert normalize_channel_url(text) == URL


@pytest.mark.parametrize("text,word", [
    (f"https://open.spotify.com/album/{PID}", "album"),
    (f"https://open.spotify.com/track/{PID}", "single track"),
    (f"https://open.spotify.com/artist/{PID}", "artist"),
    ("https://spotify.link/abcdef", "Short links"),
    ("https://open.spotify.com/playlist/short", "incomplete"),
    ("https://open.spotify.com/", "playlist link"),
])
def test_other_spotify_links_get_a_clear_message(text, word):
    with pytest.raises(ChannelError) as e:
        normalize_channel_url(text)
    assert word in str(e.value)


def test_soundcloud_links_still_go_to_soundcloud():
    assert normalize_channel_url("soundcloud.com/Some-Label") == "https://soundcloud.com/some-label"
    assert is_playlist_url("https://soundcloud.com/a/sets/b") and is_playlist_url(URL)
    assert not is_playlist_url("https://soundcloud.com/a")
    assert source_name(URL) == "Spotify" and source_name("https://soundcloud.com/a") == "SoundCloud"


# --- reading -------------------------------------------------------------------------------------

def test_titles_artists_and_length_are_read():
    c = client(page([
        track(T1, "Domino - Space 92 Remix", "Oxia,\xa0Space 92", ms=392_000),
        track(T2, "Stop The Wedding!", "Ashe", ms=198_840),
        track(T3, "Under Pressure - 2011 Remaster", "Queen,\xa0David Bowie"),
    ]))
    stubs = c.latest(URL)
    assert [s.sc_id for s in stubs] == [f"spotify:{T1}", f"spotify:{T2}", f"spotify:{T3}"]
    assert stubs[0].title == "Oxia, Space 92 - Domino (Space 92 Remix)"
    assert stubs[2].title == "Queen, David Bowie - Under Pressure (2011 Remaster)"
    assert stubs[0].url == f"https://open.spotify.com/track/{T1}"
    info = c.track(stubs[0].url)
    assert info.duration == 392 and info.uploader == "Oxia, Space 92" and info.sc_id == f"spotify:{T1}"
    assert c.channel_info(URL).name == "Late Night Techno"
    assert c.channel_info(URL).kind == "playlist"


def test_the_title_parser_gets_artist_title_and_version():
    from seeksync.titles import parse_title
    stub = client(page([track(T1, "Domino - Space 92 Remix", "Oxia,\xa0Space 92")])).latest(URL)[0]
    p = parse_title(stub.title)
    assert (p.artist, p.title, p.version) == ("Oxia, Space 92", "Domino", "Space 92 Remix")


def test_episodes_and_rows_without_title_are_left_out():
    stubs = client(page([track(T1, "Real", "A"), track("ep1", "A podcast", "Show", kind="episode"),
                         track(T2, "", "B")])).latest(URL)
    assert [s.sc_id for s in stubs] == [f"spotify:{T1}"]


def test_track_before_latest_is_an_error_the_engine_can_handle():
    with pytest.raises(ChannelError):
        client(page([])).track(f"https://open.spotify.com/track/{T1}")


# --- why a playlist can't be read -----------------------------------------------------------------

def test_missing_playlist_says_so():
    with pytest.raises(ChannelError) as e:
        client(page([], status=404)).latest(URL)
    assert "doesn't exist, or it's private" in str(e.value)


def test_a_page_that_changed_says_so():
    with pytest.raises(ChannelError) as e:
        client("<html>nothing here</html>").latest(URL)
    assert "looks different" in str(e.value)
    with pytest.raises(ChannelError):
        client('<script id="__NEXT_DATA__">{"props": {}}</script>').latest(URL)
    with pytest.raises(ChannelError):
        client('<script id="__NEXT_DATA__">not json</script>').latest(URL)


def test_http_errors_become_messages(monkeypatch):
    import urllib.error

    def boom(code):
        def opener(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, code, "x", {}, None)
        return opener

    for code, word in ((429, "blocking"), (404, "private"), (500, "HTTP 500")):
        monkeypatch.setattr(sp.urllib.request, "urlopen", boom(code))
        with pytest.raises(ChannelError) as e:
            sp._fetch("https://open.spotify.com/embed/playlist/x")
        assert word in str(e.value)

    def offline(req, timeout=0):
        raise sp.urllib.error.URLError("no network")
    monkeypatch.setattr(sp.urllib.request, "urlopen", offline)
    with pytest.raises(ChannelError) as e:
        sp._fetch("https://open.spotify.com/embed/playlist/x")
    assert "Can't reach Spotify" in str(e.value)


def test_sources_hands_each_link_to_its_own_client():
    class SC:
        def channel_info(self, url): return ("sc", url)
        def latest(self, url, reposts=False, limit=25): return ("sc-latest", url, reposts, limit)
        def track(self, url): return ("sc-track", url)

    src = Sources(SC(), client(page([track(T1, "Real", "A")])))
    assert src.channel_info("https://soundcloud.com/x") == ("sc", "https://soundcloud.com/x")
    assert src.latest("https://soundcloud.com/x", True, 10) == ("sc-latest", "https://soundcloud.com/x", True, 10)
    assert src.latest(URL)[0].sc_id == f"spotify:{T1}"
    assert src.track(f"https://open.spotify.com/track/{T1}").title == "A - Real"


# --- in the engine ----------------------------------------------------------------------------------

def test_a_spotify_playlist_is_added_and_new_tracks_are_picked_up(setup):
    eng, db, _sc, slsk, tmp = setup
    html = {"v": page([track(T1, "Domino - Space 92 Remix", "Oxia,\xa0Space 92", ms=392_000),
                       track(T2, "Stop The Wedding!", "Ashe")])}
    eng.sc = Sources(_sc, sp.SpotifyClient(fetch=lambda url: html["v"]))

    async def scenario():
        cid = db.add_channel(URL, "Late Night Techno", False, 0, kind="playlist")
        await eng.check_channel(cid)
        rows = {t["sc_id"]: t for t in db.tracks()}
        assert set(rows) == {f"spotify:{T1}", f"spotify:{T2}"}
        r = rows[f"spotify:{T1}"]
        assert (r["artist"], r["title"], r["version"]) == ("Oxia, Space 92", "Domino", "Space 92 Remix")
        assert r["duration"] == 392 and r["state"] == "wanted" and r["url"].startswith("https://open.spotify.com/track/")
        assert db.channel(cid)["initialized"] == 1 and db.channel(cid)["last_error"] == ""

        html["v"] = page([track(T1, "Domino - Space 92 Remix", "Oxia,\xa0Space 92", ms=392_000),
                          track(T2, "Stop The Wedding!", "Ashe"), track(T3, "Third", "C")])
        await eng.check_channel(cid)
        assert len(db.tracks()) == 3

    asyncio.run(scenario())


def test_a_playlist_that_can_not_be_read_shows_the_reason(setup):
    eng, db, _sc, slsk, tmp = setup
    eng.sc = Sources(_sc, sp.SpotifyClient(fetch=lambda url: page([], status=404)))

    async def scenario():
        cid = db.add_channel(URL, "Gone", False, 0, kind="playlist")
        await eng.check_channel(cid)
        assert "private" in db.channel(cid)["last_error"]
        assert any("Spotify" in a["msg"] for a in eng.activity)

    asyncio.run(scenario())


def test_the_first_check_of_a_full_page_mentions_the_100_track_limit(setup):
    eng, db, _sc, slsk, tmp = setup
    ids = [f"{i:022d}" for i in range(sp.MAX_TRACKS)]
    eng.sc = Sources(_sc, sp.SpotifyClient(fetch=lambda url: page([track(i, f"Song {n}", "A") for n, i in enumerate(ids)])))

    async def scenario():
        cid = db.add_channel(URL, "Big", False, 0, kind="playlist")
        await eng.check_channel(cid)
        assert len(db.tracks(limit=500)) == sp.MAX_TRACKS
        assert any("first 100 tracks" in a["msg"] for a in eng.activity)

    asyncio.run(scenario())


# --- the "add" button -------------------------------------------------------------------------------

def test_adding_a_spotify_playlist_through_the_api(setup):
    from aiohttp.test_utils import TestClient, TestServer
    from seeksync.server import Api

    eng, db, _sc, slsk, tmp = setup
    eng.sc = Sources(_sc, sp.SpotifyClient(fetch=lambda url: page([track(T1, "Real", "A,\xa0B")])))
    api = Api(eng, db, token="t")
    h = {"X-Token": "t"}

    async def scenario():
        async with TestClient(TestServer(api.app())) as c:
            r = await c.post("/api/channels", json={"url": URL + "?si=1", "backlog": 5, "include_reposts": True}, headers=h)
            body = await r.json()
            assert r.status == 200 and body["name"] == "Late Night Techno" and body["kind"] == "playlist"
            ch = db.channel(body["id"])
            assert ch["url"] == URL and ch["kind"] == "playlist" and not ch["include_reposts"]
            again = await c.post("/api/channels", json={"url": f"spotify:playlist:{PID}"}, headers=h)
            assert again.status == 400 and "already watching this playlist" in (await again.json())["error"]
            album = await c.post("/api/channels", json={"url": f"https://open.spotify.com/album/{PID}"}, headers=h)
            assert album.status == 400 and "album" in (await album.json())["error"]
            eng.sc = Sources(_sc, sp.SpotifyClient(fetch=lambda url: page([], status=404)))
            gone = await c.post("/api/channels", json={"url": f"https://open.spotify.com/playlist/{'a' * 22}"}, headers=h)
            assert gone.status == 400 and "private" in (await gone.json())["error"]
            await asyncio.sleep(0.2)                      # the first check runs in the background

    asyncio.run(scenario())
    assert [t["sc_id"] for t in db.tracks()] == [f"spotify:{T1}"]
