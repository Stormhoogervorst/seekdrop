# SeekDrop

Follow SoundCloud channels and playlists. When a track shows up, SeekDrop looks for it on
Soulseek and downloads the best copy it can find.

For DJs and producers who don't want to check twenty label pages every day.

- **Channels:** add any public SoundCloud profile (a label, artist, promo or repost channel).
  New uploads are checked every hour (you can change this).
- **Playlists:** paste a playlist link (`soundcloud.com/name/sets/…`, private `…/s-xxxx` links
  work too). Every track in it is searched and downloaded, and tracks added later are fetched too.
- Messy titles are cleaned up: `PREMIERE: Artist - Track (Someone Remix) [FREE DL]` becomes
  artist *Artist*, title *Track*, version *Someone Remix*. Label names and catalog numbers
  (`- Drumcode - DC360`) are dropped.
- DJ mixes, radio shows, podcasts and anything over 10 minutes are skipped (you can still get
  one on purpose).
- Results are scored on title, artist, remix name, length, format, bitrate and how fast the peer
  can send it. Remixes are never accepted when you want the original, and the other way round.
  DJ-pool edits (`(Clean)`, `(Intro)`, `TMU …`) and spam peers that advertise a website are skipped.
- Quality profiles: **Club** (lossless, MP3 320 at least), **Balanced** (MP3 320 or better) or
  **Space saver**. If a track first comes in below your goal (say MP3 320 while you want lossless),
  the app keeps looking for a better copy for 30 days and asks before it replaces your file (cue
  points in Rekordbox or Serato are tied to the file name). Replaced files go to SeekDrop's trash.
- Not on Soulseek yet? It tries again after 1 h, 3 h, 6 h, 12 h, then daily, for up to 30 days.
- Files land in `Music/SeekDrop/<channel or playlist>/Artist - Title (Version).flac`.

SeekDrop is an independent project. It is not made by or affiliated with the Nicotine+ team.

## Install

