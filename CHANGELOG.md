# Changelog

## 0.6.3

A stability release for Windows. I couldn't try these on a Windows PC myself, so this version also keeps a
better log: if something still freezes, the log shows where (see below).

- New: **Install and restart now works on Windows too** (Settings, Updates). SeekSync downloads the installer
  of the new version, checks its size and checksum, closes itself, runs the installer quietly over the old
  version (no administrator rights needed) and starts again. Your channels and settings are kept. When SeekSync
  can't change its own folder (for example when it was installed for all users), it says so and the release
  page is still the way. This is the first version that can do this, so to get to 0.6.3 from an older version,
  download the installer from the release page once, like before. If the update doesn't work for you, the log
  (`%LOCALAPPDATA%\SeekSync\Logs\seeksync.log`) and `setup.log` in `%LOCALAPPDATA%\SeekSync\update` say what
  happened.
- Fixed: **freezes while a download comes in.** Moving a finished file into your music folder, putting it in
  quarantine and replacing a file with a better copy all happened on the thread that also runs the screen and the
  Soulseek connection. When the antivirus scanner or a slow disk took a few seconds, everything stood still. These
  steps now run in the background.
- Fixed: **"access denied" and "used by another process"** while a file was moved or saved (the antivirus scanner
  often still holds a file for a second). SeekSync now waits and tries again, up to about 8 seconds, for files,
  the settings file, the Rekordbox file and tags. Before, the download counted as failed.
- Fixed: **black windows flashing** during file checks, and checks that could hang. ffmpeg and ffprobe now run
  without a console window and without waiting for keyboard input.
- Fixed: **SeekSync kept running after you closed it** (and then said "already running" at the next start) when
  a check or a connection was still busy. If quitting takes more than 12 seconds, the app now ends itself.
- Fixed: on a Windows PC without the Microsoft Edge WebView2 runtime the screen was drawn by an old Internet
  Explorer engine and half of it didn't work. SeekSync now opens its screen in your browser in that case.
- Fixed: *Show file* opened Documents instead of the file in Explorer.
- Fixed: very long titles in a deep folder could make the file name too long for Windows (260 characters), and
  names like `CON` or `NUL` can't be created there. Names are now shortened or changed when needed.
- ffmpeg is now also found when it was installed with winget, Scoop or Chocolatey.
- The screen no longer says "SeekSync stopped" after one missed answer, only after a few in a row, and a
  request that never gets an answer is given up after 30 seconds.
- For problems: the log is `seeksync.log` in `%LOCALAPPDATA%\SeekSync\Logs`. It now notes when the app stops
  answering for more than 10 seconds, with what every part was doing, and uncaught errors and crashes
  (`crash.log`) are written there too.

## 0.6.2

- Fixed: on Windows many good downloads went to quarantine as "Damaged file". Two causes, neither about the audio:
  a broken or odd cover picture inside the file ("Could not find codec parameters for stream 1 (Video: mjpeg…)"),
  and an ffmpeg that can't set up the silence check ("Error initializing a simple filtergraph"). Problems with the
  cover art are now ignored (the tags step puts the SoundCloud artwork in anyway), and when your ffmpeg can't run
  the silence check, that one check is skipped and Settings says so; the other checks still run.
  Files already in quarantine for these reasons can be let through with *Approve anyway*.
- Covers: tracks from a Spotify playlist now get the album cover (640 px) and the year, read from each track's own
  Spotify page. A track without an artwork link (its details failed when it was added) or with a link that no
  longer works is looked up again when its file comes in, and a failed cover download is tried once more.
- New in Settings, Names and tags: **Fill in missing covers**. Every downloaded file without a cover (or with a
  broken one) gets one; only the picture is added. Useful for files from 0.6.0 and earlier, whose covers couldn't
  be downloaded in the packaged app.

## 0.6.1

- Fixed: in the downloaded app, *Check now* said "Can't reach GitHub" although the internet worked. The app didn't
  trust any HTTPS certificates on other computers than the one it was built on. That also stopped Spotify playlists
  and the artwork in the tags from working. The app now carries its own certificates.
- Because of this, the update button of version 0.6.0 can't find 0.6.1: download this version yourself once.

## 0.6.0

- The app is now called **SeekSync** (it was SeekDrop). Your settings, channels and history are taken over from the
  old data folder on the first start. If you use Nicotine+, the SeekSync Bridge plugin takes over the key of the old
  SeekDrop Bridge: in Nicotine+ (Preferences, Plugins) turn **SeekDrop Bridge** off and **SeekSync Bridge** on, once.
- Download the first SeekSync version yourself: the update button of an older SeekDrop can't install it, because
  the app has another name. After that, updating from inside the app works again.
- The Rekordbox file is now called `SeekSync for Rekordbox.xml` and its folder in Rekordbox is `SeekSync`.
  Import it once; the old SeekDrop folder in Rekordbox can be removed.
- The GitHub repository is now `Stormhoogervorst/seeksync` (old links keep working). The environment variable
  `SEEKDROP_HOME` is now `SEEKSYNC_HOME`.

## 0.5.1

- Settings, Updates: a *Check now* button that looks on GitHub straight away. In the Mac app, *Install and
  restart* downloads the new version, checks it, replaces the app and starts it again; the old app is kept in
  `previous-versions` (last two). Windows and the source version still open the release page.

## 0.5.0

- Spotify playlists: paste the link of a public Spotify playlist and SeekDrop searches its tracks on Soulseek,
  like a SoundCloud playlist. Spotify only shows the first 100 tracks of a playlist, and private playlists can't be read.

## 0.4.1

- Fixed: the music folders you add under "Your music collection" were saved as single letters, so nothing was
  found. They are now saved as folders, and a list broken that way is cleared when SeekDrop starts (add the
  folders again).
- Fixed: the built app stopped with "No module named 'anyascii._data'" when it compared titles (a scan, or
  checking a new track). The data is now part of the app.
- Music folders have their own section in Settings, with an *Add folder…* button.

## 0.4.0

- Rekordbox: an optional XML file (Settings) with every downloaded track and a playlist per channel or
  playlist, kept up to date after each download, upgrade or removal. Import it in Rekordbox through
  Preferences, Advanced, Database, rekordbox xml. SeekDrop never touches Rekordbox' own library.
  New upgrade setting: replace better copies right away, but ask first for tracks that are in Rekordbox
  (choose an export of your Rekordbox collection in Settings, it is only read), so cue points stay safe.
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
