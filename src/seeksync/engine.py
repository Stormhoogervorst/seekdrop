"""The background worker: watch channels, search Soulseek, download, retry."""
from __future__ import annotations

import asyncio
import errno
import json
import logging
import os
import re
import shutil
import time
from collections import deque
from dataclasses import replace
from typing import Callable, Optional

from . import db as states
from .config import SettingsStore
from .config import data_dir
from .db import Database
from .matching import Candidate, MatchPrefs, aliases_of, closest, folder_of, parse_aliases, rank, summary
from .politeness import (BLOCK_DAYS, SearchThrottle, block_reason, low_disk_space, peer_score,
                         sharing_warning)
from .nicotine import migrate_legacy_plugin, update_plugin_if_outdated
from .soundcloud import SoundCloudClient, TrackStub
from .sources import source_name
from .spotify import MAX_TRACKS as SPOTIFY_MAX
from .quality import (TIER_LABELS, UPGRADE_DAYS, UPGRADE_EVERY, is_better, profile, tier_of,
                      wants_upgrade)
from . import __version__, library, naming, rekordbox, tagging
from . import rules as rules_mod
from .titles import parse_title, search_queries

log = logging.getLogger(__name__)

RETRY_DELAYS = [3600, 3 * 3600, 6 * 3600, 12 * 3600, 24 * 3600]
QUEUE_TIMEOUT = 45 * 60       # give up on a peer whose queue doesn't move
STALL_TIMEOUT = 5 * 60        # no bytes received for this long while downloading
MAX_CANDIDATES = 3            # peers to try per search round
SEARCH_WAIT = 12.0            # seconds to collect results per search
TRASH_DAYS = 30               # replaced files stay in the app's trash this long


REKORDBOX_DELAY = 30           # seconds to wait after a download before the Rekordbox XML is written again
PART_SUFFIX = ".seeksync-part"   # hidden temp name while a file is copied to another disk
OLD_PART_SUFFIXES = (".seekdrop-part",)    # leftovers of the previous app name are tidied up too

# A check gets the track row and the staged file and returns a reason to reject it, or None.
Check = Callable[[dict, str], Optional[str]]


def publish_file(src: str, dest: str) -> None:
    """Move src to dest so that dest appears in one go, complete and with its final name.
    Same disk: a rename. Other disk (e.g. music on an external drive): copy to a hidden temp file
    next to dest, then rename that; a half-copied file never carries the real name."""
    try:
        os.rename(src, dest)
        return
    except OSError as e:
        if e.errno != errno.EXDEV:
            raise
    tmp = os.path.join(os.path.dirname(dest), "." + os.path.basename(dest) + PART_SUFFIX)
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    os.remove(src)


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _clear_dir(path: str) -> int:
    """Delete everything inside path (not path itself). Returns the number of entries removed."""
    n = 0
    if not path or not os.path.isdir(path):
        return 0
    for name in os.listdir(path):
        full = os.path.join(path, name)
        try:
            if os.path.isdir(full) and not os.path.islink(full):
                shutil.rmtree(full)
            else:
                os.remove(full)
            n += 1
        except OSError:
            log.debug("couldn't remove %s", full, exc_info=True)
    return n


def _load_meta(t: dict) -> dict:
    try:
        meta = json.loads(t.get("sc_meta") or "{}")
        return meta if isinstance(meta, dict) else {}
    except ValueError:
        return {}


def _year(ts) -> str:
    try:
        return str(time.gmtime(float(ts)).tm_year) if ts else ""
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def safe_filename(name: str, limit: int = 150) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:limit].strip(" .") or "track"