Download the latest version from the
[Releases page](https://github.com/Stormhoogervorst/seekdrop/releases/latest).

**macOS 11 or newer, Apple Silicon (M1 and later):** `SeekDrop-x.y.z-macos-arm64.dmg`

1. Open the DMG and drag **SeekDrop** to Applications.
2. Open it. If macOS says it can't check the app for malicious software: open
   **System Settings → Privacy & Security**, scroll down and click **Open Anyway** next to
   SeekDrop, then confirm. You only need to do this once.

**Windows 10/11:** `SeekDrop-x.y.z-windows-setup.exe`

Windows may show a SmartScreen warning because the app isn't code-signed: click
**More info**, then **Run anyway**. The installer can start the app when you log in.

The app tells you when a new version is out (Settings → Updates). Download it from the
Releases page and install it over the old one; your channels and settings are kept.

## Two ways to connect to Soulseek

- **Through Nicotine+ (recommended if you already use it).** Uses your Nicotine+ account and
  shares. In setup (or Settings) click *Add plugin to Nicotine+*, then in Nicotine+ open
  **Preferences → Plugins** and turn on **SeekDrop Bridge**. If it isn't in the list,
  close Preferences and open it again, or restart Nicotine+.
  The plugin only listens on 127.0.0.1 and only accepts SeekDrop's key. Searches don't
  create search tabs or history in Nicotine+; downloads show up in its Downloads tab.
  Nicotine+ must be open while SeekDrop works.
- **With its own account.** SeekDrop logs in to Soulseek itself; no other app needed.
  Use a separate Soulseek account for it: logging in with the same account somewhere else
  disconnects one of them. A name that doesn't exist yet is created when you first log in.

The app only checks while it's open.

## File checks (optional: ffmpeg)

If [ffmpeg](https://ffmpeg.org) is installed (on a Mac: `brew install ffmpeg`), every download is
checked before it goes to your music folder: it must play all the way through, be the format its name
says (no MP3 renamed to .flac), be about as long as on SoundCloud, and not start or end with a long
silence. It also looks at the spectrum to catch fake lossless: an MP3 converted to FLAC or WAV
(or a 128 kbps MP3 passed off as 320) stops at a hard cutoff around 16-19 kHz. Each track shows
where its audio stops. Files that fail end up under **Quarantine** with the reason; you can approve or delete them,
and the app tries another peer. Without ffmpeg the checks are skipped (Settings shows this).

## Use it responsibly

Soulseek is a network where people share their own music folders. Only download music you have
the right to have, such as free downloads, promos sent to you, or tracks you bought elsewhere.
You are responsible for what you download and share. SeekDrop reads only public (or
shared-with-you) SoundCloud pages and never downloads audio from SoundCloud itself.

## Privacy

Everything stays on your computer. The app talks to SoundCloud (to read channels and playlists),
to Soulseek (directly or through Nicotine+), and twice a day to GitHub to see if there is a new
version (you can turn that off in Settings). There is no tracking or analytics.

Settings, database and logs live in `~/Library/Application Support/SeekDrop` (macOS) or
`%LOCALAPPDATA%\SeekDrop` (Windows).

## Troubleshooting

- **"Can't reach Nicotine+"**: open Nicotine+ and check that SeekDrop Bridge is turned on
  (Preferences → Plugins). After updating the app, turn the plugin off and on once.
- **A track stays at "Waiting for peer"**: the peer has a queue. After 45 minutes the app tries
  another peer.
- **"Not on Soulseek yet"** for a track you can find by hand: open an issue with the SoundCloud
  link and the file name you found. Title matching is strict on purpose.
- Logs: `seekdrop.log` in the folder above. Please attach it to bug reports.

Report problems on the [Issues page](https://github.com/Stormhoogervorst/seekdrop/issues).

## Run from source

Python 3.11 to 3.13.

```bash
python3.13 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m seekdrop            # app window
python -m seekdrop --browser  # UI in your browser
pytest
```

**UI work:** `python scripts/demo.py` starts the real UI with made-up data at
http://localhost:8765/#token=dev, without SoundCloud or Soulseek, in a throwaway data folder.
Edits to `src/seekdrop/ui/` show up when you refresh the page; Python changes need a restart.
`DEMO_SETUP=1` shows the first-run setup instead. (In Claude Code: `.claude/launch.json` → `ui-demo`.)
Use a throwaway data folder with `SEEKDROP_HOME=/tmp/ns python -m seekdrop --browser`.

## Releases

1. Update the version in `pyproject.toml`, `src/seekdrop/__init__.py` and (if the plugin
   changed) `src/seekdrop/nicotine_plugin/seekdrop_bridge/PLUGININFO`, and add the
   changes to `CHANGELOG.md`.
2. Push a tag like `v0.3.0`. GitHub Actions runs the tests, builds the Windows installer and the
   macOS DMG, smoke-tests both, and attaches them to a **draft** release.
3. Check the draft on the Releases page and publish it. Only then do users get the update notice.

macOS signing and notarization run automatically once these repository secrets are set:
`MACOS_CERT_P12` (base64 of a Developer ID Application certificate), `MACOS_CERT_PASSWORD`,
`APPLE_ID`, `APPLE_TEAM_ID` and `APPLE_APP_PASSWORD`. That needs an Apple Developer account.

Local build: `pyinstaller packaging/seekdrop.spec --noconfirm`.

## How it's built

| Part | File |
|---|---|
| Read SoundCloud profiles and playlists (via yt-dlp) | `src/seekdrop/soundcloud.py` |
| Clean up titles, spot mixes, build search queries | `src/seekdrop/titles.py` |
| Score Soulseek results | `src/seekdrop/matching.py` |
| Soulseek client (via aioslsk) | `src/seekdrop/soulseek.py` |
| Nicotine+ client + plugin installer | `src/seekdrop/nicotine.py` |
| Nicotine+ plugin (runs inside Nicotine+) | `src/seekdrop/nicotine_plugin/seekdrop_bridge/` |
| Scheduler, retries, file naming | `src/seekdrop/engine.py` |
| Update notice | `src/seekdrop/updates.py` |
| Local API + UI | `src/seekdrop/server.py`, `src/seekdrop/ui/` |
| App window (pywebview) | `src/seekdrop/__main__.py` |

## License

GPL-3.0-or-later (required because it builds on aioslsk). The bundled Inter Tight font is under the
SIL Open Font License; the icons are from Lucide (ISC License). The visual style follows `DESIGN.md`.
