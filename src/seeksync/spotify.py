"""Read public Spotify playlists (roadmap step 16).

Spotify's official Web API only shows the contents of playlists you own or work on (since February 2026) and
needs a Premium developer account, so SeekSync reads the page Spotify itself offers for embedding a playlist,
open.spotify.com/embed/playlist/<id>. That page needs no login and lists title, artists and length of every
track, but only the first 100 tracks of a playlist. It is not an official API: when Spotify changes the page,
reading stops and SeekSync says so. The playlist page has no pictures, so for the cover (and the release date)
each new track's own embed page is read too, open.spotify.com/embed/track/<id>. No audio is ever downloaded
from Spotify; only the album cover goes into the tags."""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import urlparse

from .soundcloud import ChannelError, ChannelInfo, TrackInfo, TrackStub

log = logging.getLogger(__name__)

MAX_TRACKS = 100                 # what the embed page shows of one playlist
PREFIX = "spotify:"              # tracks.sc_id of a Spotify track: "spotify:<22 characters>"
_ID = r"[A-Za-z0-9]{22}"
_HOSTS = ("open.spotify.com", "play.spotify.com")
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def is_spotify(text: str) -> bool:
    s = (text or "").strip().lower()
    return s.startswith("spotify:") or "spotify.com" in s or "spotify.link" in s


def normalize_playlist_url(text: str) -> str:
    """Accepts a playlist link in any of its spellings (also with a language part, ?si=… or /embed/) and
    'spotify:playlist:<id>'. Returns https://open.spotify.com/playlist/<id>."""
    s = (text or "").strip()
    if not s:
        raise ChannelError("Paste a Spotify playlist link.")
    m = re.fullmatch(rf"spotify:playlist:({_ID})", s)
    if m:
        return f"https://open.spotify.com/playlist/{m.group(1)}"
    if "://" not in s:
        s = "https://" + s
    u = urlparse(s)
    host = (u.hostname or "").lower()
    if host in ("spotify.link", "spoti.fi") or host.endswith(".spotify.link"):
        raise ChannelError("Short links (spotify.link) aren't supported. Open it and copy the full link.")
    if host not in _HOSTS:
        raise ChannelError("That's not a Spotify link.")
    parts = [p for p in u.path.split("/") if p and not re.fullmatch(r"intl-[a-z-]+", p, re.I) and p.lower() != "embed"]
    if len(parts) >= 2 and parts[0].lower() == "playlist":
        if re.fullmatch(_ID, parts[1]):
            return f"https://open.spotify.com/playlist/{parts[1]}"
        raise ChannelError("That playlist link looks incomplete. Copy it again from Spotify (Share, Copy link).")
    if parts and parts[0].lower() in ("album", "track", "artist", "show", "episode", "user", "collection"):
        what = {"album": "an album", "track": "a single track", "artist": "an artist",
                "user": "a profile", "collection": "your library"}.get(parts[0].lower(), "something that isn't a playlist")
        raise ChannelError(f"That's a link to {what}. Paste the link to a playlist instead.")
    raise ChannelError("That's not a Spotify playlist link.")


