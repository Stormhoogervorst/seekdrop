"""Roadmap step 9: rules per channel, the global blocklist, and what happens when rules change."""
import asyncio
import json
import sqlite3

from seekdrop import rules as R
from seekdrop.db import Database
from seekdrop.soundcloud import TrackInfo, TrackStub
from seekdrop.titles import parse_title

from test_engine import setup  # noqa: F401  (fixture)


def chk(title, duration=300, rules=None, **kw):
    return R.check(R.clean_rules(rules), parse_title(title), title, duration, **kw)


# --- the rules themselves ----------------------------------------------------------------------

def test_a_58_minute_mix_and_a_30_second_clip_are_skipped_each_with_its_rule():
    assert chk("Artist - Long Journey", 58 * 60) == "Longer than 12 minutes (58:00)"
    assert chk("Artist - Quick One", 30) == "Shorter than 2 minutes (0:30)"
    assert chk("Artist - Track (Clip)", 100) == "Preview or clip"
    assert chk("Label Radio Show 042", 300) == "Looks like a mix"
    assert chk("Artist - Normal (Extended Mix)", 372) == ""
    assert chk("Artist - Unknown Length", None) == ""          # no length known: no judgement


def test_defaults_and_summary():
    r = R.clean_rules({})
    assert (r["min_minutes"], r["max_minutes"], r["remixes"], r["skip_previews"], r["skip_mixes"]) == (2, 12, True, True, True)
    assert R.summary(r) == "2 to 12 min"
    assert R.summary(R.clean_rules({"remixes": False, "exclude": ["live at"], "max_minutes": 0})) == \
        "over 2 min, no remixes, 1 excluded"


def test_remixes_can_be_turned_off_but_vip_and_dub_stay():
    off = {"remixes": False}
    assert chk("Artist - Track (Bob Remix)", rules=off) == "Remixes are turned off for this channel"
    assert chk("Artist - Track (Bob Rework)", rules=off)
    assert chk("Artist - Track (Bob Bootleg)", rules=off)
    for ok in ("Artist - Track", "Artist - Track (Extended Mix)", "Artist - Track (Bob VIP)", "Artist - Track (Dub Mix)",
               "Artist - Track (Club Edit)"):
        assert chk(ok, rules=off) == "", ok
    assert chk("Artist - Track (Bob Remix)") == ""            # on by default


def test_exclude_and_require_words():
    assert chk("Artist - Track (Live at Fabric)", rules={"exclude": ["live at"]}) == "Excluded word: live at"
    assert chk("Artist - Track", rules={"exclude": ["live at"]}) == ""
    only = {"require": ["extended", "club mix"]}
    assert chk("Artist - Track (Extended Mix)", rules=only) == ""
    assert chk("Artist - Track (Club Mix)", rules=only) == ""
    assert chk("Artist - Track", rules=only).startswith("Missing a required word")
    # whole words only, accents folded
    assert chk("Artist - Delivery", rules={"exclude": ["live"]}) == ""
    assert chk("Artist - Café Del Mar", rules={"exclude": ["cafe"]}) == "Excluded word: cafe"


def test_global_blocklist_wins_over_channel_rules():
    kw, ar = ["bootleg pack"], ["Bad Guy"]
    assert chk("Artist - Track (Bootleg Pack)", block_keywords=kw) == "Blocked word: bootleg pack"
    assert chk("Bad Guy - Track", block_artists=ar) == "Blocked artist: Bad Guy"
    assert chk("Bad Guy & Good Girl - Track", block_artists=ar) == "Blocked artist: Bad Guy"
    assert chk("Good Girl - Track", block_artists=ar) == ""
    # a channel that requires the word still can't get the blocked artist
    assert chk("Bad Guy - Track (Extended)", rules={"require": ["extended"]}, block_artists=ar).startswith("Blocked")


def test_input_is_cleaned():
    r = R.clean_rules({"min_minutes": "x", "max_minutes": 9999, "exclude": "a\n\n  b  \nA", "remixes": 0, "junk": 1})
    assert r["min_minutes"] == 2 and r["max_minutes"] == 600
    assert r["exclude"] == ["a", "b"] and r["remixes"] is False and "junk" not in r
    assert R.clean_rules({"min_minutes": 20, "max_minutes": 5})["min_minutes"] == 5       # swapped, never impossible
    assert R.parse_rules("") == R.clean_rules({}) and R.parse_rules("not json") == R.clean_rules({})
    assert R.parse_rules(R.dump_rules({"max_minutes": 20}))["max_minutes"] == 20


