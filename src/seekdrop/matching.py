"""Score Soulseek search results against a wanted track."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .quality import TIER_LABELS, DEFAULT_PROFILE, candidate_position, profile, tier_of
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
    sample_rate: Optional[int] = None  # Hz, when the peer sends it
    bit_depth: Optional[int] = None    # bits, when the peer sends it
    has_free_slots: bool = False
    queue_size: int = 0
    avg_speed: int = 0            # bytes/s
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    rejected: str = ""            # why it isn't a match ("" = accepted), shown under "Why not?"
    stage: int = 0                # how far it got before being rejected (higher = closer to a match)

    @property
    def basename(self) -> str:
        return re.split(r"[\\/]", self.filename)[-1]

    @property
    def parent(self) -> str:
        parts = re.split(r"[\\/]", self.filename)
        return parts[-2] if len(parts) > 1 else ""


@dataclass
class MatchPrefs:
    profile: str = DEFAULT_PROFILE       # quality profile (quality.PROFILES)
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


# Rejection stages: the later a file is turned down, the closer it was to a match.
STAGE_FILE, STAGE_TITLE, STAGE_ARTIST, STAGE_VERSION, STAGE_LENGTH, STAGE_QUALITY, STAGE_OK = range(7)


def _mmss(sec: float) -> str:
    sec = int(round(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def _reject(c: Candidate, stage: int, why: str) -> None:
    c.rejected, c.stage, c.score = why, stage, 0.0
    return None


def score_candidate(target: ParsedTitle, target_duration: Optional[float], c: Candidate,
                    prefs: MatchPrefs) -> Optional[float]:
    """Return a score (higher = better) or None if the file is not a match; then c.rejected says why."""
    reasons: list[str] = []
    c.rejected, c.stage = "", STAGE_OK
    ext = (c.ext or file_ext(c.filename)).lower().lstrip(".")
    if not ext:
        ext = file_ext(c.filename)
    c.ext = ext
    if ext not in ALLOWED_EXT:
        return _reject(c, STAGE_FILE, f"Format not used (.{ext})" if ext else "Not an audio file")
    if is_spam(c):
        return _reject(c, STAGE_FILE, "Spam peer (advertises a website)")
    if c.size and c.size < 1_000_000:
        return _reject(c, STAGE_FILE, "File too small to be the track")

    name = c.basename.rsplit(".", 1)[0]
    name_t = set(tokens(name))
    path_t = name_t | set(tokens(c.parent))

    # 1. Title words must be in the file name.
    title_t = tokens(target.title, drop_stop=True) or tokens(target.title)
    if not title_t:
        return _reject(c, STAGE_FILE, "No title to compare with")
    missing = [t for t in title_t if t not in name_t]
    allowed_missing = 1 if len(title_t) >= 4 else 0
    if len(missing) > allowed_missing:
        return _reject(c, STAGE_TITLE, f"Title doesn't match (missing: {', '.join(missing)})")
    score = 40.0 - 10 * len(missing)

    # 2. Artist words: anywhere in file name or parent folder.
    artist_t = tokens(target.artist, drop_stop=True)
    if artist_t:
        frac = sum(t in path_t for t in artist_t) / len(artist_t)
        if frac == 0 and not target.artist_from_uploader:
            # A different artist with the same title is a different track.
            extra_t = [t for a in target.extra_artists for t in tokens(a, drop_stop=True)]
            if not any(t in path_t for t in extra_t):
                return _reject(c, STAGE_ARTIST, "Different artist")
        score += 25 * frac
        if frac < 1:
            reasons.append("artist partly in name")

    # 3. Version (remix / edit / extended). DJ-pool edits only when that's what we want.
    target_words = set(tokens(target.version)) | set(tokens(target.title))
    pool = pool_edit_words(c.basename)
    bad_pool = [w for w in pool if not set(w.split()) <= target_words]
    if bad_pool:
        return _reject(c, STAGE_VERSION, f"DJ-pool edit ({', '.join(sorted(bad_pool))})")

    file_versions = {t for t in name_t if t in DIFFERENT_VERSION_WORDS} - set(title_t)
    if target.version and version_is_different(target.version):
        remixer = target.remixer_tokens
        if remixer and not all(t in name_t for t in remixer):
            return _reject(c, STAGE_VERSION, f"Not the {target.version}")
        score += 10
    elif file_versions:
        # We want the original, this file is a remix/bootleg/etc.
        return _reject(c, STAGE_VERSION, f"This is a {'/'.join(sorted(file_versions))}, you want the original")
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
            hint = " (radio edit?)" if c.duration < target_duration else ""
            return _reject(c, STAGE_LENGTH, f"{_mmss(c.duration)} long, expected {_mmss(target_duration)}{hint}")

    # 5. Format & quality: the profile's ladder. Under the floor = not a match.
    prof = profile(prefs.profile)
    pos = candidate_position(prof, ext, c.bitrate, c.bit_depth)
    if pos is None:
        have = TIER_LABELS.get(tier_of(ext, c.bitrate, c.bit_depth) or "", ext.upper())
        if ext == "mp3" and c.bitrate:
            have = f"{c.bitrate} kbps"
        return _reject(c, STAGE_QUALITY, f"{have}, under your minimum ({TIER_LABELS[prof['order'][-1]]})")
    score += (len(prof["order"]) - pos) * 10
    if ext == "mp3" and not c.bitrate:
        score -= 8
        reasons.append("bitrate unknown")

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


def closest(evaluated: list[Candidate], n: int = 10) -> list[Candidate]:
    """For "Why not?": accepted files by score, then rejected ones that came closest to a match."""
    ok = sorted([c for c in evaluated if not c.rejected], key=lambda c: c.score, reverse=True)
    near = sorted([c for c in evaluated if c.rejected], key=lambda c: (c.stage, c.has_free_slots, c.size), reverse=True)
    return (ok + near)[:n]


def summary(results: int, evaluated: list[Candidate], queries: list[str]) -> str:
    """One line for a track that didn't get a match."""
    if not results:
        return "No results for " + ", ".join(f"'{q}'" for q in queries) if queries else "No results on Soulseek"
    best = closest(evaluated, 1)
    if best and best[0].rejected:
        return f"{results} results, none matched: closest was {best[0].rejected[0].lower()}{best[0].rejected[1:]}"
    return f"{results} results, none matched"


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
