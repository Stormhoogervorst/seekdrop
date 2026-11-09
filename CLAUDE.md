# SeekSync: notes for Claude Code

Desktop app (Python, pywebview UI) that follows SoundCloud channels and playlists and downloads
the tracks from Soulseek, either with its own login (aioslsk) or through Nicotine+ via the bundled
`seeksync_bridge` plugin. Formerly Cratewatch, then Nicotine+ Sync, then SeekDrop (renamed to SeekSync in 0.6.0; "SoulSync"
is taken by another Soulseek project). On first start the old data folder and plugin key are taken
over (`config.migrate_legacy_data`, `nicotine.migrate_legacy_plugin`). UI copy is English; the owner speaks Dutch.
Repo: github.com/Stormhoogervorst/seeksync (renamed from seekdrop and before that nicotinesync; GitHub redirects the old names).

## Run / test
- Python 3.11 to 3.13 (not 3.14: deps). ffmpeg is optional (`brew install ffmpeg`); without it the
  file-check tests are skipped and the app skips the checks. `python3.13 -m venv .venv && .venv/bin/pip install -e ".[dev]"`.
- `python -m seeksync` (window) or `--browser` / `--headless`.
- `pytest -q` (unit + engine tests with fakes). `tests/conftest.py` points XDG_DATA_HOME, APPDATA and
  SEEKSYNC_HOME at a temp dir, so no test can touch the real Nicotine+ plugins or app data.
- UI dev server: `python scripts/demo.py` (launch.json `ui-demo`), open http://localhost:8765/#token=dev.
  Made-up data in a temp folder, no network; UI file edits show on refresh.
- Throwaway data dir: `SEEKSYNC_HOME=/tmp/ns python -m seeksync --headless --port 47900`.
  The printed URL has `#token=…`; send it as `X-Token` to `/api/*`.
- Nicotine+ plugin harness: `pip download nicotine-plus --no-deps`, unzip the wheel, then
  `PYTHONPATH=src:<unzipped> python tests/manual/nicotine_harness.py`.
- Local build: `pyinstaller packaging/seeksync.spec --noconfirm` -> `dist/SeekSync.app`.

## Verified against the real services (Nov 2026, macOS 26, Nicotine+ 3.3.11)
- SoundCloud via yt-dlp: profiles, playlists (flat entries have no title; some URLs are
  api-v2 track URLs, `track()` resolves them), durations, artwork, curl_cffi impersonation.
- Nicotine+ bridge: plugin loads, search, download, move to download folder, candidate fallback,
  stale-transfer cleanup. Plugin 0.5.1 `/status` reports `shared_folders` (via
  `core.shares.get_shared_folders()`, run against the 3.3.11 core: 0 folders -> 0, one added -> 1).
  `shared_files` is always None: the file count needs Nicotine+'s own share scan. Note `core.config`
  doesn't exist in 3.3.11 (`from pynicotine.config import config`); that bit an earlier version.
- PyInstaller .app runs (headless + window process); GitHub Actions builds macOS + Windows.

