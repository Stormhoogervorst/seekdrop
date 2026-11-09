"""Quality profiles and the quality ladder (roadmap step 4).

A file's *tier* is a rung on the ladder below. A profile is an ordered list of the tiers it accepts
(best first; anything not listed is under the floor) plus a target: once a track reaches the target,
the app stops looking for a better copy.
"""
from __future__ import annotations

from typing import Optional

LOSSLESS_TIERS = ("flac24", "flac16", "wav")

TIER_LABELS = {
    "flac24": "FLAC 24-bit",
    "flac16": "FLAC 16-bit",
    "wav": "WAV/AIFF",
    "mp3_320": "MP3 320",
    "mp3_256": "MP3 256",
    "mp3_192": "MP3 192",
    "mp3_low": "MP3 under 192",
    "other": "Other format",
}

PROFILES = {
    "club": {
        "label": "Club",
        "help": "Lossless. MP3 320 is the minimum; the app keeps looking for a lossless copy.",
        "order": ["flac24", "flac16", "wav", "mp3_320"],
        "target": "wav",          # any lossless
    },
    "balanced": {
        "label": "Balanced",
        "help": "MP3 320 or better. MP3 256 is the minimum.",
        "order": ["flac24", "flac16", "wav", "mp3_320", "mp3_256"],
        "target": "mp3_320",
    },
    "space": {
        "label": "Space saver",
        "help": "MP3 320 or 256; MP3 192 is the minimum. Lossless only if there is nothing else.",
        "order": ["mp3_320", "mp3_256", "mp3_192", "flac16", "wav", "flac24"],
        "target": "mp3_256",
    },
}
DEFAULT_PROFILE = "club"
UPGRADE_DAYS = 30              # keep looking for a better copy this long after a track first came in
UPGRADE_EVERY = 24 * 3600      # how often a track below its target is searched again


def profile(name: str) -> dict:
    return PROFILES.get(name) or PROFILES[DEFAULT_PROFILE]


def tier_of(ext: str, bitrate_kbps: Optional[float] = None, bit_depth: Optional[int] = None) -> Optional[str]:
    """Tier from what is known about a file. None for an MP3 whose bitrate is unknown."""
    ext = (ext or "").lower().lstrip(".")
    if ext == "flac":
        return "flac24" if (bit_depth or 0) >= 24 else "flac16"
    if ext in ("wav", "aiff", "aif", "alac"):
        return "wav"
    if ext == "mp3":
        if not bitrate_kbps:
            return None
        if bitrate_kbps >= 300:
            return "mp3_320"
        if bitrate_kbps >= 240:
            return "mp3_256"
        if bitrate_kbps >= 180:
            return "mp3_192"
        return "mp3_low"
    return "other"


def position(prof: dict, tier: Optional[str]) -> Optional[int]:
    """0 = best in this profile; None = not accepted (under the floor)."""
    try:
        return prof["order"].index(tier)
    except ValueError:
        return None


def candidate_position(prof: dict, ext: str, bitrate_kbps: Optional[float], bit_depth: Optional[int]) -> Optional[int]:
    """Position for a search result. An MP3 without a bitrate counts as the lowest MP3 the profile
    accepts; the file is measured after download anyway."""
    t = tier_of(ext, bitrate_kbps, bit_depth)
    if t is None:
        mp3s = [x for x in prof["order"] if x.startswith("mp3_")]
        return position(prof, mp3s[-1]) if mp3s else None
    return position(prof, t)


def wants_upgrade(prof: dict, tier: Optional[str]) -> bool:
    """Below the target and lossy: worth looking for a better copy. Lossless never gets swapped for
    lossy, even in a profile that ranks MP3 first."""
    if not tier or tier in LOSSLESS_TIERS:
        return False
    pos, target = position(prof, tier), position(prof, prof["target"])
    return pos is None or (target is not None and pos > target)


def is_better(prof: dict, new: Optional[str], old: Optional[str]) -> bool:
    pn, po = position(prof, new), position(prof, old)
    if pn is None:
        return False
    return po is None or pn < po


def profile_from_old_settings(preferred_format: str, min_bitrate: int) -> str:
    """Settings from before profiles existed."""
    if preferred_format == "mp3":
        return "space" if (min_bitrate or 320) <= 192 else "balanced"
    return "club"
