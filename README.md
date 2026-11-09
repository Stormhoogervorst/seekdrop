# SeekDrop

Follow SoundCloud channels and playlists. When a track shows up, SeekDrop looks for it on
Soulseek and downloads the best copy it can find.

For DJs and producers who don't want to check twenty label pages every day.

🇳🇱 Nederlandse uitleg van alles wat de app doet: [naar beneden](#uitleg-in-het-nederlands).

- **Channels:** add any public SoundCloud profile (a label, artist, promo or repost channel).
  New uploads are checked every hour (you can change this).
- **Playlists:** paste a playlist link (`soundcloud.com/name/sets/…`, private `…/s-xxxx` links
  work too). Every track in it is searched and downloaded, and tracks added later are fetched too.
- Messy titles are cleaned up: `PREMIERE: Artist - Track (Someone Remix) [FREE DL]` becomes
  artist *Artist*, title *Track*, version *Someone Remix*. Label names and catalog numbers
  (`- Drumcode - DC360`) are dropped.
- Rules per channel or playlist: shortest and longest track (2 to 12 minutes by default), remixes
  on or off, previews and clips, DJ mixes and radio shows, words that exclude or are required, plus a
  blocklist of words and artists for everything. Skipped tracks stay in the list with the rule that
  stopped them, and you can still get one on purpose.
- Versions are told apart: Original and Extended go together, but a radio edit, dub, VIP or someone
  else's remix is never taken for the one you want. Producers with several names can be given aliases.
- Results are scored on title, artist, remix name, length, format, bitrate and how fast the peer
  can send it. Remixes are never accepted when you want the original, and the other way round.
  DJ-pool edits (`(Clean)`, `(Intro)`, `TMU …`) and spam peers that advertise a website are skipped.
- Quality profiles: **Club** (lossless, MP3 320 at least), **Balanced** (MP3 320 or better) or
  **Space saver**. If a track first comes in below your goal (say MP3 320 while you want lossless),
  the app keeps looking for a better copy for 30 days and asks before it replaces your file (cue
  points in Rekordbox or Serato are tied to the file name). Replaced files go to SeekDrop's trash.
- A good Soulseek citizen: searches are spaced out (8 s apart, at most 20 per 5 minutes, you can only
  slow that down), downloads pause when the disk runs low (5 GB by default), peers that were slow,
  failed or sent fake lossless files score lower and are blocked after repeated problems, tracks of
  one playlist are taken from the same user and folder when possible, and the app warns you when
  you share nothing (many users block that).
- Not on Soulseek yet? It tries again after 1 h, 3 h, 6 h, 12 h, then daily, for up to 30 days.
- Rekordbox: turn on "Keep a Rekordbox XML file up to date" in Settings. Every downloaded track becomes a track and
  every channel or playlist a playlist in a folder called SeekDrop; import it through Rekordbox' Preferences, Advanced,
  Database, rekordbox xml. SeekDrop only writes that one file and never touches Rekordbox' own library.
  Point SeekDrop at an export of your Rekordbox collection (File, Export Collection in xml format) and the upgrade
  setting "Replace right away, but ask for tracks that are in Rekordbox" keeps your cue points safe.
- Already have it? Point SeekDrop at your music folders (Settings). A new track that is in there under a
  slightly different name is marked "Already in your collection" and not downloaded again; a Duplicates tab lists
  doubles in the download folder with the best copy marked. SeekDrop only reads your folders.
- Files get tags for DJ software: artist, title with the version in it, genre, year, the SoundCloud link,
  and the SoundCloud artwork (500 px) embedded. MP3 gets ID3v2.3, FLAC Vorbis comments, AIFF ID3. Turn on
  "Convert WAV to AIFF" for lossless files that keep their tags in Rekordbox and Serato. Folders and file
  names follow a template (default `Music/SeekDrop/<channel>/Artist - Title (Version).flac`).

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

## Uitleg in het Nederlands

### Wat is SeekDrop?

SeekDrop volgt SoundCloud-kanalen en -playlists. Komt er een nieuwe track op, dan zoekt de app die op
Soulseek, kiest de beste kopie, controleert het bestand, zet er tags en een hoes in en legt het in je
muziekmap. Optioneel maakt het ook een bestand waarmee je alles in Rekordbox kunt inlezen.
De app downloadt zelf **nooit** audio van SoundCloud: SoundCloud wordt alleen gebruikt om te lezen welke
tracks er zijn (titel, artiest, lengte, hoes). De audio komt van Soulseek.

### Zo loopt een track door de app

1. **Ophalen:** elk uur (instelbaar) kijkt de app welke nieuwe uploads er zijn op je kanalen en playlists.
2. **Titel opschonen:** `PREMIERE: Artist - Track (Someone Remix) [FREE DL]` wordt artiest *Artist*, titel
   *Track*, versie *Someone Remix*. Je kunt artiest, titel en versie per track zelf corrigeren.
3. **Regels:** past de track bij de regels van het kanaal (lengte, remixes, woorden, blokkeerlijst)? Zo niet,
   dan staat hij onder *Skipped* met de reden, en met *Get it* haal je hem toch op.
4. **Heb je hem al?** Staat de track al in je muziekmappen, dan krijgt hij de status *Already in your
   collection* en wordt hij niet gedownload.
5. **Zoeken op Soulseek:** meerdere zoektermen, rustig na elkaar (zie "Netjes op Soulseek").
6. **Kiezen:** elk zoekresultaat krijgt een score op titel, artiest, versie, lengte, formaat, bitrate,
   snelheid, wachtrij en de reputatie van de gebruiker. De beste (maximaal 3) worden geprobeerd.
7. **Downloaden** naar een tijdelijke map (*staging*) in de app-data, nooit direct in je muziekmap.
8. **Controleren** (met ffmpeg, optioneel): speelt het helemaal af, klopt het formaat, de lengte, geen lange
   stilte, en is het geen omgezette MP3 die als lossless wordt verkocht. Afgekeurd gaat naar *Quarantine*.
9. **Taggen:** artiest, titel met versie, genre, jaar, SoundCloud-link en de hoes (500 px) gaan in het bestand.
10. **Publiceren:** het bestand verschijnt in één keer, met de definitieve naam, in je muziekmap. Een
    onderbroken download laat dus nooit een half bestand achter voor Rekordbox of Serato.
11. **Rekordbox-bestand bijwerken** (als je dat aan hebt gezet).

Staat een track nog niet op Soulseek? Dan probeert de app het na 1 uur, 3, 6 en 12 uur, daarna elke dag,
tot 30 dagen (instelbaar).

### Aan de slag

1. Installeer de app (zie *Install* hierboven) en open hem.
2. Accepteer de voorwaarden en kies hoe je met Soulseek verbindt: **via Nicotine+** (aanbevolen als je dat al
   gebruikt) of **met een eigen Soulseek-account**. Gebruik voor een eigen account een apart account, anders
   gooien twee programma's elkaar eruit.
3. Plak links een SoundCloud-profiel of -playlist in het veld *Add a channel or playlist*.
   - Bij een **profiel** kies je hoeveel recente tracks je meteen wilt ("Also get the latest") en of
     reposts meetellen. Daarna komen alleen nieuwe uploads binnen.
   - Bij een **playlist** wordt elke track gezocht, in de volgorde van de playlist, ook tracks die later
     worden toegevoegd.
4. Laat de app openstaan: hij werkt alleen zolang hij draait (en bij Nicotine+ moet Nicotine+ ook open zijn).

### De tabbladen

- **All / In progress / Downloaded:** wat je nodig hebt, wat bezig is en wat klaar is.
- **In collection:** tracks die je al had.
- **Not found yet:** nog niet op Soulseek gevonden. *Why not?* laat zien waarom.
- **Skipped:** overgeslagen door een regel of door jou, met de reden en *Get it*.
- **Quarantine:** bestanden die de controles niet haalden, met de reden. Je kunt ze toch goedkeuren
  (*Approve anyway*) of verwijderen.
- **Duplicates:** dubbele bestanden in je downloadmap, de beste kopie gemarkeerd. SeekDrop verwijdert nooit
  iets zelf.

### Waarom vindt hij mijn track niet? ("Why not?")

Bij elke track zonder download laat *Why not?* de laatste zoekpogingen zien: welke zoektermen, hoeveel
resultaten en de 10 dichtstbijzijnde bestanden met de reden van afwijzing ("192 kbps, onder je ondergrens",
"3:12 lang, verwacht 6:45", "remix van iemand anders"). Je kunt daar:
- **Download this anyway:** dat bestand toch halen (het gaat nog steeds door de controles),
- **Search with another term:** een eigen zoekterm, die voortaan als eerste wordt geprobeerd,
- artiest, titel of versie corrigeren (gaat voor de automatische opschoning),
- **Stop looking.**

### Regels per kanaal

Met de knop **Rules** boven de lijst stel je per kanaal of playlist in wat er binnenkomt:
kortste en langste track (standaard 2 tot 12 minuten), remixes wel of niet (remix, rework, flip, bootleg;
VIP, dub en edit blijven altijd toegestaan), previews en clips overslaan, DJ-mixen, radioshows en podcasts
overslaan, woorden die een track uitsluiten en woorden waarvan er minstens één verplicht is, en reposts.
In **Settings → Blocklist** staat een lijst met woorden en artiesten voor alle kanalen samen; die wint altijd.
Pas je een regel aan, dan worden tracks die nu wel mogen weer opgepakt en nog niet gezochte tracks die niet
meer mogen overgeslagen. Wat al klaar is of door jou is gekozen blijft met rust.

### Kwaliteit en upgrades

Je kiest een profiel: **Club** (lossless; MP3 320 is het minimum), **Balanced** (MP3 320 of beter) of
**Space saver**. Komt een track binnen onder het doel (bijvoorbeeld MP3 320 terwijl je lossless wilt), dan
zoekt de app elke dag verder naar een betere kopie (tot 30 dagen). Wat een bestand echt is, wordt gemeten
en niet geloofd: een omgezette MP3 als "FLAC" telt als MP3.

Wat er met een betere kopie gebeurt, stel je in:
- **Ask me first** (standaard): je krijgt *Replace* of *Keep*.
- **Replace right away:** direct vervangen; het oude bestand gaat 30 dagen naar de prullenbak van de app.
- **Replace right away, but ask for tracks that are in Rekordbox:** zie "Rekordbox" hieronder.
- **Don't look for better copies.**

Let op: van .mp3 naar .flac veranderen betekent een andere bestandsnaam. Rekordbox en Serato koppelen
cue points aan het pad, dus die raak je dan kwijt.

### Bestandscontrole en quarantaine

Met [ffmpeg](https://ffmpeg.org) geïnstalleerd (Mac: `brew install ffmpeg`) wordt elk bestand gecontroleerd
voordat het in je muziekmap komt. Een afgekeurd bestand gaat naar quarantaine, die combinatie van gebruiker en
bestand wordt voor deze track geblokkeerd en de app probeert de volgende kandidaat. Per track zie je waar de
audio ophoudt (bijvoorbeeld "Full range" of "Suspect: stops at 20.3 kHz"). Zonder ffmpeg werkt de app nog, maar
worden de controles overgeslagen (Settings laat dat zien).

### Tags, hoezen en bestandsnamen

Elk bestand krijgt: artiest, titel met de versie erin (`Track (Extended Mix)`), genre, jaar, de SoundCloud-link
als commentaar en de hoes van SoundCloud (minimaal 500 bij 500 pixels, een grotere hoes die al in het bestand
zit blijft). MP3 krijgt ID3v2.3, FLAC Vorbis-comments, AIFF ID3, M4A MP4-tags. BPM en toonsoort die de uploader
zelf inbedde blijven staan; de app rekent die niet zelf uit. Label en album geeft SoundCloud niet; het label
kan optioneel de kanaalnaam worden.

- **Convert WAV to AIFF:** (standaard uit) zet WAV om naar AIFF met precies dezelfde audio, omdat DJ-software
  tags in AIFF beter leest dan in WAV.
- **Folder and file name:** een sjabloon met `{channel}`, `{artist}`, `{title}`, `{version}`, `{year}` en
  `{genre}`, standaard `{channel}/{artist} - {title} ({version})`. Settings laat een voorbeeld zien. Lege
  haakjes en streepjes verdwijnen als een veld ontbreekt.

Staan de tags je niet aan? Zet *Write tags and cover art* uit in Settings.

### Wat heb je al? (je eigen muziekmappen)

Zet bij **Settings → Music folders you already have** de mappen waar je muziek staat. De downloadmap van
SeekDrop telt altijd mee. De app leest die mappen (alleen lezen, hij wijzigt of verwijdert niets) en onthoudt
wat erin staat. De eerste keer worden alle bestanden gelezen, daarna alleen nieuwe of gewijzigde. Een nieuwe
track die er al in staat (ook onder een iets andere naam, of via een ander kanaal) wordt niet gedownload.
Een versie telt apart: een remix van iemand anders of een radio edit is niet de originele track.
Verdwijnt het bestand later uit je map, dan wordt de track weer gezocht. Met *Get it anyway* haal je hem
toch op.

### Rekordbox

Zet in **Settings → Rekordbox** het vinkje *Keep a Rekordbox XML file ... up to date* aan.
SeekDrop schrijft dan één bestand (standaard `SeekDrop for Rekordbox.xml` in je downloadmap) met elke
gedownloade track en een playlist per kanaal of playlist, in een map "SeekDrop". Het wordt een halve minuut na
elke download, upgrade of verwijderd kanaal bijgewerkt.

Inlezen in Rekordbox: **Voorkeuren → Geavanceerd → Database → rekordbox xml** en kies dit bestand. Open daarna
**rekordbox xml** in de boomstructuur, klik met rechts op een playlist en kies **Import Playlist**.
SeekDrop schrijft alleen dit ene bestand en komt nooit aan de database van Rekordbox.

Wil je dat een betere kopie geen cue points kost? Maak in Rekordbox een export van je collectie
(**File → Export Collection in xml format**), kies dat bestand bij *Your Rekordbox collection export* en kies
bij de upgrades *Replace right away, but ask for tracks that are in Rekordbox*. Tracks die in de export staan
worden dan nooit vanzelf vervangen; de rest wel. Is er geen export of is hij onleesbaar, dan vraagt de app
altijd eerst. Exporteer af en toe opnieuw.

### Netjes op Soulseek

Soulseek wordt door vrijwilligers gedragen. De app is daarom rustig:
- **Zoeken wordt afgeremd:** minstens 8 seconden tussen zoekopdrachten en hoogstens 20 per 5 minuten. Je kunt
  dat alleen trager zetten (minimaal 4 seconden), niet uitzetten.
- **Schijfruimte:** onder 5 GB vrij starten er geen nieuwe downloads (instelbaar). De app meldt het en gaat
  vanzelf weer door.
- **Reputatie:** de app onthoudt per gebruiker wie snel en betrouwbaar was, wie downloads liet mislukken en
  wie nep-lossless leverde. Dat telt mee in de score; na 3 keer nep, of 5 keer mislukken zonder één succes,
  wordt een gebruiker 30 dagen geblokkeerd. In Settings kun je dat opheffen (*Unblock*).
- **EP of playlist bij elkaar:** een bestand uit dezelfde map van dezelfde gebruiker als eerdere tracks uit die
  playlist krijgt een voorkeur, zodat de bestanden bij elkaar passen.
- **Deel je iets?** De app waarschuwt als je niets deelt: veel gebruikers blokkeren wie niets deelt.
  Met een eigen account deelt de downloadmap standaard mee; bij Nicotine+ stel je dat daar in.

### Waar staat wat?

- **Je muziek:** de downloadmap (standaard in je Muziek-map: `SeekDrop/<kanaal>/Artiest - Titel (Versie).ext`).
- **Instellingen, database, logs en tijdelijke mappen** (`staging`, `quarantine`, `trash`, `upgrades`):
  `~/Library/Application Support/SeekDrop` (macOS) of `%LOCALAPPDATA%\SeekDrop` (Windows).
- Alles blijft op je computer. De app praat met SoundCloud (lezen), met Soulseek (direct of via Nicotine+) en
  twee keer per dag met GitHub om te zien of er een nieuwe versie is (uit te zetten).

### Wat de app nog niet kan

- Serato-crates, M3U-playlists en Traktor; alleen Rekordbox is gekoppeld.
- Een extra controle met AcoustID, meldingen (Telegram, Discord), automatische back-ups, en andere bronnen
  dan SoundCloud (Spotify, Beatport, bestanden). Zie `ROADMAP.md` voor wat er gepland is.
- Wat nog niet in de praktijk is bewezen (zie `ROADMAP.md` en `CLAUDE.md`): de eigen Soulseek-login
  (zonder Nicotine+) en het inlezen van het bestand in Rekordbox zelf.

### Verantwoord gebruik

Soulseek is een netwerk waar mensen hun eigen muziekmappen delen. Download alleen muziek die je mag hebben,
zoals gratis downloads, promo's die naar jou zijn gestuurd of tracks die je elders hebt gekocht. Jij bent
verantwoordelijk voor wat je downloadt en deelt.

## License

GPL-3.0-or-later (required because it builds on aioslsk). The bundled Inter Tight font is under the
SIL Open Font License; the icons are from Lucide (ISC License). The visual style follows `DESIGN.md`.