# --- in the engine -----------------------------------------------------------------------------

def _channel(eng, db, sc, tracks, name="Label", kind="profile", rules=None, backlog=10):
    """tracks: [(sc_id, title, duration)]; returns the channel id after one check."""
    sc.tracks = [TrackStub(i, f"https://soundcloud.com/x/{i}", t) for i, t, _ in tracks]
    durations = {f"https://soundcloud.com/x/{i}": d for i, _, d in tracks}
    sc.track = lambda url: TrackInfo(url.rsplit("/", 1)[1], url, next(t.title for t in sc.tracks if t.url == url),
                                     uploader="lbl", duration=durations[url], uploaded_at=1.0)
    cid = db.add_channel(f"https://soundcloud.com/{name.lower()}", name, False, backlog=backlog, kind=kind)
    if rules:
        db.update_channel(cid, rules=R.dump_rules(rules))
    asyncio.run(eng.check_channel(cid))
    return cid


def _by_id(db):
    return {t["sc_id"]: (t["state"], t["last_error"]) for t in db.tracks()}


TRACKS = [("1", "Artist - Fine Track", 300), ("2", "Artist - Long Journey", 58 * 60),
          ("3", "Artist - Quick One", 30), ("4", "Artist - Remix Time (Bob Remix)", 300)]


def test_rules_are_applied_per_channel(setup):
    eng, db, sc, slsk, tmp = setup
    _channel(eng, db, sc, TRACKS, name="Strict", rules={"remixes": False})
    got = _by_id(db)
    assert got["1"] == ("wanted", "")
    assert got["2"] == ("skipped", "Longer than 12 minutes (58:00)")
    assert got["3"] == ("skipped", "Shorter than 2 minutes (0:30)")
    assert got["4"] == ("skipped", "Remixes are turned off for this channel")
    assert all(t["skip_rule"] == t["last_error"] for t in db.tracks() if t["state"] == "skipped")

    # another channel with other rules takes the same kind of uploads
    sc.tracks = [TrackStub("9", "https://soundcloud.com/x/9", "Artist - Long Journey")]
    cid = _channel(eng, db, sc, [("9", "Artist - Long Journey", 58 * 60)], name="Loose",
                   rules={"max_minutes": 0, "min_minutes": 0})
    assert _by_id(db)["9"] == ("wanted", "")


def test_get_it_still_works_and_survives_later_rule_changes(setup):
    eng, db, sc, slsk, tmp = setup
    cid = _channel(eng, db, sc, TRACKS)
    tid = next(t["id"] for t in db.tracks() if t["sc_id"] == "2")
    eng.retry_now(tid)
    assert db.track(tid)["state"] == "wanted" and db.track(tid)["skip_rule"] == R.OVERRIDDEN
    # tightening the rules doesn't take it away again, loosening doesn't touch it either
    db.update_channel(cid, rules=R.dump_rules({"exclude": ["long"]}))
    eng.reapply_rules(cid)
    assert db.track(tid)["state"] == "wanted"


def test_changed_rules_revive_and_skip_the_right_tracks(setup):
    eng, db, sc, slsk, tmp = setup
    cid = _channel(eng, db, sc, TRACKS + [("5", "Artist - Done Already", 300), ("6", "Artist - Stopped By Me", 300),
                                          ("7", "Artist - Being Fetched", 300)])
    ids = {t["sc_id"]: t["id"] for t in db.tracks()}
    db.update_track(ids["5"], state="done")
    db.update_track(ids["7"], state="downloading", attempts=1)
    eng.skip(ids["6"])                                         # the user's own choice: no rule involved
    assert db.track(ids["6"])["skip_rule"] == ""

    # loosen: the 58-minute track and the clip are fine now
    db.update_channel(cid, rules=R.dump_rules({"min_minutes": 0, "max_minutes": 90}))
    assert eng.reapply_rules(cid) == (2, 0)
    got = _by_id(db)
    assert got["2"] == ("wanted", "") and got["3"] == ("wanted", "")
    assert got["6"][0] == "skipped"                            # still the user's choice

    # tighten: tracks never searched are skipped, finished and running ones are left alone
    db.update_channel(cid, rules=R.dump_rules({"min_minutes": 0, "max_minutes": 90, "exclude": ["track", "fetched", "done"]}))
    revived, skipped = eng.reapply_rules(cid)
    got = _by_id(db)
    assert got["1"] == ("skipped", "Excluded word: track")
    assert got["5"][0] == "done" and got["7"][0] == "downloading"
    assert skipped >= 1


