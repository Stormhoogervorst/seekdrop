"""SQLite storage for channels and tracks."""
from __future__ import annotations

import json
import os
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
    rules TEXT NOT NULL DEFAULT '',           -- JSON, see rules.py ('' = the default rules)
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
    fix_artist TEXT NOT NULL DEFAULT '',   -- manual corrections (step 6): win over the automatic parse
    fix_title TEXT NOT NULL DEFAULT '',
    fix_version TEXT NOT NULL DEFAULT '',
    sc_meta TEXT NOT NULL DEFAULT '',      -- JSON from SoundCloud for the tags: genre, release date (step 10)
    skip_rule TEXT NOT NULL DEFAULT '',    -- why a rule skipped it (rules.py); 'overridden' = user fetched it anyway
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
-- The DJ's own music folders (roadmap step 11): one row per audio file, see library.py.
CREATE TABLE IF NOT EXISTS library (
    path TEXT PRIMARY KEY,
    root TEXT NOT NULL DEFAULT '',          -- the listed folder it was found under
    size INTEGER NOT NULL DEFAULT 0,
    mtime_ns INTEGER NOT NULL DEFAULT 0,    -- size + mtime decide whether a file is read again
    artist TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    version TEXT NOT NULL DEFAULT '',
    stem TEXT NOT NULL DEFAULT '',          -- file name without extension (and track number)
    duration REAL,
    ext TEXT NOT NULL DEFAULT '',
    bitrate INTEGER,
    bit_depth INTEGER,
    tier TEXT NOT NULL DEFAULT '',          -- quality.py ladder
    title_key TEXT NOT NULL DEFAULT '',     -- normalised title words, what a lookup starts from
    stem_key TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS library_title ON library(title_key);
-- Reputation per Soulseek user (roadmap step 8): good deliveries, failed downloads and fake
-- lossless / fake 320 files. Feeds the score; blocked_until > now keeps a peer out of the results.
CREATE TABLE IF NOT EXISTS peer_stats (
    username TEXT PRIMARY KEY,
    ok INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    fake INTEGER NOT NULL DEFAULT 0,
    blocked_until REAL NOT NULL DEFAULT 0,
    block_reason TEXT NOT NULL DEFAULT '',
    updated_at REAL NOT NULL DEFAULT 0
);
"""

# Track states
COLLECTED = "collected"    # already in the DJ's own music folders (step 11); file_path says where
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
            if "rules" not in cols:   # databases from before rules per channel (step 9)
                self.conn.execute("ALTER TABLE channels ADD COLUMN rules TEXT NOT NULL DEFAULT ''")
            tcols = {r[1] for r in self.conn.execute("PRAGMA table_info(tracks)")}
            if "cutoff_hz" not in tcols:   # databases from before the spectrum check
                self.conn.execute("ALTER TABLE tracks ADD COLUMN cutoff_hz REAL")
            if "quality" not in tcols:
                self.conn.execute("ALTER TABLE tracks ADD COLUMN quality TEXT NOT NULL DEFAULT ''")
            for col, ddl in (("tier", "TEXT NOT NULL DEFAULT ''"), ("next_upgrade", "REAL NOT NULL DEFAULT 0"),
                             ("upgrade_path", "TEXT NOT NULL DEFAULT ''"), ("upgrade_tier", "TEXT NOT NULL DEFAULT ''"),
                             ("custom_query", "TEXT NOT NULL DEFAULT ''"), ("fix_artist", "TEXT NOT NULL DEFAULT ''"),
                             ("fix_title", "TEXT NOT NULL DEFAULT ''"), ("fix_version", "TEXT NOT NULL DEFAULT ''")):
                if col not in tcols:   # databases from before quality profiles
                    self.conn.execute(f"ALTER TABLE tracks ADD COLUMN {col} {ddl}")
            if "sc_meta" not in tcols:   # step 10
                self.conn.execute("ALTER TABLE tracks ADD COLUMN sc_meta TEXT NOT NULL DEFAULT ''")
            if "skip_rule" not in tcols:   # step 9: the two fixed rules of before are now rules
                self.conn.execute("ALTER TABLE tracks ADD COLUMN skip_rule TEXT NOT NULL DEFAULT ''")
                self.conn.execute("""UPDATE tracks SET skip_rule=last_error WHERE state='skipped'
                                     AND last_error IN ('Looks like a mix', 'Longer than 10 minutes')""")

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

    # Library index (step 11) --------------------------------------------
    LIBRARY_COLS = ("path", "root", "size", "mtime_ns", "artist", "title", "version", "stem", "duration", "ext",
                    "bitrate", "bit_depth", "tier", "title_key", "stem_key")

    def library_stats(self) -> dict[str, tuple]:
        with self.lock:
            return {r[0]: (r[1], r[2], r[3]) for r in
                    self.conn.execute("SELECT path, size, mtime_ns, root FROM library")}

    def library_paths_of(self, root: Optional[str]) -> list[tuple[str, str]]:
        sql, args = "SELECT path, root FROM library", ()
        if root is not None:
            sql, args = sql + " WHERE root=?", (root,)
        with self.lock:
            return [(r[0], r[1]) for r in self.conn.execute(sql, args)]

    def library_upsert(self, rows: list[dict]) -> None:
        if not rows:
            return
        cols = self.LIBRARY_COLS
        sql = (f"INSERT OR REPLACE INTO library({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})")
        with self.lock:
            self.conn.execute("BEGIN")
            try:
                self.conn.executemany(sql, [tuple(r.get(c) for c in cols) for r in rows])
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    def library_delete(self, paths: list[str]) -> int:
        n = 0
        with self.lock:
            for i in range(0, len(paths), 500):
                chunk = paths[i:i + 500]
                n += self.conn.execute(f"DELETE FROM library WHERE path IN ({','.join('?' * len(chunk))})", chunk).rowcount
        return n

    def library_count(self) -> int:
        return self._q("SELECT COUNT(*) AS n FROM library")[0]["n"]

    def library_candidates(self, key: str) -> list[dict]:
        """Files whose title is `key`, or whose file name contains those words in a row."""
        return self._q("SELECT * FROM library WHERE title_key=? OR (' ' || stem_key || ' ') LIKE ?",
                       (key, f"% {key.replace('%', '').replace('_', '')} %"))

    def library_under(self, folder: str) -> list[dict]:
        prefix = folder.rstrip("/\\") + os.sep          # "/Music/" must not match "/Music2/..."
        esc = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return self._q("SELECT * FROM library WHERE path LIKE ? ESCAPE '\\' ORDER BY path", (esc + "%",))

    def library_has(self, path: str) -> bool:
        return bool(self._q("SELECT 1 AS x FROM library WHERE path=?", (path,)))

    # Peer reputation (step 8) -------------------------------------------
    def peer_stats(self, usernames: Optional[list[str]] = None) -> dict[str, dict]:
        if usernames is not None:
            if not usernames:
                return {}
            marks = ",".join("?" * len(usernames))
            rows = self._q(f"SELECT * FROM peer_stats WHERE username IN ({marks})", tuple(usernames))
        else:
            rows = self._q("SELECT * FROM peer_stats")
        return {r["username"]: r for r in rows}

    def bump_peer(self, username: str, column: str) -> dict:
        """Count one event (ok | failed | fake) for a peer and return its new totals."""
        assert column in ("ok", "failed", "fake")
        self._x("INSERT OR IGNORE INTO peer_stats(username) VALUES (?)", (username,))
        self._x(f"UPDATE peer_stats SET {column}={column}+1, updated_at=? WHERE username=?", (time.time(), username))
        return self.peer_stats([username])[username]

    def block_peer(self, username: str, until: float, reason: str) -> None:
        self._x("INSERT OR IGNORE INTO peer_stats(username) VALUES (?)", (username,))
        self._x("UPDATE peer_stats SET blocked_until=?, block_reason=? WHERE username=?", (until, reason, username))

    def unblock_peer(self, username: str) -> None:
        """Lifts the block and forgets the bad history, so one more slip doesn't block again at once."""
        self._x("UPDATE peer_stats SET blocked_until=0, block_reason='', failed=0, fake=0 WHERE username=?", (username,))

    def blocked_peers(self, now: float) -> list[dict]:
        return self._q("SELECT * FROM peer_stats WHERE blocked_until>? ORDER BY updated_at DESC", (now,))

    def peers_of_channel(self, channel_id: int, artist: str = "") -> list[dict]:
        """Where finished tracks of this channel (and of this artist anywhere) came from:
        peer + the remote folder, used to keep an EP or album together."""
        rows = self._q("""SELECT peer, remote_file FROM tracks
                          WHERE state='done' AND peer!='' AND remote_file!='' AND channel_id=?""", (channel_id,))
        if artist:
            rows += self._q("""SELECT peer, remote_file FROM tracks
                               WHERE state='done' AND peer!='' AND remote_file!='' AND artist=? AND channel_id!=?""",
                            (artist, channel_id))
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

    def tracks_for_collection(self) -> list[dict]:
        """Tracks that may be (or stop being) found in the DJ's own folders: waiting ones and collected ones."""
        return self._q("""SELECT * FROM tracks WHERE state IN ('wanted','waiting','gave_up','collected')
                          AND skip_rule!='overridden' ORDER BY id""")

    def tracks_for_rules(self, channel_id: Optional[int] = None) -> list[dict]:
        """Tracks the rules may still decide about: skipped by a rule, or wanted and never searched."""
        where, args = "", ()
        if channel_id:
            where, args = "AND t.channel_id=?", (channel_id,)
        return self._q(f"""
            SELECT t.* FROM tracks t
            WHERE ((t.state='skipped' AND t.skip_rule NOT IN ('', 'overridden'))
                OR (t.state='wanted' AND t.attempts=0 AND t.skip_rule=''))
            {where} ORDER BY t.id""", args)

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
