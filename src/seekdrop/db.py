"""SQLite storage for channels and tracks."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    avatar TEXT NOT NULL DEFAULT '',
    include_reposts INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    initialized INTEGER NOT NULL DEFAULT 0,
    backlog INTEGER NOT NULL DEFAULT 0,
    kind TEXT NOT NULL DEFAULT 'profile',
    last_checked REAL,
    last_error TEXT NOT NULL DEFAULT '',
    added_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY,
    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    sc_id TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL DEFAULT '',
    raw_title TEXT NOT NULL DEFAULT '',
    uploader TEXT NOT NULL DEFAULT '',
    publisher_artist TEXT NOT NULL DEFAULT '',
    artist TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    version TEXT NOT NULL DEFAULT '',
    duration REAL,
    artwork TEXT NOT NULL DEFAULT '',
    uploaded_at REAL,
    state TEXT NOT NULL DEFAULT 'wanted',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt REAL NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    peer TEXT NOT NULL DEFAULT '',
    remote_file TEXT NOT NULL DEFAULT '',
    file_path TEXT NOT NULL DEFAULT '',
    progress REAL NOT NULL DEFAULT 0,
    cutoff_hz REAL,                        -- where the audio stops (Hz); 22050 = full range
    quality TEXT NOT NULL DEFAULT '',     -- '' (not measured) | genuine | suspect | fake
    tier TEXT NOT NULL DEFAULT '',        -- rung on the quality ladder (quality.py), e.g. mp3_320
    next_upgrade REAL NOT NULL DEFAULT 0, -- done but below target: when to look for a better copy (0 = not)
    upgrade_path TEXT NOT NULL DEFAULT '',-- better copy waiting for the user ("ask" mode)
    upgrade_tier TEXT NOT NULL DEFAULT '',
    custom_query TEXT NOT NULL DEFAULT '', -- the user's own search term, tried first
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS tracks_state ON tracks(state, next_attempt);
-- Files that failed the file checks (roadmap step 2). A row also blocks that peer + file for the
-- track, so it is never tried again. path is the file in quarantine ('' once approved or deleted).
CREATE TABLE IF NOT EXISTS rejects (
    id INTEGER PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    peer TEXT NOT NULL,
    remote_file TEXT NOT NULL,
    reason TEXT NOT NULL,
    path TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'quarantined',   -- quarantined | approved | deleted
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS rejects_track ON rejects(track_id);
-- Search attempts for "Why not?" (roadmap step 5): the queries with their result counts and the
-- 10 closest files with their score or the reason they were turned down. Last 3 per track.
CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    queries TEXT NOT NULL DEFAULT '[]',      -- JSON [{"query": ..., "results": n}]
    candidates TEXT NOT NULL DEFAULT '[]',   -- JSON, see Engine._save_search
    summary TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS searches_track ON searches(track_id, created_at);
"""

# Track states
WANTED = "wanted"          # search as soon as possible
SEARCHING = "searching"
DOWNLOADING = "downloading"
WAITING = "waiting"        # not found yet, will retry at next_attempt
DONE = "done"
GAVE_UP = "gave_up"
SKIPPED = "skipped"
ACTIVE_STATES = (WANTED, SEARCHING, DOWNLOADING, WAITING)


