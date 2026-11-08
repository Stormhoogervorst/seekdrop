"""Roadmap step 4: quality ladder and profiles."""
import json

from seekdrop.config import SettingsStore
from seekdrop.quality import PROFILES, is_better, position, profile, profile_from_old_settings, tier_of, wants_upgrade


def test_tiers():
    assert tier_of("flac", None, 24) == "flac24"
    assert tier_of("flac") == "flac16"
    assert tier_of("aiff") == tier_of("wav") == "wav"
    assert tier_of("mp3", 320) == "mp3_320" and tier_of("mp3", 256) == "mp3_256"
    assert tier_of("mp3", 192) == "mp3_192" and tier_of("mp3", 128) == "mp3_low"
    assert tier_of("mp3") is None and tier_of("m4a", 256) == "other"


def test_three_profiles_with_floor_and_target():
    assert set(PROFILES) == {"club", "balanced", "space"}
    club, bal, space = profile("club"), profile("balanced"), profile("space")
    assert position(club, "mp3_256") is None            # under Club's floor
    assert position(bal, "mp3_256") is not None and position(bal, "mp3_192") is None
    assert position(space, "mp3_320") == 0               # Space saver prefers MP3
    assert wants_upgrade(club, "mp3_320") and not wants_upgrade(club, "flac16")
    assert wants_upgrade(bal, "mp3_256") and not wants_upgrade(bal, "mp3_320")
    assert not wants_upgrade(space, "flac16")            # never swap lossless for lossy
    assert is_better(club, "flac16", "mp3_320") and not is_better(club, "mp3_320", "flac16")
    assert not is_better(club, "mp3_320", "mp3_320") and not is_better(club, None, "mp3_320")


def test_old_settings_become_a_profile(tmp_path):
    assert profile_from_old_settings("lossless", 320) == "club"
    assert profile_from_old_settings("mp3", 320) == "balanced"
    assert profile_from_old_settings("mp3", 192) == "space"
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"preferred_format": "mp3", "min_bitrate": 256, "accepted_terms": True}))
    s = SettingsStore(f).settings
    assert s.quality_profile == "balanced" and s.upgrade_mode == "ask" and s.accepted_terms
