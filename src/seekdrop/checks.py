"""File checks on a downloaded file before it may enter the music folder (roadmap step 2).

Uses ffprobe/ffmpeg when they are installed. Without them the checks are skipped and the app
says so in Settings; nothing else depends on them.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# GUI apps on macOS don't get the shell's PATH, so also look where Homebrew & co. install.
_EXTRA_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/opt/local/bin")

# What each extension must contain: (container names ffprobe may report, audio codecs).
_EXPECTED = {
    "flac": ({"flac"}, {"flac"}),
    "mp3": ({"mp3"}, {"mp3"}),
    "wav": ({"wav"}, None),     # any PCM codec
    "aiff": ({"aiff"}, None),
    "aif": ({"aiff"}, None),
    "m4a": ({"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}, {"aac", "alac"}),
    "alac": ({"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}, {"alac"}),
}
_FRIENDLY = {"flac": "FLAC", "mp3": "MP3", "wav": "WAV", "aiff": "AIFF", "aac": "AAC", "alac": "ALAC",
             "vorbis": "Ogg Vorbis", "opus": "Opus", "wmav2": "WMA"}

SILENCE_NOISE_DB = -60          # quieter than this counts as silence
CUT_OFF_SECONDS = 2.0           # decoded audio this much shorter than the header says = cut off


def find_tool(name: str) -> Optional[str]:
    found = shutil.which(name)
    if found:
        return found
    for d in _EXTRA_DIRS:
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


@dataclass
class Tools:
    ffmpeg: Optional[str] = None
    ffprobe: Optional[str] = None

    @property
    def available(self) -> bool:
        return bool(self.ffmpeg and self.ffprobe)

    @classmethod
    def find(cls) -> "Tools":
        return cls(find_tool("ffmpeg"), find_tool("ffprobe"))


@dataclass
class Analysis:
    container: str = ""                 # e.g. "flac", "mp3", "mov,mp4,m4a,3gp,3g2,mj2"
    codec: str = ""
    bit_rate: Optional[int] = None      # bits/s as the file claims (used for MP3s)
    header_duration: Optional[float] = None
    decoded_duration: Optional[float] = None
    errors: list[str] = field(default_factory=list)
    silences: list[tuple[float, Optional[float]]] = field(default_factory=list)   # (start, end)


def _fmt(sec: float) -> str:
    sec = int(round(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def analyse(path: str, tools: Tools, silence_seconds: float, timeout: float = 120) -> Analysis:
    """One ffprobe call (container, codec, header length) and one full decode with silencedetect."""
    a = Analysis()
    out = subprocess.run(
        [tools.ffprobe, "-v", "error", "-show_entries", "format=format_name,duration,bit_rate:stream=codec_type,codec_name,bit_rate",
         "-of", "json", path], capture_output=True, text=True, timeout=timeout)
    try:
        info = json.loads(out.stdout or "{}")
    except ValueError:
        info = {}
    fmt = info.get("format") or {}
    a.container = fmt.get("format_name") or ""
    try:
        a.header_duration = float(fmt["duration"])
    except (KeyError, TypeError, ValueError):
        pass
    audio = [s for s in info.get("streams") or [] if s.get("codec_type") == "audio"]
    a.codec = audio[0].get("codec_name", "") if audio else ""
    for src in ((audio[0] if audio else {}), fmt):
        try:
            a.bit_rate = int(src["bit_rate"])
            break
        except (KeyError, TypeError, ValueError):
            pass
    if out.returncode != 0 and out.stderr.strip():
        a.errors.append(out.stderr.strip().splitlines()[-1])

    run = subprocess.run(
        [tools.ffmpeg, "-hide_banner", "-nostats", "-v", "info", "-i", path, "-map", "0:a:0?",
         "-af", f"silencedetect=noise={SILENCE_NOISE_DB}dB:d={max(silence_seconds, 0.5)}",
         "-f", "null", "-progress", "pipe:1", "-"],
        capture_output=True, text=True, timeout=timeout)
    times = re.findall(r"out_time_us=(\d+)", run.stdout)
    if times:
        a.decoded_duration = int(times[-1]) / 1_000_000
    start = None
    for line in run.stderr.splitlines():
        m = re.search(r"silence_start: ([\d.]+)", line)
        if m:
            start = float(m.group(1))
            continue
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m:
            a.silences.append((start or 0.0, float(m.group(1))))
            start = None
            continue
        low = line.lower()
        if "silencedetect" in low:
            continue
        if any(k in low for k in ("error", "invalid data", "corrupt", "header missing", "decode_frame",
                                  "could not find codec", "truncat")):
            a.errors.append(line.strip())
    if start is not None:
        a.silences.append((start, None))   # silence runs to the end of the file
    if run.returncode != 0 and not a.errors:
        a.errors.append((run.stderr.strip().splitlines() or ["ffmpeg failed"])[-1])
    return a


def verdict(path: str, a: Analysis, expected_seconds: Optional[float], margin_seconds: float,
            silence_seconds: float) -> Optional[str]:
    """Reason to reject the file, or None when it is fine."""
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if not a.codec:
        return "Not an audio file"

    want = _EXPECTED.get(ext)
    if want:
        containers, codecs = want
        got = set(a.container.split(","))
        codec_ok = (a.codec.startswith("pcm_") if codecs is None else a.codec in codecs)
        if not (got & containers) or not codec_ok:
            real = _FRIENDLY.get(a.codec, a.codec.upper())
            return f"Not really {_FRIENDLY.get(ext, ext.upper())} (it's {real})"

    dur = a.decoded_duration if a.decoded_duration is not None else a.header_duration
    if a.header_duration and a.decoded_duration is not None and a.decoded_duration < a.header_duration - CUT_OFF_SECONDS:
        return f"File is cut off at {_fmt(a.decoded_duration)} (should be {_fmt(a.header_duration)})"
    if a.errors:
        detail = re.sub(r"^\[[^\]]*\]\s*", "", a.errors[0])   # drop "[flac @ 0x…]"
        return f"Damaged file ({detail[:100]})"

    if expected_seconds and dur:
        longer_ok = dur > expected_seconds and "extended" in os.path.basename(path).lower()
        if abs(dur - expected_seconds) > margin_seconds and not longer_ok:
            return f"{_fmt(expected_seconds)} expected, file is {_fmt(dur)}"

    if dur and silence_seconds > 0:
        for start, end in a.silences:
            stop = end if end is not None else dur
            length = stop - start
            if length < silence_seconds:
                continue
            if start <= 0.5:
                return f"{int(round(length))} s of silence at the start"
            if stop >= dur - 0.5:
                return f"{int(round(length))} s of silence at the end"
    return None


# --- Fake lossless (roadmap step 3) ---------------------------------------------------------------
# An MP3 throws away everything above a fixed frequency (about 16-17 kHz at 128 kbps, 19 kHz at
# 192, 20-20.5 kHz at 320). Converting it to FLAC/WAV doesn't bring that back, so a hard "cliff" in
# the spectrum below ~20.8 kHz gives a transcode away. Real lossless has no such cliff.
LOSSLESS_EXT = {"flac", "wav", "aiff", "aif", "alac"}
FAKE_BELOW_HZ = 19_500          # lossless with a cliff below this: a transcoded MP3 (<= ~192 kbps)
GENUINE_FROM_HZ = 20_800        # cliff between the two: suspect (320 kbps MP3, or a band-limited master)
MP3_FAKE_BELOW_HZ = 18_500      # "320 kbps" MP3 that stops this low was made from a ~128 kbps file
MP3_SUSPECT_BELOW_HZ = 19_500
FULL_RANGE_HZ = 22_050          # stored when there is no cliff
_SEGMENTS, _SEGMENT_SECONDS, _RATE, _FFT = 4, 8.0, 44100, 4096


def measure_cutoff(path: str, tools: Tools, duration: Optional[float], timeout: float = 30) -> Optional[float]:
    """Frequency (Hz) where the audio stops, or FULL_RANGE_HZ when there is no hard cutoff.
    Decodes 4 short pieces spread over the track (mono, 44.1 kHz), averages their spectrum, then looks
    from the top down for a drop of 25 dB within ~1 kHz. None when it can't tell (numpy missing,
    silent or unreadable file)."""
    try:
        import numpy as np
    except ImportError:
        return None
    win = np.hanning(_FFT)
    total, frames = None, 0
    dur = duration or 0.0
    for i in range(_SEGMENTS):
        off = max(0.0, (dur - _SEGMENT_SECONDS) * (i + 1) / (_SEGMENTS + 1)) if dur else 0.0
        raw = subprocess.run(
            [tools.ffmpeg, "-v", "error", "-ss", f"{off:.2f}", "-t", str(_SEGMENT_SECONDS), "-i", path,
             "-map", "0:a:0?", "-ac", "1", "-ar", str(_RATE), "-f", "f32le", "-"],
            capture_output=True, timeout=timeout).stdout
        x = np.frombuffer(raw, dtype=np.float32)
        n = len(x) // _FFT
        if n == 0:
            continue
        spec = (np.abs(np.fft.rfft(x[: n * _FFT].reshape(n, _FFT) * win, axis=1)) ** 2).sum(axis=0)
        total = spec if total is None else total + spec
        frames += n
        if not dur:
            break
    if total is None:
        return None
    f = np.fft.rfftfreq(_FFT, 1 / _RATE)
    db = 10 * np.log10(total / frames + 1e-20)
    db = np.convolve(db, np.ones(9) / 9, mode="same")          # ~100 Hz smoothing
    if np.median(db[(f > 1000) & (f < 8000)]) < -100:          # (near) silent: nothing to judge
        return None
    for i in np.where((f >= 12000) & (f <= 21800))[0][::-1]:
        fi = f[i]
        above = db[(f > fi + 150) & (f <= min(fi + 1500, 21950))]
        below = db[(f >= fi - 1200) & (f < fi - 150)]
        if len(above) < 3 or len(below) < 3:
            continue
        b, a = below.mean(), above.mean()
        if b - a >= 25:
            edge = np.where((f >= fi - 1500) & (f <= fi + 150) & (db > b - 6))[0]
            return float(f[edge.max()]) if len(edge) else float(fi)
    return float(FULL_RANGE_HZ)


def _mp3_guess(hz: float) -> str:
    if hz < 17_500:
        return "about 128 kbps"
    if hz < 19_500:
        return "about 192 kbps"
    return "320 kbps"


def classify(ext: str, cutoff_hz: Optional[float], bit_rate: Optional[int]) -> tuple[str, str]:
    """("genuine" | "suspect" | "fake" | "", reason). "" when not judged."""
    if cutoff_hz is None:
        return "", ""
    khz = f"{cutoff_hz / 1000:.1f} kHz"
    if ext in LOSSLESS_EXT:
        if cutoff_hz < FAKE_BELOW_HZ:
            return "fake", f"Fake lossless: audio stops at {khz} (MP3 at {_mp3_guess(cutoff_hz)})"
        if cutoff_hz < GENUINE_FROM_HZ:
            return "suspect", f"Suspect lossless: audio stops at {khz} (maybe an MP3 at 320 kbps)"
        return "genuine", ""
    if ext == "mp3" and bit_rate and bit_rate >= 300_000:
        if cutoff_hz < MP3_FAKE_BELOW_HZ:
            return "fake", f"Fake 320 kbps: audio stops at {khz} ({_mp3_guess(cutoff_hz)})"
        if cutoff_hz < MP3_SUSPECT_BELOW_HZ:
            return "suspect", f"Suspect 320 kbps: audio stops at {khz}"
    return "genuine", ""


class FileChecker:
    """Engine check (see Engine.checks): returns a reject reason or None. Skips when ffmpeg is missing."""

    def __init__(self, settings_getter, tools: Optional[Tools] = None):
        self._settings = settings_getter
        self.tools = tools or Tools.find()
        if not self.tools.available:
            log.info("ffmpeg/ffprobe not found: file checks are off")

    def __call__(self, track: dict, path: str) -> Optional[str]:
        if not self.tools.available:
            return None
        s = self._settings()
        try:
            a = analyse(path, self.tools, s.check_silence_seconds)
        except subprocess.TimeoutExpired:
            return "File check took too long (file may be damaged)"
        why = verdict(path, a, track.get("duration"), s.check_length_margin, s.check_silence_seconds)
        if why:
            return why
        # Fake lossless / fake 320 (step 3). The result is kept on the track (see Engine).
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        if ext not in LOSSLESS_EXT and ext != "mp3":
            return None
        try:
            cutoff = measure_cutoff(path, self.tools, a.decoded_duration or a.header_duration)
        except subprocess.TimeoutExpired:
            cutoff = None
        quality, reason = classify(ext, cutoff, a.bit_rate)
        meta = track.setdefault("_meta", {})
        if cutoff is not None:
            meta.update(cutoff_hz=round(cutoff), quality=quality)
        if quality == "fake" or (quality == "suspect" and s.suspect_quality == "reject"):
            return reason
        return None