class Engine:
    def __init__(self, db: Database, store: SettingsStore, sc: SoundCloudClient, slsk, poll_tick: float = 30.0,
                 slsk_factory=None, staging_dir: Optional[str] = None, quarantine_dir: Optional[str] = None):
        self.db = db
        # Finished downloads wait here (app data, never the music folder) until every check passed.
        self.staging_dir = staging_dir or str(data_dir() / "staging")
        # Files that failed a check, kept so the user can look at them, approve or delete them.
        self.quarantine_dir = quarantine_dir or str(data_dir() / "quarantine")
        # Step 4: a replaced file goes to the trash (kept TRASH_DAYS); a better copy waiting for the
        # user's OK ("ask" mode) waits in upgrades/.
        root = os.path.dirname(self.quarantine_dir)
        self.trash_dir = os.path.join(root, "trash")
        self.upgrades_dir = os.path.join(root, "upgrades")
        self.checks: list[Check] = []   # file checks (roadmap steps 2, 3, 10) run on the staged file
        self.file_checker = None        # the ffmpeg check (checks.FileChecker), shown in Settings
        self._clean_incoming = True     # once per start, after leftover transfers were dealt with
        self.slsk_factory = slsk_factory   # mode -> service; lets the user switch built-in / Nicotine+
        self.store = store
        self.sc = sc
        self.slsk = slsk
        self.poll_tick = poll_tick
        self.activity: deque[dict] = deque(maxlen=80)
        self.active: dict[int, dict] = {}          # track id -> {"transfer", "task", "candidate"}
        self.checking: set[int] = set()            # channel ids being checked
        self.next_poll_at: float = 0.0
        self._wake_poll = asyncio.Event()
        self._wake_search = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._stale: list[dict] = []
        self._share_rescan: Optional[asyncio.Task] = None
        self.throttle = SearchThrottle()       # step 8: spacing + maximum per 5 minutes
        self.paused_reason = ""                # step 8: set while the disk is too full to download
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._rb_task: Optional[asyncio.Task] = None
        self._rb_lock = asyncio.Lock()
        self._rb_cache: dict = {}
        self.rekordbox_state = {"written_at": 0.0, "tracks": 0, "playlists": 0, "error": ""}
        self._rb_known: Optional[tuple] = None             # (path, mtime, size) -> set of paths in the user's Rekordbox export
        self.rekordbox_library = {"tracks": 0, "error": ""}
        self._scan_lock = asyncio.Lock()       # step 11: one scan of the music folders at a time
        self.library_state = {"scanning": False, "done": 0, "total": 0, "files": 0,
                              "scanned_at": 0.0, "missing": [], "error": ""}

    # ------------------------------------------------------------------ lifecycle
    @property
    def settings(self):
        return self.store.settings

    def note(self, msg: str, level: str = "info") -> None:
        self.activity.appendleft({"t": time.time(), "msg": msg, "level": level})
        getattr(log, "warning" if level == "warn" else "info")(msg)

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        # Transfers from the last session may still sit in Nicotine+'s queue; tidy them up once connected.
        self._stale = self.db.interrupted_transfers()
        self.db.reset_interrupted()
        self._tidy_files()
        if self.settings.configured:
            await self._connect()
        self._tasks = [
            asyncio.create_task(self._poll_loop(), name="poll"),
            asyncio.create_task(self._search_loop(), name="search"),
            asyncio.create_task(self._watchdog(), name="watchdog"),
            asyncio.create_task(self._status_watch(), name="status"),
            asyncio.create_task(self.scan_library(), name="library"),
            asyncio.create_task(self.write_rekordbox(), name="rekordbox"),
        ]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        downloads = [entry["task"] for entry in self.active.values()]
        for t in downloads:
            t.cancel()
        # Let cancelled downloads abort their transfers before the connection goes away.
        try:
            await asyncio.wait_for(asyncio.gather(*self._tasks, *downloads, return_exceptions=True), 10)
        except asyncio.TimeoutError:
            log.warning("some downloads didn't stop in time")
        await self.slsk.stop()

    def _tidy_files(self) -> None:
        """Leftovers of a crash or forced quit: anything in staging, and hidden half-copied files in
        the music folder. Incoming is cleaned later, once leftover transfers have been dealt with."""
        n = _clear_dir(self.staging_dir)
        if os.path.isdir(self.trash_dir):
            cutoff = time.time() - TRASH_DAYS * 86400
            for name in os.listdir(self.trash_dir):
                full = os.path.join(self.trash_dir, name)
                try:
                    if os.path.getmtime(full) < cutoff:
                        shutil.rmtree(full) if os.path.isdir(full) else os.remove(full)
                except OSError:
                    pass
        root = self.settings.download_dir
        if root and os.path.isdir(root):
            dirs = [root] + [os.path.join(root, d) for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]
            for d in dirs:
                for name in os.listdir(d):
                    if name.startswith(".") and name.endswith((PART_SUFFIX, *OLD_PART_SUFFIXES)):
                        try:
                            os.remove(os.path.join(d, name))
                            n += 1
                        except OSError:
                            pass
        if n:
            log.info("Removed %d leftover file(s) from an earlier session", n)

    def _tidy_incoming(self) -> None:
        if self.active:            # never while downloads are running
            return
        n = _clear_dir(getattr(self.slsk, "incoming_dir", ""))
        if n:
            log.info("Removed %d leftover file(s) from the incoming folder", n)
        self._clean_incoming = False

    async def _recover_stale(self) -> None:
        """Deal with transfers from the previous session: keep files that finished meanwhile,
        cancel the rest (the track is searched again)."""
        remaining = []
        for t in self._stale:
            try:
                info = await self.slsk.lookup(t["peer"], t["remote_file"])
                if info and info["state"] == "COMPLETE" and info.get("local_path") and os.path.exists(info["local_path"]):
                    c = Candidate(t["peer"], t["remote_file"])
                    path, why = await self._stage_and_publish(t, info["local_path"], c)
                    await self.slsk.cancel(t["peer"], t["remote_file"])   # clears the finished entry
                    if path:
                        self.db.update_track(t["id"], state=states.DONE, file_path=path, progress=1.0, last_error="",
                                             **self._done_fields(t, c))
                        self.note(f"Downloaded {os.path.basename(path)}")
                elif info:
                    await self.slsk.cancel(t["peer"], t["remote_file"])
            except Exception:
                log.debug("couldn't tidy up %s", t["remote_file"], exc_info=True)
                remaining.append(t)
        self._stale = remaining

    async def _connect(self) -> None:
        if self.settings.soulseek_mode == "nicotine":
            try:
                if await asyncio.to_thread(migrate_legacy_plugin):
                    self.note("The Nicotine+ plugin has a new name. In Nicotine+, turn off the old bridge plugin (SeekDrop Bridge) "
                              "and turn on SeekSync Bridge (Preferences, Plugins).", "warn")
                elif await asyncio.to_thread(update_plugin_if_outdated):
                    self.note("Updated the Nicotine+ plugin. In Nicotine+, turn SeekSync Bridge off and on "
                              "(Preferences, Plugins) to use the new version.", "warn")
            except OSError as e:
                log.warning("couldn't update the Nicotine+ plugin: %s", e)
            self.note("Connecting to Nicotine+…")
            await self.slsk.start(self.settings)
            if self.slsk.connected:
                self.note(f"Connected through Nicotine+ as {getattr(self.slsk, 'username', '')}.")
            elif self.slsk.error:
                self.note(self.slsk.error, "warn")
            return
        self.note(f"Connecting to Soulseek as {self.settings.soulseek_username}…")
        await self.slsk.start(self.settings)
        if self.slsk.connected:
            self.note("Connected to Soulseek.")
        elif self.slsk.error:
            self.note(self.slsk.error, "warn")

    async def apply_settings(self, changed: set[str]) -> None:
        reconnect = {"soulseek_username", "soulseek_password", "listen_port", "share_dirs",
                     "share_downloads", "download_dir", "accepted_terms",
                     "soulseek_mode", "nicotine_port", "nicotine_token"}
        if self.slsk_factory and getattr(self.slsk, "mode", None) != self.settings.soulseek_mode:
            for entry in list(self.active.values()):
                entry["task"].cancel()
            await self.slsk.stop()
            self.slsk = self.slsk_factory(self.settings.soulseek_mode)
        if changed & reconnect and self.settings.configured:
            for entry in list(self.active.values()):
                entry["task"].cancel()
            await self._connect()
        if changed & {"rekordbox_export", "rekordbox_xml_path", "label_from_channel"}:
            asyncio.create_task(self.write_rekordbox())
        if changed & {"library_dirs", "download_dir"}:
            asyncio.create_task(self.scan_library())
        if changed & {"block_keywords", "block_artists"}:
            self.reapply_rules()
        if changed & {"check_interval_minutes"}:
            self.next_poll_at = time.time() + self.settings.check_interval_minutes * 60
        self.wake()

    def wake(self, poll: bool = False) -> None:
        if poll:
            self.next_poll_at = 0
            self._wake_poll.set()
        self._wake_search.set()

    async def _status_watch(self) -> None:
        """Note in the activity list when the connection drops or comes back by itself."""
        was = self.slsk.connected
        while True:
            await asyncio.sleep(3)
            now = self.slsk.connected
            if now and not was:
                self.note("Connected through Nicotine+." if getattr(self.slsk, "mode", "") == "nicotine"
                          else "Connected to Soulseek.")
            elif was and not now and self.slsk.error:
                self.note(self.slsk.error, "warn")
            was = now

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(120)
            if self.settings.configured and self.slsk.status == "error" and self.slsk.retryable:
                await self._connect()

    # ------------------------------------------------------------------ SoundCloud
    async def _poll_loop(self) -> None:
        while True:
            try:
                if self.settings.configured and time.time() >= self.next_poll_at:
                    self.next_poll_at = time.time() + self.settings.check_interval_minutes * 60
                    await self.scan_library()           # so new uploads are compared with what you have now
                    for ch in self.db.channels():
                        if ch["enabled"]:
                            await self.check_channel(ch["id"])
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("poll loop error")
            self._wake_poll.clear()
            try:
                await asyncio.wait_for(self._wake_poll.wait(), self.poll_tick)
            except asyncio.TimeoutError:
                pass

    async def check_channel(self, cid: int) -> None:
        ch = self.db.channel(cid)
        if not ch or cid in self.checking:
            return
        self.checking.add(cid)
        try:
            stubs: list[TrackStub] = await asyncio.to_thread(self.sc.latest, ch["url"], bool(ch["include_reposts"]))
            playlist = ch.get("kind") == "playlist"
            known_rows = self.db.tracks_by_sc_ids([s.sc_id for s in stubs])
            known = {r["sc_id"] for r in known_rows}
            new = [s for s in stubs if s.sc_id not in known]
            if playlist:
                # A playlist is a wish list: every track in it is wanted, in playlist order.
                wanted = new
                revived = self._claim_skipped(cid, known_rows)
                if not ch["initialized"]:
                    cap = (f" Spotify shows only the first {SPOTIFY_MAX} tracks of a playlist."
                           if source_name(ch["url"]) == "Spotify" and len(stubs) >= SPOTIFY_MAX else "")
                    self.note(f"{ch['name']}: getting {len(wanted) + revived} track(s) from this playlist.{cap}")
                elif wanted or revived:
                    self.note(f"{ch['name']}: {len(wanted) + revived} new track(s) in the playlist.")
            elif not ch["initialized"]:
                # First look at a channel: only the newest `backlog` tracks are wanted.
                wanted = new[: ch["backlog"]]
                for s in new[ch["backlog"]:]:
                    p = parse_title(s.title)
                    self.db.add_track(channel_id=cid, sc_id=s.sc_id, url=s.url, raw_title=s.title,
                                      artist=p.artist, title=p.title, version=p.version, state=states.SKIPPED)
                if wanted:
                    self.note(f"{ch['name']}: getting the latest {len(wanted)} track(s).")
                else:
                    self.note(f"{ch['name']}: watching for new releases.")
            else:
                wanted = new
                if wanted:
                    self.note(f"{ch['name']}: {len(wanted)} new track(s).")
            skipped = failed = collected = 0
            for s in (wanted if playlist else reversed(wanted)):   # profiles: oldest first
                added = await self._add_wanted(cid, s)
                if added is None:
                    failed += 1
                elif added == "collected":
                    collected += 1
                elif not added:
                    skipped += 1
            if collected:
                self.note(f"{ch['name']}: {collected} track(s) already in your collection.")
            if skipped:
                self.note(f"{ch['name']}: skipped {skipped} track(s) because of your rules.")
            if failed:
                self.note(f"{ch['name']}: couldn't read {failed} track(s) from {source_name(ch['url'])}, trying again next check.", "warn")
            self.db.update_channel(cid, last_checked=time.time(), last_error="", initialized=1)
            self._wake_search.set()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("channel check failed")
            msg = str(e).replace("ERROR: ", "")[:200]
            self.db.update_channel(cid, last_checked=time.time(), last_error=msg)
            self.note(f"{ch['name']}: couldn't check {source_name(ch['url'])} ({msg})", "warn")
        finally:
            self.checking.discard(cid)

    def _claim_skipped(self, cid: int, rows: list[dict]) -> int:
        """Tracks in a playlist that another channel skipped (older than its backlog) are wanted
        after all: move them to the playlist. Tracks skipped by the user in this playlist, or
        skipped as a mix, stay skipped."""
        n = 0
        for r in rows:
            if r["state"] == states.SKIPPED and r["channel_id"] != cid and not r["last_error"]:
                why = self._rule_reason(cid, self._parsed(r), r["raw_title"], r["duration"])
                if why:   # this playlist's rules don't want it either
                    self.db.update_track(r["id"], channel_id=cid, last_error=why, skip_rule=why)
                    continue
                self.db.update_track(r["id"], channel_id=cid, state=states.WANTED, next_attempt=0)
                n += 1
        return n

    def _rule_reason(self, cid: int, p, raw: str, duration) -> str:
        """Why the rules of this channel (and the global blocklist) skip an upload; '' = wanted."""
        ch = self.db.channel(cid)
        return rules_mod.check(rules_mod.parse_rules(ch["rules"] if ch else ""), p, raw, duration,
                               self.settings.block_keywords, self.settings.block_artists)

    def reapply_rules(self, cid: Optional[int] = None) -> tuple[int, int]:
        """After the user changed rules: tracks a rule had skipped come back when they are allowed now,
        and tracks not yet searched are skipped when they are not. Downloads, tracks in progress and
        tracks the user fetched or stopped by hand are left alone. Returns (revived, skipped)."""
        revived = skipped = 0
        for t in self.db.tracks_for_rules(cid):
            why = self._rule_reason(t["channel_id"], self._parsed(t), t["raw_title"], t["duration"])
            if t["state"] == states.SKIPPED:
                if why:
                    if why != t["skip_rule"]:
                        self.db.update_track(t["id"], last_error=why, skip_rule=why)
                else:
                    self.db.update_track(t["id"], state=states.WANTED, next_attempt=0, last_error="", skip_rule="")
                    revived += 1
            elif why:
                self.db.update_track(t["id"], state=states.SKIPPED, last_error=why, skip_rule=why)
                skipped += 1
        if revived:
            self._wake_search.set()
        return revived, skipped

    async def _add_wanted(self, cid: int, stub: TrackStub) -> Optional[bool]:
        """Store a new upload. Returns False if a rule skipped it (step 9), "collected" if it is already in
        the DJ's own folders (step 11), True if it is wanted, and None if
        SoundCloud gave no title for it (not stored, so the next check tries again)."""
        try:
            info = await asyncio.to_thread(self.sc.track, stub.url)
        except Exception:
            log.debug("track details failed for %s", stub.url, exc_info=True)
            info = None
        raw = (info.title if info else "") or stub.title
        if not raw:
            return None
        uploader = info.uploader if info else ""
        pub = info.publisher_artist if info else ""
        p = parse_title(raw, uploader=uploader, publisher_artist=pub)
        duration = info.duration if info else None
        reason = self._rule_reason(cid, p, raw, duration)
        hit = None if reason else self._collection_hit(p, duration)
        self.db.add_track(
            channel_id=cid, sc_id=stub.sc_id, url=(info.url if info else stub.url), raw_title=raw,
            uploader=uploader, publisher_artist=pub, artist=p.artist, title=p.title, version=p.version,
            duration=duration, artwork=info.artwork if info else "",
            uploaded_at=info.uploaded_at if info else None,
            state=states.SKIPPED if reason else states.COLLECTED if hit else states.WANTED,
            last_error=reason, skip_rule=reason, file_path=hit["path"] if hit else "", sc_meta=self._sc_meta(info))
        return "collected" if hit else not reason

    @staticmethod
    def _sc_meta(info) -> str:
        """What SoundCloud knows that goes into the tags (step 10): genre and release date."""
        meta = {}
        if info and info.genre:
            meta["genre"] = info.genre
        if info and info.released_at:
            meta["released_at"] = info.released_at
        return json.dumps(meta) if meta else ""

    # ------------------------------------------------------------------ Rekordbox (step 12)
    def rekordbox_path(self) -> str:
        p = (self.settings.rekordbox_xml_path or "").strip()
        p = os.path.abspath(os.path.expanduser(p)) if p else os.path.join(self.settings.download_dir, rekordbox.DEFAULT_NAME)
        return os.path.join(p, rekordbox.DEFAULT_NAME) if os.path.isdir(p) else p

    def rekordbox_known(self) -> Optional[set]:
        """The paths in the user's Rekordbox collection export, or None when none is set or it can't be read.
        Cached until the file changes. Only reads the file."""
        path = (self.settings.rekordbox_library_xml or "").strip()
        if not path:
            self.rekordbox_library.update(tracks=0, error="")
            return None
        path = os.path.abspath(os.path.expanduser(path))
        try:
            st = os.stat(path)
            key = (path, st.st_mtime_ns, st.st_size)
            if self._rb_known and self._rb_known[0] == key:
                return self._rb_known[1]
            known = rekordbox.collection_paths(path)
        except Exception as e:
            self._rb_known = None
            self.rekordbox_library.update(tracks=0, error=(e.strerror if isinstance(e, OSError) and e.strerror else
                                                           "That doesn't look like a Rekordbox export")[:120])
            return None
        self._rb_known = (key, known)
        self.rekordbox_library.update(tracks=len(known), error="")
        return known

    def in_rekordbox(self, file_path: str) -> Optional[bool]:
        """Is this file in the user's Rekordbox collection? None = unknown (no export, or unreadable)."""
        known = self.rekordbox_known()
        return None if known is None else rekordbox.has_file(known, file_path)

    def schedule_rekordbox(self) -> None:
        """Write the Rekordbox XML again soon (once for a burst of downloads). Safe to call from any thread."""
        if not self.settings.rekordbox_export:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._start_rekordbox_timer)

    def _start_rekordbox_timer(self) -> None:
        if self._rb_task and not self._rb_task.done():
            return

        async def later():
            await asyncio.sleep(REKORDBOX_DELAY)
            await self.write_rekordbox()
        self._rb_task = asyncio.get_running_loop().create_task(later())

    async def write_rekordbox(self) -> None:
        if not self.settings.rekordbox_export:
            return
        async with self._rb_lock:
            try:
                await asyncio.to_thread(self.write_rekordbox_sync)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.exception("Rekordbox XML failed")
                self.rekordbox_state["error"] = (e.strerror if isinstance(e, OSError) and e.strerror else str(e))[:200]
                self.note(f"Couldn't write the Rekordbox file ({self.rekordbox_state['error']}).", "warn")

    def write_rekordbox_sync(self) -> dict:
        """Collect every finished download that is still on disk and write the XML. Returns the new state."""
        tracks: list[rekordbox.Track] = []
        order: dict[int, list] = {}
        for t in self.db.tracks_for_rekordbox():
            path = t["file_path"]
            if not os.path.isfile(path):
                continue
            meta = self._tag_meta(t)
            facts = rekordbox.file_facts(path, self._rb_cache)
            tracks.append(rekordbox.Track(track_id=t["id"], path=path, name=meta.title, artist=meta.artist,
                                          genre=meta.genre, year=meta.year, label=meta.label, comment=meta.comment,
                                          added=t["created_at"], **facts))
            order.setdefault(t["channel_id"], [t["channel_name"], []])[1].append(t["id"])
        names = rekordbox.unique_names([n for n, _ids in order.values()])
        playlists = [rekordbox.Playlist(name, ids) for name, (_n, ids) in zip(names, order.values())]
        path = self.rekordbox_path()
        rekordbox.write(path, tracks, playlists, __version__)
        self.rekordbox_state.update(written_at=time.time(), tracks=len(tracks), playlists=len(playlists), error="")
        return dict(self.rekordbox_state)

    # ------------------------------------------------------------------ your own music folders (step 11)
    def library_roots(self) -> list[str]:
        """The folders that count as "what the DJ has": the listed ones and SeekSync's own download folder."""
        return library.clean_roots([self.settings.download_dir, *self.settings.library_dirs])

    def _collection_hit(self, p, duration) -> Optional[dict]:
        try:
            return library.find(self.db, p, duration, parse_aliases(self.settings.artist_aliases))
        except Exception:
            log.debug("collection lookup failed", exc_info=True)
            return None

    def _scan_progress(self, done: int, total: int) -> None:
        self.library_state.update(done=done, total=total)

    async def scan_library(self) -> None:
        """Bring the index of the music folders up to date (new and changed files only), then compare
        the tracks that are still waiting with it."""
        async with self._scan_lock:
            st = self.library_state
            st.update(scanning=True, done=0, total=0, error="")
            try:
                if not self.db.library_count():
                    self.note("Reading your music folders for the first time. Searching starts when that is done.")
                res = await asyncio.to_thread(library.scan, self.db, self.library_roots(), self._scan_progress)
                st.update(files=res.files, scanned_at=time.time(), missing=res.missing or [])
                if res.added or res.removed:
                    self.note(f"Music folders: {res.files} file(s), {res.added} new, {res.removed} gone.")
                for m in res.missing or []:
                    self.note(f"The music folder {m} isn't there (drive not connected?). What was known about it is kept.", "warn")
                found, lost = await asyncio.to_thread(self.recheck_collection)
                if found:
                    self.note(f"{found} track(s) were already in your collection.")
                if lost:
                    self.note(f"{lost} track(s) are no longer in your folders and are wanted again.")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.exception("library scan failed")
                st["error"] = str(e)[:200]
            finally:
                st["scanning"] = False
                st["files"] = self.db.library_count()
        self._wake_search.set()

    def recheck_collection(self) -> tuple[int, int]:
        """After a scan: waiting tracks that are in the folders now become 'collected'; collected tracks whose
        file is gone become wanted again. Tracks being searched, downloaded, finished, skipped by the user or
        fetched on purpose are left alone. Returns (found, lost)."""
        found = lost = 0
        aliases = parse_aliases(self.settings.artist_aliases)
        for t in self.db.tracks_for_collection():
            hit = library.find(self.db, self._parsed(t), t["duration"], aliases)
            if t["state"] == states.COLLECTED:
                if not hit:
                    self.db.update_track(t["id"], state=states.WANTED, file_path="", next_attempt=0, last_error="")
                    lost += 1
                elif hit["path"] != t["file_path"]:
                    self.db.update_track(t["id"], file_path=hit["path"])
            elif hit and t["id"] not in self.active:
                self.db.update_track(t["id"], state=states.COLLECTED, file_path=hit["path"], last_error="", progress=0)
                found += 1
        return found, lost

    def duplicates(self) -> list[dict]:
        """Duplicate files in SeekSync's download folder, best copy first. Nothing is touched."""
        rows = [r for r in self.db.library_under(self.settings.download_dir) if os.path.exists(r["path"])]
        return library.duplicates(rows, self.settings.quality_profile)

    # ------------------------------------------------------------------ Soulseek
    async def _search_loop(self) -> None:
        while True:
            try:
                if self.settings.configured and self.slsk.connected:
                    if self._stale:
                        await self._recover_stale()
                    if self._clean_incoming and not self._stale:
                        self._tidy_incoming()
                    paused = self._check_disk() or self.library_state["scanning"]   # not while the library is being read
                    for t in ([] if paused else self.db.due_tracks(time.time())):
                        if len(self.active) >= self.settings.max_parallel_downloads:
                            break
                        if not self.slsk.connected:
                            break
                        await self._search_track(t)
                    # Better copies (step 4): only with a free slot, one at a time.
                    if (self.settings.upgrade_mode != "off" and not paused
                            and len(self.active) < self.settings.max_parallel_downloads):
                        now = time.time()
                        for t in self.db.due_upgrades(now, now - UPGRADE_DAYS * 86400, limit=1):
                            if t["id"] not in self.active:
                                await self._upgrade_search(t)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("search loop error")
            self._wake_search.clear()
            try:
                await asyncio.wait_for(self._wake_search.wait(), 20)
            except asyncio.TimeoutError:
                pass

    async def _throttle(self) -> None:
        """Wait our turn for a Soulseek search (spacing and maximum per 5 minutes, step 8)."""
        self.throttle.configure(self.settings.search_spacing, self.settings.search_max_per_5min)
        await self.throttle.wait()

    def _check_disk(self) -> str:
        """Pause new downloads while the disk is too full; note it once and resume by itself."""
        why = low_disk_space([os.path.dirname(self.staging_dir), self.settings.download_dir],
                             self.settings.min_free_gb) or ""
        if why and not self.paused_reason:
            self.note(why, "warn")
        elif self.paused_reason and not why:
            self.note("There is enough disk space again, downloads continue.")
        self.paused_reason = why
        return why

    def share_warning(self) -> str:
        """A message when nothing is shared on Soulseek (users who share nothing are often blocked)."""
        slsk = self.slsk
        if getattr(slsk, "mode", "") == "nicotine":
            return sharing_warning(None, folders=getattr(slsk, "shared_folders", None),
                                   files=getattr(slsk, "shared_files", None))
        from .soulseek import _share_dirs
        return sharing_warning(_share_dirs(self.settings))

    def _prefs(self, t: Optional[dict] = None, candidates: Optional[list] = None) -> MatchPrefs:
        """Matching preferences, with what we know about peers (step 8): reputation, blocks, and where
        earlier tracks of this release came from (an EP or album is best taken from one place)."""
        prefs = MatchPrefs(profile=self.settings.quality_profile, aliases=parse_aliases(self.settings.artist_aliases))
        if not candidates:
            return prefs
        now = time.time()
        stats = self.db.peer_stats(sorted({c.username for c in candidates}))
        for name, r in stats.items():
            if r["blocked_until"] > now:
                prefs.blocked_peers[name] = r["block_reason"] or "too many problems before"
            else:
                prefs.peer_scores[name] = peer_score(r["ok"], r["failed"], r["fake"])
        if t:
            earlier = self.db.peers_of_channel(t["channel_id"], t.get("artist") or "")
            prefs.same_folder = frozenset((r["peer"], folder_of(r["remote_file"])) for r in earlier)
            prefs.same_peers = frozenset(r["peer"] for r in earlier)
        return prefs

    def _record_peer(self, username: str, outcome: str) -> None:
        """Count a good delivery, a failed download or a fake file for a peer; block repeat offenders."""
        try:
            r = self.db.bump_peer(username, outcome)
            why = block_reason(r["ok"], r["failed"], r["fake"])
            if why and r["blocked_until"] <= time.time():
                self.db.block_peer(username, time.time() + BLOCK_DAYS * 86400, why)
                self.note(f"Blocked {username} for {BLOCK_DAYS} days: {why.lower()}", "warn")
        except Exception:
            log.debug("couldn't record peer %s", username, exc_info=True)

    def unblock_peer(self, username: str) -> None:
        self.db.unblock_peer(username)

    async def _search_track(self, t: dict) -> None:
        tid = t["id"]
        p = self._parsed(t)
        if t["skip_rule"] != rules_mod.OVERRIDDEN:
            hit = self._collection_hit(p, t["duration"])
            if hit:                                   # added to your folders since it was queued
                self.db.update_track(tid, state=states.COLLECTED, file_path=hit["path"], last_error="")
                self.note(f"{p.display} is already in your collection.")
                return
        self.db.update_track(tid, state=states.SEARCHING, attempts=t["attempts"] + 1)
        ranked: list[Candidate] = []
        tried: list[dict] = []                 # {"query", "results"} for "Why not?"
        evaluated: dict[tuple, Candidate] = {}
        try:
            for q in self._queries(t, p):
                await self._throttle()
                results = await self.slsk.search(q, wait=SEARCH_WAIT)
                tried.append({"query": q, "results": len(results)})
                ranked = rank(p, t["duration"], results, self._prefs(t, results))
                blocked = self.db.blocked(tid)      # files that failed the checks before
                for c in results:
                    if (c.username, c.filename) in blocked and not c.rejected:
                        c.rejected, c.stage = "Failed the file check before", 5
                    evaluated.setdefault((c.username, c.filename), c)
                ranked = [c for c in ranked if (c.username, c.filename) not in blocked]
                if ranked:
                    break
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("search failed for %s: %s", p.display, e)
            self.db.update_track(tid, state=states.WANTED, next_attempt=time.time() + 300,
                                 last_error="Search failed, retrying in 5 minutes")
            return

        # Count each file once, even when several search terms found it.
        why = summary(len(evaluated), list(evaluated.values()), [x["query"] for x in tried]) if not ranked else ""
        self._save_search(tid, tried, list(evaluated.values()), why)
        current = self.db.track(tid)
        if not current or current["state"] != states.SEARCHING:   # user skipped meanwhile
            return
        if not ranked:
            self._schedule_retry(current, why)
            return

        self.db.update_track(tid, state=states.DOWNLOADING, progress=0, last_error="")
        task = asyncio.create_task(self._download(current, ranked[:MAX_CANDIDATES]))
        self.active[tid] = {"task": task, "transfer": None, "candidate": None}

    @staticmethod
    def _parsed(t: dict):
        """What we look for: the automatic parse of the SoundCloud title, with the user's own
        corrections (step 6) taking precedence field by field."""
        p = parse_title(t["raw_title"], uploader=t["uploader"], publisher_artist=t["publisher_artist"])
        fa, ft, fv = (t.get("fix_artist") or "").strip(), (t.get("fix_title") or "").strip(), (t.get("fix_version") or "").strip()
        if fa:
            fixed = parse_title(f"{fa} - x")           # splits "A x B" into main + extra artists
            p = replace(p, artist=fixed.artist or fa, extra_artists=fixed.extra_artists, artist_from_uploader=False)
        if ft:
            p = replace(p, title=ft)
        if fv:
            p = replace(p, version="" if fv.lower() in ("original", "original mix") else fv)
        return p

    def set_fix(self, tid: int, artist: str, title: str, version: str) -> None:
        """Save the user's correction of artist / title / version and search again with it."""
        clean = lambda v: " ".join((v or "").split())[:200]
        self.db.update_track(tid, fix_artist=clean(artist), fix_title=clean(title), fix_version=clean(version))
        t = self.db.track(tid)
        if not t:
            return
        p = self._parsed(t)
        self.db.update_track(tid, artist=p.artist, title=p.title, version=p.version)   # what the list shows
        if t["state"] in (states.WAITING, states.GAVE_UP, states.SKIPPED, states.WANTED):
            self.retry_now(tid)

    def _queries(self, t: dict, p) -> list[str]:
        """The user's own search term first (step 5), then the automatic ones, then the same under
        each alias of the artist (step 6)."""
        auto = search_queries(p)
        alias_q = []
        main = p.artist.split(",")[0]
        for alias in aliases_of(main, parse_aliases(self.settings.artist_aliases)):
            alias_q += search_queries(replace(p, artist=alias, extra_artists=[]))[:1]
        out = []
        for q in ([t.get("custom_query") or ""] + auto[:1] + alias_q + auto[1:]):
            q = q.strip()
            if q and q not in out:
                out.append(q)
        return out

    def _save_search(self, tid: int, tried: list[dict], evaluated: list[Candidate], why: str) -> None:
        keep = [{
            "username": c.username, "filename": c.filename, "size": c.size, "ext": c.ext,
            "bitrate": c.bitrate, "duration": c.duration, "sample_rate": c.sample_rate, "bit_depth": c.bit_depth,
            "free_slots": c.has_free_slots, "queue": c.queue_size, "speed": c.avg_speed,
            "score": c.score, "rejected": c.rejected, "notes": c.reasons,
        } for c in closest(evaluated, 10)]
        try:
            self.db.add_search(tid, tried, keep, why)
        except Exception:
            log.debug("couldn't store search attempt", exc_info=True)

    # ------------------------------------------------------------------ "Why not?" actions (step 5)
    def pick(self, tid: int, cand: dict) -> bool:
        """The user picks a file from "Why not?". It still goes through staging and the file checks."""
        t = self.db.track(tid)
        if not t or tid in self.active or t["state"] not in (states.WANTED, states.WAITING, states.GAVE_UP, states.SKIPPED):
            return False
        c = Candidate(username=cand["username"], filename=cand["filename"], size=int(cand.get("size") or 0),
                      ext=cand.get("ext") or "", bitrate=cand.get("bitrate"), duration=cand.get("duration"),
                      sample_rate=cand.get("sample_rate"), bit_depth=cand.get("bit_depth"))
        self.db.update_track(tid, state=states.DOWNLOADING, progress=0, last_error="")
        task = asyncio.create_task(self._download(self.db.track(tid), [c]))
        self.active[tid] = {"task": task, "transfer": None, "candidate": None}
        self.note(f"Getting {c.basename} from {c.username}, as you asked")
        return True

    def set_query(self, tid: int, query: str) -> None:
        """Save the user's own search term (kept for every later attempt) and search right away."""
        self.db.update_track(tid, custom_query=" ".join((query or "").split())[:200])
        t = self.db.track(tid)
        if t and t["state"] in (states.WAITING, states.GAVE_UP, states.SKIPPED, states.WANTED):
            self.retry_now(tid)

    def stop_looking(self, tid: int) -> None:
        self.skip(tid)
        self.db.update_track(tid, last_error="Stopped by you")

    async def _download(self, t: dict, candidates: list[Candidate]) -> None:
        tid = t["id"]
        reason = "Download failed"
        try:
            for c in candidates:
                ok, info = await self._try_candidate(t, c)
                if ok:
                    try:
                        path, why = await self._stage_and_publish(t, info["local_path"], c)
                    finally:
                        await self.slsk.forget(info["transfer"])
                    if path:
                        self._record_peer(c.username, "ok")
                        self.db.update_track(tid, state=states.DONE, file_path=path, progress=1.0, last_error="",
                                             **self._done_fields(t, c))
                        self.note(f"Downloaded {os.path.basename(path)}")
                        self._schedule_share_rescan()
                        self.schedule_rekordbox()
                        return
                    t.pop("_meta", None)
                    info["fail_reason"] = why
                    self.note(f"Rejected a file from {c.username}: {why}", "warn")
                reason = info.get("fail_reason") or reason
                if self.db.track(tid)["state"] != states.DOWNLOADING:   # skipped by user
                    return
            self._schedule_retry(self.db.track(tid), f"Peers didn't deliver ({reason})")
        except asyncio.CancelledError:
            t2 = self.db.track(tid)
            if t2 and t2["state"] == states.DOWNLOADING:
                self.db.update_track(tid, state=states.WANTED, progress=0, next_attempt=0)
            raise
        except Exception as e:
            log.exception("download error")
            self._schedule_retry(self.db.track(tid), f"Error: {e}")
        finally:
            self.active.pop(tid, None)
            self._wake_search.set()

    async def _try_candidate(self, t: dict, c: Candidate, record: bool = True) -> tuple[bool, dict]:
        """Download one candidate. record=False (upgrades) leaves the track row alone: it describes
        the file the user already has."""
        tid = t["id"]
        transfer = await self.slsk.download(c.username, c.filename)
        entry = self.active.get(tid)
        if entry is not None:
            entry["transfer"], entry["candidate"] = transfer, c
        if record:
            self.db.update_track(tid, peer=c.username, remote_file=c.filename, progress=0)
        started = last_change = time.time()
        last_bytes = -1
        info: dict = {}
        try:
            while True:
                await asyncio.sleep(2)
                info = self.slsk.transfer_info(transfer)
                info["transfer"] = transfer
                st = info["state"]
                if st == "COMPLETE" and info["local_path"]:
                    return True, info
                if st in ("FAILED", "ABORTED", "INCOMPLETE"):
                    if st != "ABORTED":     # an abort is our own doing (the user skipped the track)
                        self._record_peer(c.username, "failed")
                    return False, info
                now = time.time()
                if info["bytes"] != last_bytes:
                    last_bytes, last_change = info["bytes"], now
                    if info["size"] and record:
                        self.db.update_track(tid, progress=round(info["bytes"] / info["size"], 3))
                if st == "DOWNLOADING" and now - last_change > STALL_TIMEOUT:
                    info["fail_reason"] = "stalled"
                    self._record_peer(c.username, "failed")
                    await self.slsk.abort(transfer)
                    return False, info
                if st != "DOWNLOADING" and now - started > QUEUE_TIMEOUT:
                    info["fail_reason"] = "peer queue too long"
                    self._record_peer(c.username, "failed")
                    await self.slsk.abort(transfer)
                    return False, info
        except asyncio.CancelledError:
            await self.slsk.abort(transfer)
            raise
        finally:
            if info.get("state") != "COMPLETE":
                # Removing an unfinished transfer also lets aioslsk drop the partial file.
                await self.slsk.forget(transfer)

    def _done_fields(self, t: dict, c: Candidate) -> dict:
        """Columns for a freshly published file: measured quality/tier and when to look for better."""
        meta = t.pop("_meta", {}) or {}
        tier = meta.get("tier") or tier_of(c.ext or os.path.splitext(c.filename)[1], c.bitrate, c.bit_depth) or ""
        meta["tier"] = tier
        prof = profile(self.settings.quality_profile)
        later = wants_upgrade(prof, tier) and self.settings.upgrade_mode != "off"
        meta["next_upgrade"] = time.time() + UPGRADE_EVERY if later else 0
        return meta

    async def _stage_and_check(self, t: dict, src: str, c: Candidate) -> tuple[Optional[str], str]:
        """incoming -> staging -> checks. Returns (staged path, "") or (None, reason); a rejected file
        is in quarantine and its peer + file are blocked for this track."""
        staged = self._stage(t, src)
        for check in self.checks:
            try:
                why = await asyncio.to_thread(check, t, staged)   # ffmpeg can take a few seconds
            except Exception as e:      # a broken check must not let an unchecked file through
                log.exception("file check failed")
                why = f"Check failed ({e})"
            if why:
                if (t.get("_meta") or {}).get("quality") == "fake":   # a converted MP3 sold as lossless / 320
                    self._record_peer(c.username, "fake")
                self._quarantine(t, staged, c, why)
                return None, why
        staged = await asyncio.to_thread(self.finish_file, t, staged)     # step 10: AIFF, tags, cover
        return staged, ""

    def finish_file(self, t: dict, path: str) -> str:
        """Convert WAV to AIFF when asked and write the tags and the cover (roadmap step 10).
        A problem here never keeps a good file from the user: it is published as it is, with a note.
        Returns the (possibly new) path."""
        s = self.settings
        if s.wav_to_aiff and path.lower().endswith(".wav"):
            dst = os.path.splitext(path)[0] + ".aiff"
            try:
                tagging.wav_to_aiff(path, dst)
                os.remove(path)
                path = dst
            except tagging.NotConvertible as e:
                self.note(f"Kept {os.path.basename(path)} as WAV ({e}).")
            except Exception as e:
                log.exception("WAV to AIFF failed")
                self.note(f"Couldn't convert {os.path.basename(path)} to AIFF ({e}); kept as WAV.", "warn")
        if s.tag_files and os.path.splitext(path)[1].lower().lstrip(".") in tagging.TAGGABLE:
            try:
                cover = tagging.fetch_cover(t.get("artwork") or "")
                tagging.tag_file(path, self._tag_meta(t), cover)
                if not cover and t.get("artwork"):
                    self.note(f"{os.path.basename(path)}: tagged, but the cover couldn't be downloaded.", "warn")
            except Exception as e:
                log.exception("tagging failed")
                self.note(f"Couldn't write tags into {os.path.basename(path)} ({e}); it is published without.", "warn")
        return path

    def _tag_meta(self, t: dict) -> tagging.TagMeta:
        f = self._name_fields(t)
        ch = self.db.channel(t["channel_id"])
        label = f["channel"] if self.settings.label_from_channel and ch and ch["kind"] == "profile" else ""
        return tagging.TagMeta(
            artist=t["artist"], title=t["title"] + (f" ({t['version']})" if t["version"] else ""),
            genre=f["genre"], year=f["year"], label=label, comment=t.get("url") or "")

    async def _stage_and_publish(self, t: dict, src: str, c: Candidate) -> tuple[Optional[str], str]:
        """incoming -> staging -> checks -> music folder. Returns (published path, "") or
        (None, reason) when a check rejected the file. A rejected file goes to quarantine and its
        peer + file are blocked for this track; it never reaches the music folder."""
        staged, why = await self._stage_and_check(t, src, c)
        if not staged:
            return None, why
        return self._finalize(t, staged, c), ""

    def _quarantine(self, t: dict, staged: str, c: Candidate, why: str) -> None:
        folder = os.path.join(self.quarantine_dir, str(t["id"]))
        os.makedirs(folder, exist_ok=True)
        dest = os.path.join(folder, os.path.basename(staged))
        n = 2
        while os.path.exists(dest):
            root, ext = os.path.splitext(os.path.basename(staged))
            dest = os.path.join(folder, f"{root} ({n}){ext}")
            n += 1
        try:
            shutil.move(staged, dest)
            try:
                os.rmdir(os.path.dirname(staged))
            except OSError:
                pass
        except OSError:
            log.exception("couldn't move %s to quarantine", staged)
            dest = ""
        self.db.add_reject(t["id"], c.username, c.filename, why, dest)

    def _stage(self, t: dict, src: str) -> str:
        folder = os.path.join(self.staging_dir, str(t["id"]))
        os.makedirs(folder, exist_ok=True)
        staged = os.path.join(folder, os.path.basename(src))
        shutil.move(src, staged)    # incoming and staging are both in the app data: a rename
        return staged

    def _name_fields(self, t: dict) -> dict:
        """The values a file name template can use (naming.TOKENS)."""
        ch = self.db.channel(t["channel_id"])
        meta = _load_meta(t)
        return {"channel": ch["name"] if ch else "Other", "artist": t["artist"], "title": t["title"],
                "version": t["version"], "year": _year(meta.get("released_at") or t.get("uploaded_at")),
                "genre": meta.get("genre", "")}

    def _finalize(self, t: dict, src: str, c: Candidate) -> str:
        s = self.settings
        *folders, base = naming.render(s.filename_template, self._name_fields(t))
        dest_dir = os.path.join(s.download_dir, *folders)
        os.makedirs(dest_dir, exist_ok=True)
        ext = os.path.splitext(src)[1].lower() or ("." + c.ext if c.ext else "")
        dest = os.path.join(dest_dir, base + ext)
        n = 2
        while os.path.exists(dest):
            dest = os.path.join(dest_dir, f"{base} ({n}){ext}")
            n += 1
        publish_file(src, dest)
        try:
            library.index_file(self.db, dest, os.path.abspath(s.download_dir))   # known at once, before the next scan
        except Exception:
            log.debug("couldn't index %s", dest, exc_info=True)
        try:
            os.rmdir(os.path.dirname(src))   # the track's staging folder, if now empty
        except OSError:
            pass
        return dest

    # ------------------------------------------------------------------ upgrades (step 4)
    def _candidate_tier(self, c: Candidate) -> Optional[str]:
        return tier_of(c.ext or os.path.splitext(c.filename)[1], c.bitrate, c.bit_depth)

    async def _upgrade_search(self, t: dict) -> None:
        """Look for a copy that is higher on the quality ladder than the file the user has."""
        tid = t["id"]
        prof = profile(self.settings.quality_profile)
        self.db.update_track(tid, next_upgrade=time.time() + UPGRADE_EVERY)   # not again today
        p = self._parsed(t)
        better: list[Candidate] = []
        try:
            for q in search_queries(p):
                await self._throttle()
                results = await self.slsk.search(q, wait=SEARCH_WAIT)
                blocked = self.db.blocked(tid)
                better = [c for c in rank(p, t["duration"], results, self._prefs(t, results))
                          if (c.username, c.filename) not in blocked
                          and is_better(prof, self._candidate_tier(c), t["tier"])]
                if better:
                    break
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.info("upgrade search failed for %s: %s", p.display, e)
            return
        if not better or tid in self.active:
            return
        task = asyncio.create_task(self._upgrade_download(t, better[:MAX_CANDIDATES]))
        self.active[tid] = {"task": task, "transfer": None, "candidate": None, "upgrade": True}

    async def _upgrade_download(self, t: dict, candidates: list[Candidate]) -> None:
        tid = t["id"]
        prof = profile(self.settings.quality_profile)
        try:
            for c in candidates:
                ok, info = await self._try_candidate(t, c, record=False)
                if not ok:
                    continue
                try:
                    staged, why = await self._stage_and_check(t, info["local_path"], c)
                finally:
                    await self.slsk.forget(info["transfer"])
                if not staged:
                    t.pop("_meta", None)
                    continue
                self._record_peer(c.username, "ok")
                meta = t.pop("_meta", {}) or {}
                new_tier = meta.get("tier") or self._candidate_tier(c)
                if not is_better(prof, new_tier, t["tier"]):
                    # Measured, it's no better than what the user has: drop it, never try it again.
                    _remove(staged)
                    self.db.add_reject(tid, c.username, c.filename,
                                       f"Not better than your copy ({TIER_LABELS.get(new_tier, new_tier)})", "")
                    self.db.update_reject(self.db.blocked_last_id(tid), status="deleted")
                    continue
                cur = self.db.track(tid)
                if not cur or cur["state"] != states.DONE:
                    _remove(staged)
                    return
                mode = self.settings.upgrade_mode
                if mode == "auto_unless_dj":
                    # Replace by itself only when we KNOW the track isn't in Rekordbox: a new file name
                    # would cost its cue points. No export or an unreadable one counts as "might be there".
                    known = await asyncio.to_thread(self.in_rekordbox, cur["file_path"])
                    if known is True:
                        self.note(f"{os.path.basename(cur['file_path'])} is in Rekordbox, so the better copy waits for your OK.")
                    elif known is None:
                        self.note("The better copy waits for your OK: SeekSync can't tell what is in Rekordbox "
                                  "(choose your Rekordbox export in Settings).", "warn")
                if mode == "auto" or (mode == "auto_unless_dj" and known is False):
                    self._replace(cur, staged, c, meta, new_tier)
                else:
                    folder = os.path.join(self.upgrades_dir, str(tid))
                    _clear_dir(folder)
                    os.makedirs(folder, exist_ok=True)
                    pending = os.path.join(folder, os.path.basename(staged))
                    shutil.move(staged, pending)
                    self.db.update_track(tid, upgrade_path=pending, upgrade_tier=new_tier, next_upgrade=0)
                    self.note(f"Better copy found for {cur['title']} ({TIER_LABELS.get(new_tier, new_tier)})")
                return
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("upgrade failed")
        finally:
            self.active.pop(tid, None)
            self._wake_search.set()

    def _to_trash(self, path: str, tid: int) -> Optional[str]:
        if not path or not os.path.exists(path):
            return None
        folder = os.path.join(self.trash_dir, f"{tid}-{int(time.time())}")
        os.makedirs(folder, exist_ok=True)
        dest = os.path.join(folder, os.path.basename(path))
        shutil.move(path, dest)
        os.utime(folder)          # the trash is emptied by age of this folder
        return dest

    def _replace(self, t: dict, new_file: str, c: Candidate, meta: dict, new_tier: str) -> str:
        """Put a better copy in place of the current file; the old file goes to the app's trash."""
        old = t["file_path"]
        self._to_trash(old, t["id"])
        path = self._finalize(t, new_file, c)
        prof = profile(self.settings.quality_profile)
        later = wants_upgrade(prof, new_tier) and self.settings.upgrade_mode != "off"
        self.db.update_track(t["id"], file_path=path, tier=new_tier, peer=c.username, remote_file=c.filename,
                             upgrade_path="", upgrade_tier="", cutoff_hz=meta.get("cutoff_hz"),
                             quality=meta.get("quality", ""),
                             next_upgrade=time.time() + UPGRADE_EVERY if later else 0)
        self.note(f"Upgraded {os.path.basename(path)} ({TIER_LABELS.get(new_tier, new_tier)})")
        self.schedule_rekordbox()
        return path

    def replace_upgrade(self, tid: int) -> Optional[str]:
        """User said yes to a waiting better copy ("ask" mode)."""
        t = self.db.track(tid)
        if not t or not t["upgrade_path"]:
            return None
        pending = t["upgrade_path"]
        if not os.path.exists(pending):
            self.db.update_track(tid, upgrade_path="", upgrade_tier="")
            return None
        probe = dict(t)
        for check in self.checks:         # measure it again for the cutoff/quality columns
            try:
                check(probe, pending)
            except Exception:
                log.debug("re-measure failed", exc_info=True)
        meta = probe.get("_meta", {}) or {}
        path = self._replace(t, pending, Candidate(t["peer"], os.path.basename(pending)), meta, t["upgrade_tier"])
        try:
            os.rmdir(os.path.dirname(pending))
        except OSError:
            pass
        return path

    def keep_current(self, tid: int) -> None:
        """User keeps the file they have: drop the waiting copy and stop looking for this track."""
        t = self.db.track(tid)
        if not t:
            return
        if t["upgrade_path"]:
            _remove(t["upgrade_path"])
            try:
                os.rmdir(os.path.dirname(t["upgrade_path"]))
            except OSError:
                pass
        self.db.update_track(tid, upgrade_path="", upgrade_tier="", next_upgrade=0)

    def _schedule_retry(self, t: Optional[dict], reason: str) -> None:
        if not t:
            return
        age = time.time() - t["created_at"]
        if age > self.settings.give_up_days * 86400:
            self.db.update_track(t["id"], state=states.GAVE_UP, last_error=reason, progress=0)
            return
        delay = RETRY_DELAYS[min(max(t["attempts"] - 1, 0), len(RETRY_DELAYS) - 1)]
        self.db.update_track(t["id"], state=states.WAITING, next_attempt=time.time() + delay,
                             last_error=reason, progress=0)

    def _schedule_share_rescan(self) -> None:
        if not (self.settings.share_downloads and self.slsk.connected):
            return
        if self._share_rescan and not self._share_rescan.done():
            return

        async def later():
            await asyncio.sleep(60)
            await self.slsk.rescan_shares()
        self._share_rescan = asyncio.create_task(later())

    # ------------------------------------------------------------------ user actions
    def retry_now(self, tid: int) -> None:
        t = self.db.track(tid)
        if t and t["state"] in (states.WAITING, states.GAVE_UP, states.SKIPPED, states.WANTED, states.COLLECTED):
            # The user wants it: neither the rules nor the collection check take it away again.
            fields = {"skip_rule": rules_mod.OVERRIDDEN} if t["skip_rule"] or t["state"] == states.COLLECTED else {}
            if t["state"] == states.COLLECTED:
                fields["file_path"] = ""
            self.db.update_track(tid, state=states.WANTED, next_attempt=0, last_error="", **fields)
            self._wake_search.set()

    def skip(self, tid: int) -> None:
        entry = self.active.get(tid)
        self.db.update_track(tid, state=states.SKIPPED, progress=0, last_error="")
        if entry:
            entry["task"].cancel()

    def approve_reject(self, rid: int) -> Optional[str]:
        """User overrides a check: move the quarantined file to the music folder and mark the
        track downloaded. Returns the new path, or None when the file is gone."""
        r = self.db.reject(rid)
        if not r or r["status"] != "quarantined" or not r["path"] or not os.path.exists(r["path"]):
            return None
        t = self.db.track(r["track_id"])
        if not t:
            return None
        if t["state"] == states.DONE:     # it was a candidate for a better copy: replace, keep the old in trash
            self._to_trash(t["file_path"], t["id"])
        ready = self.finish_file(t, r["path"])            # it never got its tags: it was held back
        path = self._finalize(t, ready, Candidate(r["peer"], r["remote_file"]))
        self.db.update_track(t["id"], state=states.DONE, file_path=path, progress=1.0, last_error="",
                             peer=r["peer"], remote_file=r["remote_file"],
                             tier=tier_of(os.path.splitext(path)[1]) or "", next_upgrade=0)
        self.db.update_reject(rid, status="approved", path="")
        entry = self.active.get(t["id"])
        if entry:
            entry["task"].cancel()      # a new attempt for this track is no longer needed
        self.note(f"Approved {os.path.basename(path)} anyway")
        self.schedule_rekordbox()
        return path

    def delete_reject(self, rid: int) -> None:
        r = self.db.reject(rid)
        if not r or r["status"] != "quarantined":
            return
        if r["path"]:
            try:
                os.remove(r["path"])
                os.rmdir(os.path.dirname(r["path"]))
            except OSError:
                pass
        self.db.update_reject(rid, status="deleted", path="")   # the block stays

    def remove_channel(self, cid: int) -> None:
        for t in self.db.tracks(limit=100000, channel_id=cid):
            entry = self.active.get(t["id"])
            if entry:
                entry["task"].cancel()
        self.db.delete_channel(cid)
        self.schedule_rekordbox()
