"""A Rekordbox XML for the tracks SeekSync downloaded (roadmap step 12).

Rekordbox reads this file through Preferences > Advanced > Database > rekordbox xml. SeekSync only ever
writes this one file; Rekordbox' own database is never touched. The file holds every finished download as
a track and one playlist per channel or playlist, inside a folder called "SeekSync"."""
from __future__ import annotations

import os
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from . import fsutil
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote, unquote

DEFAULT_NAME = "SeekSync for Rekordbox.xml"
FOLDER = "SeekSync"
KINDS = {"mp3": "MP3 File", "flac": "FLAC File", "wav": "WAV File", "aiff": "AIFF File", "aif": "AIFF File",
         "m4a": "M4A File", "mp4": "M4A File"}
_BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
# Characters Rekordbox leaves as they are in a Location (found in its own export code). Everything else is
# percent-encoded, so that our file names look exactly like the ones Rekordbox writes itself.
_SAFE = "/!#$()*+,:;=?@"


def clean(text) -> str:
    """Text that is safe inside an XML attribute: no control characters, no broken Unicode."""
    return _BAD_XML.sub("", str(text or "").encode("utf-8", "ignore").decode("utf-8"))


# --- paths -------------------------------------------------------------------------------------

def location(path: str) -> str:
    """The Location attribute: file://localhost/ plus the path, percent-encoded the way Rekordbox does it
    (Windows drive letters included)."""
    p = os.path.abspath(path) if not _DRIVE.match(path) else path
    if _DRIVE.match(p):
        return "file://localhost/" + quote(p.replace("\\", "/"), safe=_SAFE)
    return "file://localhost" + quote(p, safe=_SAFE)


def path_from_location(url: str) -> str:
    """Inverse of location(): the file path a Location points to (also for what Rekordbox itself exports)."""
    s = unquote(url or "")
    for prefix in ("file://localhost", "file://"):
        if s.lower().startswith(prefix):
            s = s[len(prefix):]
            break
    if re.match(r"^/[A-Za-z]:[\\/]", s):
        s = s[1:]
    return s


# --- one track ---------------------------------------------------------------------------------

@dataclass
class Track:
    track_id: int
    path: str
    name: str                       # title with the version in it: "Track (Extended Mix)"
    artist: str = ""
    genre: str = ""
    year: str = ""
    label: str = ""
    comment: str = ""
    added: float = 0.0
    size: int = 0
    seconds: int = 0
    bitrate: int = 0
    sample_rate: int = 0
    kind: str = ""


@dataclass
class Playlist:
    name: str
    track_ids: list[int] = field(default_factory=list)


def file_facts(path: str, cache: Optional[dict] = None) -> dict:
    """Size, length, bitrate, sample rate and kind of an audio file. Read once per (path, size, mtime)."""
    st = os.stat(path)
    key = (path, st.st_size, st.st_mtime_ns)
    if cache is not None and key in cache:
        return cache[key]
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    facts = {"size": st.st_size, "seconds": 0, "bitrate": 0, "sample_rate": 0, "kind": KINDS.get(ext, "")}
    try:
        import mutagen
        f = mutagen.File(path)
        if f is not None:
            info = f.info
            facts["seconds"] = int(round(getattr(info, "length", 0) or 0))
            br = getattr(info, "bitrate", 0) or 0
            facts["bitrate"] = int(br / 1000) if br > 2000 else int(br)
            facts["sample_rate"] = int(getattr(info, "sample_rate", 0) or 0)
    except Exception:
        pass
    if cache is not None:
        cache[key] = facts
    return facts


# --- the file ----------------------------------------------------------------------------------

