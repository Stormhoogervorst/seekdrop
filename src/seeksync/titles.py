"""Turn messy SoundCloud titles into clean artist / title / version parts.

SoundCloud titles look like:
    "PREMIERE: Artist - Track Name (Someone Remix) [FREE DL]"
    "Artist x Other - Track (Extended Mix) | OUT NOW"
    "Track Name"                       (artist is then the uploader)
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Words in a bracket/segment that mark it as promo noise rather than part of the title.
_NOISE_WORDS = (
    "free dl", "free download", "freedownload", "free d/l", "download", "out now", "premiere",
    "exclusive", "buy", "click buy", "support", "supported by", "played by", "preorder",
    "pre-order", "pre order", "bandcamp", "beatport", "spotify", "available", "forthcoming",
    "release", "ep", "lp", "album", "label", "records", "recordings", "music", "teaser",
)
_PREVIEW_WORDS = ("clip", "preview", "snippet", "cut", "teaser", "sample")
_VERSION_WORDS = (
    "remix", "rmx", "edit", "mix", "vip", "bootleg", "flip", "rework", "dub", "version",
    "remaster", "remastered", "instrumental", "acapella", "a cappella", "refix", "re-edit",
    "reprise", "extended", "radio",
)
# Versions that mean "a different track" when they don't match.
DIFFERENT_VERSION_WORDS = {"remix", "rmx", "bootleg", "flip", "rework", "vip", "refix", "dub", "acapella", "instrumental"}

_PREFIX_RE = re.compile(
    r"^\s*(?:premiere|exclusive|free\s*(?:dl|download)|out\s*now|new|world\s*premiere|"
    r"track\s*premiere|\d{1,3}\s*/\s*\d{1,3}|#\d+)\s*[:|\-–—]\s*",
    re.I,
)
_DASH_RE = re.compile(r"\s+[-–—]{1,2}\s+|\s+[-–—]{1,2}(?=\S)|(?<=\S)[-–—]{1,2}\s+")
_FEAT_RE = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\s+", re.I)
_BRACKET_RE = re.compile(r"\(([^()]*)\)|\[([^\[\]]*)\]|\{([^{}]*)\}")
_CATALOG_RE = re.compile(r"^[A-Z]{2,8}\s?\d{2,5}[A-Z]?$")


@dataclass
class ParsedTitle:
    artist: str = ""
    title: str = ""             # core title, without version
    version: str = ""           # e.g. "Someone Remix", "Extended Mix" ("" = original)
    featuring: str = ""
    is_preview: bool = False
    artist_from_uploader: bool = False
    raw: str = ""
    extra_artists: list[str] = field(default_factory=list)

    @property
    def display(self) -> str:
        t = self.title + (f" ({self.version})" if self.version else "")
        return f"{self.artist} - {t}" if self.artist else t

    @property
    def remixer_tokens(self) -> list[str]:
        """Tokens that must appear in a matching file for remix-type versions."""
        if not self.version or not version_is_different(self.version):
            return []
        toks = [t for t in tokens(self.version, drop_stop=True)
                if t not in DIFFERENT_VERSION_WORDS and t not in {"mix", "edit", "remix", "version"}]
        return toks


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


try:   # any script to Latin letters: "Мот" -> "Mot", "Ελληνικά" -> "Ellinika" (roadmap step 6)
    from anyascii import anyascii as _to_latin
except ImportError:      # pragma: no cover - optional at runtime
    _to_latin = strip_accents

_ACRONYM_RE = re.compile(r"\b((?:[A-Za-z]\.){2,})")   # "A.B.C." -> "ABC" (single letters would be dropped)


def normalize(s: str) -> str:
    """Lowercase ASCII words only: accents, other scripts, "&", quotes and punctuation normalised."""
    s = _ACRONYM_RE.sub(lambda m: m.group(1).replace(".", ""), s or "")
    s = _to_latin(s).lower()
    s = s.replace("&", " and ").replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _native_words(s: str) -> str:
    """Words in their own script (for searching Soulseek, where files keep their original names)."""
    s = re.sub(r"[^\w\s]+", " ", s or "", flags=re.UNICODE).lower()
    return " ".join(s.split())


def _non_latin(s: str) -> bool:
    return any(ch.isalpha() and ord(ch) > 0x24F for ch in s or "")


_STOP = {"the", "a", "an", "and", "of", "x", "vs", "feat", "ft", "featuring", "with"}


def tokens(s: str, drop_stop: bool = False) -> list[str]:
    out = [t for t in normalize(s).split() if len(t) > 1 or t.isdigit()]
    if drop_stop:
        out = [t for t in out if t not in _STOP]
    return out


def version_is_different(version: str) -> bool:
    return any(t in DIFFERENT_VERSION_WORDS for t in tokens(version))


def _classify_bracket(text: str) -> str:
    low = normalize(text)
    if not low:
        return "noise"
    words = low.split()
    if any(w in ("feat", "ft", "featuring") for w in words[:1]):
        return "feat"
    if any(re.search(rf"\b{re.escape(p)}\b", low) for p in _PREVIEW_WORDS) and len(words) <= 3:
        return "preview"
    if any(re.search(rf"\b{re.escape(v)}\b", low) for v in _VERSION_WORDS):
        # "Original Mix" is the same as no version.
        if low in ("original mix", "original", "original version"):
            return "original"
        return "version"
    if any(re.search(rf"\b{re.escape(n)}\b", low) for n in _NOISE_WORDS):
        return "noise"
    if _CATALOG_RE.match(text.strip()):
        return "noise"
    return "keep"


def _clean_symbols(s: str) -> str:
    s = "".join(ch for ch in s if unicodedata.category(ch)[0] not in ("S", "C") or ch in "&$|+")
    s = re.sub(r"#\w+", " ", s)                      # hashtags
    s = re.sub(r"\s+", " ", s)
    return s.strip(" -–—|:*~_.,")


_QUOTES = "'\"‘’“”‚„`´"


def _unquote(s: str) -> str:
    """"'You & Me'" -> "You & Me" (only quotes wrapped around the whole title)."""
    s = s.strip()
    while len(s) > 2 and s[0] in _QUOTES and s[-1] in _QUOTES:
        s = s[1:-1].strip()
    return s


def parse_title(raw: str, uploader: str = "", publisher_artist: str = "") -> ParsedTitle:
    p = ParsedTitle(raw=raw)
    s = raw or ""

    # Remove emoji / symbols early (keeps letters, digits, punctuation).
    s = _clean_symbols(s)

    # Drop "PREMIERE:" style prefixes (can be stacked).
    for _ in range(3):
        new = _PREFIX_RE.sub("", s)
        if new == s:
            break
        s = new

    # Everything after " | " or " // " is almost always promo text.
    s = re.split(r"\s+(?:\||//|‖)\s+", s)[0]

    # Handle bracketed segments.
    versions: list[str] = []
    def repl(m: re.Match) -> str:
        inner = next(g for g in m.groups() if g is not None)
        kind = _classify_bracket(inner)
        if kind == "version":
            versions.append(inner.strip())
            return " "
        if kind == "feat":
            p.featuring = re.sub(r"^(feat\.?|ft\.?|featuring)\s*", "", inner.strip(), flags=re.I)
            return " "
        if kind == "preview":
            p.is_preview = True
            return " "
        if kind == "keep" and m.group(0).startswith("("):
            return m.group(0)
        return " "
    for _ in range(2):
        s = _BRACKET_RE.sub(repl, s)
    s = re.sub(r"\s+", " ", s).strip(" -–—|:")

    # Split artist / title.
    parts = _DASH_RE.split(s, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        artist, title = parts[0].strip(), parts[1].strip()
    else:
        artist = (publisher_artist or uploader or "").strip()
        title = s.strip()
        p.artist_from_uploader = bool(artist)

    # Extra dash segments after the title: "Track - Someone Remix", or label / catalog
    # suffixes like "Track - Drumcode - DC360". Unknown segments stay part of the title.
    segs = [x.strip() for x in _DASH_RE.split(title) if x.strip()]
    if len(segs) > 1:
        uploader_n = normalize(uploader)
        keep = [segs[0]]
        for seg in segs[1:]:
            kind = _classify_bracket(seg)
            if kind == "version":
                versions.append(seg)
            elif kind in ("original", "noise") or (uploader_n and normalize(seg) == uploader_n):
                pass
            else:
                keep.append(seg)
        title = " - ".join(keep)

    # "feat." inside the artist or title part.
    for part_name in ("artist", "title"):
        val = artist if part_name == "artist" else title
        fp = _FEAT_RE.split(val, maxsplit=1)
        if len(fp) == 2:
            if not p.featuring:
                p.featuring = fp[1].strip()
            if part_name == "artist":
                artist = fp[0].strip()
            else:
                title = fp[0].strip()

    # Collaborations: "A x B", "A & B", "A, B" -> keep first as main, rest as extra.
    collab = re.split(r"\s+(?:x|&|and|vs\.?|with)\s+|,\s*", artist, flags=re.I)
    if len(collab) > 1:
        p.extra_artists = [c.strip() for c in collab[1:] if c.strip()]

    p.artist = _clean_symbols(artist)
    p.title = _unquote(_clean_symbols(title)) or _clean_symbols(raw)
    # Prefer the most specific version (a remix beats "Extended Mix").
    versions.sort(key=lambda v: (not version_is_different(v), len(v)))
    p.version = versions[0] if versions else ""
    return p


# DJ mixes, radio shows and sets (not to be confused with versions like "Extended Mix").
_MIX_RE = re.compile(
    r"\b(?:radio ?show|podcast|dj ?set|live ?set|hybrid ?set|mix ?tape|mixed by|guest ?mix|essential mix|"
    r"mini ?mix|mega ?mix|continuous mix|year ?mix|boiler room|takeover|episode \d+|ep \d{2,}|"
    r"live (?:at|from|in)|b2b|mix \d{2,}|podcast \d+)\b")


_MONTHS = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
# A title that ends in a date is a show or a set ("Silva Bumpa - 14 April 2026", "... 22.10.24",
# "... @ The Lot Radio 11-24-2025"); tracks don't carry dates.
_DATE_END_RE = re.compile(
    rf"(?:\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTHS}(?:\s+\d{{2,4}})?"
    rf"|\b{_MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?"
    r"|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s*\)?\s*$", re.I)
_AT_VENUE_RE = re.compile(r"\s@\s+\S")          # "Artist @ Venue": a recorded set


def is_mix(raw: str) -> bool:
    """True for uploads that look like a DJ mix, radio show or live set rather than a track."""
    raw = raw or ""
    return bool(_MIX_RE.search(normalize(raw)) or _DATE_END_RE.search(raw.strip()) or _AT_VENUE_RE.search(raw))


def search_queries(p: ParsedTitle) -> list[str]:
    """Search strings to try on Soulseek, most specific first."""
    main_artist = p.artist.split(",")[0]
    main_artist = re.split(r"\s+(?:x|&|and|vs\.?|with)\s+", main_artist, flags=re.I)[0]
    artist_t = tokens(main_artist, drop_stop=True)[:3]
    title_t = tokens(p.title, drop_stop=True)[:6] or tokens(p.title)[:6]
    remix_t = p.remixer_tokens[:2]

    queries = []
    if _non_latin(main_artist + p.title):
        # Files on Soulseek usually keep their own script: search that first.
        queries.append(_native_words(f"{main_artist} {p.title}"))
    if artist_t:
        queries.append(" ".join(artist_t + title_t + remix_t))
    queries.append(" ".join(title_t + remix_t))
    # De-duplicate, keep order, drop too-short queries (Soulseek ignores them).
    out = []
    for q in queries:
        if q and q not in out and len(q.replace(" ", "")) >= 4:
            out.append(q)
    return out
