"""Where the tracks come from: SoundCloud profiles and playlists, Spotify playlists (roadmap step 16).
The engine talks to one object (`Sources`) that hands each link to the right client."""
from __future__ import annotations

from . import soundcloud, spotify
from .soundcloud import ChannelError, ChannelInfo, SoundCloudClient, TrackInfo, TrackStub
from .spotify import SpotifyClient

__all__ = ["Sources", "normalize_channel_url", "is_playlist_url", "source_name", "ChannelError"]


def normalize_channel_url(text: str) -> str:
    """The canonical link of a SoundCloud profile/playlist or a Spotify playlist."""
    if spotify.is_spotify(text):
        return spotify.normalize_playlist_url(text)
    return soundcloud.normalize_channel_url(text)


def is_playlist_url(url: str) -> bool:
    return spotify.is_spotify(url) or soundcloud.is_playlist_url(url)


def source_name(url: str) -> str:
    return "Spotify" if spotify.is_spotify(url) else "SoundCloud"


class Sources:
    """Same interface as SoundCloudClient (channel_info, latest, track), for every source."""

    def __init__(self, sc: SoundCloudClient, sp: SpotifyClient | None = None):
        self.sc = sc
        self.spotify = sp or SpotifyClient()

    def _for(self, url: str):
        return self.spotify if spotify.is_spotify(url) else self.sc

    def channel_info(self, url: str) -> ChannelInfo:
        return self._for(url).channel_info(url)

    def latest(self, url: str, include_reposts: bool = False, limit: int = 25) -> list[TrackStub]:
        if spotify.is_spotify(url):
            return self.spotify.latest(url, include_reposts)
        return self.sc.latest(url, include_reposts, limit)

    def track(self, url: str) -> TrackInfo:
        return self._for(url).track(url)
