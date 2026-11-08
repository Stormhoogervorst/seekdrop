# Cratewatch

Follow SoundCloud channels. When something new drops, Cratewatch looks for it on
Soulseek and downloads the best copy it can find.

For DJs and producers who don't want to check twenty label pages every day.

- Add any public SoundCloud profile: a label, artist, promo or repost channel.
- New uploads are checked every hour (you can change this).
- Messy titles are cleaned up: `PREMIERE: Artist - Track (Someone Remix) [FREE DL]`
  becomes artist *Artist*, title *Track*, version *Someone Remix*.
- Results are scored on title, artist, remix name, length, format, bitrate and how fast
  the peer can send it. Remixes are never accepted when you want the original, and the
  other way round.
- Lossless (FLAC/WAV/AIFF) or 320 kbps MP3, your choice.
- Not on Soulseek yet? Cratewatch tries again after 1 h, 3 h, 6 h, 12 h, then daily,
  for up to 30 days.
- Files land in `Music/Cratewatch/<channel>/Artist - Title (Version).flac`.

## Two ways to connect to Soulseek

- **Through Nicotine+.** If you already use [Nicotine+](https://nicotine-plus.org), Cratewatch
  can use your Nicotine+ account and shares. In setup (or Settings) click *Add plugin to
  Nicotine+*, then in Nicotine+ open Preferences, Plugins and turn on **Cratewatch Bridge**.
  The plugin only listens on 127.0.0.1 and only accepts Cratewatch's key. Cratewatch searches
  don't create search tabs or history in Nicotine+; downloads show up in its Downloads tab.
  Nicotine+ must be open while Cratewatch works.
- **With its own account.** Cratewatch logs in to Soulseek itself. No other app needed.

## Use it responsibly

Soulseek is a network where people share their own music folders. Only download music
you have the right to have, such as free downloads, promos sent to you, or tracks you
bought elsewhere. You are responsible for what you download and share. Cratewatch
reads only public SoundCloud pages and never downloads audio from SoundCloud itself.

## Install

Download the latest release:

- **Windows 10/11**: `Cratewatch-x.y.z-windows-setup.exe`. Windows may show a
  SmartScreen warning because the app isn't code-signed yet: click *More info* and
  *Run anyway*.
- **macOS 11+ (Apple Silicon)**: `Cratewatch-x.y.z-macos-arm64.dmg`. Drag it to
  Applications. The first time, right-click the app and choose *Open*, because the app
  isn't notarized yet.

On first launch, pick a Soulseek username and password (a new name is created
automatically) and a download folder. Use a separate Soulseek account for
Cratewatch: logging in with the same account somewhere else disconnects one of them.

Cratewatch only checks while it's open. On Windows, the installer can start it when
you log in.

## Run from source

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m cratewatch            # app window
python -m cratewatch --browser  # UI in your browser
pytest
```

`scripts/demo.py` starts the UI with made-up data, without needing SoundCloud or Soulseek.

## Build installers

Push a tag like `v0.1.0`. GitHub Actions runs the tests, builds the Windows installer
and the macOS DMG, smoke-tests both, and attaches them to a draft release.

Locally: `pyinstaller packaging/cratewatch.spec --noconfirm`.

## How it's built

| Part | File |
|---|---|
| Read SoundCloud profiles (via yt-dlp) | `src/cratewatch/soundcloud.py` |
| Clean up titles, build search queries | `src/cratewatch/titles.py` |
| Score Soulseek results | `src/cratewatch/matching.py` |
| Soulseek client (via aioslsk) | `src/cratewatch/soulseek.py` |
| Nicotine+ client + plugin installer | `src/cratewatch/nicotine.py` |
| Nicotine+ plugin (runs inside Nicotine+) | `src/cratewatch/nicotine_plugin/cratewatch_bridge/` |
| Scheduler, retries, file naming | `src/cratewatch/engine.py` |
| Local API + UI | `src/cratewatch/server.py`, `src/cratewatch/ui/` |
| App window (pywebview) | `src/cratewatch/__main__.py` |

Settings, database and logs live in the user data folder
(`%LOCALAPPDATA%\Cratewatch` on Windows, `~/Library/Application Support/Cratewatch` on macOS).

## License

GPL-3.0-or-later (required because it builds on aioslsk). The bundled Archivo font is
under the SIL Open Font License.
