"""Run the UI with fake data (no SoundCloud/Soulseek needed). For screenshots and UI work.

    NICOTINE_SYNC_HOME=/tmp/ns-demo python scripts/demo.py
"""
import os, sys, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from nicotine_sync.app import Backend, setup_logging
from nicotine_sync.config import SettingsStore, data_dir
from nicotine_sync.db import Database

class IdleSlsk:
    status, error, connected, retryable = "connected", "", True, False
    async def start(self, s): pass
    async def stop(self): pass
    async def search(self, q, wait=0): return []
    def transfer_info(self, t): return t
    async def forget(self, t): pass
    async def abort(self, t): pass

class IdleSC:
    def latest(self, *a, **k): raise RuntimeError("demo mode")
    def channel_info(self, url):
        from nicotine_sync.soundcloud import ChannelInfo
        return ChannelInfo(url, url.rsplit("/", 1)[-1].replace("-", " ").title())

home = data_dir()
store = SettingsStore()
if os.environ.get("DEMO_SETUP") != "1":
    store.update({"accepted_terms": True, "soulseek_username": "djnina_cw", "soulseek_password": "x",
                  "download_dir": str(home / "Music")})
db = Database(home / "nicotine-sync.db")
if not db.channels() and os.environ.get("DEMO_SETUP") != "1":
    now = time.time()
    chans = [("https://soundcloud.com/nightshift-records", "Nightshift Records"), ("https://soundcloud.com/concrete-loop", "Concrete Loop"),
             ("https://soundcloud.com/kellerraum", "Kellerraum"), ("https://soundcloud.com/deep-signal", "Deep Signal")]
    ids = [db.add_channel(u, n, False, 0) for u, n in chans]
    for i in ids: db.update_channel(i, initialized=1, last_checked=now - 600 * i)
    db.update_channel(ids[2], last_error="SoundCloud is blocking requests right now. Try again in a few minutes.")
    rows = [
        (ids[0], "Mira Kova & Delen - Night Signal (Extended Mix)", "Mira Kova", "Night Signal", "Extended Mix", "downloading", 0.62, "", "vinyl_vault"),
        (ids[1], "Juno Raske - Overdrive [CL045]", "Juno Raske", "Overdrive", "", "searching", 0, "", ""),
        (ids[3], "PREMIERE: Taro Vell - Glasshouse (Someone Remix) [FREE DL]", "Taro Vell", "Glasshouse", "Someone Remix", "waiting", 0, "Not on Soulseek yet", ""),
        (ids[0], "Ostin Pell - Lights Out", "Ostin Pell", "Lights Out", "", "done", 1, "", "deepcrates"),
        (ids[1], "Lune Varga - Hypnotic Loop", "Lune Varga", "Hypnotic Loop", "", "done", 1, "", "berlin_bits"),
        (ids[2], "Unknown Producer - Warehouse Tool 3", "Unknown Producer", "Warehouse Tool 3", "", "wanted", 0, "", ""),
        (ids[3], "Sam Hollow - Places (Club Edit)", "Sam Hollow", "Places", "Club Edit", "gave_up", 0, "Not on Soulseek yet", ""),
        (ids[2], "Old Upload - From Before", "Old Upload", "From Before", "", "skipped", 0, "", ""),
    ]
    for n, (cid, raw, a, t, v, st, prog, err, peer) in enumerate(rows):
        tid = db.add_track(channel_id=cid, sc_id=str(1000 + n), url="https://soundcloud.com/x/y", raw_title=raw,
                           artist=a, title=t, version=v, duration=360, state=st, progress=prog, last_error=err,
                           peer=peer, uploaded_at=now - n * 3600 * 5, next_attempt=now + 7200,
                           file_path=(str(home / "Music" / f"{a} - {t}.flac") if st == "done" else ""))

setup_logging()
b = Backend(port=int(os.environ.get("PORT", "8765")), slsk=IdleSlsk(), sc=IdleSC())
# keep demo rows as they are: don't let the engine reset/search
import nicotine_sync.engine as E
async def _noop(self): pass
E.Engine._search_loop = _noop
E.Engine._poll_loop = _noop
E.Engine._watchdog = _noop
E.Engine.start_orig = E.Engine.start
async def start(self):
    self.note("Connected to Soulseek."); self.note("Concrete Loop: 1 new track(s).")
    self.note("Kellerraum: couldn't check SoundCloud (blocked)", "warn"); self.note("Downloaded Ostin Pell - Lights Out.flac")
    import asyncio
    self._tasks = []
    self.next_poll_at = time.time() + 2400
E.Engine.start = start
print(b.start(), flush=True)
threading.Event().wait()
