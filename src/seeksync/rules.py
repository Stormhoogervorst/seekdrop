"""Which uploads are wanted (roadmap step 9): rules per channel or playlist plus a global blocklist.

`check()` returns the reason an upload is skipped, or "" when it is wanted. Pure functions, no
network and no database, so they are easy to test."""
from __future__ import annotations

import json
from typing import Optional

from .matching import version_of
from .titles import ParsedTitle, is_mix, normalize

DEFAULT_RULES = {
    "min_minutes": 2,         # shorter uploads are clips and snippets
    "max_minutes": 12,        # longer ones are mixes and sets
    "remixes": True,          # False: skip remixes, reworks, refixes, flips and bootlegs
    "skip_previews": True,    # "(Clip)", "(Preview)", "(Snippet)" ...
    "skip_mixes": True,       # radio shows, podcasts, DJ sets (titles.is_mix)
    "exclude": [],            # words or phrases that skip a track ("live at", "podcast")
    "require": [],            # when set, only tracks with at least one of these words are wanted
}
MIN_LIMIT, MAX_LIMIT = 0, 600     # minutes
MAX_WORDS, MAX_WORD_LEN = 50, 60

# skip_rule on a track (db): '' = not skipped by a rule, OVERRIDDEN = the user fetched it anyway
# (rules never skip it again), anything else = the reason a rule skipped it.
OVERRIDDEN = "overridden"
REMIX_KINDS = ("remix", "bootleg")


def clean_words(value) -> list[str]:
    """A list or a text with one word or phrase per line -> clean list (no blanks or duplicates)."""
    if isinstance(value, str):
        value = value.splitlines()
    out: list[str] = []
    for v in value or []:
        v = " ".join(str(v).split())[:MAX_WORD_LEN]
        if v and v.lower() not in (o.lower() for o in out):
            out.append(v)
    return out[:MAX_WORDS]


def clean_rules(data: Optional[dict]) -> dict:
    """Validated rules from user input; missing or invalid fields fall back to the defaults."""
    data = data if isinstance(data, dict) else {}
    r = json.loads(json.dumps(DEFAULT_RULES))
    for key in ("min_minutes", "max_minutes"):
        try:
            r[key] = min(max(int(data[key]), MIN_LIMIT), MAX_LIMIT) if key in data else r[key]
        except (TypeError, ValueError):
            pass
    for key in ("remixes", "skip_previews", "skip_mixes"):
        if key in data:
            r[key] = bool(data[key])
    for key in ("exclude", "require"):
        if key in data:
            r[key] = clean_words(data[key])
    if r["max_minutes"] and r["min_minutes"] > r["max_minutes"]:      # 0 = no maximum
        r["min_minutes"], r["max_minutes"] = r["max_minutes"], r["min_minutes"]
    return r


def parse_rules(stored: str | dict | None) -> dict:
    """Rules as stored in channels.rules ('' = defaults)."""
    if isinstance(stored, str):
        try:
            stored = json.loads(stored) if stored.strip() else {}
        except ValueError:
            stored = {}
    return clean_rules(stored)


def dump_rules(rules: dict) -> str:
    return json.dumps(clean_rules(rules), sort_keys=True)


def _has_phrase(text: str, phrase: str) -> bool:
    p = normalize(phrase)
    return bool(p) and f" {p} " in f" {text} "


def _mmss(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 60}:{s % 60:02d}"


def check(rules: dict, p: ParsedTitle, raw_title: str, duration: Optional[float] = None,
          block_keywords: Optional[list[str]] = None, block_artists: Optional[list[str]] = None) -> str:
    """The reason this upload is skipped, or '' when it is wanted. The global blocklist goes first
    and wins over the rules of the channel."""
    text = normalize(raw_title)
    for kw in block_keywords or []:
        if _has_phrase(text, kw):
            return f"Blocked word: {kw}"
    names = normalize(" ".join([p.artist, *p.extra_artists]))
    for artist in block_artists or []:
        if _has_phrase(names, artist) or _has_phrase(text, artist):
            return f"Blocked artist: {artist}"

    for kw in rules["exclude"]:
        if _has_phrase(text, kw):
            return f"Excluded word: {kw}"
    if rules["require"] and not any(_has_phrase(text, kw) for kw in rules["require"]):
        return "Missing a required word (" + ", ".join(rules["require"][:3]) + ")"

    if rules["skip_previews"] and p.is_preview:
        return "Preview or clip"
    if duration:
        low, high = rules["min_minutes"] * 60, rules["max_minutes"] * 60
        if high and duration > high:
            return f"Longer than {rules['max_minutes']} minutes ({_mmss(duration)})"
        if low and duration < low:
            return f"Shorter than {rules['min_minutes']} minutes ({_mmss(duration)})"
    if rules["skip_mixes"] and is_mix(raw_title):
        return "Looks like a mix"
    if not rules["remixes"] and p.version and version_of(p.version).kind in REMIX_KINDS:
        return "Remixes are turned off for this channel"
    return ""


def summary(rules: dict) -> str:
    """One short line for the channel bar."""
    lo, hi = rules["min_minutes"], rules["max_minutes"]
    bits = [f"{lo} to {hi} min" if lo and hi else f"under {hi} min" if hi else f"over {lo} min" if lo else "any length"]
    if not rules["remixes"]:
        bits.append("no remixes")
    if not rules["skip_mixes"]:
        bits.append("mixes allowed")
    if not rules["skip_previews"]:
        bits.append("previews allowed")
    if rules["exclude"]:
        bits.append(f"{len(rules['exclude'])} excluded")
    if rules["require"]:
        bits.append(f"{len(rules['require'])} required")
    return ", ".join(bits)
