"""Folder and file names from a template (roadmap step 10), e.g. "{channel}/{artist} - {title} ({version})"."""
from __future__ import annotations

import re
import sys

TOKENS = ("channel", "artist", "title", "version", "year", "genre")
DEFAULT_TEMPLATE = "{channel}/{artist} - {title} ({version})"
FLAT_TEMPLATE = "{artist} - {title} ({version})"        # what "no folder per channel" used to mean
SEGMENT_LIMIT = 150
MAX_PATH_WINDOWS = 250          # Windows refuses longer paths (260 with the end mark) unless long paths are switched on
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
SAMPLE = {"channel": "Nightshift Records", "artist": "Mira Kova & Delen", "title": "Night Signal",
          "version": "Extended Mix", "year": "2026", "genre": "Techno"}

_TOKEN_RE = re.compile(r"\{([^{}]*)\}")
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_EMPTY_BRACKETS = re.compile(r"\(\s*\)|\[\s*\]|\{\s*\}")
_EDGE_JUNK = re.compile(r"^[\s\-–—_.,]+|[\s\-–—_.,]+$")


def template_error(template: str) -> str:
    """'' when the template is usable, otherwise what is wrong with it (shown in Settings)."""
    t = (template or "").strip()
    if not t:
        return "The template is empty."
    if len(t) > 200:
        return "The template is too long."
    if "{title}" not in t:
        return "The template needs {title}, otherwise every track would get the same name."
    for name in _TOKEN_RE.findall(t):
        if name not in TOKENS:
            return f"Unknown {{{name}}}. You can use " + ", ".join("{" + x + "}" for x in TOKENS) + "."
    if "{" in _TOKEN_RE.sub("", t) or "}" in _TOKEN_RE.sub("", t):
        return "A { or } is missing its partner."
    return ""


def _clean_value(value: str) -> str:
    return re.sub(r"\s+", " ", _BAD_CHARS.sub(" ", str(value or ""))).strip()


def _tidy(segment: str) -> str:
    """Lost fields leave empty brackets and dangling separators behind: remove them."""
    prev = None
    while prev != segment:
        prev = segment
        segment = _EMPTY_BRACKETS.sub(" ", segment)
        segment = re.sub(r"\s+", " ", segment)
        segment = re.sub(r"(?:\s[-–—]\s)(?:\s?[-–—]\s)+", " - ", segment)     # " -  - " after a lost field
        segment = _EDGE_JUNK.sub("", segment)
    segment = segment[:SEGMENT_LIMIT].strip(" .")
    if segment.split(".")[0].strip().upper() in _RESERVED:      # Windows can't create a file or folder called CON, NUL, COM1...
        segment = "_" + segment
    return segment


def render(template: str, fields: dict) -> list[str]:
    """Path parts for a track: folders first, the file name (no extension) last. A folder that comes
    out empty is dropped; an empty file name falls back to the title."""
    if template_error(template):
        template = DEFAULT_TEMPLATE
    values = {k: _clean_value(fields.get(k, "")) for k in TOKENS}
    parts = []
    for raw in re.split(r"[\\/]", template.strip()):
        seg = _TOKEN_RE.sub(lambda m: values.get(m.group(1), ""), raw)
        parts.append(_tidy(seg))
    name = parts.pop() if parts else ""
    folders = [p for p in parts if p]
    return folders + [name or values["title"] or "track"]


def fit_name(folder: str, base: str, ext: str, limit: int | None = None) -> str:
    """Shorten a file name (without extension) so that folder + name + extension stays under the path limit.
    Only Windows has a limit that matters; elsewhere (limit 0) the name is returned as it is."""
    if limit is None:
        limit = MAX_PATH_WINDOWS if sys.platform.startswith("win") else 0
    if not limit:
        return base
    room = limit - len(folder) - 1 - len(ext) - 5       # 5: room for " (99)" when a file with that name exists
    if len(base) <= room:
        return base
    return base[:max(room, 12)].rstrip(" .") or "track"


def example(template: str) -> str:
    """The template filled with a sample track, for the Settings page."""
    return "/".join(render(template, SAMPLE)) + ".flac"
