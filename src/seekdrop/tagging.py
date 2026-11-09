"""Tags, artwork and WAV to AIFF (roadmap step 10), applied to the staged file after every check passed.

Written for DJ software: ID3v2.3 on MP3, ID3 inside AIFF, Vorbis comments plus a picture on FLAC,
MP4 tags on M4A. Fields we manage are always set or cleared; everything else the uploader embedded
(BPM, key, ...) stays. We never calculate BPM or key: the DJ software does that better."""
from __future__ import annotations

import logging
import os
import re
import struct
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

log = logging.getLogger(__name__)

MIN_COVER_PX = 500
MAX_COVER_BYTES = 8 * 1024 * 1024
COVER_HOSTS = ("sndcdn.com", "soundcloud.com")      # artwork only comes from SoundCloud's own CDN
TAGGABLE = {"mp3", "flac", "aiff", "aif", "wav", "m4a", "mp4"}


@dataclass
class TagMeta:
    artist: str = ""
    title: str = ""            # with the version in it: "Track (Extended Mix)"
    genre: str = ""
    year: str = ""
    label: str = ""
    comment: str = ""          # the SoundCloud link


# --- images ------------------------------------------------------------------------------------

def image_info(data: bytes) -> Optional[tuple[int, int, str]]:
    """(width, height, mime) of a JPEG or PNG, or None when it isn't one."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24])
        return w, h, "image/png"
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h, "image/jpeg"
            i += 2 + length
    return None


def cover_urls(url: str) -> list[str]:
    """SoundCloud artwork links to try, biggest sensible one first (the app stores the 300 px link)."""
    if not url:
        return []
    big = re.sub(r"-(?:t\d+x\d+|large|crop|mini|tiny|small|badge|original)\.", "-t500x500.", url)
    return [big, url] if big != url else [url]


def _allowed(url: str) -> bool:
    p = urllib.parse.urlparse(url)
    host = (p.hostname or "").lower()
    return p.scheme == "https" and any(host == h or host.endswith("." + h) for h in COVER_HOSTS)


def fetch_cover(url: str, opener: Optional[Callable] = None, timeout: float = 10.0) -> Optional[bytes]:
    """Download SoundCloud artwork. Returns the image bytes or None; never raises."""
    best = None
    for u in cover_urls(url):
        if not _allowed(u):
            log.info("not fetching artwork from %s", urllib.parse.urlparse(u).hostname)
            continue
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "SeekDrop"})
            with (opener or urllib.request.urlopen)(req, timeout=timeout) as r:
                data = r.read(MAX_COVER_BYTES + 1)
        except Exception as e:
            log.info("artwork download failed (%s): %s", u, e)
            continue
        info = image_info(data) if len(data) <= MAX_COVER_BYTES else None
        if not info:
            continue
        if min(info[0], info[1]) >= MIN_COVER_PX:
            return data
        if best is None or min(info[:2]) > min(image_info(best)[:2]):
            best = data
    return best


# --- tags --------------------------------------------------------------------------------------

def _id3_cover_px(tags) -> int:
    best = 0
    for apic in tags.getall("APIC"):
        info = image_info(bytes(apic.data))
        best = max(best, min(info[:2]) if info else 0)
    return best


def _write_id3(tags, meta: TagMeta, cover: Optional[bytes]) -> None:
    from mutagen import id3
    for key in ("TPE1", "TIT2", "TALB", "TPUB", "TCON", "TDRC", "TYER", "TDAT", "TIME", "TRDA"):
        tags.delall(key)
    tags.delall("COMM")
    enc = 1                                         # UTF-16: the one Unicode encoding ID3v2.3 has
    if meta.artist:
        tags.add(id3.TPE1(encoding=enc, text=meta.artist))
    if meta.title:
        tags.add(id3.TIT2(encoding=enc, text=meta.title))
    if meta.label:
        tags.add(id3.TPUB(encoding=enc, text=meta.label))
    if meta.genre:
        tags.add(id3.TCON(encoding=enc, text=meta.genre))
    if meta.year:
        tags.add(id3.TDRC(encoding=enc, text=meta.year))
    if meta.comment:
        tags.add(id3.COMM(encoding=enc, lang="eng", desc="", text=meta.comment))
    if cover:
        info = image_info(cover)
        if info and (_id3_cover_px(tags) < min(info[:2]) or not tags.getall("APIC")):
            tags.delall("APIC")
            tags.add(id3.APIC(encoding=enc, mime=info[2], type=3, desc="Cover", data=cover))


def _tag_id3_file(path: str, ext: str, meta: TagMeta, cover: Optional[bytes]) -> None:
    from mutagen import id3
    if ext == "mp3":
        try:
            tags = id3.ID3(path)
        except id3.ID3NoHeaderError:
            tags = id3.ID3()
        _write_id3(tags, meta, cover)
        tags.save(path, v2_version=3)
        return
    if ext in ("aiff", "aif"):
        from mutagen.aiff import AIFF
        f = AIFF(path)
    else:
        from mutagen.wave import WAVE
        f = WAVE(path)
    if f.tags is None:
        f.add_tags()
    _write_id3(f.tags, meta, cover)
    f.save(v2_version=3)


def _tag_flac(path: str, meta: TagMeta, cover: Optional[bytes]) -> None:
    from mutagen.flac import FLAC, Picture
    f = FLAC(path)
    for key in ("artist", "title", "album", "label", "publisher", "organization", "genre", "date", "year", "comment"):
        if key in f:
            del f[key]
    for key, value in (("artist", meta.artist), ("title", meta.title), ("label", meta.label), ("genre", meta.genre),
                       ("date", meta.year), ("comment", meta.comment)):
        if value:
            f[key] = value
    info = image_info(cover) if cover else None
    have = max((min(p.width, p.height) for p in f.pictures), default=0)
    if info and (have < min(info[:2]) or not f.pictures):
        pic = Picture()
        pic.type, pic.mime, pic.desc, pic.data = 3, info[2], "Cover", cover
        pic.width, pic.height, pic.depth = info[0], info[1], 24
        f.clear_pictures()
        f.add_picture(pic)
    f.save()


def _tag_mp4(path: str, meta: TagMeta, cover: Optional[bytes]) -> None:
    from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm
    f = MP4(path)
    if f.tags is None:
        f.add_tags()
    t = f.tags
    for key in ("\xa9ART", "\xa9nam", "\xa9alb", "\xa9gen", "\xa9day", "\xa9cmt", "----:com.apple.iTunes:LABEL"):
        if key in t:
            del t[key]
    if meta.artist:
        t["\xa9ART"] = [meta.artist]
    if meta.title:
        t["\xa9nam"] = [meta.title]
    if meta.genre:
        t["\xa9gen"] = [meta.genre]
    if meta.year:
        t["\xa9day"] = [meta.year]
    if meta.comment:
        t["\xa9cmt"] = [meta.comment]
    if meta.label:
        t["----:com.apple.iTunes:LABEL"] = [MP4FreeForm(meta.label.encode("utf-8"))]
    info = image_info(cover) if cover else None
    have = max((min(image_info(bytes(c))[:2]) for c in t.get("covr", []) if image_info(bytes(c))), default=0)
    if info and (have < min(info[:2]) or "covr" not in t):
        fmt = MP4Cover.FORMAT_PNG if info[2] == "image/png" else MP4Cover.FORMAT_JPEG
        t["covr"] = [MP4Cover(cover, imageformat=fmt)]
    f.save()


def tag_file(path: str, meta: TagMeta, cover: Optional[bytes] = None) -> None:
    """Write the tags (and the cover, unless the file already has a bigger one) into the file."""
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in ("mp3", "aiff", "aif", "wav"):
        _tag_id3_file(path, ext, meta, cover)
    elif ext == "flac":
        _tag_flac(path, meta, cover)
    elif ext in ("m4a", "mp4"):
        _tag_mp4(path, meta, cover)
    else:
        raise ValueError(f"can't write tags into .{ext} files")


# --- WAV to AIFF -------------------------------------------------------------------------------

class NotConvertible(Exception):
    """This WAV can't be converted without changing its audio (float, 8 bit, ...): keep it as WAV."""