def test_global_blocklist_applies_and_reapplies(setup):
    eng, db, sc, slsk, tmp = setup
    _channel(eng, db, sc, [("1", "Bad Guy - Track", 300), ("2", "Good Guy - Track", 300)])
    assert _by_id(db)["1"][0] == "wanted"
    eng.store.update({"block_artists": "Bad Guy\n\nbad guy", "block_keywords": ["xyz"]})
    assert eng.settings.block_artists == ["Bad Guy"]            # blanks and duplicates are gone
    asyncio.run(eng.apply_settings({"block_artists"}))
    got = _by_id(db)
    assert got["1"] == ("skipped", "Blocked artist: Bad Guy") and got["2"][0] == "wanted"
    eng.store.update({"block_artists": []})
    asyncio.run(eng.apply_settings({"block_artists"}))
    assert _by_id(db)["1"] == ("wanted", "")


def test_playlist_claiming_a_track_applies_the_playlist_rules(setup):
    eng, db, sc, slsk, tmp = setup
    # channel A skipped both as backlog, then a playlist with stricter rules claims them
    ch = db.add_channel("https://soundcloud.com/a", "A", False, backlog=0)
    for sid, title, dur in (("1", "Artist - Ok One", 300), ("2", "Artist - Remix Two (Bob Remix)", 300)):
        db.add_track(channel_id=ch, sc_id=sid, raw_title=title, artist="Artist", title=title.split(" - ")[1],
                     duration=dur, state="skipped")
    sc.tracks = [TrackStub("1", "https://soundcloud.com/x/1", "Artist - Ok One"),
                 TrackStub("2", "https://soundcloud.com/x/2", "Artist - Remix Two (Bob Remix)")]
    sc.track = lambda url: TrackInfo(url[-1], url, "t", duration=300, uploaded_at=1.0)
    pl = db.add_channel("https://soundcloud.com/a/sets/p", "P", False, backlog=0, kind="playlist")
    db.update_channel(pl, rules=R.dump_rules({"remixes": False}))
    asyncio.run(eng.check_channel(pl))
    got = _by_id(db)
    assert got["1"] == ("wanted", "") and got["2"] == ("skipped", "Remixes are turned off for this channel")
    assert {t["channel_id"] for t in db.tracks()} == {pl}


# --- storage and API ---------------------------------------------------------------------------

def test_old_database_gets_the_columns_and_old_skips_become_rules(tmp_path):
    path = tmp_path / "old.db"
    db = Database(path)                              # today's schema, then take step 9's columns away again
    cid = db.add_channel("u", "n", False, 0)
    for sid, why in (("a", "Looks like a mix"), ("b", ""), ("c", "Longer than 10 minutes")):
        db.add_track(channel_id=cid, sc_id=sid, state="skipped", last_error=why)
    db.conn.close()
    con = sqlite3.connect(path)
    con.execute("ALTER TABLE channels DROP COLUMN rules")
    con.execute("ALTER TABLE tracks DROP COLUMN skip_rule")
    con.commit()
    con.close()

    db = Database(path)
    assert db.channel(cid)["rules"] == ""
    rows = {t["sc_id"]: t["skip_rule"] for t in db.tracks()}
    assert rows == {"a": "Looks like a mix", "b": "", "c": "Longer than 10 minutes"}


class Req:
    def __init__(self, cid, data):
        self.match_info, self._data, self.query = {"id": str(cid)}, data, {}

    async def json(self):
        return self._data


def test_api_saves_rules_and_reports_what_changed(setup):
    from seekdrop.server import Api
    eng, db, sc, slsk, tmp = setup
    cid = _channel(eng, db, sc, TRACKS)
    api = Api(eng, db, token="t")

    bad = asyncio.run(api.patch_channel(Req(cid, {"rules": "nope"})))
    assert bad.status == 400

    ok = asyncio.run(api.patch_channel(Req(cid, {"rules": {"max_minutes": 90, "min_minutes": 0}})))
    body = json.loads(ok.text)
    assert body["ok"] and body["revived"] == 2
    state = json.loads(asyncio.run(api.state(Req(cid, {}))).text)
    ch = next(c for c in state["channels"] if c["id"] == cid)
    assert ch["rules"]["max_minutes"] == 90 and ch["rules_summary"] == "under 90 min"
    assert state["rule_defaults"]["max_minutes"] == 12
