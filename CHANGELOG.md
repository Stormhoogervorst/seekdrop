# Changelog

## 0.4.0

- **New name: SeekDrop** (was Nicotine+ Sync). Your channels, settings and downloads are taken over
  automatically on first start. The Nicotine+ plugin is now called *SeekDrop Bridge*: in Nicotine+,
  turn off *Nicotine+ Sync Bridge* and turn on *SeekDrop Bridge* once (the app reminds you).
- New light, calm look (see DESIGN.md): grey shell, one white card, Inter Tight, Lucide icons.
  Yellow only marks what is downloading right now; statuses are plain text with a small icon;
  row actions are quiet grey text buttons.

## 0.3.0

First public release as **Nicotine+ Sync** (was Cratewatch).

- Playlists: paste a SoundCloud playlist link (also private `/s-…` links). Every track is searched
  and downloaded, tracks added later are fetched too.
- Skip DJ mixes, radio shows, podcasts and uploads over 10 minutes. The reason shows in the list.
- Better matching: label names and catalog numbers are dropped from titles, remixer names with
  "&" match again, spam peers and DJ-pool edits (`(Clean)`, `(Intro)`, `TMU`) are skipped.
- Nicotine+: downloads left over from a previous session are tidied up at start (a file that
  finished in the meantime is kept). Quitting stops queued downloads in Nicotine+.
- The app replaces an outdated Nicotine+ plugin after an update.
- Quotes around a title (`'You & Me'`) no longer end up in file names.
- The activity list says when the connection comes back by itself.
- Update notice when a new version is on GitHub (can be turned off in Settings).

## 0.2.0

- Connect through Nicotine+ with the bundled bridge plugin, or log in to Soulseek directly.
