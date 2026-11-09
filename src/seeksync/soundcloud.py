"""Read public SoundCloud profiles via yt-dlp (no downloads from SoundCloud itself)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

log = logging.getLogger(__name__)

_RESERVED = {"tracks", "albums", "sets", "reposts", "likes", "spotlight", "comments", "popular-tracks"}
_NOT_PROFILES = {"discover", "search", "stream", "you", "upload", "charts", "pages", "terms-of-use", "settings"}


MAX_PLAYLIST = 500   # tracks read from one playlist


class ChannelError(ValueError):
    pass


@dataclass
class ChannelInfo:
    url: str
    name: str
    kind: str = "profile"     # "profile" | "playlist"


@dataclass
class TrackStub:
    sc_id: str
    url: str
    title: str


@dataclass
class TrackInfo:
    sc_id: str
    url: str
    title: str
    uploader: str = ""
    publisher_artist: str = ""
    duration: Optional[float] = None
    artwork: str = ""
    uploaded_at: Optional[float] = None
    genre: str = ""
    released_at: Optional[float] = None


def normalize_channel_url(text: str) -> str:
    """Accepts 'artist', 'soundcloud.com/artist', 'https://m.soundcloud.com/artist/tracks', ...
    and playlist links like 'soundcloud.com/artist/sets/name' (also private ones with '/s-xxxx')."""
    s = (text or "").strip()
    if not s:
        raise ChannelError("Paste a SoundCloud profile or playlist link.")
    if re.fullmatch(r"[A-Za-z0-9_-]{2,}", s):
        return f"https://soundcloud.com/{s.lower()}"
    if "://" not in s:
        s = "https://" + s
    u = urlparse(s)
    host = (u.hostname or "").lower()
    if host == "on.soundcloud.com":
        raise ChannelError("Short links (on.soundcloud.com) aren't supported yet. Open it and copy the full link.")
    if host not in ("soundcloud.com", "www.soundcloud.com", "m.soundcloud.com"):
        raise ChannelError("That's not a SoundCloud link.")
    parts = [p for p in u.path.split("/") if p]
    if not parts or parts[0].lower() in _NOT_PROFILES:
        raise ChannelError("That's not a SoundCloud profile or playlist link.")
    if len(parts) >= 3 and parts[1].lower() == "sets":
        url = f"https://soundcloud.com/{parts[0].lower()}/sets/{parts[2].lower()}"
        if len(parts) >= 4 and parts[3].startswith("s-"):
            url += "/" + parts[3]          # secret token of a private playlist (case-sensitive)
        return url
    if len(parts) >= 2 and parts[1].lower() not in _RESERVED:
        raise ChannelError("That's a link to a single track. Paste the link to the profile or playlist instead.")
    return f"https://soundcloud.com/{parts[0].lower()}"


def is_playlist_url(url: str) -> bool:
    return "/sets/" in url


def _thumb(info: dict) -> str:
    thumbs = info.get("thumbnails") or []
    for want in ("t300x300", "t500x500", "large", "crop"):
        for t in thumbs:
            if t.get("id") == want and t.get("url"):
                return t["url"]
    return (thumbs[0].get("url") if thumbs else "") or info.get("thumbnail") or ""


class SoundCloudClient:
    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir

    def _ydl(self, **extra):
        import yt_dlp  # imported lazily: slow import

        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noprogress": True,
            "socket_timeout": 20,
            "extractor_retries": 2,
            "logger": _QuietLogger(),
            "getcomments": False,
        }
        if self.cache_dir:
            opts["cachedir"] = self.cache_dir
        opts.update(extra)
        return yt_dlp.YoutubeDL(opts)

    def channel_info(self, channel_url: str) -> ChannelInfo:
        url = normalize_channel_url(channel_url)
        playlist = is_playlist_url(url)
        with self._ydl(extract_flat="in_playlist", playlist_items="1") as ydl:
            try:
                info = ydl.extract_info(url if playlist else url + "/tracks", download=False)
            except Exception as e:  # yt-dlp raises DownloadError with useful text
                raise ChannelError(_friendly_error(e, playlist)) from e
        name = re.sub(r"\s*\((?:Tracks|All)\)\s*$", "", info.get("title") or "") or url.rsplit("/", 1)[-1]
        return ChannelInfo(url=url, name=name, kind="playlist" if playlist else "profile")

    def latest(self, channel_url: str, include_reposts: bool = False, limit: int = 25) -> list[TrackStub]:
        """Newest uploads of a profile, or every track of a playlist (up to MAX_PLAYLIST)."""
        if is_playlist_url(channel_url):
            page, limit = channel_url, MAX_PLAYLIST
        else:
            page = channel_url + ("" if include_reposts else "/tracks")
        with self._ydl(extract_flat="in_playlist", playlist_items=f"1-{limit}") as ydl:
            info = ydl.extract_info(page, download=False)
        out = []
        for e in info.get("entries") or []:
            if not e:
                continue
            url = e.get("url") or ""
            if "/sets/" in url or not e.get("id"):
                continue
            out.append(TrackStub(sc_id=str(e["id"]), url=url, title=e.get("title") or ""))
        return out

    def track(self, url: str) -> TrackInfo:
        with self._ydl() as ydl:
            info = ydl.extract_info(url, download=False, process=False)
        artists = info.get("artists") or []
        genres = info.get("genres") or []
        return TrackInfo(
            sc_id=str(info.get("id")),
            url=info.get("webpage_url") or url,
            title=info.get("title") or "",
            uploader=info.get("uploader") or "",
            publisher_artist=artists[0] if artists else "",
            duration=info.get("duration"),
            artwork=_thumb(info),
            uploaded_at=info.get("timestamp"),
            genre=str(genres[0]) if genres else "",
            released_at=info.get("release_timestamp"),
        )


def _friendly_error(e: Exception, playlist: bool = False) -> str:
    msg = str(e)
    if any(k in msg for k in ("Unable to connect", "Name or service", "getaddrinfo", "timed out", "Network is unreachable")):
        return "Can't reach SoundCloud. Check your internet connection."
    if "404" in msg:
        return f"SoundCloud says this {'playlist' if playlist else 'profile'} doesn't exist (or it's private)."
    if "403" in msg or "429" in msg:
        return "SoundCloud is blocking requests right now. Try again in a few minutes."
    return f"Couldn't read this SoundCloud {'playlist' if playlist else 'profile'}. " + re.sub(r"^ERROR:\s*", "", msg)[:160]


class _QuietLogger:
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        log.debug("yt-dlp: %s", msg)

    def error(self, msg):
        log.warning("yt-dlp: %s", msg)
