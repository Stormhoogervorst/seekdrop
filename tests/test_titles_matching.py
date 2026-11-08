from seekdrop.matching import Candidate, MatchPrefs, rank, score_candidate
from seekdrop.titles import parse_title, search_queries


def test_premiere_and_free_dl_noise():
    p = parse_title("PREMIERE: Artist Name - Track Name (Someone Remix) [FREE DL]", uploader="label")
    assert (p.artist, p.title, p.version) == ("Artist Name", "Track Name", "Someone Remix")
    assert search_queries(p)[0] == "artist name track name someone"


def test_pipe_promo_and_extended():
    p = parse_title("Artist x Other - Track (Extended Mix) | OUT NOW")
    assert (p.artist, p.title, p.version) == ("Artist x Other", "Track", "Extended Mix")
    assert p.extra_artists == ["Other"]
    assert search_queries(p)[0] == "artist track"


def test_no_dash_uses_uploader():
    p = parse_title("Track Name", uploader="DJ Someone")
    assert p.artist == "DJ Someone" and p.artist_from_uploader


def test_original_mix_catalog_feat_emoji():
    p = parse_title("🔥 Ben Böhmer feat. Lowmoon - Rust (Original Mix) [ANJ123]")
    assert (p.artist, p.title, p.version, p.featuring) == ("Ben Böhmer", "Rust", "", "Lowmoon")


def test_trailing_remix_after_second_dash_and_preview():
    p = parse_title("Artist - Track - Bob Remix")
    assert (p.title, p.version) == ("Track", "Bob Remix")
    assert parse_title("Artist - Track (Clip)").is_preview


PREFS = MatchPrefs()


def cand(name, **kw):
    base = dict(username="peer", filename=f"@@music\\Artist\\{name}", size=10_000_000,
                bitrate=320, duration=300, has_free_slots=True)
    base.update(kw)
    return Candidate(**base)


def test_rejects_wrong_track_and_remix_for_original():
    p = parse_title("Artist - Track")
    assert score_candidate(p, 300, cand("Artist - Other Song.mp3"), PREFS) is None
    assert score_candidate(p, 300, cand("Artist - Track (Bob Remix).mp3"), PREFS) is None
    assert score_candidate(p, 300, cand("Artist - Track.mp3"), PREFS) is not None


def test_requires_remixer_for_remix():
    p = parse_title("Artist - Track (Bob Remix)")
    assert score_candidate(p, 300, cand("Artist - Track (Alice Remix).mp3"), PREFS) is None
    assert score_candidate(p, 300, cand("Artist - Track (Bob Remix).mp3"), PREFS) is not None


def test_quality_and_duration_rules():
    p = parse_title("Artist - Track")
    assert score_candidate(p, 300, cand("Artist - Track.mp3", bitrate=192), PREFS) is None
    assert score_candidate(p, 300, cand("Artist - Track.mp3", duration=500), PREFS) is None
    assert score_candidate(p, 300, cand("Artist - Track.ogg"), PREFS) is None
    flac = cand("Artist - Track.flac", bitrate=None)
    mp3 = cand("Artist - Track.mp3")
    assert rank(p, 300, [mp3, flac], PREFS)[0] is flac
    assert rank(p, 300, [mp3, flac], MatchPrefs(preferred_format="mp3"))[0] is mp3


def test_prefers_free_slots_and_artist_in_folder():
    p = parse_title("Artist - Track")
    busy = cand("01 Track.mp3", has_free_slots=False, queue_size=40)
    free = cand("01 Track.mp3", username="other", has_free_slots=True)
    assert rank(p, 300, [busy, free], PREFS)[0] is free


def test_different_artist_same_title_rejected():
    p = parse_title("Artist - Track")
    c = cand("Track.mp3", filename="@@x\\Someone Else\\Track.mp3")
    assert score_candidate(p, 300, c, PREFS) is None


def test_label_and_catalog_suffix_dropped():
    p = parse_title("Adam Beyer & Lenk - DC01 (Jesper Dahlbäck Rework) - Drumcode - DC360",
                    uploader="Drumcode", publisher_artist="VA")
    assert (p.artist, p.title, p.version) == ("Adam Beyer & Lenk", "DC01", "Jesper Dahlbäck Rework")
    assert search_queries(p)[0] == "adam beyer dc01 jesper dahlback"
    # Catalog number alone, no uploader given.
    assert parse_title("Artist - Track - ABC123").title == "Track"
    # Unknown extra segments stay in the title.
    assert parse_title("Artist - Track - Part Two").title == "Track - Part Two"


def test_remixer_tokens_skip_stop_words():
    p = parse_title("A, B - Congenial Endeavor (Veerus & Mattia Saviolo Remix) - Drumcode - DC360", uploader="Drumcode")
    assert p.title == "Congenial Endeavor"
    assert p.remixer_tokens == ["veerus", "mattia", "saviolo"]
    c = cand("A - Congenial Endeavor (Veerus, Mattia Saviolo Remix).mp3", filename="@@x\\A\\A - Congenial Endeavor (Veerus, Mattia Saviolo Remix).mp3")
    assert score_candidate(p, 300, c, PREFS) is not None


