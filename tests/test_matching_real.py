"""Roadmap step 6: matching rules against real SoundCloud titles.

Titles from soundcloud.com/silvabumpa (the owner's channel, fetched Nov 2026; uploads and reposts),
with the artist / title / version a DJ would expect.
"""
import pytest

from seekdrop.matching import Candidate, MatchPrefs, parse_aliases, score_candidate, version_of
from seekdrop.titles import is_mix, normalize, parse_title, search_queries

UPLOADER = "Silva Bumpa"

# raw title -> (artist, title, version)
TRACKS = {
    "A.B.C. - PEOPLE IN THE PLACE": ("A.B.C", "PEOPLE IN THE PLACE", ""),
    "On 2nite (Jelsen Remix)": ("Silva Bumpa", "On 2nite", "Jelsen Remix"),
    "HOLD DA PHONE": ("Silva Bumpa", "HOLD DA PHONE", ""),
    "Fantasy (Baby if u know me) [feat. Kosmo Kint]": ("Silva Bumpa", "Fantasy (Baby if u know me)", ""),
    "In Da Game": ("Silva Bumpa", "In Da Game", ""),
    "That Y'all": ("Silva Bumpa", "That Y'all", ""),
    "On 2nite": ("Silva Bumpa", "On 2nite", ""),
    "Swagger Sound": ("Silva Bumpa", "Swagger Sound", ""),
    "Make It Hot": ("Silva Bumpa", "Make It Hot", ""),
    "Bludz & Cripz": ("Silva Bumpa", "Bludz & Cripz", ""),
    "Hypa": ("Silva Bumpa", "Hypa", ""),
    "Lifting": ("Silva Bumpa", "Lifting", ""),
    "Silva Bumpa x Riordan - Lifting": ("Silva Bumpa x Riordan", "Lifting", ""),
    "Wanna Party (Ranger Trucco Remix) [feat. Dennis G]": ("Silva Bumpa", "Wanna Party", "Ranger Trucco Remix"),
    "Feel This Way": ("Silva Bumpa", "Feel This Way", ""),
    "Wanna Party (feat. Dennis G)": ("Silva Bumpa", "Wanna Party", ""),
    "Supa Smoov (Bumpa’s Xtra Smoov Mix)": ("Silva Bumpa", "Supa Smoov", "Bumpa’s Xtra Smoov Mix"),
    "Body On Me (feat. EVA)": ("Silva Bumpa", "Body On Me", ""),
    "Doin' It featuring MC DT": ("Silva Bumpa", "Doin' It", ""),
    "Rock It Just Like Dat": ("Silva Bumpa", "Rock It Just Like Dat", ""),
    "Feel Da Same": ("Silva Bumpa", "Feel Da Same", ""),
    "Badstar - What I Want (What You Need)": ("Badstar", "What I Want (What You Need)", ""),
    "Badstar ft. Megan Wroe - Stay": ("Badstar", "Stay", ""),
    "Check Dis Out": ("Silva Bumpa", "Check Dis Out", ""),
    "House Nation": ("Silva Bumpa", "House Nation", ""),
    "Rush On Me": ("Silva Bumpa", "Rush On Me", ""),
    "Wrap It Up": ("Silva Bumpa", "Wrap It Up", ""),
    "All My People (Silva Bumpa Remix)": ("Silva Bumpa", "All My People", "Silva Bumpa Remix"),
    "Sadie Ama - Fallin' [Silva Bumpa Edit]": ("Sadie Ama", "Fallin'", "Silva Bumpa Edit"),
    "Diffrent x Silva Bumpa - I Don't Want U (Extended)": ("Diffrent x Silva Bumpa", "I Don't Want U", "Extended"),
    "I Don't Want U": ("Silva Bumpa", "I Don't Want U", ""),
    "Automatic": ("Silva Bumpa", "Automatic", ""),
    "Spirit Of Da Underground - Way I Are (HARDLINE01)": ("Spirit Of Da Underground", "Way I Are", ""),
    "Me + U": ("Silva Bumpa", "Me + U", ""),
}

# Radio shows, sets and recordings from the same channel: never searched as tracks.
SHOWS = [
    "Silva Bumpa invites Bowlesy - 09 June 2026",
    "Silva Bumpa - 14 April 2026",
    "Silva Bumpa with Newsham - 10 March 2026",
    "Silva Bumpa - 10 February 2026",
    "Silva Bumpa b2b Osmosis Jones @ Revolver Upstairs Melbourne 18 Jan 2026",
    "Silva Bumpa - 26 December 2025",
    "Silva Bumpa @ The Lot Radio 11-24-2025",
    "Silva Bumpa - 11 November 2025",
    "Silva Bumpa | Boiler Room: Sheffield",
    "ATW Records presents Silva Bumpa - 24 December 2024",
    "Silva Bumpa - 01 December",
    "INTERPLANETARY CRIMINAL + SILVA BUMPA 22.10.24",
]


@pytest.mark.parametrize("raw,expected", list(TRACKS.items()))
def test_real_titles_parse(raw, expected):
    p = parse_title(raw, uploader=UPLOADER)
    assert (p.artist, p.title, p.version) == expected
    assert not is_mix(raw)


def test_enough_real_titles():
    assert len(TRACKS) >= 30


@pytest.mark.parametrize("raw", SHOWS)
def test_real_shows_are_recognised(raw):
    assert is_mix(raw)


def test_featured_artists_are_kept_apart():
    assert parse_title("Fantasy (Baby if u know me) [feat. Kosmo Kint]", uploader=UPLOADER).featuring == "Kosmo Kint"
    assert parse_title("Doin' It featuring MC DT", uploader=UPLOADER).featuring == "MC DT"
    assert parse_title("Badstar ft. Megan Wroe - Stay").featuring == "Megan Wroe"
    assert parse_title("Silva Bumpa x Riordan - Lifting").extra_artists == ["Riordan"]


