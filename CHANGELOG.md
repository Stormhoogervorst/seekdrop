# Changelog

## 0.6.4

A stability release: the whole app was read through for weak spots. No new features and nothing works
differently; these are things that could go wrong and now don't.

- Fixed: **when SeekSync couldn't start, it just closed** (on Windows nobody could see why). It now shows a
  window with the reason and where the log file is. New in Settings, under Updates: **Show log file**, to send
  along with a question.
- Fixed: the track list showed only the newest 400 tracks, and the **numbers on the filters** counted only those.
  The numbers now count everything, and each filter shows its own newest 400 (so an old *Not found yet* track
  is no longer out of sight). When there are more, the list says so.
- Fixed: **uploads were missed after the app was off for a long time.** A check looks at a profile's newest 25
  uploads; when more had come out, the rest was never seen. When none of those 25 is known, SeekSync now looks
  200 uploads back.
- Fixed: ***Search now* on a track that had stopped** stopped again after one try, because the 30 days counted
  from when the track first came in. They now count from your click, and the waits start at 1 hour again.
- Fixed: a search that couldn't happen (connection gone) counted as a try, so the wait before the next one grew.
- Fixed: looking for a **better copy** ignored your own search term and the artist's other names.
- Changed: SeekSync waits **15 minutes instead of 45** in a busy peer's queue when another peer is still left to
  try (45 for the last one), and a long queue no longer counts towards blocking that peer for 30 days. A
  download that stalls still does.
- Changed: files in **quarantine** that nobody approved or deleted are deleted after 30 days, like the trash. The
  block stays, so that file from that peer is still never tried again.
- Fixed: with the built-in login and a big shared folder, every start after a crash or a forced quit read all
  shared files again. The index of shared files is now saved after each scan.
- Changed: on **Windows the Soulseek password and the Nicotine+ key** are now stored encrypted (Windows Data
  Protection: only your Windows account on this computer can read them). On macOS the settings file was already
  readable only by you. If you copy your settings to another PC, enter the password there once.
- Fixed: **Windows users who came from SeekDrop and started with an empty SeekSync** (0.6.0 to 0.6.3) get their
  channels and settings back on the first start of 0.6.4, as long as SeekSync still has no channels. What
  SeekSync had made meanwhile is kept in a folder `before-takeover-…` next to it.
- Changed: ***Why not?* is easier to find.** For a track that wasn't found, the reason in the list ("3 results,
  none matched…") is now itself a button with a small arrow, and *Why not?* is a filled button at the front of
  the row instead of grey text between the others. Both open the same panel as before.
- Fixed: **the app stopped responding, mostly on Windows.** Not reproduced on a Windows PC, but these causes
  were found in the code and are gone:
  - With the built-in Soulseek login, every start reads all the folders you share, one small job per file. Those
    jobs went into the same queue as SeekSync's own file work (since 0.6.3: moving, checking and tagging a
    download, and writing a running download to disk). With a big music folder that queue held thousands of jobs
    and everything else waited behind them: downloads stood still and buttons did nothing. The shared folders are
    now read on threads of their own.
  - The screen asks the app for its state every 2 seconds, and answering looked at your music drive and read the
    database on the thread that also runs the Soulseek connection. A drive that was asleep, a network share that
    was away or a disk busy copying a download made everything wait. The state is now put together on its own
    threads, and the disk space check no longer runs on the main thread either.
  - On a computer with few processor cores, a library scan plus a few file checks could use up all worker
    threads, so a running download couldn't be written. There are more of them now.
  - The database forced every small change to disk at once (a download's progress is one every 2 seconds), which
    is slow on Windows. It now does that the usual, still safe way.
- Fixed: **the window only opened after Soulseek had logged in**, and when that took more than 30 seconds the
  app closed again without a word. The window now opens at once and shows "Connecting".
- Fixed: **a track you skipped could be searched anyway** when you pressed Skip while another track was being
  searched. The same for a track whose channel you had just removed.
- Fixed: pressing **Skip at the moment a download finished** marked the track as skipped although the file was
  already in your music folder.
- Fixed: **saving Settings failed** ("Request failed (500)") when a number box was empty. An empty or invalid
  number now keeps the old value. Ports and margins that can't work are brought back into range.
- Fixed: a **settings file with a wrong kind of value** in it (edited by hand, or from an older version) could
  make the app misbehave later. Such a field now falls back to its default, the rest is kept. A settings file that
  can't be read at all is kept as `settings.json.unreadable` instead of being silently overwritten.
- Fixed: **the app didn't start** when a folder in your music folder couldn't be read (for example when macOS
  hadn't given permission yet), or when the database file was damaged. A damaged database is set aside under
  another name (never deleted) and the app starts with a new one.
- Fixed: on **Windows, your channels and settings from SeekDrop were not taken over** on the first start as
  SeekSync, because the log folder was made first and the app then thought it already had data. If this happened
  to you, your old data is still in `%LOCALAPPDATA%\SeekDrop`.
- Fixed: a **music folder that couldn't be read for a moment** (a network share that dropped, a missing
  permission) counted as "the files are gone", after which tracks you already have were wanted again.
- Fixed: **downloads into nothing** while the drive with your music folder is not connected. Downloads now wait
  ("Downloads paused") until the folder is back, instead of downloading, failing to save and trying again later.
- Fixed: when **replacing a file with a better copy** (or *Approve anyway* for a track you already have) failed
  half-way, for example on a full disk, the old file stayed in SeekSync's trash. It is now put back.
- Fixed: **good files could go to quarantine** when ffmpeg had been removed or moved while the app was running, or
  when the spectrum measurement itself failed. A check that can't run is not a bad file.
- Fixed: one **Soulseek peer that couldn't be asked** for a file ended the whole attempt; the next candidate is
  now tried. One search result with odd data could make a whole search fail.
- Fixed: after **switching between the built-in login and Nicotine+**, downloads that were still running could
  make the screen stop updating for a while. They are now stopped properly before the switch.
- Fixed: background jobs (the connection check, reconnecting, a scan or check started from the screen) could
  **stop without a trace** after an unexpected error. They now keep running, and the error is in the log.
- Fixed: a file chosen as your **Rekordbox export** that isn't one counted as "nothing is in Rekordbox", so with
  *Replace by itself, unless it is in Rekordbox* files could be replaced without asking. Now SeekSync asks.
  Exports with track numbers that aren't plain numbers are read too.
- Fixed: reading a big Rekordbox export, and looking into shared folders, no longer hold up the screen.
- Fixed: the screen showed nothing useful when the app ran into an unexpected error; it now shows what went wrong.
  Small things: *Remove playlist* kept its label, *Check now* and the folder button show an error instead of
  doing nothing, and a channel removed in another window no longer leaves an empty list.

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
