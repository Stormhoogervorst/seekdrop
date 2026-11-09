# Changelog

## 0.4.0

- Knows what you already have: add your music folders in Settings and a new track that is already there
  (also under a slightly different name or from another channel) is marked "Already in your collection"
  instead of being downloaded again. The first scan reads every file, later scans only what changed.
  A *Duplicates* tab lists doubles in the download folder with the best copy marked; nothing is deleted.
- Tags and artwork: every finished file gets artist, title with version, genre, year, the SoundCloud
  link and the SoundCloud cover (500 px) written in (MP3 ID3v2.3, FLAC, AIFF, M4A). BPM and key tags the
  uploader embedded stay. Optional: convert WAV to AIFF (same audio, tags that DJ software reads), and use the
  channel name as the label. Folder and file names now follow a template with a live example in Settings
  (the "folder per channel" checkbox became the default template). Turn tagging off in Settings if you prefer.
- Rules per channel and playlist (button *Rules* above the list): shortest and longest track (2 to 12
  minutes by default, was a fixed 10), remixes on or off, skip previews and clips, skip mixes and
  radio shows, words that exclude a track or are required, and reposts. A blocklist of words and
  artists in Settings applies everywhere. Skipped tracks show which rule stopped them and can still
  be fetched with *Get it*; changing a rule re-checks the tracks that were skipped.
- Politer on Soulseek: searches wait at least 4 s (8 s by default) and stay under 20 per 5 minutes;
  downloads pause when free disk space drops under a limit (5 GB) and continue by themselves;
  peers that failed, went quiet or delivered fake files are scored lower, and blocked for 30 days
  after repeated problems (Settings shows them, with Unblock); an EP or playlist is taken from the
  same user and folder when possible; a warning appears when you share nothing. With Nicotine+,
  the app updates the plugin; turn *SeekDrop Bridge* off and on once in Nicotine+ for the sharing check.
- Smarter matching: versions are compared properly (a VIP is not a Vocal mix, a radio edit or dub
  is never taken for the original), titles in other scripts are found, artist aliases (Settings),
  and you can correct a track's artist, title or version yourself.
- "Why not?": every track that didn't come in says why, and shows the closest files with the
  reason each was turned down. Download one of them anyway (still checked), search with your own
  term (kept for later attempts), or stop looking.
- Quality profiles (Club, Balanced, Space saver) replace the format and bitrate settings, with
  automatic upgrades: a track that came in below your goal is replaced by a better copy when one
  turns up (asks first by default). The old file goes to SeekDrop's trash for 30 days.
- Fake lossless detection: MP3s converted to FLAC/WAV and fake 320 kbps MP3s are recognised by
  their spectrum. Fakes go to Quarantine; suspect files are kept with a label (or rejected, your choice).
  Every track shows where its audio stops.
- File checks with ffmpeg (optional): damaged, cut-off, wrong-format, wrong-length and silent files
  go to Quarantine with a reason instead of your music folder. Approve or delete them there.
- Downloads wait in a staging folder and appear in your music folder in one go.
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
