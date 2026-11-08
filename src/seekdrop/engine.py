"""The background worker: watch channels, search Soulseek, download, retry."""
from __future__ import annotations

import asyncio
import errno
import logging
import os
import re
import shutil
import time
from collections import deque
from typing import Callable, Optional

from . import db as states
from .config import SettingsStore
from .config import data_dir
from .db import Database
from .matching import Candidate, MatchPrefs, rank
from .nicotine import migrate_legacy_plugin, update_plugin_if_outdated
from .soundcloud import SoundCloudClient, TrackStub
from .titles import is_mix, parse_title, search_queries

log = logging.getLogger(__name__)

RETRY_DELAYS = [3600, 3 * 3600, 6 * 3600, 12 * 3600, 24 * 3600]
QUEUE_TIMEOUT = 45 * 60       # give up on a peer whose queue doesn't move
STALL_TIMEOUT = 5 * 60        # no bytes received for this long while downloading
MAX_CANDIDATES = 3            # peers to try per search round
SEARCH_SPACING = 8.0          # seconds between Soulseek searches (be a good citizen)
SEARCH_WAIT = 12.0            # seconds to collect results per search
MAX_TRACK_SECONDS = 10 * 60   # longer uploads are mixes/sets, not tracks


PART_SUFFIX = ".seekdrop-part"   # hidden temp name while a file is copied to another disk

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


def safe_filename(name: str, limit: int = 150) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:limit].strip(" .") or "track"


class Engine:
    def __init__(self, db: Database, store: SettingsStore, sc: SoundCloudClient, slsk, poll_tick: float = 30.0,
                 slsk_factory=None, staging_dir: Optional[str] = None):
        self.db = db
        # Finished downloads wait here (app data, never the music folder) until every check passed.
        self.staging_dir = staging_dir or str(data_dir() / "staging")
        self.checks: list[Check] = []   # file checks (roadmap steps 2, 3, 10) run on the staged file
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
        self._last_search = 0.0

    # ------------------------------------------------------------------ lifecycle
    @property
    def settings(self):
        return self.store.settings

    def note(self, msg: str, level: str = "info") -> None:
        self.activity.appendleft({"t": time.time(), "msg": msg, "level": level})
        getattr(log, "warning" if level == "warn" else "info")(msg)

    async def start(self) -> None:
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
        root = self.settings.download_dir
        if root and os.path.isdir(root):
            dirs = [root] + [os.path.join(root, d) for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]
            for d in dirs:
                for name in os.listdir(d):
                    if name.startswith(".") and name.endswith(PART_SUFFIX):
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
                    path, why = self._stage_and_publish(t, info["local_path"], c)
                    await self.slsk.cancel(t["peer"], t["remote_file"])   # clears the finished entry
                    if path:
                        self.db.update_track(t["id"], state=states.DONE, file_path=path, progress=1.0, last_error="")
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
                    self.note("The Nicotine+ plugin has a new name. In Nicotine+, turn off Nicotine+ Sync Bridge "
                              "and turn on SeekDrop Bridge (Preferences, Plugins).", "warn")
                elif await asyncio.to_thread(update_plugin_if_outdated):
                    self.note("Updated the Nicotine+ plugin. In Nicotine+, turn SeekDrop Bridge off and on "
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
                    self.note(f"{ch['name']}: getting {len(wanted) + revived} track(s) from this playlist.")
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
            skipped = failed = 0
            for s in (wanted if playlist else reversed(wanted)):   # profiles: oldest first
                added = await self._add_wanted(cid, s)
                if added is None:
                    failed += 1
                elif not added:
                    skipped += 1
            if skipped:
                self.note(f"{ch['name']}: skipped {skipped} mix(es) or track(s) over 10 minutes.")
            if failed:
                self.note(f"{ch['name']}: couldn't read {failed} track(s) from SoundCloud, trying again next check.", "warn")
            self.db.update_channel(cid, last_checked=time.time(), last_error="", initialized=1)
            self._wake_search.set()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("channel check failed")
            msg = str(e).replace("ERROR: ", "")[:200]
            self.db.update_channel(cid, last_checked=time.time(), last_error=msg)
            self.note(f"{ch['name']}: couldn't check SoundCloud ({msg})", "warn")
        finally:
            self.checking.discard(cid)

    def _claim_skipped(self, cid: int, rows: list[dict]) -> int:
        """Tracks in a playlist that another channel skipped (older than its backlog) are wanted
        after all: move them to the playlist. Tracks skipped by the user in this playlist, or
        skipped as a mix, stay skipped."""
        n = 0
        for r in rows:
            if r["state"] == states.SKIPPED and r["channel_id"] != cid and not r["last_error"]:
                self.db.update_track(r["id"], channel_id=cid, state=states.WANTED, next_attempt=0)
                n += 1
        return n

    async def _add_wanted(self, cid: int, stub: TrackStub) -> Optional[bool]:
        """Store a new upload. Returns False if it was skipped as a mix / long upload, and None if
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
        reason = ""
        if duration and duration > MAX_TRACK_SECONDS:
            reason = "Longer than 10 minutes"
        elif is_mix(raw):
            reason = "Looks like a mix"
        self.db.add_track(
            channel_id=cid, sc_id=stub.sc_id, url=(info.url if info else stub.url), raw_title=raw,
            uploader=uploader, publisher_artist=pub, artist=p.artist, title=p.title, version=p.version,
            duration=duration, artwork=info.artwork if info else "",
            uploaded_at=info.uploaded_at if info else None,
            state=states.SKIPPED if reason else states.WANTED, last_error=reason)
        return not reason

    # ------------------------------------------------------------------ Soulseek
    async def _search_loop(self) -> None:
        while True:
            try:
                if self.settings.configured and self.slsk.connected:
                    if self._stale:
                        await self._recover_stale()
                    if self._clean_incoming and not self._stale:
                        self._tidy_incoming()
                    for t in self.db.due_tracks(time.time()):
                        if len(self.active) >= self.settings.max_parallel_downloads:
                            break
                        if not self.slsk.connected:
                            break
                        await self._search_track(t)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("search loop error")
            self._wake_search.clear()
            try:
                await asyncio.wait_for(self._wake_search.wait(), 20)
            except asyncio.TimeoutError:
                pass

    def _prefs(self) -> MatchPrefs:
        return MatchPrefs(preferred_format=self.settings.preferred_format, min_bitrate=self.settings.min_bitrate)

    async def _search_track(self, t: dict) -> None:
        tid = t["id"]
        p = parse_title(t["raw_title"], uploader=t["uploader"], publisher_artist=t["publisher_artist"])
        self.db.update_track(tid, state=states.SEARCHING, attempts=t["attempts"] + 1)
        ranked: list[Candidate] = []
        try:
            for q in search_queries(p):
                wait = SEARCH_SPACING - (time.time() - self._last_search)
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last_search = time.time()
                results = await self.slsk.search(q, wait=SEARCH_WAIT)
                ranked = rank(p, t["duration"], results, self._prefs())
                if ranked:
                    break
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("search failed for %s: %s", p.display, e)
            self.db.update_track(tid, state=states.WANTED, next_attempt=time.time() + 300,
                                 last_error="Search failed, retrying in 5 minutes")
            return

        current = self.db.track(tid)
        if not current or current["state"] != states.SEARCHING:   # user skipped meanwhile
            return
        if not ranked:
            self._schedule_retry(current, "Not on Soulseek yet")
            return

        self.db.update_track(tid, state=states.DOWNLOADING, progress=0, last_error="")
        task = asyncio.create_task(self._download(current, ranked[:MAX_CANDIDATES]))
        self.active[tid] = {"task": task, "transfer": None, "candidate": None}

    async def _download(self, t: dict, candidates: list[Candidate]) -> None:
        tid = t["id"]
        reason = "Download failed"
        try:
            for c in candidates:
                ok, info = await self._try_candidate(t, c)
                if ok:
                    try:
                        path, why = self._stage_and_publish(t, info["local_path"], c)
                    finally:
                        await self.slsk.forget(info["transfer"])
                    if path:
                        self.db.update_track(tid, state=states.DONE, file_path=path, progress=1.0, last_error="")
                        self.note(f"Downloaded {os.path.basename(path)}")
                        self._schedule_share_rescan()
                        return
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

    async def _try_candidate(self, t: dict, c: Candidate) -> tuple[bool, dict]:
        tid = t["id"]
        transfer = await self.slsk.download(c.username, c.filename)
        entry = self.active.get(tid)
        if entry is not None:
            entry["transfer"], entry["candidate"] = transfer, c
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
                    return False, info
                now = time.time()
                if info["bytes"] != last_bytes:
                    last_bytes, last_change = info["bytes"], now
                    if info["size"]:
                        self.db.update_track(tid, progress=round(info["bytes"] / info["size"], 3))
                if st == "DOWNLOADING" and now - last_change > STALL_TIMEOUT:
                    info["fail_reason"] = "stalled"
                    await self.slsk.abort(transfer)
                    return False, info
                if st != "DOWNLOADING" and now - started > QUEUE_TIMEOUT:
                    info["fail_reason"] = "peer queue too long"
                    await self.slsk.abort(transfer)
                    return False, info
        except asyncio.CancelledError:
            await self.slsk.abort(transfer)
            raise
        finally:
            if info.get("state") != "COMPLETE":
                # Removing an unfinished transfer also lets aioslsk drop the partial file.
                await self.slsk.forget(transfer)

    def _stage_and_publish(self, t: dict, src: str, c: Candidate) -> tuple[Optional[str], str]:
        """incoming -> staging -> checks -> music folder. Returns (published path, "") or
        (None, reason) when a check rejected the file; a rejected file never reaches the music folder."""
        staged = self._stage(t, src)
        for check in self.checks:
            try:
                why = check(t, staged)
            except Exception as e:      # a broken check must not let an unchecked file through
                log.exception("file check failed")
                why = f"check failed ({e})"
            if why:
                try:
                    os.remove(staged)
                except OSError:
                    pass
                return None, why
        return self._finalize(t, staged, c), ""

    def _stage(self, t: dict, src: str) -> str:
        folder = os.path.join(self.staging_dir, str(t["id"]))
        os.makedirs(folder, exist_ok=True)
        staged = os.path.join(folder, os.path.basename(src))
        shutil.move(src, staged)    # incoming and staging are both in the app data: a rename
        return staged

    def _finalize(self, t: dict, src: str, c: Candidate) -> str:
        s = self.settings
        dest_dir = s.download_dir
        if s.organize_by_channel:
            ch = self.db.channel(t["channel_id"])
            dest_dir = os.path.join(dest_dir, safe_filename(ch["name"] if ch else "Other"))
        os.makedirs(dest_dir, exist_ok=True)
        ext = os.path.splitext(src)[1].lower() or ("." + c.ext if c.ext else "")
        base = t["title"] + (f" ({t['version']})" if t["version"] else "")
        if t["artist"]:
            base = f"{t['artist']} - {base}"
        base = safe_filename(base)
        dest = os.path.join(dest_dir, base + ext)
        n = 2
        while os.path.exists(dest):
            dest = os.path.join(dest_dir, f"{base} ({n}){ext}")
            n += 1
        publish_file(src, dest)
        try:
            os.rmdir(os.path.dirname(src))   # the track's staging folder, if now empty
        except OSError:
            pass
        return dest

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
        if t and t["state"] in (states.WAITING, states.GAVE_UP, states.SKIPPED, states.WANTED):
            self.db.update_track(tid, state=states.WANTED, next_attempt=0, last_error="")
            self._wake_search.set()

    def skip(self, tid: int) -> None:
        entry = self.active.get(tid)
        self.db.update_track(tid, state=states.SKIPPED, progress=0, last_error="")
        if entry:
            entry["task"].cancel()

    def remove_channel(self, cid: int) -> None:
        for t in self.db.tracks(limit=100000, channel_id=cid):
            entry = self.active.get(t["id"])
            if entry:
                entry["task"].cancel()
        self.db.delete_channel(cid)
