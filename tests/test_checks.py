"""Roadmap step 2: file checks with ffmpeg. Test audio is generated locally; no network."""
import os
import shutil
import subprocess

import pytest

from seeksync.checks import FileChecker, Tools, analyse, verdict

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
    from seeksync import checks
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

from seeksync.checks import classify, measure_cutoff  # noqa: E402

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


# --- Roadmap step 4: quality floor on the measured file --------------------------------------

@needs_ffmpeg
def test_measured_tier_and_floor(spectra):
    class S:
        check_length_margin = 10
        check_silence_seconds = 10
        suspect_quality = "label"
        quality_profile = "club"
    fc = FileChecker(lambda: S, TOOLS)
    assert fc({"duration": 30}, str(spectra / "p128.mp3")) == "Below your quality minimum (MP3 under 192)"
    track = {"duration": 30}
    assert fc(track, str(spectra / "real320.mp3")) is None and track["_meta"]["tier"] == "mp3_320"
    track = {"duration": 30}
    assert fc(track, str(spectra / "noise.flac")) is None and track["_meta"]["tier"] == "flac24"   # ffmpeg writes 24-bit here
    track = {"duration": 30}
    assert fc(track, str(spectra / "lp195.flac")) is None
    assert track["_meta"]["tier"] == "mp3_320"            # suspect lossless counts as MP3 320
    S.quality_profile = "space"
    assert fc({"duration": 30}, str(spectra / "p128.mp3")) == "Below your quality minimum (MP3 under 192)"


# --- Windows report (0.6.1): good files in quarantine ------------------------------------------------
# 1. "Damaged file (Could not find codec parameters for stream 1 (Video: mjpeg…))": a broken cover picture
#    in an otherwise fine file. 2. "Damaged file (Error initializing a simple filtergraph)" on every file:
#    that ffmpeg couldn't set up the silencedetect filter. Neither says anything about the audio.

def test_messages_about_cover_art_are_not_about_the_audio():
    from seeksync.checks import _about_other_stream as other
    assert other("[mp3 @ 0x5613] Could not find codec parameters for stream 1 (Video: mjpeg, none(bt470bg/unknown/unknown)): unspecified size")
    assert other("[in#0/flac @ 0x55] Could not find codec parameters for stream 1 (Video: mjpeg, none): unspecified size")
    assert other("[mjpeg @ 0x55c9] unable to decode APP fields: Invalid data found when processing input")
    assert other("[vist#0:1/mjpeg @ 0x55] Error while decoding stream")
    assert other("[dec:png @ 0x55] Invalid PNG signature")
    assert not other("[mp3 @ 0x55] Could not find codec parameters for stream 0 (Audio: mp3 (mp3float), 0 channels, fltp): unspecified frame size")
    assert not other("[flac @ 0x55] invalid residual")
    assert not other("[aist#0:0/mp3 @ 0x55] Error submitting packet to decoder")


@pytest.fixture(scope="module")
def broken_covers(audio, tmp_path_factory):
    from mutagen.flac import FLAC, Picture
    from mutagen.id3 import APIC, ID3
    d = tmp_path_factory.mktemp("covers")
    ffmpeg("-i", str(audio / "good.flac"), "-b:a", "320k", str(d / "good.mp3"))
    for name, data in (("zeros", b"\x00" * 5000), ("bad_jpeg", b"\xff\xd8\xff\xe0" + b"\x00" * 20)):
        shutil.copy(d / "good.mp3", d / f"{name}.mp3")
        tags = ID3()
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="", data=data))
        tags.save(str(d / f"{name}.mp3"), v2_version=3)
        shutil.copy(audio / "good.flac", d / f"{name}.flac")
        f = FLAC(str(d / f"{name}.flac"))
        pic = Picture()
        pic.type, pic.mime, pic.data = 3, "image/jpeg", data
        f.add_picture(pic)
        f.save()
    return d


@needs_ffmpeg
def test_broken_cover_art_does_not_make_a_file_damaged(broken_covers):
    for name in ("zeros.mp3", "bad_jpeg.mp3", "zeros.flac", "bad_jpeg.flac"):
        assert check(broken_covers / name, 40) is None, name


@needs_ffmpeg
def test_real_damage_still_counts(audio, tmp_path):
    garbage = tmp_path / "garbage.mp3"
    garbage.write_bytes(os.urandom(200_000))
    assert check(garbage, 40) is not None
    assert check(audio / "cut.flac", 40).startswith("File is cut off at 0:")


@pytest.fixture
def ffmpeg_without_silencedetect(tmp_path):
    """An ffmpeg that fails to set up any -af filter, like the Windows build in the report."""
    import sys
    fake = tmp_path / "ffmpeg"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "if '-af' in sys.argv:\n"
        "    sys.stderr.write(\"[AVFilterGraph @ 0x1] No such filter: 'silencedetect'\\n\"\n"
        "                     'Error initializing a simple filtergraph\\n')\n"
        "    sys.exit(1)\n"
        f"os.execv({TOOLS.ffmpeg!r}, [{TOOLS.ffmpeg!r}] + sys.argv[1:])\n")
    fake.chmod(0o755)
    return Tools(str(fake), TOOLS.ffprobe)


@needs_ffmpeg
@pytest.mark.skipif(os.name == "nt", reason="uses a script as a stand-in ffmpeg")
def test_ffmpeg_that_cannot_run_the_silence_filter(audio, ffmpeg_without_silencedetect):
    tools = ffmpeg_without_silencedetect

    def run(path, expected):
        return verdict(str(path), analyse(str(path), tools, 10), expected, 10, 10)

    assert run(audio / "good.flac", 40) is None
    assert tools.silence_filter is False                    # remembered: the next file skips the filter
    a = analyse(str(audio / "silence.flac"), tools, 10)
    assert a.decoded and not a.silence_checked
    assert verdict(str(audio / "silence.flac"), a, 70, 10, 10) is None    # can't check silence: let it through
    assert run(audio / "cut.flac", 40).startswith("File is cut off at 0:")
    assert run(audio / "fake.flac", 40) == "Not really FLAC (it's MP3)"


@needs_ffmpeg
def test_normal_ffmpeg_keeps_the_silence_check(audio):
    tools = Tools(TOOLS.ffmpeg, TOOLS.ffprobe)
    a = analyse(str(audio / "silence.flac"), tools, 10)
    assert a.silence_checked and tools.silence_filter is True
