import pytest


@pytest.fixture(autouse=True)
def _no_real_user_folders(tmp_path, monkeypatch):
    """No test may touch the real Nicotine+ plugin folder or SeekSync's app data."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("SEEKSYNC_HOME", str(tmp_path / "home"))


@pytest.fixture(autouse=True)
def _no_waiting_between_spotify_pages(monkeypatch):
    """The pause between two Spotify track pages is for the real site; tests that check it set it back."""
    from seeksync.spotify import SpotifyClient
    monkeypatch.setattr(SpotifyClient, "TRACK_PAGE_SPACING", 0.0, raising=False)


@pytest.fixture(autouse=True)
def _no_waiting_before_a_second_cover_try(monkeypatch):
    from seeksync.engine import Engine
    monkeypatch.setattr(Engine, "COVER_RETRY_WAIT", 0.0, raising=False)