# --- versions --------------------------------------------------------------------------------

def test_version_kinds():
    assert version_of("") == version_of("Original Mix") and version_of("").kind == "original"
    assert version_of("Extended").kind == "extended"
    assert version_of("Jelsen Remix") == version_of("Jelsen Rework")
    v = version_of("Bumpa’s Xtra Smoov Mix")
    assert v.kind == "remix" and {"bumpas", "xtra", "smoov"} <= v.names   # the apostrophe goes on both sides
    assert version_of("Silva Bumpa Edit").kind == "edit"
    assert version_of("Radio Edit").kind == "radio"
    assert version_of("Larse VIP").kind == "vip" and version_of("Dub").kind == "dub"


def _match(sc_title, file_name, uploader=""):
    p = parse_title(sc_title, uploader=uploader)
    c = Candidate("peer", "@@music\\" + file_name, size=30_000_000, ext=file_name.rsplit(".", 1)[-1],
                  bitrate=320 if file_name.endswith(".mp3") else None, has_free_slots=True)
    return score_candidate(p, None, c, MatchPrefs()) is not None, c.rejected


@pytest.mark.parametrize("sc,file,ok", [
    ("Candi Staton - Hallelujah Anyway (Larse VIP)", "Candi Staton - Hallelujah Anyway (Larse Vocal).flac", False),
    ("Candi Staton - Hallelujah Anyway (Larse VIP)", "Candi Staton - Hallelujah anyway (Larse extended VIP).aiff", True),
    ("Candi Staton - Hallelujah Anyway (Larse VIP)", "Candi Staton - Hallelujah Anyway (Larse VIP Dub).flac", False),
    ("Adam Beyer & Lenk - DC01 (Jesper Dahlbäck Rework)", "Adam Beyer, Lenk - DC01, Pt. 1 (Jesper Dahlbäck Remix).flac", True),
    ("On 2nite (Jelsen Remix)", "Silva Bumpa - On 2nite (Jelsen Extended Remix).flac", True),
    ("On 2nite (Jelsen Remix)", "Silva Bumpa - On 2nite (Original Mix).flac", False),
    ("On 2nite (Jelsen Remix)", "Silva Bumpa - On 2nite (Someone Else Remix).flac", False),
    ("On 2nite", "Silva Bumpa - On 2nite (Jelsen Remix).flac", False),
    ("On 2nite", "Silva Bumpa - On 2nite (Extended Mix).flac", True),
    ("On 2nite", "Silva Bumpa - On 2nite (Radio Edit).mp3", False),
    ("On 2nite", "Silva Bumpa - On 2nite (Dub).flac", False),
    ("Supa Smoov (Bumpa’s Xtra Smoov Mix)", "Silva Bumpa - Supa Smoov (Bumpa's Xtra Smoov Mix).flac", True),
    ("Supa Smoov (Bumpa’s Xtra Smoov Mix)", "Silva Bumpa - Supa Smoov (Original Mix).flac", False),
    ("Sadie Ama - Fallin' [Silva Bumpa Edit]", "Sadie Ama - Fallin (Silva Bumpa Edit).mp3", True),
    ("Sadie Ama - Fallin' [Silva Bumpa Edit]", "Sadie Ama - Fallin (Silva Bumpa Remix).flac", False),
    ("Diffrent x Silva Bumpa - I Don't Want U (Extended)", "Diffrent, Silva Bumpa - I Don't Want U.flac", True),
    ("Artist - Track (Radio Edit)", "Artist - Track (Radio Edit).flac", True),
    ("Artist - Track (Radio Edit)", "Artist - Track (Extended Mix).flac", False),
    ("Artist - Dub Siren", "Artist - Dub Siren (Original Mix).flac", True),       # "Dub" in the title itself
    ("A.B.C. - PEOPLE IN THE PLACE", "A.B.C. - People In The Place.flac", True),
    ("A.B.C. - PEOPLE IN THE PLACE", "XYZ - People In The Place.flac", False),    # needs the artist now
])
def test_version_rules(sc, file, ok):
    got, why = _match(sc, file, uploader=UPLOADER)
    assert got == ok, why


# --- other scripts, accents, "&", feat -------------------------------------------------------

def test_normalising():
    assert normalize("Мот - Капкан") == "mot kapkan"
    assert normalize("Ελληνικά") == "ellinika"
    assert normalize("Kölsch & Friends feat. Ñu") == "kolsch and friends feat nu"
    assert normalize("A.B.C.") == "abc"
    assert _match("Мот - Капкан", "Mot - Kapkan.flac")[0]               # transliterated file name
    assert _match("Mot - Kapkan", "Мот - Капкан.flac")[0]               # and the other way round
    p = parse_title("Мот - Капкан")
    assert search_queries(p)[0] == "мот капкан"                          # search in the original script first


# --- aliases ----------------------------------------------------------------------------------

def test_aliases_count_as_the_artist():
    aliases = parse_aliases("Four Tet = Kieran Hebden, KH\nnot a line\n")
    assert aliases["four tet"] == ["Kieran Hebden", "KH"]
    assert aliases["kieran hebden"] == ["Four Tet", "KH"]
    p = parse_title("Kieran Hebden - Morning Side")
    c = Candidate("peer", "@@m\\Four Tet\\Four Tet - Morning Side.flac", size=30_000_000, ext="flac", has_free_slots=True)
    assert score_candidate(p, None, c, MatchPrefs()) is None and c.rejected == "Different artist"
    assert score_candidate(p, None, c, MatchPrefs(aliases=aliases)) is not None