def build(tracks: list[Track], playlists: list[Playlist], version: str = "") -> ET.ElementTree:
    root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
    ET.SubElement(root, "PRODUCT", Name="SeekSync", Version=clean(version), Company="SeekSync")
    coll = ET.SubElement(root, "COLLECTION", Entries=str(len(tracks)))
    for t in tracks:
        attrs = {"TrackID": str(t.track_id), "Name": clean(t.name), "Artist": clean(t.artist)}
        if t.genre:
            attrs["Genre"] = clean(t.genre)
        if t.kind:
            attrs["Kind"] = t.kind
        attrs["Size"] = str(t.size)
        attrs["TotalTime"] = str(t.seconds)
        if t.year:
            attrs["Year"] = clean(t.year)
        if t.added:
            attrs["DateAdded"] = time.strftime("%Y-%m-%d", time.localtime(t.added))
        if t.bitrate:
            attrs["BitRate"] = str(t.bitrate)
        if t.sample_rate:
            attrs["SampleRate"] = str(t.sample_rate)
        if t.comment:
            attrs["Comments"] = clean(t.comment)
        attrs["Location"] = location(t.path)
        if t.label:
            attrs["Label"] = clean(t.label)
        ET.SubElement(coll, "TRACK", attrs)

    nodes = ET.SubElement(root, "PLAYLISTS")
    top = ET.SubElement(nodes, "NODE", Type="0", Name="ROOT", Count="1")
    folder = ET.SubElement(top, "NODE", Type="0", Name=FOLDER, Count=str(len(playlists)))
    for pl in playlists:
        node = ET.SubElement(folder, "NODE", Name=clean(pl.name), Type="1", KeyType="0", Entries=str(len(pl.track_ids)))
        for tid in pl.track_ids:
            ET.SubElement(node, "TRACK", Key=str(tid))
    ET.indent(root, space="  ")
    return ET.ElementTree(root)


def unique_names(names: list[str]) -> list[str]:
    """Playlist names must differ inside a folder: the second "Label" becomes "Label (2)"."""
    seen: dict[str, int] = {}
    out = []
    for raw in names:
        name = clean(raw).strip() or "Untitled"
        seen[name.lower()] = seen.get(name.lower(), 0) + 1
        out.append(name if seen[name.lower()] == 1 else f"{name} ({seen[name.lower()]})")
    return out


def write(path: str, tracks: list[Track], playlists: list[Playlist], version: str = "") -> None:
    """Write the XML so that the file appears in one go: a hidden temporary file next to it, then a rename.
    If anything goes wrong the previous file stays as it was."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    tmp = os.path.join(folder, "." + os.path.basename(path) + ".seeksync-part")
    try:
        body = ET.tostring(build(tracks, playlists, version).getroot(), encoding="unicode")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n")      # the declaration the way Rekordbox writes it
        fsutil.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


# --- reading (tests, and Rekordbox exports in a later step) ------------------------------------

def read(path: str) -> dict:
    """What a Rekordbox XML holds: {"tracks": {id: {attribute: value}}, "playlists": [(name, [ids])]}.
    Works for this file and for the collection export Rekordbox itself makes."""
    root = ET.parse(path).getroot()
    tracks = {}
    coll = root.find("COLLECTION")
    for t in (coll if coll is not None else []):
        tracks[int(t.get("TrackID", "0"))] = dict(t.attrib)
    playlists = []

    def walk(node):
        for n in node.findall("NODE"):
            if n.get("Type") == "1":
                playlists.append((n.get("Name", ""), [int(k.get("Key")) for k in n.findall("TRACK")]))
            else:
                walk(n)
    top = root.find("PLAYLISTS")
    if top is not None:
        walk(top)
    return {"tracks": tracks, "playlists": playlists}


# --- which files Rekordbox already has ---------------------------------------------------------

def normalize_path(path: str) -> str:
    """A path in a form that two spellings of the same file share: one kind of slash, composed Unicode
    (macOS stores accents decomposed, Rekordbox writes them composed) and no difference in case (the usual
    file systems of DJ computers don't tell them apart)."""
    p = unicodedata.normalize("NFC", str(path or "")).replace("\\", "/")
    return re.sub(r"/+", "/", p).rstrip("/").casefold()


def collection_paths(xml_path: str) -> set[str]:
    """The file paths in a Rekordbox collection export (Rekordbox: File, Export Collection in xml format),
    normalised for comparison. Only reads the file."""
    return {normalize_path(path_from_location(t.get("Location", "")))
            for t in read(xml_path)["tracks"].values() if t.get("Location")}


def has_file(known: set[str], path: str) -> bool:
    """Is this file one of the paths in `known`? Also checks the spelling with symbolic links resolved."""
    if normalize_path(os.path.abspath(path)) in known:
        return True
    try:
        return normalize_path(os.path.realpath(path)) in known
    except OSError:
        return False