def test_spam_peers_rejected():
    p = parse_title("Mason Collective - Tell You Why")
    spam = cand("Mason Collective - Tell You Why [rawzik.com].aiff", username="https://www.rawzik.com", bitrate=None)
    spam_name = cand("Mason Collective - Tell You Why [rawzik.com].aiff", username="normalname", bitrate=None)
    real = cand("Mason Collective - Tell You Why.flac", username="enjoy", bitrate=None)
    assert score_candidate(p, 300, spam, PREFS) is None
    assert score_candidate(p, 300, spam_name, PREFS) is None
    assert rank(p, 300, [spam, real], PREFS) == [real]


def test_implausible_speed_gets_no_bonus():
    p = parse_title("Artist - Track")
    fast = cand("Artist - Track.mp3", avg_speed=5_000_000)
    fake = cand("Artist - Track.mp3", username="liar", avg_speed=256_000_000)
    assert rank(p, 300, [fake, fast], PREFS)[0] is fast


def test_is_mix():
    from seekdrop.titles import is_mix
    for raw in ["Defected Radio Show Hosted by Monki w/ Special Guest: Elvis Guetta 06.11.26",
                "Defected Radio Show Takeover by Ranger Trucco 30.10.26",
                "Drumcode Live 812 - Adam Beyer Live at Awakenings", "Artist - Essential Mix 2026",
                "Label Podcast 045 - Someone", "Artist b2b Other @ Boiler Room Berlin", "Guest Mix: Artist",
                "Artist - Mixtape Vol. 3", "Artist DJ Set | Printworks"]:
        assert is_mix(raw), raw
    for raw in ["Artist - Track (Extended Mix)", "Artist - Track (Original Mix)", "Artist - Track (Club Mix)",
                "Artist - Track (Dub Mix)", "Artist - Mixed Feelings", "Artist - Episode", "Mason Collective & VLAD vs Route 94 - Tell you Why",
                "Artist - Live Your Life"]:
        assert not is_mix(raw), raw


def test_playlist_urls():
    import pytest
    from seekdrop.soundcloud import ChannelError, is_playlist_url, normalize_channel_url
    assert normalize_channel_url("https://soundcloud.com/DefectedRecords/sets/Somehow-It-Flies?si=abc") == \
        "https://soundcloud.com/defectedrecords/sets/somehow-it-flies"
    # Private playlists keep their (case-sensitive) secret token.
    assert normalize_channel_url("soundcloud.com/me/sets/promos/s-AbC123") == "https://soundcloud.com/me/sets/promos/s-AbC123"
    assert is_playlist_url(normalize_channel_url("m.soundcloud.com/x/sets/y"))
    # A profile's sets page is still the profile.
    assert normalize_channel_url("soundcloud.com/drumcode/sets") == "https://soundcloud.com/drumcode"
    assert not is_playlist_url("https://soundcloud.com/drumcode")
    with pytest.raises(ChannelError):
        normalize_channel_url("soundcloud.com/drumcode/some-track")


def test_dj_pool_edits_rejected():
    p = parse_title("Majestic x Todd Terry - Rhythm In My Soul")
    pool = cand("Todd Terry, Majestic - Rhythm In My Soul (TMU Extended Mix) (Clean) 8A 126.mp3",
                filename="@@x\\Majestic\\Todd Terry, Majestic - Rhythm In My Soul (TMU Extended Mix) (Clean) 8A 126.mp3")
    intro = cand("Majestic - Rhythm In My Soul (Quick Hit).mp3", filename="@@x\\Majestic\\Majestic - Rhythm In My Soul (Quick Hit).mp3")
    real = cand("Majestic - Rhythm In My Soul (Extended Mix).mp3", filename="@@x\\Majestic\\Majestic - Rhythm In My Soul (Extended Mix).mp3")
    assert score_candidate(p, 300, pool, PREFS) is None
    assert score_candidate(p, 300, intro, PREFS) is None
    assert score_candidate(p, 300, real, PREFS) is not None
    # Words outside brackets (an artist called Clean Bandit, a track called Intro) are fine.
    cb = parse_title("Clean Bandit - Rather Be")
    assert score_candidate(cb, 300, cand("Clean Bandit - Rather Be.mp3", filename="@@x\\Clean Bandit\\Clean Bandit - Rather Be.mp3"), PREFS) is not None
    it = parse_title("The xx - Intro")
    assert score_candidate(it, 300, cand("The xx - Intro.mp3", filename="@@x\\The xx\\The xx - Intro.mp3"), PREFS) is not None
    # And when the upload itself is the clean edit, the clean edit is fine.
    ce = parse_title("Artist - Track (Clean Edit)")
    assert score_candidate(ce, 300, cand("Artist - Track (Clean Edit).mp3"), PREFS) is not None


def test_quoted_title_unwrapped():
    p = parse_title("Moby x Anfisa Letyago - 'You & Me' (Moby Remix)")
    assert (p.title, p.version) == ("You & Me", "Moby Remix")
    assert parse_title("Artist - “Track”").title == "Track"
    assert parse_title("Artist - Don't Stop 'Til").title == "Don't Stop 'Til"
