"""Roadmap step 2: file checks with ffmpeg. Test audio is generated locally; no network."""
import os
import shutil
import subprocess

import pytest

from seekdrop.checks import FileChecker, Tools, analyse, verdict

TOOLS = Tools.find()
needs_ffmpeg = pytest.mark.skipif(not TOOLS.available, reason="ffmpeg/ffprobe not installed")


def ffmpeg(*args):
    subprocess.run([TOOLS.ffmpeg, "-v", "error", "-y", *args], check=True, timeout=60)


@pytest.fixture(scope="module")
def audio(tmp_path_factory):
    d = tmp_path_factory.mktemp("audio")
    noise = ["-f", "lavfi", "-i", "anoisesrc=d=40:c=pink:a=0.3", "-ac", "2", "-ar", "44100"]
    ffmpeg(*noise, str(d / "good.flac"))
    data = (d / "good.flac").read_bytes()
    (d / "cut.flac").write_bytes(data[: len(data) // 2])                  # download stopped halfway
    ffmpeg("-f", "lavfi", "-t", "30", "-i", "anullsrc=r=44100:cl=stereo", *noise[:4],
           "-filter_complex", "[0][1]concat=n=2:v=0:a=1", "-ac", "2", str(d / "silence.flac"))   # 30 s silence + 40 s
    ffmpeg(*noise, "-b:a", "320k", str(d / "fake.mp3"))
    shutil.copy(d / "fake.mp3", d / "fake.flac")                           # MP3 with a .flac name
    return d


def check(path, expected, margin=10, silence=10):
    return verdict(str(path), analyse(str(path), TOOLS, silence), expected, margin, silence)


@needs_ffmpeg
def test_good_file_passes(audio):
    assert check(audio / "good.flac", 40) is None
    assert check(audio / "fake.mp3", 40) is None          # a real MP3 named .mp3 is fine


@needs_ffmpeg
def test_three_bad_files_each_with_own_reason(audio):
    cut = check(audio / "cut.flac", 40)
    silence = check(audio / "silence.flac", 70)
    fake = check(audio / "fake.flac", 40)
    assert cut.startswith("File is cut off at 0:")
    assert silence == "30 s of silence at the start"
    assert fake == "Not really FLAC (it's MP3)"
    assert len({cut, silence, fake}) == 3


@needs_ffmpeg
def test_length_must_match_soundcloud(audio):
    assert check(audio / "good.flac", 120) == "2:00 expected, file is 0:40"
    assert check(audio / "good.flac", 47, margin=10) is None
    assert check(audio / "good.flac", None) is None        # unknown SoundCloud length: no length check
    ext = audio / "Artist - Track (Extended Mix).flac"     # an extended mix may be longer
    shutil.copy(audio / "good.flac", ext)
    assert check(ext, 25) is None


@needs_ffmpeg
def test_file_checker_uses_settings(audio):
    class S:
        check_length_margin = 10
        check_silence_seconds = 40     # 30 s of silence is now allowed
    fc = FileChecker(lambda: S, TOOLS)
    assert fc({"duration": 70}, str(audio / "silence.flac")) is None
    assert fc({"duration": 40}, str(audio / "fake.flac")) == "Not really FLAC (it's MP3)"


def test_without_ffmpeg_checks_are_skipped(tmp_path):
    fc = FileChecker(lambda: None, Tools(None, None))
    assert not fc.tools.available
    (tmp_path / "x.flac").write_bytes(b"not audio at all")
    assert fc({"duration": 300}, str(tmp_path / "x.flac")) is None


def test_finds_homebrew_ffmpeg_without_path(monkeypatch, tmp_path):
    # GUI apps on macOS don't get the shell PATH; the known install folders are searched too.
    from seekdrop import checks
    fake = tmp_path / "bin"
    fake.mkdir()
    tool = fake / "ffprobe"
    tool.write_text("#!/bin/sh\n")
    tool.chmod(0o755)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(checks, "_EXTRA_DIRS", (str(fake),))
    assert checks.find_tool("ffprobe") == str(tool)
