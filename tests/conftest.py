import pytest


@pytest.fixture(autouse=True)
def _no_real_user_folders(tmp_path, monkeypatch):
    """No test may touch the real Nicotine+ plugin folder or SeekDrop's app data."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("SEEKDROP_HOME", str(tmp_path / "home"))
