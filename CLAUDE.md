# Cratewatch: notes for Claude Code

Desktop app (Python, pywebview UI) that watches SoundCloud channels and downloads new releases
from Soulseek, either with its own login (aioslsk) or through Nicotine+ via the bundled
`cratewatch_bridge` plugin. UI copy is English; the owner speaks Dutch.

## Run / test
- `pip install -e ".[dev]"`, then `python -m cratewatch` (window) or `--browser` / `--headless`.
- `pytest -q` (unit + engine tests with fakes).
- `python scripts/demo.py` runs the UI with made-up data, no network.
- Nicotine+ plugin harness: `pip download nicotine-plus --no-deps`, unzip the wheel, then
  `PYTHONPATH=src:<unzipped> python tests/manual/nicotine_harness.py`. Loads the plugin into a
  headless Nicotine+ core and fakes a peer reply.
- Use a throwaway data dir: `CRATEWATCH_HOME=/tmp/cw python -m cratewatch --browser`.

## Never verified against the real services (built in a sandbox without access)
1. SoundCloud via yt-dlp: `SoundCloudClient().channel_info/latest/track`. Check that fields
   (duration, artists, artwork) are filled, and that curl_cffi impersonation is picked up.
2. Built-in Soulseek login + search + download with aioslsk (`soulseek.py`).
3. The plugin in the real Nicotine+ macOS app (3.3.x): loads, logs "ready", searches return
   results, downloads land in `~/Library/Application Support/Cratewatch/incoming-nicotine`
   and get moved to the download folder.
4. pywebview window + native folder picker on macOS; PyInstaller .app via GitHub Actions.

## Design notes
- Engine (`engine.py`) only uses the service interface: start/stop/status/error/connected/
  retryable/search/download/transfer_info/abort/forget/rescan_shares. `SoulseekService` and
  `NicotineBridge` both implement it; `Backend.make_slsk` picks one by `settings.soulseek_mode`.
- The plugin inserts its `file-search-response` callback first, because Nicotine+ drops
  responses for tokens that have no search tab. It uses private-ish Nicotine+ internals
  (`core.search.token`, `sanitize_search_term`, `events._callbacks`); re-check on Nicotine+ updates.
- Search spacing 8 s and 12 s collection per query (`engine.py`) to be a polite Soulseek client.
- License GPL-3.0-or-later (aioslsk). Keep it that way.
