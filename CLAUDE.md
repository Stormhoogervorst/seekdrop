# SeekDrop: notes for Claude Code

Desktop app (Python, pywebview UI) that follows SoundCloud channels and playlists and downloads
the tracks from Soulseek, either with its own login (aioslsk) or through Nicotine+ via the bundled
`seekdrop_bridge` plugin. Formerly Cratewatch, then Nicotine+ Sync (renamed because "SoulSync"
is taken by another Soulseek project). On first start the old data folder and plugin key are taken
over (`config.migrate_legacy_data`, `nicotine.migrate_legacy_plugin`). UI copy is English; the owner speaks Dutch.
Repo: github.com/Stormhoogervorst/nicotinesync.

## Run / test
- Python 3.11 to 3.13 (not 3.14: deps). ffmpeg is optional (`brew install ffmpeg`); without it the
  file-check tests are skipped and the app skips the checks. `python3.13 -m venv .venv && .venv/bin/pip install -e ".[dev]"`.
- `python -m seekdrop` (window) or `--browser` / `--headless`.
- `pytest -q` (unit + engine tests with fakes). `tests/conftest.py` points XDG_DATA_HOME, APPDATA and
  SEEKDROP_HOME at a temp dir, so no test can touch the real Nicotine+ plugins or app data.
- UI dev server: `python scripts/demo.py` (launch.json `ui-demo`), open http://localhost:8765/#token=dev.
  Made-up data in a temp folder, no network; UI file edits show on refresh.
- Throwaway data dir: `SEEKDROP_HOME=/tmp/ns python -m seekdrop --headless --port 47900`.
  The printed URL has `#token=…`; send it as `X-Token` to `/api/*`.
- Nicotine+ plugin harness: `pip download nicotine-plus --no-deps`, unzip the wheel, then
  `PYTHONPATH=src:<unzipped> python tests/manual/nicotine_harness.py`.
- Local build: `pyinstaller packaging/seekdrop.spec --noconfirm` -> `dist/SeekDrop.app`.

## Verified against the real services (Nov 2026, macOS 26, Nicotine+ 3.3.11)
- SoundCloud via yt-dlp: profiles, playlists (flat entries have no title; some URLs are
  api-v2 track URLs, `track()` resolves them), durations, artwork, curl_cffi impersonation.
- Nicotine+ bridge: plugin loads, search, download, move to download folder, candidate fallback,
  stale-transfer cleanup.
- PyInstaller .app runs (headless + window process); GitHub Actions builds macOS + Windows.

## Not verified yet
1. Built-in Soulseek login with aioslsk (`soulseek.py`): needs a Soulseek account (the owner must
   enter it; don't create accounts).
2. Windows app beyond the CI smoke test; signed/notarized macOS build (needs Apple secrets).

## Architectuur
Feature work follows `ROADMAP.md` (one step per session, plan first, wait for approval).
- **SoundCloud** (`soundcloud.py`): yt-dlp, metadata only. `latest()` lists a profile's uploads or
  every track of a playlist; `track()` gives title, uploader, duration, artwork. Never downloads audio.
- **Titles** (`titles.py`): `parse_title()` → artist / title / version (drops promo text, label and
  catalog suffixes, quotes), `is_mix()`, `search_queries()`.
- **Matching** (`matching.py`): `score_candidate()` hard-rejects (wrong title/artist/remixer, length,
  bitrate, spam peers, DJ-pool edits) and scores the rest (format, length, free slot, speed); `rank()`.
- **Soulseek**, two interchangeable services: `soulseek.py` (own login via aioslsk) and `nicotine.py`
  (HTTP to the `seekdrop_bridge` plugin running inside Nicotine+, 127.0.0.1 + key). Chosen by
  `settings.soulseek_mode`. Steps that touch peers (4, 8) must work through both.
- **Engine** (`engine.py`): poll loop checks channels → `tracks` rows (state wanted…done); search
  loop: queries → rank → up to 3 candidates → download into the service's incoming folder in the
  app data → `_stage_and_publish()`: move to `staging/<track id>/`, run `Engine.checks` (each returns a
  reject reason or None), then `publish_file()` to `download_dir/<channel>/Artist - Title (Version).ext`
  in one go. Start-up removes staging leftovers and hidden `.…seekdrop-part` files.
  Retries 1h/3h/6h/12h/daily up to `give_up_days`.
- **File checks** (`checks.py`): `FileChecker` is in `Engine.checks`; ffprobe/ffmpeg (optional, found on
  PATH or in Homebrew dirs) for decode errors, cut-off, format vs extension, length vs SoundCloud,
  silence. Rejects go to `quarantine/` + table `rejects` (also the per-track peer/file blocklist).
- **Storage**: `db.py` (SQLite: `channels`, `tracks`, `rejects`), `config.py` (settings.json, data dir, migration).
- **UI**: `server.py` (aiohttp JSON API with a per-run key) + `ui/` (plain HTML/CSS/JS, no build),
  shown in a pywebview window by `__main__.py`; `updates.py` checks GitHub releases.

## Design notes
- Engine (`engine.py`) only uses the service interface: start/stop/status/error/connected/
  retryable/search/download/transfer_info/abort/forget/rescan_shares/lookup/cancel.
  `SoulseekService` and `NicotineBridge` both implement it; `Backend.make_slsk` picks one by
  `settings.soulseek_mode`.
- Channels table has `kind` = profile | playlist. Playlists: every track wanted, playlist order;
  tracks another channel skipped (backlog) move to the playlist.
- Skips uploads > `MAX_TRACK_SECONDS` (600) and `titles.is_mix()` titles at add time.
- The plugin inserts its `file-search-response` callback first, because Nicotine+ drops
  responses for tokens that have no search tab. It uses private-ish Nicotine+ internals
  (`core.search.token`, `sanitize_search_term`, `events._callbacks`); re-check on Nicotine+ updates.
- Bump `PLUGININFO` Version when the plugin changes: the app then replaces the installed copy.
- Search spacing 8 s and 12 s collection per query (`engine.py`) to be a polite Soulseek client.
- License GPL-3.0-or-later (aioslsk). Keep it that way.
