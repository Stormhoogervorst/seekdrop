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


# --- Roadmap step 3: fake lossless ------------------------------------------------------------
import time  # noqa: E402

from seekdrop.checks import classify, measure_cutoff  # noqa: E402

numpy = pytest.importorskip("numpy")


@pytest.fixture(scope="module")
def spectra(tmp_path_factory):
    d = tmp_path_factory.mktemp("spectra")
    noise = ["-f", "lavfi", "-i", "anoisesrc=d=30:c=white:a=0.3:r=44100", "-ac", "2"]
    ffmpeg(*noise, str(d / "noise.flac"))
    for name, hz in (("lp16.flac", 16000), ("lp195.flac", 19500)):      # brick-wall low-pass
        ffmpeg("-i", str(d / "noise.flac"), "-af",
               f"firequalizer=gain='if(lt(f,{hz}),0,-120)':delay=0.05:accuracy=5", str(d / name))
    ffmpeg("-f", "lavfi", "-i", "anoisesrc=d=30:c=pink:a=0.3:r=44100", "-ac", "2", "-b:a", "128k", str(d / "p128.mp3"))
    ffmpeg("-i", str(d / "p128.mp3"), str(d / "transcode128.flac"))       # a real MP3 -> FLAC transcode
    ffmpeg("-i", str(d / "p128.mp3"), "-b:a", "320k", str(d / "fake320.mp3"))   # 128 blown up to "320"
    ffmpeg("-f", "lavfi", "-i", "anoisesrc=d=30:c=pink:a=0.3:r=44100", "-ac", "2", "-b:a", "320k", str(d / "real320.mp3"))
    return d


def judge(path, bit_rate=None):
    ext = os.path.splitext(str(path))[1].lstrip(".")
    cutoff = measure_cutoff(str(path), TOOLS, 30)
    return cutoff, classify(ext, cutoff, bit_rate)[0]


@needs_ffmpeg
def test_generated_signals_are_classified(spectra):
    cut, q = judge(spectra / "noise.flac")
    assert q == "genuine" and cut == 22050
    cut, q = judge(spectra / "lp16.flac")
    assert q == "fake" and 15500 < cut < 17000
    cut, q = judge(spectra / "lp195.flac")
    assert q == "suspect" and 19000 < cut < 20500
    assert judge(spectra / "transcode128.flac")[1] == "fake"


@needs_ffmpeg
def test_fake_320_mp3(spectra):
    assert judge(spectra / "fake320.mp3", 320_000)[1] == "fake"
    assert judge(spectra / "real320.mp3", 320_000)[1] == "genuine"
    assert judge(spectra / "fake320.mp3", 128_000)[1] == "genuine"   # a 128 kbps MP3 is what it says


@needs_ffmpeg
def test_analysis_is_fast(spectra):
    start = time.time()
    measure_cutoff(str(spectra / "transcode128.flac"), TOOLS, 30)
    assert time.time() - start < 5


def test_reasons_name_the_cutoff():
    q, why = classify("flac", 16400, None)
    assert q == "fake" and why == "Fake lossless: audio stops at 16.4 kHz (MP3 at about 128 kbps)"
    q, why = classify("wav", 20300, None)
    assert q == "suspect" and "20.3 kHz" in why
    assert classify("flac", None, None) == ("", "")      # not measured: no judgement


@needs_ffmpeg
def test_suspect_setting_and_result_kept_on_track(spectra):
    class S:
        check_length_margin = 10
        check_silence_seconds = 10
        suspect_quality = "label"
    fc = FileChecker(lambda: S, TOOLS)
    track = {"duration": 30}
    assert fc(track, str(spectra / "lp195.flac")) is None          # let through, but marked
    assert track["_meta"]["quality"] == "suspect" and 19000 < track["_meta"]["cutoff_hz"] < 20500
    S.suspect_quality = "reject"
    assert fc({"duration": 30}, str(spectra / "lp195.flac")).startswith("Suspect lossless")
    assert fc({"duration": 30}, str(spectra / "lp16.flac")).startswith("Fake lossless")
