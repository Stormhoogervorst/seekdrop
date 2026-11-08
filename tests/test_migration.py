"""Taking over data and the Nicotine+ plugin from the app's earlier names."""
import json

from seekdrop import nicotine
from seekdrop.config import migrate_legacy_data


def _old_folder(path, db="nicotine-sync.db"):
    path.mkdir(parents=True)
    (path / "settings.json").write_text('{"accepted_terms": true}')
    for suffix in ("", "-wal", "-shm"):
        (path / (db + suffix)).write_text("x")
    return path


def test_old_data_folder_is_taken_over(tmp_path):
    old = _old_folder(tmp_path / "Nicotine+ Sync")
    new = tmp_path / "SeekDrop"
    assert migrate_legacy_data(new, [old, tmp_path / "Cratewatch"]) == old
    assert not old.exists()
    assert (new / "settings.json").read_text() == '{"accepted_terms": true}'
    assert sorted(p.name for p in new.iterdir()) == ["seekdrop.db", "seekdrop.db-shm", "seekdrop.db-wal", "settings.json"]
    # Running it again changes nothing.
    assert migrate_legacy_data(new, [old]) is None
    assert (new / "seekdrop.db").exists()


def test_oldest_name_and_empty_new_folder(tmp_path):
    old = _old_folder(tmp_path / "Cratewatch", db="cratewatch.db")
    new = tmp_path / "SeekDrop"
    new.mkdir()                                   # e.g. created by the log setup
    assert migrate_legacy_data(new, [tmp_path / "Nicotine+ Sync", old]) == old
    assert (new / "seekdrop.db").exists()


def test_never_overwrites_existing_seekdrop_data(tmp_path):
    old = _old_folder(tmp_path / "Nicotine+ Sync")
    new = tmp_path / "SeekDrop"
    new.mkdir()
    (new / "settings.json").write_text("{}")
    assert migrate_legacy_data(new, [old]) is None
    assert old.exists() and (new / "settings.json").read_text() == "{}"


def test_plugin_takes_over_old_key(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    old = tmp_path / "nicotine" / "plugins" / "nicotine_sync_bridge"
    old.mkdir(parents=True)
    (old / "bridge.json").write_text(json.dumps({"port": 47820, "token": "old-key"}))
    assert nicotine.migrate_legacy_plugin()
    new = tmp_path / "nicotine" / "plugins" / "seekdrop_bridge"
    assert json.loads((new / "bridge.json").read_text()) == {"port": 47820, "token": "old-key"}
    assert (new / "PLUGININFO").exists() and (new / "__init__.py").exists()
    assert not nicotine.migrate_legacy_plugin()   # only once


def test_old_default_download_dir(tmp_path):
    from seekdrop.config import _retarget_default_download_dir
    music = tmp_path / "Music"
    cfg = tmp_path / "settings.json"
    # Empty / missing old default -> new default.
    cfg.write_text(json.dumps({"download_dir": str(music / "Nicotine+ Sync")}))
    _retarget_default_download_dir(cfg, music)
    assert json.loads(cfg.read_text())["download_dir"] == str(music / "SeekDrop")
    # Old default that already holds music -> untouched.
    (music / "Nicotine+ Sync").mkdir(parents=True)
    (music / "Nicotine+ Sync" / "track.flac").write_text("x")
    cfg.write_text(json.dumps({"download_dir": str(music / "Nicotine+ Sync")}))
    _retarget_default_download_dir(cfg, music)
    assert json.loads(cfg.read_text())["download_dir"] == str(music / "Nicotine+ Sync")
    # A folder the user picked -> untouched.
    cfg.write_text(json.dumps({"download_dir": "/Volumes/DJ/Incoming"}))
    _retarget_default_download_dir(cfg, music)
    assert json.loads(cfg.read_text())["download_dir"] == "/Volumes/DJ/Incoming"


def test_old_database_gets_quality_columns(tmp_path):
    import sqlite3
    from seekdrop.db import Database
    path = tmp_path / "old.db"
    Database(path).conn.close()
    con = sqlite3.connect(path)           # make it look like a database from before step 3
    con.execute("ALTER TABLE tracks DROP COLUMN cutoff_hz")
    con.execute("ALTER TABLE tracks DROP COLUMN quality")
    con.commit()
    con.close()
    assert not {"cutoff_hz", "quality"} & {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(tracks)")}
    Database(path)
    cols = {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(tracks)")}
    assert {"cutoff_hz", "quality"} <= cols


def test_old_database_gets_search_history(tmp_path):
    import sqlite3
    from seekdrop.db import Database
    path = tmp_path / "old.db"
    Database(path).conn.close()
    con = sqlite3.connect(path)
    con.execute("DROP TABLE searches")
    con.execute("ALTER TABLE tracks DROP COLUMN custom_query")
    con.commit()
    con.close()
    db = Database(path)
    tables = {r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    cols = {r[1] for r in db.conn.execute("PRAGMA table_info(tracks)")}
    assert "searches" in tables and "custom_query" in cols
