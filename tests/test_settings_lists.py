"""Folder lists in the settings: a text box sent as one string must become one folder per line,
and a list that an earlier version split into single letters is cleared on load."""
import json

from seeksync.config import SettingsStore


def test_text_box_string_becomes_one_folder_per_line(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    s, changed = store.update({"library_dirs": "/Users/me/Music/DJ\n  /Volumes/Disk/My Tracks \n\n"})
    assert s.library_dirs == ["/Users/me/Music/DJ", "/Volumes/Disk/My Tracks"]
    assert "library_dirs" in changed
    assert SettingsStore(tmp_path / "s.json").settings.library_dirs == s.library_dirs


def test_list_value_still_works(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    s, _ = store.update({"share_dirs": ["/a", " /b "]})
    assert s.share_dirs == ["/a", "/b"]


def test_path_split_into_letters_is_cleared_on_load(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"library_dirs": list("/Users/me/Music"), "share_dirs": ["/ok"]}))
    s = SettingsStore(path).settings
    assert s.library_dirs == []
    assert s.share_dirs == ["/ok"]


def test_a_real_single_folder_is_kept(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"library_dirs": ["/Users/me/Music"]}))
    assert SettingsStore(path).settings.library_dirs == ["/Users/me/Music"]
