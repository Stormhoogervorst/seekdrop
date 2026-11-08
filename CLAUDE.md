# Nicotine+ Sync: notes for Claude Code

Desktop app (Python, pywebview UI) that follows SoundCloud channels and playlists and downloads
the tracks from Soulseek, either with its own login (aioslsk) or through Nicotine+ via the bundled
`nicotine_sync_bridge` plugin. Formerly called Cratewatch. UI copy is English; the owner speaks Dutch.
Repo: github.com/Stormhoogervorst/nicotinesync.

## Run / test
- Python 3.11 to 3.13 (not 3.14: deps). `python3.13 -m venv .venv && .venv/bin/pip install -e ".[dev]"`.
- `python -m nicotine_sync` (window) or `--browser` / `--headless`.
- `pytest -q` (unit + engine tests with fakes).
- `python scripts/demo.py` runs the UI with made-up data, no network.
- Throwaway data dir: `NICOTINE_SYNC_HOME=/tmp/ns python -m nicotine_sync --headless --port 47900`.
  The printed URL has `#token=…`; send it as `X-Token` to `/api/*`.
- Nicotine+ plugin harness: `pip download nicotine-plus --no-deps`, unzip the wheel, then
  `PYTHONPATH=src:<unzipped> python tests/manual/nicotine_harness.py`.
- Local build: `pyinstaller packaging/nicotine_sync.spec --noconfirm` -> `dist/Nicotine+ Sync.app`.

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