def playlist_id(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


# --- turning Spotify's fields into the way a SoundCloud title reads ------------------------------

def clean_artists(subtitle: str) -> str:
    """'Oxia,\xa0Space 92' -> 'Oxia, Space 92'."""
    names = [re.sub(r"\s+", " ", n.replace("\xa0", " ")).strip() for n in (subtitle or "").split(",\xa0")]
    if len(names) == 1:                                   # no non-breaking space: a plain comma separates them
        names = [re.sub(r"\s+", " ", n).strip() for n in (subtitle or "").replace("\xa0", " ").split(", ")]
    return ", ".join(n for n in names if n)


def title_with_version(title: str) -> str:
    """Spotify writes the version after a dash ('Domino - Space 92 Remix'); the title parser expects
    brackets ('Domino (Space 92 Remix)')."""
    t = re.sub(r"\s+", " ", (title or "").replace("\xa0", " ")).strip()
    if " - " in t:
        head, tail = t.split(" - ", 1)
        if head.strip() and tail.strip():
            return f"{head.strip()} ({tail.strip()})"
    return t


def display_title(artists: str, title: str) -> str:
    t = title_with_version(title)
    return f"{artists} - {t}" if artists else t


# --- the client ------------------------------------------------------------------------------------

class SpotifyClient:
    """Same small interface as SoundCloudClient: channel_info, latest, track."""

    TRACK_PAGE_SPACING = 0.5                           # seconds between two track pages: a polite reader

    def __init__(self, fetch=None, sleep=time.sleep):
        self._fetch = fetch or _fetch
        self._sleep = sleep
        self._info: dict[str, TrackInfo] = {}          # filled by latest(), read by track()
        self._detailed: set[str] = set()               # track links whose own page was read (cover, date)
        self._last_page = 0.0

    def _page(self, url: str) -> dict:
        pid = playlist_id(url)
        html = self._fetch(f"https://open.spotify.com/embed/playlist/{pid}")
        return parse_embed(html)

    def channel_info(self, url: str) -> ChannelInfo:
        url = normalize_playlist_url(url)
        entity = self._page(url)
        return ChannelInfo(url=url, name=(entity.get("name") or entity.get("title") or "Spotify playlist").strip(),
                           kind="playlist")

    def latest(self, url: str, include_reposts: bool = False, limit: int = MAX_TRACKS) -> list[TrackStub]:
        url = normalize_playlist_url(url)
        entity = self._page(url)
        out = []
        for e in entity.get("trackList") or []:
            uri = str(e.get("uri") or "")
            m = re.fullmatch(rf"spotify:track:({_ID})", uri)
            if not m or not e.get("title"):
                continue                                        # a podcast episode, a local file, an empty row
            tid = m.group(1)
            artists = clean_artists(e.get("subtitle") or "")
            raw = display_title(artists, e["title"])
            link = f"https://open.spotify.com/track/{tid}"
            seconds = (e.get("duration") or 0) / 1000 or None
            self._info[link] = TrackInfo(sc_id=PREFIX + tid, url=link, title=raw, uploader=artists,
                                         duration=seconds, uploaded_at=time.time())
            out.append(TrackStub(sc_id=PREFIX + tid, url=link, title=raw))
        return out

    def track(self, url: str) -> TrackInfo:
        """The details read by the last latest(), plus the cover and release date from the track's own embed
        page (the playlist page has no pictures per track). Without that page the playlist details still do."""
        info = self._info.get(url)
        if url in self._detailed and info is not None:
            return info
        extra = self._track_page(url)
        if extra is None:
            if info is None:
                raise ChannelError("No details for this Spotify track yet.")
            return info
        if info is None:
            info = extra
        else:
            info.artwork = extra.artwork or info.artwork
            info.released_at = extra.released_at or info.released_at
            info.duration = info.duration or extra.duration
        self._info[url] = info
        self._detailed.add(url)
        return info

    def _track_page(self, url: str) -> Optional[TrackInfo]:
        m = re.search(rf"/track/({_ID})", url or "")
        if not m:
            return None
        wait = self._last_page + self.TRACK_PAGE_SPACING - time.monotonic()
        if wait > 0:
            self._sleep(wait)
        self._last_page = time.monotonic()
        try:
            return parse_track_embed(self._fetch(f"https://open.spotify.com/embed/track/{m.group(1)}"), url)
        except ChannelError as e:
            log.info("no Spotify track details for %s: %s", url, e)
            return None


def parse_embed(html: str) -> dict:
    """The playlist 'entity' (name, trackList) inside the embed page, or a ChannelError that says why not."""
    m = _NEXT_DATA.search(html or "")
    if not m:
        raise ChannelError("Spotify's page looks different than expected, so SeekSync can't read this playlist. "
                           "Try again later, or check for a SeekSync update.")
    try:
        data = json.loads(m.group(1))
        props = data["props"]["pageProps"]
    except (ValueError, KeyError, TypeError) as e:
        raise ChannelError("Spotify's page looks different than expected, so SeekSync can't read this playlist. "
                           "Try again later, or check for a SeekSync update.") from e
    if props.get("status") in (404, 403):
        raise ChannelError("Spotify says this playlist doesn't exist, or it's private. "
                           "Only public playlists can be followed.")
    try:
        entity = props["state"]["data"]["entity"]
    except (KeyError, TypeError) as e:
        raise ChannelError("Spotify's page looks different than expected, so SeekSync can't read this playlist. "
                           "Try again later, or check for a SeekSync update.") from e
    if not isinstance(entity, dict) or entity.get("type") not in ("playlist", None) or "trackList" not in entity:
        raise ChannelError("Spotify shows no tracks for this link. Is it a public playlist?")
    return entity


def parse_track_embed(html: str, url: str) -> TrackInfo:
    """A track's embed page (open.spotify.com/embed/track/<id>): name, artists, length, release date and the
    album cover, biggest size first (Spotify offers 640, 300 and 64 px)."""
    m = _NEXT_DATA.search(html or "")
    try:
        e = json.loads(m.group(1))["props"]["pageProps"]["state"]["data"]["entity"] if m else None
    except (ValueError, KeyError, TypeError):
        e = None
    if not isinstance(e, dict) or e.get("type") != "track":
        raise ChannelError("Spotify's track page looks different than expected.")
    images = [i for i in ((e.get("visualIdentity") or {}).get("image") or [])
              if isinstance(i, dict) and str(i.get("url") or "").startswith("https://")]
    images.sort(key=lambda i: (i.get("maxWidth") or 0), reverse=True)
    released = None
    iso = str((e.get("releaseDate") or {}).get("isoString") or "")
    if iso:
        try:
            from datetime import datetime
            released = datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
        except ValueError:
            released = None
    artists = ", ".join(str(a.get("name") or "").strip() for a in e.get("artists") or []
                        if isinstance(a, dict) and a.get("name"))
    tid = str(e.get("id") or "")
    return TrackInfo(sc_id=PREFIX + tid if tid else "", url=url, title=display_title(artists, e.get("name") or e.get("title") or ""),
                     uploader=artists, duration=((e.get("duration") or 0) / 1000) or None,
                     artwork=images[0]["url"] if images else "", uploaded_at=time.time(), released_at=released)


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise ChannelError("Spotify is blocking requests right now. Try again in a few minutes.") from e
        if e.code == 404:
            raise ChannelError("Spotify says this playlist doesn't exist, or it's private.") from e
        raise ChannelError(f"Couldn't read this Spotify playlist (HTTP {e.code}).") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ChannelError("Can't reach Spotify. Check your internet connection.") from e
