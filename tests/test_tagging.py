"""Roadmap step 10: tags, artwork, WAV to AIFF and file name templates.
Audio is generated locally (hand-built MP3 frames, FLAC stream info, WAV samples) and covers come from a
fake downloader: no network. Tests that need real encoders use ffmpeg and are skipped without it."""
import asyncio
import json
import os
import shutil
import sqlite3
import struct
import subprocess
import wave
import zlib

import numpy as np
import pytest

from seeksync import naming, tagging
from seeksync.checks import Tools
from seeksync.config import Settings, SettingsStore
from seeksync.db import Database
from seeksync.matching import Candidate
from seeksync.soundcloud import SoundCloudClient

from test_engine import FakeSlsk, _fresh_track, setup  # noqa: F401  (fixture + fakes)

TOOLS = Tools.find()
needs_ffmpeg = pytest.mark.skipif(not TOOLS.available, reason="ffmpeg/ffprobe not installed")
META = tagging.TagMeta(artist="Mira Kova & Delen", title="Night Signal (Extended Mix)", genre="Techno", year="2026",
                       label="Nightshift Records", comment="https://soundcloud.com/x/night-signal")


# --- generated files ---------------------------------------------------------------------------

def png(w, h):
    """A valid grey PNG of the given size (compresses to almost nothing)."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x80" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def jpeg_header(w, h):
    return b"\xff\xd8\xff\xe0\x00\x04\x00\x00\xff\xc0\x00\x11\x08" + struct.pack(">HH", h, w) + b"\x03" + b"\x00" * 9


def fake_mp3(path, id3=None):
    frame = b"\xff\xfb\x90\x00" + b"\x00" * 413                     # MPEG-1 Layer III, 128 kbps, 44.1 kHz
    with open(path, "wb") as f:
        f.write(frame * 40)
    if id3:
        from mutagen.id3 import ID3
        tags = ID3()
        for frame in id3:
            tags.add(frame)
        tags.save(path, v2_version=3)


def fake_flac(path):
    info = struct.pack(">HH", 4096, 4096) + b"\0\0\0" + b"\0\0\0"
    info += struct.pack(">Q", (44100 << 44) | (1 << 41) | (15 << 36) | 441000) + b"\0" * 16
    with open(path, "wb") as f:
        f.write(b"fLaC" + bytes([0x80]) + struct.pack(">I", 34)[1:] + info)


def make_wav(path, bits=16, channels=2, rate=44100, frames=3000, seed=1):
    rng = np.random.default_rng(seed)
    top = 2 ** (bits - 1) - 1
    data = rng.integers(-top, top, size=frames * channels, dtype=np.int64)
    if bits == 16:
        raw = data.astype("<i2").tobytes()
    elif bits == 32:
        raw = data.astype("<i4").tobytes()
    else:
        raw = b"".join(int(v).to_bytes(3, "little", signed=True) for v in data)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(bits // 8)
        w.setframerate(rate)
        w.writeframes(raw)
    return raw


def read_aiff(path):
    """Independent little AIFF reader: (channels, frames, bits, rate, sample bytes in big endian)."""
    data = open(path, "rb").read()
    assert data[:4] == b"FORM" and data[8:12] == b"AIFF"
    assert struct.unpack(">I", data[4:8])[0] == len(data) - 8, "FORM size must match the file"
    pos, comm, ssnd = 12, None, None
    while pos + 8 <= len(data):
        kind, size = data[pos:pos + 4], struct.unpack(">I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if kind == b"COMM":
            ch, frames, bits = struct.unpack(">hIh", body[:8])
            exp, mant = struct.unpack(">HQ", body[8:18])
            comm = (ch, frames, bits, mant >> (63 - (exp - 16383)))
        elif kind == b"SSND":
            ssnd = body[8:]
        pos += 8 + size + (size & 1)
    return (*comm, ssnd)


# --- images and covers -------------------------------------------------------------------------

def test_image_size_of_png_and_jpeg():
    assert tagging.image_info(png(640, 480)) == (640, 480, "image/png")
    assert tagging.image_info(jpeg_header(500, 500)) == (500, 500, "image/jpeg")
    assert tagging.image_info(b"not an image") is None


def test_cover_urls_prefer_500px():
    u = "https://i1.sndcdn.com/artworks-abc-def-t300x300.jpg"
    assert tagging.cover_urls(u) == ["https://i1.sndcdn.com/artworks-abc-def-t500x500.jpg", u]
    assert tagging.cover_urls("https://i1.sndcdn.com/x-t500x500.jpg") == ["https://i1.sndcdn.com/x-t500x500.jpg"]
    assert tagging.cover_urls("") == []


class Opener:
    """A fake urlopen: serves what it is given per URL and remembers what was asked."""

    def __init__(self, files):
        self.files, self.asked = files, []

    def __call__(self, req, timeout=0):
        self.asked.append(req.full_url)
        body = self.files.get(req.full_url)
        if body is None:
            raise OSError("404")
        return _Resp(body)


class _Resp:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self.body if n < 0 else self.body[:n]


def test_cover_download_takes_the_big_one_and_only_from_soundcloud():
    small, big = "https://i1.sndcdn.com/a-t300x300.jpg", "https://i1.sndcdn.com/a-t500x500.jpg"
    op = Opener({small: png(300, 300), big: png(500, 500)})
    got = tagging.fetch_cover(small, opener=op)
    assert tagging.image_info(got)[:2] == (500, 500) and op.asked == [big]

    # the big one isn't there: the 300 px one is the best we have, and it is used
    op = Opener({small: png(300, 300)})
    assert tagging.image_info(tagging.fetch_cover(small, opener=op))[:2] == (300, 300)

    # artwork from anywhere else is never fetched
    op = Opener({"https://evil.example.com/a.png": png(600, 600), "http://i1.sndcdn.com/a.png": png(600, 600)})
    assert tagging.fetch_cover("https://evil.example.com/a.png", opener=op) is None
    assert tagging.fetch_cover("http://i1.sndcdn.com/a.png", opener=op) is None
    assert op.asked == []

    # not an image, too big, or a failing download: no cover and no exception
    assert tagging.fetch_cover(small, opener=Opener({big: b"<html>", small: b"<html>"})) is None
    assert tagging.fetch_cover(small, opener=Opener({})) is None
    huge = png(10, 10) + b"\0" * (tagging.MAX_COVER_BYTES + 5)
    assert tagging.fetch_cover(big, opener=Opener({big: huge})) is None


# --- tags --------------------------------------------------------------------------------------

def test_mp3_gets_id3v23_tags_and_cover_and_keeps_bpm_and_key(tmp_path):
    from mutagen import id3
    from mutagen.id3 import ID3
    p = tmp_path / "a.mp3"
    fake_mp3(p, [id3.TPE1(encoding=3, text="Wrong Artist"), id3.TALB(encoding=3, text="Wrong Album"),
                 id3.TBPM(encoding=3, text="128"), id3.TKEY(encoding=3, text="Am"),
                 id3.COMM(encoding=3, lang="eng", desc="", text="ripped by somebody")])
    tagging.tag_file(str(p), META, png(600, 600))
    tags = ID3(str(p))
    assert tags.version == (2, 3, 0)
    assert str(tags["TPE1"]) == "Mira Kova & Delen" and str(tags["TIT2"]) == "Night Signal (Extended Mix)"
    assert str(tags["TCON"]) == "Techno" and str(tags["TPUB"]) == "Nightshift Records"
    assert str(tags.get("TYER") or tags.get("TDRC")) == "2026"
    assert [str(c) for c in tags.getall("COMM")] == ["https://soundcloud.com/x/night-signal"]
    assert "TALB" not in tags                               # a wrong album from the uploader is gone
    assert str(tags["TBPM"]) == "128" and str(tags["TKEY"]) == "Am"     # their BPM and key stay
    apic = tags.getall("APIC")
    assert len(apic) == 1 and apic[0].type == 3 and tagging.image_info(bytes(apic[0].data))[:2] == (600, 600)
    # and it is readable as an MP3 afterwards
    from mutagen.mp3 import MP3
    assert MP3(str(p)).info.sample_rate == 44100


def test_unicode_survives_in_id3v23(tmp_path):
    from mutagen.id3 import ID3
    p = tmp_path / "a.mp3"
    fake_mp3(p)
    tagging.tag_file(str(p), tagging.TagMeta(artist="Björk & Дельфин", title="Café 夜"), None)
    tags = ID3(str(p))
    assert str(tags["TPE1"]) == "Björk & Дельфин" and str(tags["TIT2"]) == "Café 夜"
    assert tags.version == (2, 3, 0) and "APIC" not in tags


def test_flac_gets_vorbis_comments_and_picture(tmp_path):
    from mutagen.flac import FLAC
    p = tmp_path / "a.flac"
    fake_flac(p)
    f = FLAC(str(p))
    f["album"], f["bpm"] = "Wrong Album", "126"
    f.save()
    tagging.tag_file(str(p), META, png(500, 500))
    f = FLAC(str(p))
    assert f["artist"] == ["Mira Kova & Delen"] and f["title"] == ["Night Signal (Extended Mix)"]
    assert f["genre"] == ["Techno"] and f["date"] == ["2026"] and f["label"] == ["Nightshift Records"]
    assert f["comment"] == ["https://soundcloud.com/x/night-signal"]
    assert "album" not in f and f["bpm"] == ["126"]
    assert len(f.pictures) == 1 and f.pictures[0].type == 3 and (f.pictures[0].width, f.pictures[0].height) == (500, 500)


def test_an_existing_big_cover_stays_and_a_small_one_is_replaced(tmp_path):
    from mutagen.flac import FLAC, Picture

    def with_cover(path, px):
        fake_flac(path)
        f = FLAC(str(path))
        pic = Picture()
        pic.type, pic.mime, pic.data, pic.width, pic.height = 3, "image/png", png(px, px), px, px
        f.add_picture(pic)
        f.save()

    keep = tmp_path / "keep.flac"
    with_cover(keep, 700)
    tagging.tag_file(str(keep), META, png(500, 500))
    assert [p.width for p in FLAC(str(keep)).pictures] == [700]

    swap = tmp_path / "swap.flac"
    with_cover(swap, 300)
    tagging.tag_file(str(swap), META, png(500, 500))
    assert [p.width for p in FLAC(str(swap)).pictures] == [500]

    none = tmp_path / "none.flac"                   # no cover on SoundCloud and none in the file: still tagged
    fake_flac(none)
    tagging.tag_file(str(none), META, None)
    assert FLAC(str(none))["artist"] == ["Mira Kova & Delen"] and not FLAC(str(none)).pictures


def test_aiff_gets_id3_inside_the_file(tmp_path):
    from mutagen.aiff import AIFF
    wav, aiff = tmp_path / "a.wav", tmp_path / "a.aiff"
    make_wav(wav)
    tagging.wav_to_aiff(str(wav), str(aiff))
    tagging.tag_file(str(aiff), META, png(500, 500))
    f = AIFF(str(aiff))
    assert str(f.tags["TPE1"]) == "Mira Kova & Delen" and str(f.tags["TIT2"]) == "Night Signal (Extended Mix)"
    assert len(f.tags.getall("APIC")) == 1
    assert (f.info.channels, f.info.sample_rate, f.info.bits_per_sample) == (2, 44100, 16)
    # the audio is still all there after tagging
    assert read_aiff(aiff)[1] == 3000


def test_unknown_format_is_refused(tmp_path):
    p = tmp_path / "a.ogg"
    p.write_bytes(b"x")
    with pytest.raises(ValueError):
        tagging.tag_file(str(p), META, None)


@needs_ffmpeg
def test_real_encoded_files_are_tagged_and_still_play(tmp_path):
    from mutagen import File
    src = ["-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-ar", "44100", "-ac", "2"]
    for name, extra in (("a.mp3", ["-b:a", "256k"]), ("a.flac", []), ("a.aiff", []), ("a.m4a", ["-c:a", "aac"])):
        subprocess.run([TOOLS.ffmpeg, "-v", "error", "-y", *src, *extra, str(tmp_path / name)], check=True, timeout=60)
        tagging.tag_file(str(tmp_path / name), META, png(500, 500))
        f = File(str(tmp_path / name))
        assert f is not None, name
        out = subprocess.run([TOOLS.ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              str(tmp_path / name)], capture_output=True, text=True, timeout=30)
        assert 2.5 < float(out.stdout.strip()) < 3.6, name         # tagging didn't damage the audio
        if name == "a.m4a":
            assert f.tags["\xa9ART"] == ["Mira Kova & Delen"] and f.tags["\xa9nam"] == ["Night Signal (Extended Mix)"]
            assert len(f.tags["covr"]) == 1
        elif name == "a.flac":
            assert f["artist"] == ["Mira Kova & Delen"] and len(f.pictures) == 1
        else:
            assert str(f.tags["TPE1"]) == "Mira Kova & Delen" and len(f.tags.getall("APIC")) == 1


# --- WAV to AIFF -------------------------------------------------------------------------------

@pytest.mark.parametrize("bits,channels,frames", [(16, 2, 3001), (24, 2, 777), (32, 2, 500), (24, 1, 1001), (16, 1, 5)])
def test_wav_becomes_aiff_with_the_same_samples(tmp_path, bits, channels, frames):
    from mutagen.aiff import AIFF
    wav, aiff = tmp_path / "a.wav", tmp_path / "a.aiff"
    raw = make_wav(wav, bits=bits, channels=channels, frames=frames, rate=48000)
    tagging.wav_to_aiff(str(wav), str(aiff))
    ch, n, b, rate, big = read_aiff(aiff)
    assert (ch, n, b, rate) == (channels, frames, bits, 48000)
    width = bits // 8
    little = b"".join(big[i:i + width][::-1] for i in range(0, len(big) - len(big) % width, width))
    assert little == raw                                    # exactly the same PCM data, only the byte order differs
    info = AIFF(str(aiff)).info                             # and an independent parser agrees
    assert (info.channels, info.sample_rate, info.bits_per_sample) == (channels, 48000, bits)
    assert not (tmp_path / "a.aiff.part").exists()


@needs_ffmpeg
def test_decoded_audio_is_identical_before_and_after(tmp_path):
    wav, aiff = tmp_path / "a.wav", tmp_path / "a.aiff"
    make_wav(wav, bits=24, frames=20000)
    tagging.wav_to_aiff(str(wav), str(aiff))
    out = []
    for f in (wav, aiff):
        r = subprocess.run([TOOLS.ffmpeg, "-v", "error", "-i", str(f), "-f", "s32le", "-"], capture_output=True, timeout=60)
        out.append(r.stdout)
    assert out[0] == out[1] and len(out[0]) > 0


def test_extensible_wav_is_converted_too(tmp_path):
    """24-bit audio is often written with the WAVE_FORMAT_EXTENSIBLE header."""
    pcm = bytes(range(256)) * 12                                  # 3072 bytes = 512 stereo frames of 24 bit
    fmt = struct.pack("<HHIIHH", 0xFFFE, 2, 44100, 44100 * 6, 6, 24) + struct.pack("<HHI", 22, 24, 3) \
        + struct.pack("<H", 1) + b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71"
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(pcm)) + pcm
    wav = tmp_path / "x.wav"
    wav.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    tagging.wav_to_aiff(str(wav), str(tmp_path / "x.aiff"))
    assert read_aiff(tmp_path / "x.aiff")[:4] == (2, 512, 24, 44100)


def test_float_and_8_bit_wav_stay_wav_and_leave_nothing_behind(tmp_path):
    for tag, bits in ((3, 32), (1, 8)):                          # IEEE float, and unsigned 8 bit
        pcm = b"\x00" * 800
        fmt = struct.pack("<HHIIHH", tag, 2, 44100, 44100 * 2 * bits // 8, 2 * bits // 8, bits)
        body = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(pcm)) + pcm
        wav = tmp_path / f"w{bits}.wav"
        wav.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
        with pytest.raises(tagging.NotConvertible):
            tagging.wav_to_aiff(str(wav), str(tmp_path / f"w{bits}.aiff"))
    assert sorted(os.listdir(tmp_path)) == ["w32.wav", "w8.wav"]
    junk = tmp_path / "junk.wav"
    junk.write_bytes(b"this is not a wav file at all")
    with pytest.raises(tagging.NotConvertible):
        tagging.wav_to_aiff(str(junk), str(tmp_path / "junk.aiff"))


# --- the engine --------------------------------------------------------------------------------

def _download_as(slsk, writer):
    """Make the fake peer deliver a file written by `writer(path)`."""
    def info(t):
        writer(t.path)
        return {"state": "COMPLETE", "bytes": 10, "size": 10, "local_path": t.path, "place_in_queue": None, "fail_reason": ""}
    slsk.transfer_info = info


def _run_download(eng, db, t, filename="@@a\\Fresh Artist - Brand New.flac"):
    db.update_track(t["id"], state="downloading")
    asyncio.run(eng._download(db.track(t["id"]), [Candidate("peer", filename)]))
    return db.track(t["id"])


def _ready(eng, db, sc, monkeypatch, cover=png(500, 500)):
    eng.settings.tag_files = True
    t = _fresh_track(eng, db, sc)
    db.update_track(t["id"], url="https://soundcloud.com/lbl/fresh", artwork="https://i1.sndcdn.com/a-t300x300.jpg",
                    uploaded_at=1767225600,                                  # 1 Jan 2026
                    sc_meta=json.dumps({"genre": "Techno", "released_at": 1735689600}))   # 1 Jan 2025
    monkeypatch.setattr(tagging, "fetch_cover", lambda url, **kw: cover)
    return t


def test_a_published_download_has_its_tags_and_cover(setup, monkeypatch):
    from mutagen.flac import FLAC
    eng, db, sc, slsk, tmp = setup
    t = _ready(eng, db, sc, monkeypatch)
    _download_as(slsk, fake_flac)
    done = _run_download(eng, db, t)
    assert done["state"] == "done"
    f = FLAC(done["file_path"])
    assert f["artist"] == ["Fresh Artist"] and f["title"] == ["Brand New"] and f["genre"] == ["Techno"]
    assert f["date"] == ["2025"]                                    # the release date wins over the upload date
    assert f["comment"] == ["https://soundcloud.com/lbl/fresh"] and len(f.pictures) == 1
    assert "label" not in f                                         # off unless asked for
    assert os.listdir(tmp / "staging") == []                        # nothing is left in staging


def test_label_is_the_channel_name_only_when_asked_and_only_for_profiles(setup, monkeypatch):
    eng, db, sc, slsk, tmp = setup
    t = _ready(eng, db, sc, monkeypatch)
    assert eng._tag_meta(db.track(t["id"])).label == ""
    eng.settings.label_from_channel = True
    assert eng._tag_meta(db.track(t["id"])).label == "Label"
    db.update_channel(t["channel_id"], kind="playlist")
    assert eng._tag_meta(db.track(t["id"])).label == ""


def test_a_file_that_cant_be_tagged_is_published_anyway_with_a_warning(setup, monkeypatch):
    eng, db, sc, slsk, tmp = setup
    t = _ready(eng, db, sc, monkeypatch)
    _download_as(slsk, lambda p: open(p, "wb").write(b"not a real flac"))
    done = _run_download(eng, db, t)
    assert done["state"] == "done" and os.path.exists(done["file_path"])
    assert any("Couldn't write tags" in a["msg"] for a in eng.activity)


def test_a_cover_that_doesnt_load_still_gives_tags(setup, monkeypatch):
    from mutagen.flac import FLAC
    eng, db, sc, slsk, tmp = setup
    t = _ready(eng, db, sc, monkeypatch, cover=None)
    _download_as(slsk, fake_flac)
    done = _run_download(eng, db, t)
    f = FLAC(done["file_path"])
    assert f["artist"] == ["Fresh Artist"] and not f.pictures
    assert any("cover couldn't be downloaded" in a["msg"] for a in eng.activity)


def test_tagging_can_be_turned_off(setup, monkeypatch):
    from mutagen.flac import FLAC
    eng, db, sc, slsk, tmp = setup
    t = _ready(eng, db, sc, monkeypatch)
    eng.settings.tag_files = False
    _download_as(slsk, fake_flac)
    done = _run_download(eng, db, t)
    assert "artist" not in FLAC(done["file_path"])


def test_wav_is_published_as_tagged_aiff_when_the_setting_is_on(setup, monkeypatch):
    from mutagen.aiff import AIFF
    eng, db, sc, slsk, tmp = setup
    t = _ready(eng, db, sc, monkeypatch)
    eng.settings.wav_to_aiff = True
    raw = {}
    _download_as(slsk, lambda p: raw.setdefault("pcm", make_wav(p, bits=24, frames=2000)))
    done = _run_download(eng, db, t, "@@a\\Fresh Artist - Brand New.wav")
    assert done["state"] == "done" and done["file_path"].endswith("Fresh Artist - Brand New.aiff")
    out = sorted(os.listdir(os.path.dirname(done["file_path"])))
    assert out == ["Fresh Artist - Brand New.aiff"]                 # the WAV is gone, no leftovers
    f = AIFF(done["file_path"])
    assert str(f.tags["TPE1"]) == "Fresh Artist" and len(f.tags.getall("APIC")) == 1
    ch, n, bits, rate, big = read_aiff(done["file_path"])
    assert (ch, n, bits) == (2, 2000, 24) and len(big) == len(raw["pcm"])
    assert done["tier"] == "wav"                                    # same rung of the quality ladder


def test_wav_stays_wav_when_the_setting_is_off(setup, monkeypatch):
    eng, db, sc, slsk, tmp = setup
    t = _ready(eng, db, sc, monkeypatch)
    _download_as(slsk, lambda p: make_wav(p))
    done = _run_download(eng, db, t, "@@a\\Fresh Artist - Brand New.wav")
    assert done["file_path"].endswith(".wav")


def test_approving_a_quarantined_file_tags_it_too(setup, monkeypatch):
    from mutagen.flac import FLAC
    eng, db, sc, slsk, tmp = setup
    t = _ready(eng, db, sc, monkeypatch)
    eng.quarantine_dir = str(tmp / "quarantine")
    eng.checks.append(lambda track, path: "30 s of silence at the end")
    _download_as(slsk, fake_flac)
    _run_download(eng, db, t)
    rid = db.quarantined()[0]["id"]
    path = eng.approve_reject(rid)
    assert FLAC(path)["artist"] == ["Fresh Artist"]


def test_new_downloads_store_genre_and_release_date_from_soundcloud(setup):
    from seeksync.soundcloud import TrackInfo, TrackStub
    eng, db, sc, slsk, tmp = setup
    sc.tracks = [TrackStub("1", "https://soundcloud.com/lbl/a", "Artist - One"), TrackStub("2", "https://soundcloud.com/lbl/b", "Artist - Two")]
    sc.track = lambda url: TrackInfo(url[-1], url, "Artist - One" if url.endswith("a") else "Artist - Two", duration=300,
                                     uploaded_at=1.0, genre="House" if url.endswith("a") else "", released_at=1735689600.0 if url.endswith("a") else None)
    cid = db.add_channel("https://soundcloud.com/lbl", "Label", False, backlog=5)
    asyncio.run(eng.check_channel(cid))
    metas = {t["sc_id"]: t["sc_meta"] for t in db.tracks()}
    assert json.loads(metas["1"]) == {"genre": "House", "released_at": 1735689600.0}
    assert metas["2"] == ""


def test_soundcloud_client_reads_genre_and_release_date():
    class FakeYdl:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download=False, process=False):
            return {"id": 7, "title": "Track", "uploader": "Up", "artists": ["Art"], "duration": 301, "timestamp": 5,
                    "genres": ["Techno", "Dance"], "release_timestamp": 1735689600, "webpage_url": url, "thumbnails": []}

    client = SoundCloudClient()
    client._ydl = lambda **kw: FakeYdl()
    info = client.track("https://soundcloud.com/a/b")
    assert (info.genre, info.released_at, info.publisher_artist) == ("Techno", 1735689600, "Art")


def test_old_database_gets_the_sc_meta_column(tmp_path):
    path = tmp_path / "old.db"
    db = Database(path)
    db.conn.close()
    con = sqlite3.connect(path)
    con.execute("ALTER TABLE tracks DROP COLUMN sc_meta")
    con.commit()
    con.close()
    db = Database(path)
    cid = db.add_channel("u", "n", False, 0)
    tid = db.add_track(channel_id=cid, sc_id="a")
    assert db.track(tid)["sc_meta"] == ""


# --- file name templates -----------------------------------------------------------------------

T = naming.DEFAULT_TEMPLATE


def parts(template, **kw):
    f = {"channel": "Label", "artist": "Artist", "title": "Title", "version": "", "year": "", "genre": ""}
    f.update(kw)
    return naming.render(template, f)


def test_default_template_gives_the_old_names():
    assert parts(T) == ["Label", "Artist - Title"]
    assert parts(T, version="Extended Mix") == ["Label", "Artist - Title (Extended Mix)"]
    assert parts(naming.FLAT_TEMPLATE, version="Dub") == ["Artist - Title (Dub)"]


def test_missing_fields_leave_no_junk():
    assert parts(T, artist="") == ["Label", "Title"]
    assert parts(T, channel="") == ["Artist - Title"]
    assert parts("{artist} - {title} [{year}] ({genre})") == ["Artist - Title"]
    assert parts("{year}/{genre}/{artist} - {title}", year="2026") == ["2026", "Artist - Title"]
    assert parts("{channel} - {artist} - {title}", channel="") == ["Artist - Title"]


def test_templates_can_use_year_and_genre():
    assert parts("{genre}/{year}/{artist} - {title}", genre="Techno", year="2026") == ["Techno", "2026", "Artist - Title"]
    assert parts("{year} - {artist} - {title} ({version})", year="2026", version="VIP") == ["2026 - Artist - Title (VIP)"]


def test_unsafe_characters_never_make_folders_or_escape():
    assert parts(T, artist="AC/DC", title='Who? "Me": <x>|*') == ["Label", "AC DC - Who Me x"]
    assert parts("../{artist} - {title}") == ["Artist - Title"]          # '..' is dropped
    assert naming.render("../../{title}", {"title": "T"}) == ["T"]
    assert naming.render("/{title}", {"title": "T"}) == ["T"]
    assert len(naming.render("{title}", {"title": "x" * 400})[-1]) <= naming.SEGMENT_LIMIT


def test_bad_templates_are_explained_and_fall_back():
    assert naming.template_error(T) == ""
    assert "needs {title}" in naming.template_error("{artist}")
    assert "Unknown {bpm}" in naming.template_error("{title} {bpm}")
    assert "partner" in naming.template_error("{title} {")
    assert naming.template_error("   ") and naming.template_error("{title}" * 60)
    # an unusable template never produces odd names: the default is used instead
    assert naming.render("{artist}", {"artist": "A", "title": "T"}) == ["A - T"]
    assert naming.render("{nope} {title}", {"channel": "C", "artist": "A", "title": "T"}) == ["C", "A - T"]


def test_example_for_the_settings_page():
    assert naming.example(T) == "Nightshift Records/Mira Kova & Delen - Night Signal (Extended Mix).flac"
    assert naming.example("{year}/{genre}/{title}") == "2026/Techno/Night Signal.flac"


def test_old_checkbox_becomes_a_template(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"organize_by_channel": False, "download_dir": "/x"}))
    assert SettingsStore(path).settings.filename_template == naming.FLAT_TEMPLATE
    path.write_text(json.dumps({"organize_by_channel": True}))
    assert SettingsStore(path).settings.filename_template == T
    path.write_text(json.dumps({"organize_by_channel": False, "filename_template": "{title}"}))
    assert SettingsStore(path).settings.filename_template == "{title}"        # an explicit template wins


def test_settings_defaults_and_validation(tmp_path):
    s = Settings()
    assert (s.tag_files, s.wav_to_aiff, s.label_from_channel, s.filename_template) == (True, False, False, T)
    store = SettingsStore(tmp_path / "s.json")
    store.update({"filename_template": "{year}/{artist} - {title}", "wav_to_aiff": 1})
    assert store.settings.filename_template == "{year}/{artist} - {title}" and store.settings.wav_to_aiff is True
    store.update({"filename_template": "{nonsense}"})                     # refused: the old one stays
    assert store.settings.filename_template == "{year}/{artist} - {title}"


def test_api_explains_a_bad_template_and_previews_a_good_one(setup):
    from seeksync.server import Api

    class Req:
        def __init__(self, data):
            self._d, self.query, self.match_info = data, {}, {}

        async def json(self):
            return self._d

    eng, db, sc, slsk, tmp = setup
    api = Api(eng, db, token="t")
    bad = asyncio.run(api.put_settings(Req({"filename_template": "{artist}"})))
    assert bad.status == 400 and "needs {title}" in json.loads(bad.text)["error"]
    assert eng.settings.filename_template == T
    ok = json.loads(asyncio.run(api.template_preview(Req({"template": "{genre}/{title}"}))).text)
    assert ok == {"error": "", "example": "Techno/Night Signal.flac"}
    err = json.loads(asyncio.run(api.template_preview(Req({"template": "{title} {x}"}))).text)
    assert "Unknown {x}" in err["error"] and err["example"] == ""
    good = asyncio.run(api.put_settings(Req({"filename_template": "{genre}/{title}"})))
    assert good.status == 200 and eng.settings.filename_template == "{genre}/{title}"


def test_published_files_follow_the_template(setup, monkeypatch):
    eng, db, sc, slsk, tmp = setup
    t = _ready(eng, db, sc, monkeypatch)
    eng.settings.tag_files = False
    eng.settings.filename_template = "{genre}/{year} - {artist} - {title}"
    _download_as(slsk, fake_flac)
    done = _run_download(eng, db, t)
    assert done["file_path"] == str(tmp / "out" / "Techno" / "2025 - Fresh Artist - Brand New.flac")
    # a second file with the same name gets (2) instead of overwriting
    db.update_track(t["id"], state="downloading")
    asyncio.run(eng._download(db.track(t["id"]), [Candidate("peer", "@@a\\Fresh Artist - Brand New.flac")]))
    assert db.track(t["id"])["file_path"].endswith("Brand New (2).flac")
