"""Score Soulseek search results against a wanted track."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .titles import DIFFERENT_VERSION_WORDS, ParsedTitle, tokens, version_is_different

LOSSLESS = {"flac", "wav", "aiff", "aif", "alac"}
ALLOWED_EXT = LOSSLESS | {"mp3", "m4a"}


@dataclass
class Candidate:
    username: str
    filename: str                 # full remote path as returned by the peer
    size: int = 0
    ext: str = ""
    bitrate: Optional[int] = None  # kbps
    duration: Optional[int] = None  # seconds
    has_free_slots: bool = False
    queue_size: int = 0
    avg_speed: int = 0            # bytes/s
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)

    @property
    def basename(self) -> str:
        return re.split(r"[\\/]", self.filename)[-1]

    @property
    def parent(self) -> str:
        parts = re.split(r"[\\/]", self.filename)
        return parts[-2] if len(parts) > 1 else ""


@dataclass
class MatchPrefs:
    preferred_format: str = "lossless"   # "lossless" or "mp3"
    min_bitrate: int = 320
    duration_tolerance: int = 8          # seconds that still count as "same length"


# Spam peers advertise a website in their username or file names and answer every search
# with fake files that never leave the queue (e.g. "https://www.rawzik.com").
_DOMAIN_RE = re.compile(
    r"https?://|www\.|\b[a-z0-9-]+\.(?:com|net|org|info|biz|ru|io|xyz|club|top|site|online|fm)\b",
    re.I)
# Faster than any real peer; a peer claiming this is lying about its speed.
MAX_PLAUSIBLE_SPEED = 50_000_000   # bytes/s


# DJ-pool edits (The Mash Up, Club Killers, ...) mark their versions in brackets:
# "(TMU Extended Mix) (Clean)", "(Intro)", "(Quick Hit)". Those aren't the release.
_POOL_WORDS = {"clean", "dirty", "intro", "outro", "tmu", "quickhit", "transition", "redrum", "hype", "acap"}
_POOL_PHRASES = ("quick hit", "short edit", "acapella in", "acapella out", "slam edit", "club killers", "dj tools")
_BRACKETS_RE = re.compile(r"[(\[]([^()\[\]]*)[)\]]")


def pool_edit_words(basename: str) -> set[str]:
    """DJ-pool markers found inside brackets of a file name."""
    found = set()
    for inner in _BRACKETS_RE.findall(basename):
        low = " ".join(tokens(inner))
        found |= {w for w in low.split() if w in _POOL_WORDS}
        found |= {ph for ph in _POOL_PHRASES if ph in low}
    return found


def is_spam(c: "Candidate") -> bool:
    return bool(_DOMAIN_RE.search(c.username) or _DOMAIN_RE.search(c.basename))


def file_ext(filename: str) -> str:
    m = re.search(r"\.([A-Za-z0-9]{2,5})$", filename)
    return m.group(1).lower() if m else ""


def score_candidate(target: ParsedTitle, target_duration: Optional[float], c: Candidate,
                    prefs: MatchPrefs) -> Optional[float]:
    """Return a score (higher = better) or None if the file is not a match."""
    reasons: list[str] = []
    ext = (c.ext or file_ext(c.filename)).lower().lstrip(".")
    if not ext:
        ext = file_ext(c.filename)
    c.ext = ext
    if ext not in ALLOWED_EXT:
        return None
    if is_spam(c):
        return None
    if c.size and c.size < 1_000_000:
        return None

    name = c.basename.rsplit(".", 1)[0]
    name_t = set(tokens(name))
    path_t = name_t | set(tokens(c.parent))

    # 1. Title words must be in the file name.
    title_t = tokens(target.title, drop_stop=True) or tokens(target.title)
    if not title_t:
        return None
    missing = [t for t in title_t if t not in name_t]
    allowed_missing = 1 if len(title_t) >= 4 else 0
    if len(missing) > allowed_missing:
        return None
    score = 40.0 - 10 * len(missing)

    # 2. Artist words: anywhere in file name or parent folder.
    artist_t = tokens(target.artist, drop_stop=True)
    if artist_t:
        frac = sum(t in path_t for t in artist_t) / len(artist_t)
        if frac == 0 and not target.artist_from_uploader:
            # A different artist with the same title is a different track.
            extra_t = [t for a in target.extra_artists for t in tokens(a, drop_stop=True)]
            if not any(t in path_t for t in extra_t):
                return None
        score += 25 * frac
        if frac < 1:
            reasons.append("artist partly in name")

    # 3. Version (remix / edit / extended). DJ-pool edits only when that's what we want.
    target_words = set(tokens(target.version)) | set(tokens(target.title))
    pool = pool_edit_words(c.basename)
    if any(not set(w.split()) <= target_words for w in pool):
        return None

    file_versions = {t for t in name_t if t in DIFFERENT_VERSION_WORDS} - set(title_t)
    if target.version and version_is_different(target.version):
        remixer = target.remixer_tokens
        if remixer and not all(t in name_t for t in remixer):
            return None
        score += 10
    elif file_versions:
        # We want the original, this file is a remix/bootleg/etc.
        return None
    target_v = set(tokens(target.version))
    if "extended" in name_t:
        score += 6 if "extended" in target_v else 3
    if "radio" in name_t and "radio" not in target_v:
        score -= 12
        reasons.append("radio edit")
    if "edit" in name_t and "edit" not in target_v and "radio" not in name_t:
        score -= 6

    # 4. Duration.
    if target_duration and c.duration:
        diff = abs(c.duration - target_duration)
        longer_ok = "extended" in name_t and c.duration > target_duration
        if diff <= 3:
            score += 15
        elif diff <= prefs.duration_tolerance:
            score += 8
        elif diff <= 25 or longer_ok:
            score -= 5
        elif diff <= 60:
            score -= 20
            reasons.append(f"length differs {int(diff)}s")
        else:
            return None

    # 5. Format & quality.
    if ext in LOSSLESS:
        score += 30 if prefs.preferred_format == "lossless" else 15
    elif ext == "mp3":
        if c.bitrate and c.bitrate < prefs.min_bitrate:
            return None
        if c.bitrate:
            score += 30 if prefs.preferred_format == "mp3" else 20
        else:
            score += 12
            reasons.append("bitrate unknown")
    else:  # m4a / aac
        if prefs.min_bitrate >= 320:
            return None
        score += 5

    # 6. Will the peer actually send it soon?
    if c.has_free_slots:
        score += 15
    else:
        reasons.append("peer queue")
    score -= min(c.queue_size, 50) * 0.4
    if c.avg_speed <= MAX_PLAUSIBLE_SPEED:
        score += min(c.avg_speed / 1_000_000, 1.0) * 10

    c.score = round(score, 1)
    c.reasons = reasons
    return c.score


def rank(target: ParsedTitle, target_duration: Optional[float], candidates: list[Candidate],
         prefs: MatchPrefs) -> list[Candidate]:
    scored = []
    seen = set()
    for c in candidates:
        key = (c.username, c.filename)
        if key in seen:
            continue
        seen.add(key)
        if score_candidate(target, target_duration, c, prefs) is not None:
            scored.append(c)
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored
