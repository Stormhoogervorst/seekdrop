"""Dev server for UI work: the real UI with made-up data, no SoundCloud or Soulseek needed.

    python scripts/demo.py            -> http://localhost:8765/#token=dev
    DEMO_SETUP=1 python scripts/demo.py   (shows the first-run setup instead)

Edits to src/seekdrop/ui/* (HTML, CSS, JS) show up when you refresh the page.
Python changes need a restart. Data lives in a throwaway folder, never in your real app data.
"""
import os
import sys
import tempfile
import threading
import time

# Never touch the real app data.
os.environ.setdefault("SEEKDROP_HOME", os.path.join(tempfile.gettempdir(), "seekdrop-demo"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from seekdrop.app import Backend, setup_logging  # noqa: E402
from seekdrop.config import SettingsStore, data_dir  # noqa: E402
from seekdrop.db import Database  # noqa: E402

PORT = int(os.environ.get("PORT", "8765"))
TOKEN = os.environ.get("DEMO_TOKEN", "dev")
SETUP = os.environ.get("DEMO_SETUP") == "1"


class IdleSlsk:
    mode = "nicotine"
    status, error, connected, retryable, username = "connected", "", True, False, "djnina"
    shared_folders, shared_files = 0, 0     # step 8: shows the "you share nothing" warning
    async def start(self, s): pass
    async def stop(self): pass
    async def search(self, q, wait=0): return []
    def transfer_info(self, t):   # the one demo transfer that is "downloading right now"
        return {"state": "DOWNLOADING", "bytes": 0, "size": 0, "local_path": None, "place_in_queue": None, "fail_reason": ""}
    async def forget(self, t): pass
    async def abort(self, t): pass
    async def lookup(self, u, p): return None
    async def cancel(self, u, p): pass


class IdleSC:
    def latest(self, *a, **k): return []   # nothing new on SoundCloud in the demo
    def channel_info(self, url):
        from seekdrop.soundcloud import ChannelInfo, is_playlist_url
        name = url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title()
        return ChannelInfo(url, name, "playlist" if is_playlist_url(url) else "profile")


class DemoUpdates:
    """Pretend a newer release exists, so the update button shows."""
    latest = {"version": "9.9.9", "url": "https://github.com/Stormhoogervorst/seekdrop/releases", "asset": None}
    progress = {"stage": "", "done": 0, "total": 0, "error": ""}
    checked_at = 0
    async def check_now(self):
        import time
        self.checked_at = time.time()
        return {"status": "update", "version": "9.9.9", "message": "Version 9.9.9 is available (you have 0.5.0)."}
    def start(self): pass
    async def stop(self): pass


home = data_dir()
store = SettingsStore()
if not SETUP:
    store.update({"accepted_terms": True, "soulseek_mode": "nicotine", "nicotine_token": "demo",
                  "download_dir": str(home / "Music")})
db = Database(home / "seekdrop.db")
if not db.channels() and not SETUP:
    now = time.time()
    chans = [("https://soundcloud.com/nightshift-records", "Nightshift Records", "profile"),
             ("https://soundcloud.com/concrete-loop", "Concrete Loop", "profile"),
             ("https://soundcloud.com/kellerraum", "Kellerraum", "profile"),
             ("https://soundcloud.com/djnina/sets/friday-warmup", "Friday Warm-up", "playlist")]
    ids = [db.add_channel(u, n, False, 0, kind=k) for u, n, k in chans]
    for i in ids:
        db.update_channel(i, initialized=1, last_checked=now - 600 * i)
    db.update_channel(ids[0], rules='{"remixes": false, "max_minutes": 10}')   # step 9: rules per channel
    db.update_channel(ids[2], last_error="SoundCloud is blocking requests right now. Try again in a few minutes.")
    rows = [
        # channel, raw title, artist, title, version, state, progress, last_error, peer, duration
        (ids[0], "Mira Kova & Delen - Night Signal (Extended Mix)", "Mira Kova & Delen", "Night Signal", "Extended Mix", "downloading", 0.62, "", "vinyl_vault", 372),
        (ids[1], "Juno Raske - Overdrive [CL045]", "Juno Raske", "Overdrive", "", "searching", 0, "", "", 298),
        (ids[3], "Taro Vell - Glasshouse (Someone Remix)", "Taro Vell", "Glasshouse", "Someone Remix", "waiting", 0, "Not on Soulseek yet", "", 341),
        (ids[3], "Ostin Pell - Lights Out", "Ostin Pell", "Lights Out", "", "done", 1, "", "deepcrates", 305),
        (ids[3], "Lune Varga - Hypnotic Loop", "Lune Varga", "Hypnotic Loop", "", "done", 1, "", "berlin_bits", 412),
        (ids[3], "Kai Brenner - Drift (Original Mix)", "Kai Brenner", "Drift", "", "wanted", 0, "", "", 389),
        (ids[1], "Sam Hollow - Places (Club Edit)", "Sam Hollow", "Places", "Club Edit", "gave_up", 0, "Not on Soulseek yet", "", 256),
        (ids[0], "Nightshift Radio 042 w/ Mira Kova", "Nightshift Records", "Nightshift Radio 042 w/ Mira Kova", "", "skipped", 0, "Longer than 10 minutes (60:00)", "", 3600),
        (ids[0], "Mira Kova - Night Signal (Delen Remix)", "Mira Kova", "Night Signal", "Delen Remix", "skipped", 0, "Remixes are turned off for this channel", "", 340),
        (ids[3], "Juno Raske - Overdrive (Original Mix)", "Juno Raske", "Overdrive", "", "collected", 0, "", "", 298),
        (ids[0], "Mira Kova - Night Signal (Clip)", "Mira Kova", "Night Signal", "", "skipped", 0, "Preview or clip", "", 30),
        (ids[2], "Kellerraum Live at Tresor (4h set)", "Kellerraum", "Kellerraum Live at Tresor (4h set)", "", "skipped", 0, "Longer than 10 minutes", "", 14400),
        (ids[2], "Old Upload - From Before", "Old Upload", "From Before", "", "skipped", 0, "", "", 280),
    ]
    RULE_SKIPS = ("Longer than", "Remixes are", "Preview or")
    for n, (cid, raw, a, t, v, st, prog, err, peer, dur) in enumerate(rows):
        db.add_track(channel_id=cid, sc_id=str(1000 + n), url="https://soundcloud.com/x/y", raw_title=raw,
                     artist=a, title=t, version=v, duration=dur, state=st, progress=prog, last_error=err,
                     peer=peer, uploaded_at=now - n * 3600 * 5, next_attempt=now + 7200,
                     skip_rule=(err if st == "skipped" and err.startswith(RULE_SKIPS) else ""),
                     remote_file=(f"@@music\\{a} - {t}.flac" if peer else ""),
                     file_path=(str(home / "Music" / f"{a} - {t}.flac") if st == "done"
                                else "/Users/dj/Music/Crates/Juno Raske - Overdrive.flac" if st == "collected" else ""))

    # A stored search attempt, for the "Why not?" drawer (roadmap step 5).
    for t in db.tracks():
        if t["title"] == "Glasshouse":
            cands = [
                {"username": "crate_digger", "filename": "@@dl\\Taro Vell\\Taro Vell - Glasshouse (Someone Remix).mp3",
                 "size": 9_200_000, "ext": "mp3", "bitrate": 192, "duration": 341, "free_slots": True, "queue": 0,
                 "speed": 900_000, "score": 0, "rejected": "192 kbps, under your minimum (MP3 320)", "notes": []},
                {"username": "bassbin", "filename": "@@music\\Taro Vell - Glasshouse (Radio Edit).flac",
                 "size": 21_000_000, "ext": "flac", "bitrate": None, "duration": 192, "free_slots": False, "queue": 12,
                 "speed": 2_400_000, "score": 0, "rejected": "3:12 long, expected 5:41 (radio edit?)", "notes": []},
                {"username": "nightowl", "filename": "@@x\\Taro Vell - Glasshouse (Other Guy Remix).flac",
                 "size": 38_000_000, "ext": "flac", "bitrate": None, "duration": 356, "free_slots": True, "queue": 0,
                 "speed": 5_000_000, "score": 0, "rejected": "Not the Someone Remix", "notes": []},
            ]
            db.add_search(t["id"], [{"query": "taro vell glasshouse someone", "results": 3},
                                    {"query": "glasshouse someone", "results": 3}], cands,
                          "3 results, none matched: closest was 192 kbps, under your minimum (MP3 320)")
            db.update_track(t["id"], attempts=2, last_error="3 results, none matched: closest was 192 kbps, under your minimum (MP3 320)")

    # Measured cutoff (roadmap step 3): one full-range file, one suspect.
    for t in db.tracks():
        if t["title"] == "Lights Out":       # step 4: a better copy is waiting for the user's OK
            db.update_track(t["id"], cutoff_hz=22050, quality="genuine", tier="mp3_320",
                            upgrade_path=str(home / "upgrades" / "demo.flac"), upgrade_tier="flac16")
        if t["title"] == "Hypnotic Loop":    # suspect FLAC counts as MP3 320: still looking for better
            db.update_track(t["id"], cutoff_hz=20300, quality="suspect", tier="mp3_320",
                            next_upgrade=now + 86400)
    # Two files that failed the file checks, to design the Quarantine view.
    tracks = {t["title"]: t["id"] for t in db.tracks()}
    qdir = home / "quarantine"
    qdir.mkdir(exist_ok=True)
    for title, peer, remote, reason in [
            ("Overdrive", "bassbin", "@@music\\Juno Raske - Overdrive.flac", "Not really FLAC (it's MP3)"),
            ("Glasshouse", "crate_digger", "@@dl\\Taro Vell - Glasshouse (Someone Remix).wav", "30 s of silence at the end")]:
        f = qdir / remote.split("\\")[-1]
        f.write_bytes(b"demo")
        db.add_reject(tracks[title], peer, remote, reason, str(f))

# Step 11: two copies of one track in the download folder, for the Duplicates view.
from seekdrop import library as _lib  # noqa: E402
if not SETUP:
    (home / "Music").mkdir(exist_ok=True)
    for name, size in (("Ostin Pell - Lights Out.flac", 31_000_000), ("Ostin Pell - Lights Out.mp3", 8_400_000),
                       ("Lune Varga - Hypnotic Loop.flac", 40_000_000)):
        f = home / "Music" / name
        if not f.exists():
            f.write_bytes(b"demo")
        row = _lib.read_file(str(f), str(home / "Music"))
        if row:
            row.update(size=size, artist=name.split(" - ")[0], title=name.split(" - ")[1].rsplit(".", 1)[0],
                       tier="flac16" if name.endswith("flac") else "mp3_320", ext=name.rsplit(".", 1)[1],
                       bitrate=320 if name.endswith("mp3") else None, duration=305.0)
            row["title_key"] = _lib.title_key(row["title"])
            db.library_upsert([row])

setup_logging()

# Keep the demo rows as they are: no searching, polling or reconnecting.
import seekdrop.engine as E  # noqa: E402


async def _noop(self):
    pass


class _DemoTask:
    def cancel(self): pass


async def _start(self):
    # Show one row as actively downloading (yellow spinner + progress bar).
    for t in self.db.tracks():
        if t["state"] == "downloading":
            self.active[t["id"]] = {"task": _DemoTask(), "transfer": "demo", "candidate": None}
            break
    self.note("Connected through Nicotine+ as djnina.")
    self.note("Concrete Loop: 1 new track(s).")
    self.note("Kellerraum: couldn't check SoundCloud (blocked)", "warn")
    self.note("Downloaded Ostin Pell - Lights Out.flac")
    # Step 8: a paused disk, a blocked peer and a note about it.
    self.paused_reason = "Only 3.2 GB free on the disk with the SeekDrop folder. Downloads are paused until there are 5 GB free (change this in Settings)."
    self.db.block_peer("rawzik_mirror", time.time() + 30 * 86400, "Delivered fake lossless or fake 320 files 3 times")
    self.note("Blocked rawzik_mirror for 30 days: delivered fake lossless or fake 320 files 3 times", "warn")
    self._tasks = []
    self.next_poll_at = time.time() + 2400


def _check_disk_demo(self):
    return self.paused_reason


E.Engine._check_disk = _check_disk_demo
E.Engine.start = _start
E.Engine._search_loop = E.Engine._poll_loop = E.Engine._watchdog = _noop

b = Backend(port=PORT, slsk=IdleSlsk(), sc=IdleSC(), token=TOKEN, updates=DemoUpdates())
b.start()
print(f"Demo UI: http://localhost:{PORT}/#token={TOKEN}   (data: {home})", flush=True)
threading.Event().wait()