def _extended80(rate: int) -> bytes:
    """A whole sample rate as the 80-bit extended float AIFF uses."""
    e = rate.bit_length() - 1
    return struct.pack(">HQ", 16383 + e, rate << (63 - e))


def _read_wav_header(f) -> tuple[int, int, int, int, int]:
    """(channels, rate, bits, data offset, data size) of a PCM WAV."""
    head = f.read(12)
    if len(head) < 12 or head[:4] not in (b"RIFF", b"RF64") or head[8:12] != b"WAVE":
        raise NotConvertible("not a RIFF WAVE file")
    fmt = None
    while True:
        hdr = f.read(8)
        if len(hdr) < 8:
            raise NotConvertible("no audio data found")
        cid, size = hdr[:4], struct.unpack("<I", hdr[4:])[0]
        if cid == b"fmt ":
            body = f.read(size + (size & 1))
            tag, ch, rate, _br, _ba, bits = struct.unpack("<HHIIHH", body[:16])
            if tag == 0xFFFE and len(body) >= 26:
                tag = struct.unpack("<H", body[24:26])[0]       # the real format is in the sub-format GUID
            fmt = (tag, ch, rate, bits)
        elif cid == b"data":
            if fmt is None:
                raise NotConvertible("data before format")
            tag, ch, rate, bits = fmt
            if tag != 1:
                raise NotConvertible("not integer PCM (float or compressed)")
            if bits not in (16, 24, 32):
                raise NotConvertible(f"{bits}-bit audio")
            if not 1 <= ch <= 8 or not 1 <= rate <= 768_000:
                raise NotConvertible("unusual channel count or sample rate")
            pos = f.tell()
            f.seek(0, os.SEEK_END)
            available = f.tell() - pos
            f.seek(pos)
            if size == 0xFFFFFFFF or size > available:         # streamed or cut-off header: use what is there
                size = available
            size -= size % (ch * bits // 8)                    # whole frames only
            return ch, rate, bits, pos, size
        else:
            f.seek(size + (size & 1), os.SEEK_CURRENT)


def wav_to_aiff(src: str, dst: str) -> None:
    """Rewrite an integer-PCM WAV as AIFF with exactly the same samples (little to big endian).
    Raises NotConvertible when that isn't possible; nothing is left behind then."""
    import numpy as np
    tmp = dst + ".part"
    try:
        with open(src, "rb") as f, open(tmp, "wb") as out:
            ch, rate, bits, pos, size = _read_wav_header(f)
            width = bits // 8
            frames = size // (ch * width)
            if size + 100 >= 2 ** 32:
                raise NotConvertible("too big for AIFF")
            pad = size & 1
            comm = struct.pack(">hIh", ch, frames, bits) + _extended80(rate)
            ssnd_len = 8 + size
            form_len = 4 + 8 + len(comm) + 8 + ssnd_len + pad
            out.write(b"FORM" + struct.pack(">I", form_len) + b"AIFF")
            out.write(b"COMM" + struct.pack(">I", len(comm)) + comm)
            out.write(b"SSND" + struct.pack(">I", ssnd_len) + struct.pack(">II", 0, 0))
            f.seek(pos)
            block = ch * width * 16384
            left = size
            while left > 0:
                chunk = f.read(min(block, left))
                if not chunk:
                    raise NotConvertible("the file ended early")
                left -= len(chunk)
                if width == 3:
                    out.write(np.frombuffer(chunk, dtype=np.uint8).reshape(-1, 3)[:, ::-1].tobytes())
                else:
                    out.write(np.frombuffer(chunk, dtype=f"<u{width}").byteswap().tobytes())
            if pad:
                out.write(b"\x00")
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