## Not verified yet
1. Built-in Soulseek login with aioslsk (`soulseek.py`): needs a Soulseek account (the owner must
   enter it; don't create accounts).
2. Windows app beyond the CI smoke test; signed/notarized macOS build (needs Apple secrets).

## Architectuur
Feature work follows `ROADMAP.md` (one step per session, plan first, wait for approval).
- **SoundCloud** (`soundcloud.py`): yt-dlp, metadata only. `latest()` lists a profile's uploads or
  every track of a playlist; `track()` gives title, uploader, duration, artwork. Never downloads audio.
- **Spotify** (`spotify.py`, step 16): public playlists only, read from the embed page `open.spotify.com/embed/playlist/<id>`
  (`__NEXT_DATA__` JSON: title, artists, length; max 100 tracks; unofficial, a changed page gives a clear error). The official
  Web API only shows playlists you own since Feb 2026 and needs Premium. `sources.py` (`Sources`) routes each link to
  SoundCloud or Spotify and is what `Engine.sc` is; a Spotify playlist is a `playlist` channel with `tracks.sc_id = spotify:<id>`.
- **Titles** (`titles.py`): `parse_title()` → artist / title / version (drops promo text, label and
  catalog suffixes, quotes), `is_mix()`, `search_queries()`.
- **Matching** (`matching.py`, all comparison rules; real-title tests in `tests/test_matching_real.py`):
  `version_of()` / `version_conflict()` (kind + remixer), `parse_aliases()` for `settings.artist_aliases`.
  `titles.normalize` uses anyascii (other scripts -> Latin). Engine `_parsed(t)` applies `fix_*` columns.
 `score_candidate()` hard-rejects (wrong title/artist/remixer, length,
  bitrate, spam peers, DJ-pool edits) and scores the rest (format, length, free slot, speed); `rank()`.
- **Soulseek**, two interchangeable services: `soulseek.py` (own login via aioslsk) and `nicotine.py`
  (HTTP to the `seeksync_bridge` plugin running inside Nicotine+, 127.0.0.1 + key). Chosen by
  `settings.soulseek_mode`. Steps that touch peers (4, 8) must work through both.
- **Engine** (`engine.py`): poll loop checks channels → `tracks` rows (state wanted…done); search
  loop: queries → rank → up to 3 candidates → download into the service's incoming folder in the
  app data → `_stage_and_publish()`: move to `staging/<track id>/`, run `Engine.checks` (each returns a
  reject reason or None), then `publish_file()` to `download_dir/<channel>/Artist - Title (Version).ext`
  in one go. Start-up removes staging leftovers and hidden `.…seeksync-part` files.
  Retries 1h/3h/6h/12h/daily up to `give_up_days`.
- **File checks** (`checks.py`): `FileChecker` is in `Engine.checks`; ffprobe/ffmpeg (optional, found on
  PATH or in Homebrew dirs) for decode errors, cut-off, format vs extension, length vs SoundCloud,
  silence, and (numpy) fake lossless / fake 320 via `measure_cutoff` + `classify`; the result is put in
  `track["_meta"]` and stored as `tracks.cutoff_hz` / `tracks.quality` when the file is published.
  Rejects go to `quarantine/` + table `rejects` (also the per-track peer/file blocklist).
- **Quality** (`quality.py`): ladder of tiers + profiles (club/balanced/space: accepted order + target).
  Matching scores by ladder position; `FileChecker` measures the real tier and enforces the floor.
  Done tracks below target (lossy only) get `next_upgrade`; the search loop runs `_upgrade_search` with a
  free slot, downloads with `record=False` (track row untouched), and either replaces (`auto`, old file
  to `trash/`) or parks the copy in `upgrades/` for Replace/Keep (`ask`, default).
- **Rekordbox** (`rekordbox.py`, step 12): `Engine.write_rekordbox_sync` writes `settings.rekordbox_xml_path` (default
  `SeekSync for Rekordbox.xml` in the download folder) when `rekordbox_export` is on: every `done` track whose file exists
  (`db.tracks_for_rekordbox`), name/artist/genre/year/label/comment from `_tag_meta`, size/length/bitrate/sample rate from
  `rekordbox.file_facts` (cached per path+size+mtime), one playlist per channel in a folder "SeekSync". Rewritten
  `REKORDBOX_DELAY` (30 s) after a download/upgrade/approve/channel removal via `schedule_rekordbox` (thread-safe, one
  pending write), atomic via a hidden `.seeksync-part` file. `Location` uses Rekordbox's own safe characters
  (`!#$()*+,:;=?@`). `rekordbox.read` parses any Rekordbox XML (also Rekordbox' own export). We never touch Rekordbox'
  database. Upgrade mode `auto_unless_dj`: `Engine.in_rekordbox(path)` (True/False/None) reads the user's own Rekordbox
  collection export (`rekordbox_library_xml`, read only, cached by mtime) via `rekordbox.collection_paths` /
  `has_file` (case, NFC/NFD, slashes, symlinks); `_upgrade_download` replaces by itself only when it is False, and
  asks when True or None. The state API adds `in_rekordbox` to done tracks when an export is set. Not built: M3U,
  Serato, Traktor. The reader was only tested on hand-made exports (no real Rekordbox export was available).
- **Collection** (`library.py`, step 11): table `library` = one row per audio file in `library_dirs` plus the download
  folder (`Engine.library_roots`). `library.scan` reads only new/changed files (size + mtime + root), keeps rows of folders
  that are unreachable. `library.find(db, parsed, duration, aliases)` recognises a wanted track (title via `title_key`
  or the file name, artist/alias, `version_conflict`, length within 25% / 20 s except original vs extended). Track state
  `collected` (file_path = where): set in `_add_wanted`, in `_search_track` (last check) and by `recheck_collection` after
  each scan; `retry_now` ("Get it anyway") sets `skip_rule='overridden'`. The search loop pauses while
  `library_state["scanning"]`; `_finalize` indexes the new file at once. `library.duplicates` groups the download folder
  by artist/title/version, best first (profile ladder); the app never deletes or moves files. No fingerprints yet (step 7).
- **Tags and names** (`tagging.py`, `naming.py`, step 10): `Engine.finish_file(t, path)` runs after the checks in
  `_stage_and_check` (and for *Approve anyway*): optional WAV -> AIFF (`tagging.wav_to_aiff`, same PCM, pure Python),
  then `tagging.tag_file` (ID3v2.3 for MP3/AIFF/WAV, Vorbis + picture for FLAC, MP4 for M4A) with `TagMeta` built by
  `Engine._tag_meta`; our fields are always set or cleared, other tags (BPM, key) stay. Cover from `tracks.artwork`
  (300 px link rewritten to t500x500, only sndcdn.com/soundcloud.com), an existing cover >= 500 px is kept. Genre and
  release date come from SoundCloud into `tracks.sc_meta` (JSON) when a track is added. Failures never block a
  file. `settings.filename_template` (`naming.render`, tokens channel/artist/title/version/year/genre) replaced
  `organize_by_channel` (migrated in `SettingsStore._load`); `_finalize` uses it. Settings: `tag_files`,
  `wav_to_aiff` (off), `label_from_channel` (off). Tests build their own MP3/FLAC/WAV bytes; ffmpeg-based ones skip.
- **Politeness** (`politeness.py`, step 8): `SearchThrottle` (spacing + max per 5 min, used by both
  search paths via `Engine._throttle`; settings `search_spacing` >= 4 s, `search_max_per_5min`),
  `low_disk_space` (`min_free_gb`; `Engine._check_disk` pauses new downloads, `paused_reason` in the
  state), peer reputation (table `peer_stats`: ok / failed / fake; `peer_score` feeds `MatchPrefs.peer_scores`,
  3 fakes or 5 failures without success block a peer for 30 days = `blocked_peers`, shown in "Why not?",
  Unblock in Settings), same-folder / same-peer bonus for an EP or playlist (`MatchPrefs.same_folder`), and
  `sharing_warning` (own login: settings + folder contents; Nicotine+: plugin 0.5.1 reports `shared_folders` in
  `/status`, None = unknown = no warning). Peer events are recorded in `Engine._record_peer`.
- **Why not?** (step 5): rejections carry `Candidate.rejected` + `stage`; `_search_track` stores each
  attempt (`searches` table, last 3) and puts `matching.summary()` in `last_error`. Engine `pick()` /
  `set_query()` / `stop_looking()`; `tracks.custom_query` is tried before the automatic queries.
- **Storage**: `db.py` (SQLite: `channels`, `tracks`, `rejects`, `searches`), `config.py` (settings.json, data dir, migration).
- **UI**: `server.py` (aiohttp JSON API with a per-run key) + `ui/` (plain HTML/CSS/JS, no build),
  shown in a pywebview window by `__main__.py`; `updates.py` checks GitHub releases (`/releases/latest`, so only published ones) and, in the macOS .app only, installs one:
  download the `*macos*.dmg` asset (size + SHA-256 from the API), `ditto` the app next to the current one, then a shell script
  (`SWAP_SCRIPT`) waits for the app to quit, moves the old app to `<data>/previous-versions/` (keeps 2) and `open`s the new one.
  `Backend.on_quit` is how the route closes the app. Test it without GitHub: `SEEKSYNC_RELEASE_API=<url of a release JSON>`
  (download URLs may then be http://127.0.0.1) and `OPEN_CMD=<script>` instead of `open`. Verified end to end on a copy of the build.

## Website
`site/` is the public website (plain HTML/CSS/JS, no build): English with a Dutch switch (`site/main.js` holds the Dutch text),
download buttons that read the newest published GitHub release, screenshots taken from `scripts/demo.py` (made-up data).
Deploy on Vercel with Root Directory `site`, Framework Preset "Other", no build command (the root `vercel.json` also serves `site/` as a static site when the Root Directory is left empty, because the repo root has a pyproject.toml that Vercel would take for a Python app). Preview: launch.json `site` (port 8770).
Keep the copy in step with the README when features change (and the Dutch text in `main.js` with the English in `index.html`).

## Design notes
- Engine (`engine.py`) only uses the service interface: start/stop/status/error/connected/
  retryable/search/download/transfer_info/abort/forget/rescan_shares/lookup/cancel.
  `SoulseekService` and `NicotineBridge` both implement it; `Backend.make_slsk` picks one by
  `settings.soulseek_mode`.
- Channels table has `kind` = profile | playlist. Playlists: every track wanted, playlist order;
  tracks another channel skipped (backlog) move to the playlist.
- Rules (`rules.py`, step 9): `Engine._add_wanted` asks `rules.check()` whether an upload is wanted, using the
  channel's rules (`channels.rules` JSON, '' = `DEFAULT_RULES`: 2 to 12 min, remixes on, previews and mixes
  skipped) and the global `settings.block_keywords` / `block_artists` (these win). A skipped track keeps the
  reason in `last_error` and `skip_rule` ('overridden' once the user pressed *Get it*, so rules leave it
  alone). `Engine.reapply_rules` runs after a rules or blocklist change: revives rule-skipped tracks that
  pass now, skips never-searched wanted tracks that don't; downloads, running and hand-skipped tracks stay.
- The plugin inserts its `file-search-response` callback first, because Nicotine+ drops
  responses for tokens that have no search tab. It uses private-ish Nicotine+ internals
  (`core.search.token`, `sanitize_search_term`, `events._callbacks`); re-check on Nicotine+ updates.
- Bump `PLUGININFO` Version when the plugin changes: the app then replaces the installed copy.
- Search spacing 8 s and 12 s collection per query (`engine.py`) to be a polite Soulseek client.
- License GPL-3.0-or-later (aioslsk). Keep it that way.