class Database:
    def __init__(self, path: Path | str):
        self.conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            cols = {r[1] for r in self.conn.execute("PRAGMA table_info(channels)")}
            if "kind" not in cols:   # databases from before playlists existed
                self.conn.execute("ALTER TABLE channels ADD COLUMN kind TEXT NOT NULL DEFAULT 'profile'")
            tcols = {r[1] for r in self.conn.execute("PRAGMA table_info(tracks)")}
            if "cutoff_hz" not in tcols:   # databases from before the spectrum check
                self.conn.execute("ALTER TABLE tracks ADD COLUMN cutoff_hz REAL")
            if "quality" not in tcols:
                self.conn.execute("ALTER TABLE tracks ADD COLUMN quality TEXT NOT NULL DEFAULT ''")
            for col, ddl in (("tier", "TEXT NOT NULL DEFAULT ''"), ("next_upgrade", "REAL NOT NULL DEFAULT 0"),
                             ("upgrade_path", "TEXT NOT NULL DEFAULT ''"), ("upgrade_tier", "TEXT NOT NULL DEFAULT ''"),
                             ("custom_query", "TEXT NOT NULL DEFAULT ''")):
                if col not in tcols:   # databases from before quality profiles
                    self.conn.execute(f"ALTER TABLE tracks ADD COLUMN {col} {ddl}")

    def _q(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def _x(self, sql: str, args: tuple = ()) -> int:
        with self.lock:
            cur = self.conn.execute(sql, args)
            return cur.lastrowid or cur.rowcount

    # Channels -----------------------------------------------------------
    def add_channel(self, url: str, name: str, include_reposts: bool, backlog: int, avatar: str = "",
                    kind: str = "profile") -> int:
        return self._x(
            "INSERT INTO channels(url, name, avatar, include_reposts, backlog, kind, added_at) VALUES (?,?,?,?,?,?,?)",
            (url, name, avatar, int(include_reposts), int(backlog), kind, time.time()))

    def channels(self) -> list[dict]:
        return self._q("""
            SELECT c.*,
              (SELECT COUNT(*) FROM tracks t WHERE t.channel_id=c.id AND t.state='done') AS done_count,
              (SELECT COUNT(*) FROM tracks t WHERE t.channel_id=c.id AND t.state IN ('wanted','searching','downloading','waiting')) AS open_count
            FROM channels c ORDER BY c.name COLLATE NOCASE""")

    def channel(self, cid: int) -> Optional[dict]:
        rows = self._q("SELECT * FROM channels WHERE id=?", (cid,))
        return rows[0] if rows else None

    def channel_by_url(self, url: str) -> Optional[dict]:
        rows = self._q("SELECT * FROM channels WHERE url=?", (url,))
        return rows[0] if rows else None

    def update_channel(self, cid: int, **fields: Any) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        self._x(f"UPDATE channels SET {cols} WHERE id=?", (*fields.values(), cid))

    def delete_channel(self, cid: int) -> None:
        self._x("DELETE FROM channels WHERE id=?", (cid,))

    # Tracks -------------------------------------------------------------
    def tracks_by_sc_ids(self, ids: list[str]) -> list[dict]:
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        return self._q(f"SELECT * FROM tracks WHERE sc_id IN ({marks})", tuple(ids))

    def known_sc_ids(self, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        marks = ",".join("?" * len(ids))
        return {r["sc_id"] for r in self._q(f"SELECT sc_id FROM tracks WHERE sc_id IN ({marks})", tuple(ids))}

    def add_track(self, **fields: Any) -> int:
        now = time.time()
        fields.setdefault("created_at", now)
        fields["updated_at"] = now
        cols = ", ".join(fields)
        marks = ", ".join("?" * len(fields))
        return self._x(f"INSERT OR IGNORE INTO tracks({cols}) VALUES ({marks})", tuple(fields.values()))

    def update_track(self, tid: int, **fields: Any) -> None:
        fields["updated_at"] = time.time()
        cols = ", ".join(f"{k}=?" for k in fields)
        self._x(f"UPDATE tracks SET {cols} WHERE id=?", (*fields.values(), tid))

    # Rejects / quarantine ------------------------------------------------
    def add_reject(self, track_id: int, peer: str, remote_file: str, reason: str, path: str) -> int:
        return self._x("INSERT INTO rejects(track_id, peer, remote_file, reason, path, created_at) VALUES (?,?,?,?,?,?)",
                       (track_id, peer, remote_file, reason, path, time.time()))

    def reject(self, rid: int) -> Optional[dict]:
        rows = self._q("SELECT * FROM rejects WHERE id=?", (rid,))
        return rows[0] if rows else None

    def update_reject(self, rid: int, **fields: Any) -> None:
        cols = ", ".join(f"{k}=?" for k in fields)
        self._x(f"UPDATE rejects SET {cols} WHERE id=?", (*fields.values(), rid))

    def quarantined(self, limit: int = 200) -> list[dict]:
        return self._q("""
            SELECT r.*, t.artist, t.title, t.version, t.url, t.state AS track_state, c.name AS channel_name
            FROM rejects r JOIN tracks t ON t.id=r.track_id JOIN channels c ON c.id=t.channel_id
            WHERE r.status='quarantined' ORDER BY r.created_at DESC LIMIT ?""", (limit,))

    # Search attempts ------------------------------------------------------
    KEEP_SEARCHES = 3

    def add_search(self, track_id: int, queries: list[dict], candidates: list[dict], summary: str) -> int:
        sid = self._x("INSERT INTO searches(track_id, created_at, queries, candidates, summary) VALUES (?,?,?,?,?)",
                      (track_id, time.time(), json.dumps(queries), json.dumps(candidates), summary))
        self._x("""DELETE FROM searches WHERE track_id=? AND id NOT IN
                   (SELECT id FROM searches WHERE track_id=? ORDER BY id DESC LIMIT ?)""",
                (track_id, track_id, self.KEEP_SEARCHES))
        return sid

    def searches(self, track_id: int) -> list[dict]:
        rows = self._q("SELECT * FROM searches WHERE track_id=? ORDER BY id DESC", (track_id,))
        for r in rows:
            r["queries"] = json.loads(r["queries"] or "[]")
            r["candidates"] = json.loads(r["candidates"] or "[]")
        return rows

    def blocked_last_id(self, track_id: int) -> int:
        rows = self._q("SELECT MAX(id) AS id FROM rejects WHERE track_id=?", (track_id,))
        return rows[0]["id"] if rows and rows[0]["id"] else 0

    def blocked(self, track_id: int) -> set[tuple[str, str]]:
        """Peer + file combinations that failed the checks for this track."""
        return {(r["peer"], r["remote_file"]) for r in self._q("SELECT peer, remote_file FROM rejects WHERE track_id=?", (track_id,))}

    def track(self, tid: int) -> Optional[dict]:
        rows = self._q("SELECT * FROM tracks WHERE id=?", (tid,))
        return rows[0] if rows else None

    def tracks(self, limit: int = 500, channel_id: Optional[int] = None) -> list[dict]:
        where, args = "", ()
        if channel_id:
            where, args = "WHERE t.channel_id=?", (channel_id,)
        return self._q(f"""
            SELECT t.*, c.name AS channel_name FROM tracks t JOIN channels c ON c.id=t.channel_id
            {where} ORDER BY COALESCE(t.uploaded_at, t.created_at) DESC, t.id DESC LIMIT ?""", (*args, limit))

    def due_tracks(self, now: float, limit: int = 20) -> list[dict]:
        return self._q("""
            SELECT t.*, c.name AS channel_name FROM tracks t JOIN channels c ON c.id=t.channel_id
            WHERE c.enabled=1 AND t.state IN ('wanted','waiting') AND t.next_attempt<=?
            ORDER BY t.state='waiting', t.next_attempt, t.id LIMIT ?""", (now, limit))

    def due_upgrades(self, now: float, since: float, limit: int = 5) -> list[dict]:
        """Downloaded tracks below their quality target whose next upgrade search is due."""
        return self._q("""
            SELECT t.*, c.name AS channel_name FROM tracks t JOIN channels c ON c.id=t.channel_id
            WHERE c.enabled=1 AND t.state='done' AND t.next_upgrade>0 AND t.next_upgrade<=?
              AND t.upgrade_path='' AND t.created_at>=?
            ORDER BY t.next_upgrade LIMIT ?""", (now, since, limit))

    def interrupted_transfers(self) -> list[dict]:
        """Tracks that were downloading when the app stopped (their transfer may still exist)."""
        return self._q("SELECT * FROM tracks WHERE state='downloading' AND peer!='' AND remote_file!=''")

    def reset_interrupted(self) -> None:
        """After a restart, anything that was mid-search/download is wanted again."""
        self._x("UPDATE tracks SET state='wanted', progress=0, next_attempt=0 WHERE state IN ('searching','downloading')")

    def stats(self) -> dict:
        rows = self._q("SELECT state, COUNT(*) AS n FROM tracks GROUP BY state")
        return {r["state"]: r["n"] for r in rows}
