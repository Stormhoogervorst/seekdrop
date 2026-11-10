"""Builds site/guide.html (English) and site/guide.js (the Dutch text) from one list of content blocks, so the two
languages sit next to each other and can't drift apart. Run:  python scripts/build_guide.py
The generated files are committed; Vercel serves them as they are (no build step on the server)."""
from __future__ import annotations

import html
import json
import struct
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
GITHUB = "https://github.com/Stormhoogervorst/seeksync"

_n = 0
NL: dict[str, str] = {}


def key(en: str, nl: str) -> str:
    """A translation key for a piece of text; the Dutch goes into the dictionary."""
    global _n
    _n += 1
    k = f"g{_n}"
    NL[k] = nl
    return k


def t(en: str, nl: str, tag: str = "span", cls: str = "", attrs: str = "") -> str:
    k = key(en, nl)
    c = f' class="{cls}"' if cls else ""
    return f'<{tag}{c} data-i18n="{k}"{attrs}>{en}</{tag}>'


def P(en, nl, cls=""):
    return t(en, nl, "p", cls)


def UL(items, cls=""):
    c = f' class="{cls}"' if cls else ""
    return f"<ul{c}>" + "".join(t(e, n, "li") for e, n in items) + "</ul>"


def OL(items, cls=""):
    c = f' class="{cls}"' if cls else ""
    return f"<ol{c}>" + "".join(t(e, n, "li") for e, n in items) + "</ol>"


def H3(en, nl, id=""):
    i = f' id="{id}"' if id else ""
    return t(en, nl, "h3", "", i)


def NOTE(kind, en, nl):
    label = {"tip": ("Tip", "Tip"), "warn": ("Good to know", "Goed om te weten")}[kind]
    return (f'<aside class="note {kind}"><strong>{t(*label)}</strong>' + t(en, nl, "p") + "</aside>")


def _png_size(path: Path) -> tuple[int, int]:
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def FIG(name, alt_en, alt_nl, cap_en, cap_nl, narrow=False):
    path = SITE / "img" / name
    w, h = _png_size(path)
    ka = key(alt_en, alt_nl)
    cls = "fig narrow" if narrow else "fig"
    return (f'<figure class="{cls}"><img src="img/{name}" width="{w // 2 if w > 1500 or narrow else w // 2}" height="{h // 2}" '
            f'loading="lazy" alt="{html.escape(alt_en, quote=True)}" data-i18n-alt="{ka}">'
            + t(cap_en, cap_nl, "figcaption") + "</figure>")


def TABLE(head, rows):
    out = '<div class="tablewrap"><table class="t"><thead><tr>' + "".join(t(e, n, "th") for e, n in head) + "</tr></thead><tbody>"
    for r in rows:
        out += "<tr>" + "".join(t(e, n, "td") for e, n in r) + "</tr>"
    return out + "</tbody></table></div>"


def DL(items):
    out = '<dl class="fields">'
    for te, tn, de, dn in items:
        out += t(te, tn, "dt") + t(de, dn, "dd")
    return out + "</dl>"


SECTIONS: list[tuple[str, str, str, list[str]]] = []


def sec(id, en, nl, *blocks):
    SECTIONS.append((id, en, nl, list(blocks)))


# ======================================================================================================
sec("need", "What you need", "Wat je nodig hebt",
    UL([
        ("<strong>A Mac or a Windows PC.</strong> Mac: macOS 11 or newer on Apple Silicon (M1 and later). Windows: 10 or 11.",
         "<strong>Een Mac of een Windows-pc.</strong> Mac: macOS 11 of nieuwer met Apple Silicon (M1 en later). Windows: 10 of 11."),
        ("<strong>A way into Soulseek.</strong> Either Nicotine+ (if you already use it) or a free Soulseek account that SeekSync logs in with by itself. You don't need the Soulseek app.",
         "<strong>Een weg naar Soulseek.</strong> Of Nicotine+ (als je dat al gebruikt), of een gratis Soulseek-account waarmee SeekSync zelf inlogt. Je hebt de Soulseek-app niet nodig."),
        ("<strong>Free disk space.</strong> SeekSync pauses downloads when less than 5 GB is free (you can change that).",
         "<strong>Vrije schijfruimte.</strong> SeekSync pauzeert downloads als er minder dan 5 GB vrij is (dat kun je aanpassen)."),
        ("<strong>Optional: ffmpeg.</strong> It switches on the file checks. On a Mac: <code>brew install ffmpeg</code>. Without it, files are not checked.",
         "<strong>Optioneel: ffmpeg.</strong> Daarmee gaan de bestandscontroles aan. Op een Mac: <code>brew install ffmpeg</code>. Zonder ffmpeg worden bestanden niet gecontroleerd."),
    ]),
    NOTE("warn",
         "SeekSync only <em>reads</em> SoundCloud and Spotify: titles, artists, lengths and artwork. It never downloads audio from them. The audio comes from Soulseek, where people share their own music folders. Only download music you have the right to have, such as free downloads, promos sent to you, or tracks you bought elsewhere. You are responsible for what you download and share.",
         "SeekSync <em>leest</em> SoundCloud en Spotify alleen: titels, artiesten, lengtes en hoezen. Het downloadt er nooit audio van. De audio komt van Soulseek, waar mensen hun eigen muziekmappen delen. Download alleen muziek waarvan je het recht hebt die te hebben, zoals gratis downloads, promo's die naar jou zijn gestuurd, of tracks die je elders kocht. Jij bent verantwoordelijk voor wat je downloadt en deelt."))

sec("install", "Install", "Installeren",
    H3("On a Mac", "Op een Mac"),
    OL([
        (f'Download the <code>.dmg</code> from the <a href="index.html#download" data-keep-lang>download section</a> or the <a href="{GITHUB}/releases/latest">Releases page</a>.',
         f'Download de <code>.dmg</code> in het <a href="index.html#download" data-keep-lang>downloadgedeelte</a> of op de <a href="{GITHUB}/releases/latest">Releases-pagina</a>.'),
        ("Open the <code>.dmg</code> and drag <strong>SeekSync</strong> to Applications.",
         "Open de <code>.dmg</code> en sleep <strong>SeekSync</strong> naar Programma's."),
        ("Open SeekSync. If macOS says it can't check the app for malicious software, open <strong>System Settings, Privacy &amp; Security</strong>, scroll down and click <strong>Open Anyway</strong> next to SeekSync. You only need to do this once.",
         "Open SeekSync. Zegt macOS dat het de app niet kan controleren op schadelijke software, open dan <strong>Systeeminstellingen, Privacy en beveiliging</strong>, scrol omlaag en klik op <strong>Open toch</strong> (Open Anyway) bij SeekSync. Dat hoef je maar één keer te doen."),
    ]),
    H3("On Windows", "Op Windows"),
    OL([
        ("Download the installer (<code>SeekSync-x.y.z-windows-setup.exe</code>) and run it.",
         "Download het installatieprogramma (<code>SeekSync-x.y.z-windows-setup.exe</code>) en start het."),
        ("Windows may show a SmartScreen warning. Click <strong>More info</strong>, then <strong>Run anyway</strong>.",
         "Windows kan een SmartScreen-waarschuwing tonen. Klik op <strong>Meer informatie</strong> en dan op <strong>Toch uitvoeren</strong>."),
        ("Choose whether to add a desktop shortcut and whether SeekSync should start when you log in.",
         "Kies of je een snelkoppeling op het bureaublad wilt en of SeekSync moet starten als je inlogt."),
    ]),
    NOTE("tip",
         "The warnings appear because the app isn't signed with a paid developer certificate yet. The code is open source, and you can read it on GitHub.",
         "De waarschuwingen komen doordat de app nog niet is ondertekend met een betaald ontwikkelaarscertificaat. De code is open source en je kunt hem lezen op GitHub."))

sec("first", "First start", "De eerste keer starten",
    P("The first time you open SeekSync you see one screen with three steps. When you are done, click <strong>Start watching</strong>.",
      "De eerste keer dat je SeekSync opent, zie je één scherm met drie stappen. Als je klaar bent, klik je op <strong>Start watching</strong>."),
    FIG("guide/setup.png", "The SeekSync first-run screen with three steps: before you start, connect to Soulseek, and where tracks go.",
        "Het startscherm van SeekSync met drie stappen: voordat je begint, verbinden met Soulseek en waar tracks naartoe gaan.",
        "The first-run screen.", "Het startscherm.", narrow=True),
    OL([
        ("<strong>Before you start.</strong> Tick the box to say you understand that you decide what you download and share.",
         "<strong>Before you start.</strong> Vink het vakje aan om te bevestigen dat je begrijpt dat jij bepaalt wat je downloadt en deelt."),
        ("<strong>Connect to Soulseek.</strong> Choose <em>Through Nicotine+</em> or <em>With its own Soulseek account</em>. Both are explained in the next section.",
         "<strong>Connect to Soulseek.</strong> Kies <em>Through Nicotine+</em> of <em>With its own Soulseek account</em>. Beide staan uitgelegd in het volgende onderdeel."),
        ("<strong>Where tracks go.</strong> Pick the download folder (by default a folder called SeekSync in your Music folder). The box <em>Share this folder on Soulseek</em> is on by default: many people on Soulseek only let you download if you share something too. Sharing means others can download the files in that folder from you. Untick it if you don't want that.",
         "<strong>Where tracks go.</strong> Kies de downloadmap (standaard een map SeekSync in je Muziekmap). Het vakje <em>Share this folder on Soulseek</em> staat standaard aan: veel mensen op Soulseek laten je alleen downloaden als je zelf ook iets deelt. Delen betekent dat anderen de bestanden in die map bij jou kunnen downloaden. Haal het vinkje weg als je dat niet wilt."),
    ]))

sec("connect", "Connect to Soulseek", "Verbinden met Soulseek",
    P("You can change this at any time under <strong>Settings, Soulseek, Connect</strong>.",
      "Je kunt dit altijd aanpassen onder <strong>Settings, Soulseek, Connect</strong>."),
    H3("Option A: through Nicotine+", "Optie A: via Nicotine+"),
    P("Best if you already use Nicotine+: SeekSync uses your account and your shared folders. This is also the most thoroughly tested route.",
      "Het beste als je Nicotine+ al gebruikt: SeekSync gebruikt dan je account en je gedeelde mappen. Dit is ook de best geteste route."),
    FIG("guide/s-soulseek-nicotine.png", "Settings, Soulseek section, with Through Nicotine+ selected and the button Add plugin to Nicotine+.",
        "Instellingen, onderdeel Soulseek, met Through Nicotine+ gekozen en de knop Add plugin to Nicotine+.",
        "Settings, Soulseek: Through Nicotine+.", "Settings, Soulseek: Through Nicotine+.", narrow=True),
    OL([
        ("Install Nicotine+ and log in to Soulseek there.", "Installeer Nicotine+ en log daar in bij Soulseek."),
        ("In SeekSync click <strong>Add plugin to Nicotine+</strong>. This copies a small plugin into Nicotine+. It only listens on your own computer and only accepts SeekSync's key.",
         "Klik in SeekSync op <strong>Add plugin to Nicotine+</strong>. Zo komt er een kleine plugin in Nicotine+. Die luistert alleen op je eigen computer en accepteert alleen de sleutel van SeekSync."),
        ("In Nicotine+ open <strong>Preferences, Plugins</strong> and switch on <strong>SeekSync Bridge</strong>. If it isn't in the list, close Preferences and open it again, or restart Nicotine+.",
         "Open in Nicotine+ <strong>Preferences, Plugins</strong> en zet <strong>SeekSync Bridge</strong> aan. Staat hij niet in de lijst, sluit dan Preferences en open het opnieuw, of start Nicotine+ opnieuw."),
        ("Keep Nicotine+ open while SeekSync works. Searches don't create tabs or history in Nicotine+, and downloads show up in its Downloads tab.",
         "Laat Nicotine+ open staan zolang SeekSync werkt. Zoekopdrachten maken geen tabs of geschiedenis aan in Nicotine+, en downloads staan in het tabblad Downloads."),
    ]),
    NOTE("warn",
         "After an update SeekSync may tell you the plugin was updated. Then turn SeekSync Bridge off and on once in Nicotine+. Sharing is set up in Nicotine+, not in SeekSync.",
         "Na een update kan SeekSync melden dat de plugin is bijgewerkt. Zet dan SeekSync Bridge in Nicotine+ één keer uit en weer aan. Delen stel je in Nicotine+ in, niet in SeekSync."),
    H3("Option B: with its own account", "Optie B: met een eigen account"),
    FIG("guide/s-soulseek-builtin.png", "Settings, Soulseek section, with With its own Soulseek account selected: username, password and listening port.",
        "Instellingen, onderdeel Soulseek, met With its own Soulseek account gekozen: gebruikersnaam, wachtwoord en luisterpoort.",
        "Settings, Soulseek: its own account.", "Settings, Soulseek: eigen account.", narrow=True),
    DL([
        ("Username and password", "Username en Password",
         "Use a separate account just for SeekSync. A name that doesn't exist yet is created automatically the first time you log in. If you log in with the same account in another Soulseek app, one of the two gets disconnected. The password field shows <em>Unchanged</em> when one is saved.",
         "Gebruik een apart account alleen voor SeekSync. Een naam die nog niet bestaat, wordt automatisch aangemaakt de eerste keer dat je inlogt. Log je met hetzelfde account in een andere Soulseek-app in, dan wordt één van de twee losgekoppeld. In het wachtwoordveld staat <em>Unchanged</em> als er al een is opgeslagen."),
        ("Listening port", "Listening port",
         "The port other users connect to for transfers (default 60000). Leave it as it is unless something else uses it. Where your router allows it, SeekSync opens the port by itself.",
         "De poort waarmee anderen voor overdrachten verbinden (standaard 60000). Laat hem zo staan, tenzij iets anders hem gebruikt. Waar je router het toestaat, opent SeekSync de poort zelf."),
    ]))

sec("add", "Add channels and playlists", "Kanalen en playlists toevoegen",
    P("Paste a link into the field at the top left, under <em>Add a channel or playlist</em>. SeekSync understands:",
      "Plak een link in het veld linksboven, onder <em>Add a channel or playlist</em>. SeekSync begrijpt:"),
    UL([
        ("<strong>A SoundCloud profile</strong>: a label, an artist, a promo or repost channel. Paste <code>soundcloud.com/name</code> or just the name.",
         "<strong>Een SoundCloud-profiel</strong>: een label, artiest, promo- of repostkanaal. Plak <code>soundcloud.com/naam</code> of alleen de naam."),
        ("<strong>A SoundCloud playlist</strong> (<code>soundcloud.com/name/sets/…</code>). Private playlist links that end in <code>/s-xxxx</code> work too.",
         "<strong>Een SoundCloud-playlist</strong> (<code>soundcloud.com/naam/sets/…</code>). Privé-playlistlinks die eindigen op <code>/s-xxxx</code> werken ook."),
        ("<strong>A public Spotify playlist</strong>. Spotify only shows the first 100 tracks of a playlist, and private playlists or Liked Songs can't be read.",
         "<strong>Een openbare Spotify-playlist</strong>. Spotify toont maximaal de eerste 100 tracks van een playlist, en privé-playlists of Liked Songs kunnen niet gelezen worden."),
    ]),
    P("Short links (<code>on.soundcloud.com</code>, <code>spotify.link</code>), single tracks and albums are not supported: open the page and copy the full link of the profile or playlist.",
      "Korte links (<code>on.soundcloud.com</code>, <code>spotify.link</code>), losse tracks en albums worden niet ondersteund: open de pagina en kopieer de volledige link van het profiel of de playlist."),
    FIG("guide/add-soundcloud.png", "The add form with a SoundCloud profile pasted in: the choice to also get the latest tracks, the Include reposts box and the Add channel button.",
        "Het toevoegformulier met een SoundCloud-profiel erin geplakt: de keuze om ook de laatste tracks te halen, het vakje Include reposts en de knop Add channel.",
        "A SoundCloud profile.", "Een SoundCloud-profiel.", narrow=True),
    DL([
        ("Also get the latest", "Also get the latest",
         "For a profile: by default only <em>new</em> uploads from now on are fetched. Choose 5, 10 or 25 to also fetch that many of the most recent tracks.",
         "Bij een profiel: standaard worden alleen <em>nieuwe</em> uploads vanaf nu opgehaald. Kies 5, 10 of 25 om ook zoveel van de meest recente tracks op te halen."),
        ("Include reposts", "Include reposts",
         "Also follow what the profile reposts, not only what it uploads.",
         "Volg ook wat het profiel repost, niet alleen wat het zelf uploadt."),
    ]),
    FIG("guide/add-spotify.png", "The add form with a Spotify playlist link pasted in and a note that the playlist must be public.",
        "Het toevoegformulier met een Spotify-playlistlink erin en de opmerking dat de playlist openbaar moet zijn.",
        "A Spotify playlist.", "Een Spotify-playlist.", narrow=True),
    P("For a <strong>playlist</strong> every track in it is wanted, in the order of the playlist, and tracks added to the playlist later are fetched too. SeekSync checks every channel once an hour (change this under Settings, Schedule).",
      "Bij een <strong>playlist</strong> wil je elke track erin hebben, in de volgorde van de playlist, en tracks die later worden toegevoegd worden ook opgehaald. SeekSync controleert elk kanaal elk uur (aan te passen onder Settings, Schedule)."),
    H3("The top bar and the sidebar", "De bovenbalk en de zijbalk"),
    FIG("guide/topbar.png", "The top bar: a status line, and the buttons Check now, Open folder and Settings.",
        "De bovenbalk: een statusregel en de knoppen Check now, Open folder en Settings.",
        "The top bar.", "De bovenbalk."),
    UL([
        ("The <strong>status line</strong> says what SeekSync is doing, for example <em>Downloading 1</em>, how many tracks wait to be searched or are not found yet, when the next check is, and how you are connected.",
         "De <strong>statusregel</strong> zegt wat SeekSync doet, bijvoorbeeld <em>Downloading 1</em>, hoeveel tracks wachten om gezocht te worden of nog niet gevonden zijn, wanneer de volgende controle is en hoe je verbonden bent."),
        ("<strong>Check now</strong> looks at all your channels right away. <strong>Open folder</strong> opens your download folder. The gear opens <strong>Settings</strong>. A yellow <em>Get version x</em> button appears when a new version is out.",
         "<strong>Check now</strong> kijkt meteen bij al je kanalen. <strong>Open folder</strong> opent je downloadmap. Het tandwiel opent <strong>Settings</strong>. Een gele knop <em>Get version x</em> verschijnt als er een nieuwe versie is."),
        ("The <strong>sidebar</strong> lists your channels with when they were last checked and how many tracks are in progress. A red line under a channel is an error, such as <em>SoundCloud is blocking requests right now</em>; it usually clears by itself, so try again in a few minutes. <strong>All channels</strong> shows everything together.",
         "De <strong>zijbalk</strong> toont je kanalen met wanneer ze voor het laatst zijn gecontroleerd en hoeveel tracks bezig zijn. Een rode regel onder een kanaal is een fout, zoals <em>SoundCloud is blocking requests right now</em>; dat verdwijnt meestal vanzelf, probeer het over een paar minuten opnieuw. <strong>All channels</strong> toont alles samen."),
        ("<strong>Activity</strong> at the bottom left opens a log of what just happened.",
         "<strong>Activity</strong> linksonder opent een logboek van wat er net gebeurde."),
    ]),
    FIG("guide/activity.png", "The sidebar with the Activity log open, listing recent events such as downloads and checks.",
        "De zijbalk met het Activity-logboek open, met recente gebeurtenissen zoals downloads en controles.",
        "The Activity log.", "Het Activity-logboek.", narrow=True))

sec("list", "The track list", "De tracklijst",
    P("Every track SeekSync wants shows up in the list with a status. The tabs above the list filter it: <em>All, In progress, Downloaded, In collection, Not found yet, Skipped, Quarantine, Duplicates</em>.",
      "Elke track die SeekSync wil hebben, staat met een status in de lijst. De tabbladen boven de lijst filteren hem: <em>All, In progress, Downloaded, In collection, Not found yet, Skipped, Quarantine, Duplicates</em>."),
    FIG("guide/list.png", "The track list with statuses such as Downloading 62 percent, Searching Soulseek, Better copy found, Downloaded and Already in your collection.",
        "De tracklijst met statussen zoals Downloading 62 procent, Searching Soulseek, Better copy found, Downloaded en Already in your collection.",
        "The track list.", "De tracklijst."),
    TABLE([("Status", "Status"), ("What it means", "Wat het betekent")], [
        [("In line to search", "In line to search"), ("The track is waiting its turn. Searches are spaced out on purpose.", "De track wacht op zijn beurt. Zoekopdrachten worden met opzet gespreid.")],
        [("Searching Soulseek", "Searching Soulseek"), ("SeekSync is searching right now and scoring the results.", "SeekSync zoekt nu en beoordeelt de resultaten.")],
        [("Waiting for peer", "Waiting for peer"), ("A copy was chosen but the other user has a queue. It shows your place in line. After 45 minutes SeekSync tries another user.", "Er is een kopie gekozen maar de andere gebruiker heeft een wachtrij. Je ziet je plek in de rij. Na 45 minuten probeert SeekSync een andere gebruiker.")],
        [("Downloading 62%", "Downloading 62%"), ("The file is coming in, with the name of the user it comes from.", "Het bestand komt binnen, met de naam van de gebruiker van wie het komt.")],
        [("Not found yet", "Not found yet"), ("Nothing good was found. SeekSync tries again after 1, 3, 6 and 12 hours, then daily, until the time set under Settings, Schedule (30 days by default). The reason is shown, for example <em>3 results, none matched</em>.", "Er is niets goeds gevonden. SeekSync probeert het opnieuw na 1, 3, 6 en 12 uur, daarna dagelijks, tot de tijd die je instelt onder Settings, Schedule (standaard 30 dagen). De reden staat erbij, bijvoorbeeld <em>3 results, none matched</em>.")],
        [("Downloaded", "Downloaded"), ("Done. It shows the quality (such as FLAC 16-bit or MP3 320), where the audio stops (such as 21 kHz) and the file name. <em>Looking for better until …</em> means SeekSync still searches for a better copy.", "Klaar. Je ziet de kwaliteit (zoals FLAC 16-bit of MP3 320), waar de audio ophoudt (zoals 21 kHz) en de bestandsnaam. <em>Looking for better until …</em> betekent dat SeekSync nog zoekt naar een betere kopie.")],
        [("Better copy found", "Better copy found"), ("A better file than the one you have turned up. You choose: <em>Replace</em> or <em>Keep</em>.", "Er is een beter bestand gevonden dan dat je hebt. Jij kiest: <em>Replace</em> of <em>Keep</em>.")],
        [("Already in your collection", "Already in your collection"), ("You already own this track (see <a href=\"#collection\">Your collection</a>), so it isn't downloaded again.", "Je hebt deze track al (zie <a href=\"#collection\">Je collectie</a>), dus hij wordt niet opnieuw gedownload.")],
        [("Skipped", "Skipped"), ("Your rules (or the blocklist) said no. The reason is shown, and you can still get it with <em>Get it</em>.", "Jouw regels (of de blokkeerlijst) zeiden nee. De reden staat erbij en je kunt hem alsnog ophalen met <em>Get it</em>.")],
        [("Stopped looking", "Stopped looking"), ("The time ran out, or you pressed Stop looking. <em>Search now</em> starts again.", "De tijd is om, of je drukte op Stop looking. <em>Search now</em> begint opnieuw.")],
    ]),
    H3("The buttons on a row", "De knoppen op een rij"),
    DL([
        ("Search now", "Search now", "Search again right away, without waiting for the next try.", "Zoek meteen opnieuw, zonder te wachten op de volgende poging."),
        ("Why not?", "Why not?", "Shows what was searched and why files were rejected. See the next section.", "Toont waarop gezocht is en waarom bestanden zijn afgewezen. Zie het volgende onderdeel."),
        ("Skip", "Skip", "Stop looking for this track.", "Stop met zoeken naar deze track."),
        ("Show file", "Show file", "Shows the finished file in Finder or Explorer.", "Toont het klare bestand in Finder of Verkenner."),
        ("Replace / Keep", "Replace / Keep", "For a better copy: replace your file (the old one goes to SeekSync's trash for 30 days) or keep what you have.", "Bij een betere kopie: vervang je bestand (het oude gaat 30 dagen naar de prullenbak van SeekSync) of houd wat je hebt."),
        ("Get it / Get it anyway", "Get it / Get it anyway", "Fetch a track that was skipped by a rule, or that you already own.", "Haal een track toch op die door een regel is overgeslagen, of die je al hebt."),
    ]))

sec("why", "When a track isn't found", "Als een track niet gevonden wordt",
    P("Click <strong>Why not?</strong> on a track that wasn't found. SeekSync doesn't hide its reasoning:",
      "Klik op <strong>Why not?</strong> bij een track die niet gevonden is. SeekSync verbergt zijn redenering niet:"),
    FIG("app-why.png", "The Why not panel: the reason, what was searched for, the three closest files with the reason each was rejected, and fields to correct the track.",
        "Het paneel Why not?: de reden, waarop gezocht is, de drie dichtstbijzijnde bestanden met de reden van afwijzing, en velden om de track te corrigeren.",
        "The Why not? panel.", "Het paneel Why not?."),
    UL([
        ("<strong>The summary</strong> in one line, such as <em>3 results, none matched: closest was 192 kbps, under your minimum (MP3 320)</em>.",
         "<strong>De samenvatting</strong> in één regel, zoals <em>3 results, none matched: closest was 192 kbps, under your minimum (MP3 320)</em>."),
        ("<strong>Searched for</strong>: the search terms and how many results each gave.",
         "<strong>Searched for</strong>: de zoektermen en hoeveel resultaten elke gaf."),
        ("<strong>Closest files</strong>: the nearest candidates with the reason each was rejected (too short, a radio edit, another remix, too low a quality). <strong>Download this anyway</strong> fetches one of them. It still goes through the file checks.",
         "<strong>Closest files</strong>: de dichtstbijzijnde kandidaten met de reden van afwijzing (te kort, een radio edit, een andere remix, te lage kwaliteit). <strong>Download this anyway</strong> haalt er één binnen. Het bestand gaat nog steeds door de bestandscontroles."),
        ("<strong>Correct this track</strong>: if SeekSync misread the artist, title or version, fix it here. Your correction wins over the automatic reading.",
         "<strong>Correct this track</strong>: heeft SeekSync de artiest, titel of versie verkeerd gelezen, verbeter het dan hier. Jouw correctie gaat voor de automatische lezing."),
        ("<strong>Search with another term</strong> is tried before the automatic searches from then on. <strong>Stop looking</strong> gives up on the track.",
         "<strong>Search with another term</strong> wordt voortaan eerder geprobeerd dan de automatische zoekopdrachten. <strong>Stop looking</strong> geeft de track op."),
    ]),
    P("SeekSync is strict on purpose: an original is never replaced by a remix, and a radio edit, dub, VIP or someone else's remix is never taken for the version you want. Original and Extended go together.",
      "SeekSync is met opzet streng: een origineel wordt nooit vervangen door een remix, en een radio edit, dub, VIP of andermans remix wordt nooit aangezien voor de versie die jij wilt. Original en Extended gaan samen."))

sec("rules", "Rules per channel", "Regels per kanaal",
    P("Click a channel in the sidebar. Above its tracks you see a bar with the link and four buttons.",
      "Klik op een kanaal in de zijbalk. Boven de tracks zie je een balk met de link en vier knoppen."),
    FIG("guide/channel-bar.png", "A playlist opened: the channel bar with the link and the buttons Check now, Pause, Rules and Remove playlist.",
        "Een geopende playlist: de kanaalbalk met de link en de knoppen Check now, Pause, Rules en Remove playlist.",
        "The channel bar.", "De kanaalbalk."),
    UL([
        ("<strong>Check now</strong>: check just this channel.", "<strong>Check now</strong>: controleer alleen dit kanaal."),
        ("<strong>Pause</strong>: stop following it for a while.", "<strong>Pause</strong>: volg het een tijdje niet."),
        ("<strong>Rules</strong>: what gets fetched from this channel (below).", "<strong>Rules</strong>: wat er van dit kanaal wordt opgehaald (hieronder)."),
        ("<strong>Remove</strong>: stop following it. Files you already have stay where they are.", "<strong>Remove</strong>: stop met volgen. Bestanden die je al hebt, blijven staan."),
    ]),
    FIG("guide/rules.png", "The Rules panel: shortest and longest track, switches for remixes, previews, mixes and reposts, and lists of words to exclude or require.",
        "Het paneel Rules: kortste en langste track, schakelaars voor remixes, previews, mixen en reposts, en lijsten met woorden om uit te sluiten of te eisen.",
        "The Rules panel.", "Het paneel Rules.", narrow=True),
    DL([
        ("Shortest / longest track", "Shortest / longest track", "By default 2 to 12 minutes. Enter 0 as the longest for no limit. A label channel and a mix channel need different numbers.", "Standaard 2 tot 12 minuten. Vul 0 in als langste voor geen grens. Een labelkanaal en een mixkanaal vragen om andere getallen."),
        ("Fetch remixes, reworks, flips and bootlegs", "Fetch remixes, reworks, flips and bootlegs", "On by default. VIP, dub and edit versions are always allowed.", "Standaard aan. VIP-, dub- en edit-versies zijn altijd toegestaan."),
        ("Skip previews, clips and snippets", "Skip previews, clips and snippets", "On by default.", "Standaard aan."),
        ("Skip DJ mixes, radio shows and podcasts", "Skip DJ mixes, radio shows and podcasts", "On by default. Switch it off for a channel that only posts mixes.", "Standaard aan. Zet het uit voor een kanaal dat alleen mixen plaatst."),
        ("Include reposts", "Include reposts", "Only for profiles.", "Alleen voor profielen."),
        ("Skip a track when the title has one of these", "Skip a track when the title has one of these", "One word or phrase per line, for example <code>live at</code> or <code>podcast</code>.", "Eén woord of zin per regel, bijvoorbeeld <code>live at</code> of <code>podcast</code>."),
        ("Only fetch tracks whose title has one of these", "Only fetch tracks whose title has one of these", "One per line. Empty means everything.", "Eén per regel. Leeg betekent alles."),
    ]),
    P("Tracks that don't pass stay in the <em>Skipped</em> tab with the rule that stopped them, so you can still get one with a click. If you change the rules, tracks that now pass come back, and tracks that haven't been searched yet and no longer pass are skipped. Downloads, tracks in progress and tracks you skipped yourself are left alone. <strong>Back to defaults</strong> resets the rules.",
      "Tracks die niet door de regels komen, blijven in het tabblad <em>Skipped</em> staan met de regel die ze tegenhield, zodat je er met een klik alsnog één kunt ophalen. Pas je de regels aan, dan komen tracks die nu wel mogen terug, en tracks die nog niet gezocht zijn en niet meer mogen, worden overgeslagen. Downloads, lopende tracks en tracks die je zelf hebt overgeslagen blijven met rust. <strong>Back to defaults</strong> zet de regels terug."),
    P("Rules for everything at once (blocked words and artists) live under <a href=\"#settings\">Settings, Blocklist</a>, and they win over a channel's rules.",
      "Regels voor alles tegelijk (geblokkeerde woorden en artiesten) staan onder <a href=\"#settings\">Settings, Blocklist</a> en gaan voor op de regels van een kanaal."))

sec("settings", "Settings, one by one", "De instellingen, één voor één",
    P("Open Settings with the gear at the top right. Change what you like and click <strong>Save settings</strong> at the bottom. The sections follow the order of the screen.",
      "Open Settings met het tandwiel rechtsboven. Pas aan wat je wilt en klik onderaan op <strong>Save settings</strong>. De onderdelen volgen de volgorde van het scherm."),
    H3("Soulseek and Files", "Soulseek en Files", "set-soulseek"),
    P("Soulseek is covered in <a href=\"#connect\">Connect to Soulseek</a>. Under <em>Files</em> you set the <strong>Download folder</strong>: where finished tracks are placed. Use <em>Choose…</em> to pick it. Unfinished files are kept in a separate working area and only move to your folder once they passed every check.",
      "Soulseek staat uitgelegd bij <a href=\"#connect\">Verbinden met Soulseek</a>. Onder <em>Files</em> stel je de <strong>Download folder</strong> in: waar klare tracks komen. Kies hem met <em>Choose…</em>. Onaffe bestanden staan in een aparte werkmap en komen pas in jouw map als ze alle controles hebben doorstaan."),
    H3("Names and tags", "Names and tags", "set-names"),
    FIG("guide/s-names.png", "Settings, Names and tags: the folder and file name template with a live example, and three checkboxes for tags, WAV to AIFF and label.",
        "Instellingen, Names and tags: het sjabloon voor map en bestandsnaam met een voorbeeld, en drie vakjes voor tags, WAV naar AIFF en label.",
        "Settings, Names and tags.", "Settings, Names and tags.", narrow=True),
    DL([
        ("Folder and file name", "Folder and file name",
         "A template with these pieces: <code>{channel}</code> <code>{artist}</code> <code>{title}</code> <code>{version}</code> <code>{year}</code> <code>{genre}</code>. Use <code>/</code> for folders. The default is <code>{channel}/{artist} - {title} ({version})</code>, which gives <em>Nightshift Records/Mira Kova - Night Signal (Extended Mix).flac</em>. Empty brackets and dashes disappear when a field is missing. A live example is shown under the field.",
         "Een sjabloon met deze onderdelen: <code>{channel}</code> <code>{artist}</code> <code>{title}</code> <code>{version}</code> <code>{year}</code> <code>{genre}</code>. Gebruik <code>/</code> voor mappen. Standaard is dat <code>{channel}/{artist} - {title} ({version})</code>, wat <em>Nightshift Records/Mira Kova - Night Signal (Extended Mix).flac</em> geeft. Lege haakjes en streepjes verdwijnen als een veld ontbreekt. Onder het veld zie je een voorbeeld."),
        ("Write tags and cover art", "Write tags and cover art",
         "On by default. Every finished file gets artist, title with the version, genre, year, the link and a 500 px cover (MP3 ID3v2.3, FLAC, AIFF, M4A). BPM and key tags the uploader embedded stay. Spotify tracks get the album cover (640 px) and the year, but no genre, because Spotify's page doesn't give one.",
         "Standaard aan. Elk klaar bestand krijgt artiest, titel met versie, genre, jaar, de link en een hoes van 500 px (MP3 ID3v2.3, FLAC, AIFF, M4A). BPM- en toonsoorttags die de uploader zelf inbedde blijven staan. Spotify-tracks krijgen de albumhoes (640 px) en het jaar, maar geen genre, omdat de pagina van Spotify dat niet geeft."),
        ("Convert WAV to AIFF", "Convert WAV to AIFF",
         "Off by default. Same audio, but DJ software reads the tags of AIFF files better than those of WAV files.",
         "Standaard uit. Dezelfde audio, maar DJ-software leest de tags van AIFF-bestanden beter dan die van WAV-bestanden."),
        ("Use the channel name as the label tag", "Use the channel name as the label tag",
         "Off by default. Useful for label channels: the label tag then holds the name of the channel.",
         "Standaard uit. Handig voor labelkanalen: de labeltag bevat dan de naam van het kanaal."),
        ("Fill in missing covers", "Fill in missing covers",
         "A button. Every downloaded file without a cover (or with a broken one) gets one from SoundCloud or Spotify. Only the picture is added: the other tags, the name and the audio stay as they are. Useful for files from before version 0.6.2, and for tracks whose cover couldn't be downloaded at the time.",
         "Een knop. Elk gedownload bestand zonder hoes (of met een kapotte) krijgt er een van SoundCloud of Spotify. Alleen de afbeelding komt erbij: de andere tags, de naam en de audio blijven zoals ze zijn. Handig voor bestanden van vóór versie 0.6.2, en voor tracks waarvan de hoes toen niet gedownload kon worden."),
    ]),
    H3("Sharing", "Sharing", "set-sharing"),
    P("With its own account: <em>Share the download folder on Soulseek</em> and a box for <em>other shared folders</em>, one per line. Through Nicotine+: sharing is set up in Nicotine+. SeekSync warns you at the top when you share nothing, because many users block people who share nothing.",
      "Met een eigen account: <em>Share the download folder on Soulseek</em> en een vak voor <em>other shared folders</em>, één per regel. Via Nicotine+: delen stel je in Nicotine+ in. SeekSync waarschuwt je bovenaan als je niets deelt, want veel gebruikers blokkeren mensen die niets delen."),
    H3("File checks", "File checks", "set-checks"),
    FIG("guide/s-checks.png", "Settings, File checks: allowed length difference, longest silence at start or end, and what to do with suspect lossless files.",
        "Instellingen, File checks: toegestaan lengteverschil, langste stilte aan begin of eind, en wat te doen met verdachte lossless bestanden.",
        "Settings, File checks.", "Settings, File checks.", narrow=True),
    P("Needs ffmpeg (the line at the top says whether the checks are on). Every download is checked before it reaches your music folder.",
      "Heeft ffmpeg nodig (de regel bovenaan zegt of de controles aan staan). Elke download wordt gecontroleerd voordat hij in je muziekmap komt."),
    DL([
        ("Length may differ from SoundCloud by", "Length may differ from SoundCloud by", "5, 10 (default), 20 or 30 seconds. An Extended version may be longer than the original upload.", "5, 10 (standaard), 20 of 30 seconden. Een Extended-versie mag langer zijn dan de originele upload."),
        ("Reject silence at start or end longer than", "Reject silence at start or end longer than", "5, 10 (default), 20 or 30 seconds.", "5, 10 (standaard), 20 of 30 seconden."),
        ("Lossless (or 320 kbps) that may be a converted MP3", "Lossless (or 320 kbps) that may be a converted MP3", "SeekSync reads the spectrum of each file. A fake lossless file stops at a hard cutoff around 16 to 19 kHz. Choose <em>Keep it, but mark it as suspect</em> (default) or <em>Reject it and look for another copy</em>. A file that is clearly fake is always rejected.", "SeekSync leest het spectrum van elk bestand. Een valse lossless stopt bij een harde afkapgrens rond 16 tot 19 kHz. Kies <em>Keep it, but mark it as suspect</em> (standaard) of <em>Reject it and look for another copy</em>. Een bestand dat duidelijk vals is, wordt altijd afgewezen."),
    ]),
    H3("Quality", "Quality", "set-quality"),
    FIG("guide/s-quality.png", "Settings, Quality: the profile (Club, Balanced, Space saver) with an explanation, and what to do when a better copy turns up later.",
        "Instellingen, Quality: het profiel (Club, Balanced, Space saver) met uitleg, en wat te doen als later een betere kopie opduikt.",
        "Settings, Quality.", "Settings, Quality.", narrow=True),
    TABLE([("Profile", "Profile"), ("What you get", "Wat je krijgt")], [
        [("Club (default)", "Club (standaard)"), ("Lossless (FLAC 24-bit, FLAC 16-bit, WAV). MP3 320 is the minimum; SeekSync keeps looking for a lossless copy.", "Lossless (FLAC 24-bit, FLAC 16-bit, WAV). MP3 320 is het minimum; SeekSync blijft zoeken naar een lossless kopie.")],
        [("Balanced", "Balanced"), ("MP3 320 or better. MP3 256 is the minimum.", "MP3 320 of beter. MP3 256 is het minimum.")],
        [("Space saver", "Space saver"), ("MP3 320 or 256; MP3 192 is the minimum. Lossless only if there is nothing else.", "MP3 320 of 256; MP3 192 is het minimum. Lossless alleen als er niets anders is.")],
    ]),
    P("<strong>When a better copy turns up later</strong>: if a track first arrives below your goal (say MP3 320 while you want lossless), SeekSync keeps looking for 30 days. You choose what happens when it finds one:",
      "<strong>When a better copy turns up later</strong>: komt een track eerst binnen onder je doel (bijvoorbeeld MP3 320 terwijl je lossless wilt), dan blijft SeekSync 30 dagen zoeken. Jij kiest wat er gebeurt als het er een vindt:"),
    UL([
        ("<strong>Ask me first</strong> (default): you see <em>Better copy found</em> with Replace and Keep. This keeps your cue points safe.", "<strong>Ask me first</strong> (standaard): je ziet <em>Better copy found</em> met Replace en Keep. Zo blijven je cue points veilig."),
        ("<strong>Replace the file right away</strong>.", "<strong>Replace the file right away</strong>."),
        ("<strong>Replace right away, but ask for tracks that are in Rekordbox</strong>: see <a href=\"#rekordbox\">Rekordbox</a>.", "<strong>Replace right away, but ask for tracks that are in Rekordbox</strong>: zie <a href=\"#rekordbox\">Rekordbox</a>."),
        ("<strong>Don't look for better copies</strong>.", "<strong>Don't look for better copies</strong>."),
    ]),
    NOTE("warn",
         "Replacing an MP3 with a FLAC changes the file name, so Rekordbox or Serato lose the cue points of the old file. The old file goes to SeekSync's trash for 30 days.",
         "Een MP3 vervangen door een FLAC verandert de bestandsnaam, waardoor Rekordbox of Serato de cue points van het oude bestand kwijtraken. Het oude bestand gaat 30 dagen naar de prullenbak van SeekSync."),
    H3("Blocklist", "Blocklist", "set-blocklist"),
    FIG("guide/s-blocklist.png", "Settings, Blocklist: words that skip a track and artists that are never fetched.",
        "Instellingen, Blocklist: woorden die een track overslaan en artiesten die nooit worden opgehaald.",
        "Settings, Blocklist.", "Settings, Blocklist.", narrow=True),
    P("Applies to every channel and playlist and wins over their rules. <em>Skip tracks with these words in the title</em> and <em>Never fetch these artists</em>, one per line.",
      "Geldt voor elk kanaal en elke playlist en gaat voor op hun regels. <em>Skip tracks with these words in the title</em> en <em>Never fetch these artists</em>, één per regel."),
    H3("Soulseek etiquette", "Soulseek etiquette", "set-etiquette"),
    FIG("guide/s-etiquette.png", "Settings, Soulseek etiquette: wait between searches, searches per five minutes, and the disk space at which downloads pause.",
        "Instellingen, Soulseek etiquette: wachttijd tussen zoekopdrachten, zoekopdrachten per vijf minuten en de schijfruimte waaronder downloads pauzeren.",
        "Settings, Soulseek etiquette.", "Settings, Soulseek etiquette.", narrow=True),
    P("Soulseek is run by volunteers. Searching slowly and not filling your disk keeps you from being blocked. The choices are limited on purpose: the wait between searches can never go below a few seconds.",
      "Soulseek wordt door vrijwilligers gedraaid. Langzaam zoeken en je schijf niet vol laten lopen voorkomt dat je geblokkeerd wordt. De keuzes zijn met opzet beperkt: de wachttijd tussen zoekopdrachten kan nooit onder een paar seconden komen."),
    DL([
        ("Wait between searches", "Wait between searches", "8 seconds (default), 12, 20 or 30.", "8 seconden (standaard), 12, 20 of 30."),
        ("At most, per 5 minutes", "At most, per 5 minutes", "10, 20 (default), 30 or 40 searches.", "10, 20 (standaard), 30 of 40 zoekopdrachten."),
        ("Pause downloads when free disk space is under", "Pause downloads when free disk space is under", "5 GB by default (or never). A notice appears at the top while downloads are paused, and they continue by themselves when there is room again.", "Standaard 5 GB (of nooit). Zolang downloads gepauzeerd zijn, staat bovenaan een melding, en ze gaan vanzelf verder als er weer ruimte is."),
        ("Blocked users", "Blocked users", "Users who repeatedly sent fake files or failed are scored lower and, after repeated problems, blocked for 30 days. They appear in a list with an <strong>Unblock</strong> button.", "Gebruikers die herhaaldelijk valse bestanden stuurden of faalden, krijgen een lagere score en worden na herhaalde problemen 30 dagen geblokkeerd. Ze staan in een lijst met een knop <strong>Unblock</strong>."),
    ]),
    H3("Schedule and Artists", "Schedule en Artists", "set-schedule"),
    FIG("guide/s-schedule.png", "Settings, Schedule and Artists: how often channels are checked, how long to keep looking, parallel downloads, and artist aliases.",
        "Instellingen, Schedule en Artists: hoe vaak kanalen gecontroleerd worden, hoe lang er gezocht wordt, parallelle downloads en artiestenaliassen.",
        "Settings, Schedule and Artists.", "Settings, Schedule en Artists.", narrow=True),
    DL([
        ("Check channels every", "Check channels every", "30 minutes, an hour (default), 3 hours, 6 hours or a day. SeekSync only checks while the app is open.", "30 minuten, een uur (standaard), 3 uur, 6 uur of een dag. SeekSync controleert alleen zolang de app open staat."),
        ("Keep looking for", "Keep looking for", "1 week, 30 days (default), 90 days or a year. After that a track becomes <em>Stopped looking</em>.", "1 week, 30 dagen (standaard), 90 dagen of een jaar. Daarna wordt een track <em>Stopped looking</em>."),
        ("Downloads at the same time", "Downloads at the same time", "1, 2, 3 (default) or 5.", "1, 2, 3 (standaard) of 5."),
        ("Other names of the same artist", "Other names of the same artist", "For producers with several names. One line per artist, for example <code>Four Tet = Kieran Hebden, KH</code>. Tracks by that artist are also searched under the other names, and a file under any of the names counts.", "Voor producers met meerdere namen. Eén regel per artiest, bijvoorbeeld <code>Four Tet = Kieran Hebden, KH</code>. Tracks van die artiest worden ook onder de andere namen gezocht, en een bestand onder een van de namen telt mee."),
    ]),
    H3("Collection, Rekordbox and Updates", "Collection, Rekordbox en Updates", "set-more"),
    P("These three have their own sections below: <a href=\"#collection\">Your collection</a>, <a href=\"#rekordbox\">Rekordbox</a> and <a href=\"#updating\">Updating</a>.",
      "Deze drie hebben hieronder hun eigen onderdeel: <a href=\"#collection\">Je collectie</a>, <a href=\"#rekordbox\">Rekordbox</a> en <a href=\"#updating\">Bijwerken</a>."))

sec("collection", "Your collection and duplicates", "Je collectie en dubbelen",
    P("SeekSync can see which tracks you already own, so it doesn't download them again, even when they have a slightly different name or come from another channel.",
      "SeekSync kan zien welke tracks je al hebt, zodat het ze niet opnieuw downloadt, ook als ze een iets andere naam hebben of van een ander kanaal komen."),
    FIG("guide/s-collection.png", "Settings, Your music collection: a box for music folders, an Add folder button, a Scan now button and the number of files known.",
        "Instellingen, Your music collection: een vak voor muziekmappen, een knop Add folder, een knop Scan now en het aantal bekende bestanden.",
        "Settings, Your music collection.", "Settings, Your music collection.", narrow=True),
    OL([
        ("Open <strong>Settings, Your music collection</strong>.", "Open <strong>Settings, Your music collection</strong>."),
        ("Add your music folders, one per line, or use <strong>Add folder…</strong> to pick one. Subfolders are included. Your download folder always counts.",
         "Voeg je muziekmappen toe, één per regel, of gebruik <strong>Add folder…</strong> om er een te kiezen. Submappen doen mee. Je downloadmap telt altijd mee."),
        ("Click <strong>Save settings</strong> and then <strong>Scan now</strong>. The first scan reads every file; later scans only read what is new or changed, so they are quick. A folder on a drive that isn't connected keeps what was known about it.",
         "Klik op <strong>Save settings</strong> en daarna op <strong>Scan now</strong>. De eerste scan leest elk bestand; latere scans lezen alleen wat nieuw of gewijzigd is en zijn dus snel. Een map op een schijf die niet is aangesloten, behoudt wat er van bekend was."),
    ]),
    P("SeekSync <em>only reads</em> these folders. It never changes or deletes anything in them.",
      "SeekSync <em>leest</em> deze mappen <em>alleen</em>. Het verandert of verwijdert er nooit iets in."),
    P("A track counts as already owned when the title, artist (aliases count) and version match, and the length is not very different. A remix is never mistaken for the original. Such a track gets the status <em>Already in your collection</em> and is listed under the <em>In collection</em> tab, with <em>Show file</em> and <em>Get it anyway</em>.",
      "Een track telt als al in bezit als titel, artiest (aliassen tellen mee) en versie overeenkomen en de lengte niet sterk afwijkt. Een remix wordt nooit aangezien voor het origineel. Zo'n track krijgt de status <em>Already in your collection</em> en staat onder het tabblad <em>In collection</em>, met <em>Show file</em> en <em>Get it anyway</em>."),
    FIG("guide/collection.png", "The In collection tab: a track marked Already in your collection with its location and the buttons Show file and Get it anyway.",
        "Het tabblad In collection: een track gemarkeerd als Already in your collection met zijn locatie en de knoppen Show file en Get it anyway.",
        "The In collection tab.", "Het tabblad In collection."),
    H3("Duplicates", "Duplicates", "dups"),
    P("The <strong>Duplicates</strong> tab lists files in your download folder that are the same track (same artist, title and version), with the best copy marked <em>Best</em> according to your quality profile. Nothing is deleted or moved: you decide.",
      "Het tabblad <strong>Duplicates</strong> toont bestanden in je downloadmap die dezelfde track zijn (zelfde artiest, titel en versie), met de beste kopie gemarkeerd als <em>Best</em> volgens je kwaliteitsprofiel. Er wordt niets verwijderd of verplaatst: dat bepaal jij."),
    FIG("guide/duplicates.png", "The Duplicates tab: two copies of one track, FLAC and MP3, with the FLAC marked Best.",
        "Het tabblad Duplicates: twee kopieën van één track, FLAC en MP3, met de FLAC gemarkeerd als Best.",
        "The Duplicates tab.", "Het tabblad Duplicates."))

sec("quarantine", "Quarantine", "Quarantaine",
    P("When a downloaded file fails a check, it doesn't reach your music folder. It goes to <strong>Quarantine</strong> with the reason, and SeekSync looks for another copy from another user. That file and that user are not used again for this track.",
      "Als een gedownload bestand een controle niet doorstaat, komt het niet in je muziekmap. Het gaat naar <strong>Quarantine</strong> met de reden, en SeekSync zoekt een andere kopie bij een andere gebruiker. Dat bestand en die gebruiker worden voor deze track niet opnieuw gebruikt."),
    FIG("guide/quarantine.png", "The Quarantine tab: two rejected files, one with 30 seconds of silence at the end and one that is not really FLAC, each with the buttons Approve anyway and Delete.",
        "Het tabblad Quarantine: twee afgewezen bestanden, één met 30 seconden stilte aan het eind en één dat niet echt FLAC is, elk met de knoppen Approve anyway en Delete.",
        "The Quarantine tab.", "Het tabblad Quarantine."),
    P("Every download must: play all the way through, be the format its name says (no MP3 renamed to .flac), be about as long as the original, not start or end with a long silence, and not be a converted lossless file. You can <strong>Approve anyway</strong> (the file continues to your folder) or <strong>Delete</strong> it.",
      "Elke download moet: helemaal afspelen, het formaat hebben dat de naam zegt (geen MP3 die .flac is genoemd), ongeveer even lang zijn als het origineel, niet beginnen of eindigen met een lange stilte, en geen omgezet lossless bestand zijn. Je kunt <strong>Approve anyway</strong> kiezen (het bestand gaat alsnog naar je map) of het <strong>Delete</strong>n."),
    NOTE("tip",
         "Finished tracks show where their audio stops, such as <em>21.9 kHz</em> or <em>Suspect: stops at 20.3 kHz</em>. A real FLAC or 320 kbps MP3 goes up to about 20 kHz or higher.",
         "Klare tracks tonen waar hun audio ophoudt, zoals <em>21.9 kHz</em> of <em>Suspect: stops at 20.3 kHz</em>. Een echte FLAC of 320 kbps MP3 loopt door tot ongeveer 20 kHz of hoger."))

sec("rekordbox", "Rekordbox", "Rekordbox",
    P("SeekSync can write a Rekordbox XML file with every track it downloaded and a playlist for each channel or playlist, inside a folder called SeekSync. SeekSync only writes this one file and never touches Rekordbox' own library.",
      "SeekSync kan een Rekordbox-XML-bestand schrijven met elke gedownloade track en een playlist voor elk kanaal of elke playlist, in een map SeekSync. SeekSync schrijft alleen dit ene bestand en raakt de eigen bibliotheek van Rekordbox nooit aan."),
    FIG("guide/s-rekordbox.png", "Settings, Rekordbox: the switch to keep an XML file up to date, its location, Update now and Show file buttons, and the field for your Rekordbox collection export.",
        "Instellingen, Rekordbox: de schakelaar om een XML-bestand bij te houden, de locatie, de knoppen Update now en Show file, en het veld voor je Rekordbox-collectie-export.",
        "Settings, Rekordbox.", "Settings, Rekordbox.", narrow=True),
    H3("Step by step", "Stap voor stap"),
    OL([
        ("In SeekSync open <strong>Settings, Rekordbox</strong> and tick <em>Keep a Rekordbox XML file of the downloaded tracks up to date</em>.",
         "Open in SeekSync <strong>Settings, Rekordbox</strong> en vink <em>Keep a Rekordbox XML file of the downloaded tracks up to date</em> aan."),
        ("The file is called <code>SeekSync for Rekordbox.xml</code> and lives in your download folder (or where you point it). It is rewritten about 30 seconds after a download. <strong>Update now</strong> writes it immediately and <strong>Show file</strong> shows it.",
         "Het bestand heet <code>SeekSync for Rekordbox.xml</code> en staat in je downloadmap (of waar je het naartoe wijst). Het wordt ongeveer 30 seconden na een download opnieuw geschreven. <strong>Update now</strong> schrijft het meteen en <strong>Show file</strong> toont het."),
        ("In Rekordbox open <strong>Preferences, Advanced, Database</strong>, tick <strong>rekordbox xml</strong> and choose that file.",
         "Open in Rekordbox <strong>Preferences, Advanced, Database</strong>, vink <strong>rekordbox xml</strong> aan en kies dat bestand."),
        ("In the tree open <strong>rekordbox xml</strong>, right-click a playlist and choose <strong>Import Playlist</strong>.",
         "Open in de boomstructuur <strong>rekordbox xml</strong>, klik met rechts op een playlist en kies <strong>Import Playlist</strong>."),
    ]),
    H3("Keep your cue points safe", "Houd je cue points veilig"),
    P("A better copy of a track gets a new file name, and Rekordbox sees that as a new track without your cue points. To prevent a surprise, let SeekSync read an export of your Rekordbox collection:",
      "Een betere kopie van een track krijgt een nieuwe bestandsnaam, en Rekordbox ziet dat als een nieuwe track zonder je cue points. Om verrassingen te voorkomen, laat je SeekSync een export van je Rekordbox-collectie lezen:"),
    OL([
        ("In Rekordbox choose <strong>File, Export Collection in xml format</strong> and save the file.",
         "Kies in Rekordbox <strong>File, Export Collection in xml format</strong> en bewaar het bestand."),
        ("In SeekSync pick that file under <strong>Your Rekordbox collection export</strong>. SeekSync only reads it. Export again now and then.",
         "Kies dat bestand in SeekSync onder <strong>Your Rekordbox collection export</strong>. SeekSync leest het alleen. Exporteer af en toe opnieuw."),
        ("Under <strong>Quality</strong> choose <em>Replace right away, but ask for tracks that are in Rekordbox</em>. Tracks in your Rekordbox are then never replaced by themselves, and the list shows <em>in Rekordbox</em> next to them. Without the export file, SeekSync asks first for every track.",
         "Kies onder <strong>Quality</strong> <em>Replace right away, but ask for tracks that are in Rekordbox</em>. Tracks die in je Rekordbox staan, worden dan nooit vanzelf vervangen, en in de lijst staat <em>in Rekordbox</em> erbij. Zonder het exportbestand vraagt SeekSync bij elke track eerst."),
    ]),
    P("Only Rekordbox is connected so far. Serato crates, M3U playlists and Traktor are not built yet, but the files and their tags work in any DJ software.",
      "Voorlopig is alleen Rekordbox gekoppeld. Serato-crates, M3U-playlists en Traktor zijn nog niet gebouwd, maar de bestanden en hun tags werken in elke DJ-software."))

sec("updating", "Updating", "Bijwerken",
    P("SeekSync asks GitHub twice a day whether a new version is out, and tells you with a yellow <em>Get version x</em> button. You can also look right away under <strong>Settings, Updates, Check now</strong>.",
      "SeekSync vraagt twee keer per dag aan GitHub of er een nieuwe versie is, en meldt dat met een gele knop <em>Get version x</em>. Je kunt ook meteen kijken onder <strong>Settings, Updates, Check now</strong>."),
    FIG("guide/s-updates.png", "Settings, Updates: the box to be told about new versions, a Check now button and the status line.",
        "Instellingen, Updates: het vakje om nieuwe versies te melden, een knop Check now en de statusregel.",
        "Settings, Updates.", "Settings, Updates.", narrow=True),
    UL([
        ("<strong>On a Mac</strong> click <strong>Install and restart</strong>. SeekSync downloads the new version, checks it, replaces itself and starts again. The old app is kept in a folder called <code>previous-versions</code> in the app data (the last two).",
         "<strong>Op een Mac</strong> klik je op <strong>Install and restart</strong>. SeekSync downloadt de nieuwe versie, controleert hem, vervangt zichzelf en start opnieuw. De oude app blijft bewaard in een map <code>previous-versions</code> in de app-gegevens (de laatste twee)."),
        ("<strong>On Windows</strong> click <strong>Install and restart</strong> too. SeekSync downloads the installer, checks it, closes itself, runs the installer quietly over the old version and starts again.",
         "<strong>Op Windows</strong> klik je ook op <strong>Install and restart</strong>. SeekSync downloadt het installatieprogramma, controleert het, sluit zichzelf, draait het stil over de oude versie heen en start opnieuw."),
        ("When SeekSync can't change its own folder, use the release page: download the new installer and run it over the old one.",
         "Mag SeekSync zijn eigen map niet wijzigen, gebruik dan de releasepagina: download het nieuwe installatieprogramma en start het over het oude heen."),
        ("Your channels and settings are kept either way. Switch the notice off with the box <em>Tell me when a new version is out</em>.",
         "Je kanalen en instellingen blijven in beide gevallen bewaard. Zet de melding uit met het vakje <em>Tell me when a new version is out</em>."),
    ]))

sec("help", "Troubleshooting", "Problemen oplossen",
    DL([
        ("“Can't reach Nicotine+”", "“Can't reach Nicotine+”", "Open Nicotine+ and check that <strong>SeekSync Bridge</strong> is switched on (Preferences, Plugins). After an update, turn the plugin off and on once.", "Open Nicotine+ en controleer of <strong>SeekSync Bridge</strong> aan staat (Preferences, Plugins). Zet de plugin na een update één keer uit en aan."),
        ("A track stays at “Waiting for peer”", "Een track blijft op “Waiting for peer”", "The other user has a queue. After 45 minutes SeekSync tries another user.", "De andere gebruiker heeft een wachtrij. Na 45 minuten probeert SeekSync een andere gebruiker."),
        ("“Not found yet” for a track you can find by hand", "“Not found yet” voor een track die je met de hand wel vindt", "Title matching is strict on purpose. Open <strong>Why not?</strong>: the closest files and their reasons tell you why. Correct the artist, title or version, or download one anyway. If it still looks wrong, open an issue on GitHub with the link and the file name you found.", "De titelherkenning is met opzet streng. Open <strong>Why not?</strong>: de dichtstbijzijnde bestanden en hun redenen vertellen waarom. Verbeter de artiest, titel of versie, of download er toch een. Lijkt het nog steeds fout, open dan een issue op GitHub met de link en de bestandsnaam die je vond."),
        ("“SoundCloud is blocking requests right now”", "“SoundCloud is blocking requests right now”", "SoundCloud limits how often a program may ask. It usually clears by itself within minutes; SeekSync tries again at the next check.", "SoundCloud beperkt hoe vaak een programma mag vragen. Het verdwijnt meestal binnen enkele minuten vanzelf; SeekSync probeert het bij de volgende controle opnieuw."),
        ("“Downloads paused”", "“Downloads paused”", "Free disk space is below the limit under Settings, Soulseek etiquette. Free some space; downloads continue by themselves.", "De vrije schijfruimte is onder de grens bij Settings, Soulseek etiquette. Maak ruimte vrij; downloads gaan vanzelf verder."),
        ("“Nothing shared”", "“Nothing shared”", "You are not sharing a folder, and many Soulseek users block people who share nothing. Share a folder (see <a href=\"#connect\">Connect to Soulseek</a>).", "Je deelt geen map, en veel Soulseek-gebruikers blokkeren mensen die niets delen. Deel een map (zie <a href=\"#connect\">Verbinden met Soulseek</a>)."),
        ("Files aren't being checked", "Bestanden worden niet gecontroleerd", "Install ffmpeg (on a Mac: <code>brew install ffmpeg</code>) and restart SeekSync. Settings, File checks says whether the checks are on.", "Installeer ffmpeg (op een Mac: <code>brew install ffmpeg</code>) en start SeekSync opnieuw. Settings, File checks zegt of de controles aan staan."),
    ]),
    P(f"Still stuck? Open an issue on <a href=\"{GITHUB}/issues\">GitHub</a> and attach <code>seeksync.log</code> (see below).",
      f"Kom je er niet uit? Open een issue op <a href=\"{GITHUB}/issues\">GitHub</a> en voeg <code>seeksync.log</code> toe (zie hieronder)."))

sec("data", "Your data and privacy", "Je gegevens en privacy",
    UL([
        ("<strong>Your music</strong> goes to the download folder you chose (by default <code>Music/SeekSync</code>).",
         "<strong>Je muziek</strong> komt in de downloadmap die je koos (standaard <code>Music/SeekSync</code>)."),
        ("<strong>Settings, database and temporary folders</strong> are in <code>~/Library/Application Support/SeekSync</code> on a Mac and <code>%LOCALAPPDATA%\\SeekSync</code> on Windows.",
         "<strong>Instellingen, database en tijdelijke mappen</strong> staan in <code>~/Library/Application Support/SeekSync</code> op een Mac en <code>%LOCALAPPDATA%\\SeekSync</code> op Windows."),
        ("<strong>The log</strong> is <code>seeksync.log</code>: on a Mac in <code>~/Library/Logs/SeekSync</code>, on Windows in the SeekSync folder under <code>%LOCALAPPDATA%</code>. Attach it to bug reports.",
         "<strong>Het logbestand</strong> is <code>seeksync.log</code>: op een Mac in <code>~/Library/Logs/SeekSync</code>, op Windows in de SeekSync-map onder <code>%LOCALAPPDATA%</code>. Voeg het toe aan foutmeldingen."),
        ("<strong>Privacy:</strong> everything stays on your computer. SeekSync talks to SoundCloud and Spotify (to read channels and playlists), to Soulseek (directly or through Nicotine+) and, twice a day, to GitHub (to see if there is a new version; you can turn that off). There is no tracking and there are no analytics.",
         "<strong>Privacy:</strong> alles blijft op je computer. SeekSync praat met SoundCloud en Spotify (om kanalen en playlists te lezen), met Soulseek (direct of via Nicotine+) en twee keer per dag met GitHub (om te zien of er een nieuwe versie is; dat kun je uitzetten). Er is geen tracking en er zijn geen analytics."),
    ]))

# ======================================================================================================

HEAD = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SeekSync guide: from install to your first tracks</title>
  <meta name="description" content="A step-by-step guide to SeekSync: install, connect to Soulseek, add SoundCloud channels and Spotify playlists, read the track list, set the rules and settings, and use Rekordbox.">
  <meta name="theme-color" content="#E0E0E0">
  <meta property="og:title" content="SeekSync guide">
  <meta property="og:description" content="From install to your first tracks, step by step, with screenshots.">
  <meta property="og:type" content="article">
  <link rel="icon" href="img/logo.svg" type="image/svg+xml">
  <link rel="stylesheet" href="style.css">
</head>
<body class="guide-page">
<a class="skip" href="#main" data-i18n="{skip}">Skip to content</a>

<header class="nav">
  <div class="wrap nav-row">
    <a class="brand" href="index.html" data-keep-lang aria-label="SeekSync">
      <img src="img/logo.svg" alt="" width="36" height="36"><span>SeekSync</span>
    </a>
    <nav class="nav-links" aria-label="Main">
      <a href="index.html#how" data-keep-lang data-i18n="{n_how}">How it works</a>
      <a href="index.html#features" data-keep-lang data-i18n="{n_feat}">Features</a>
      <a href="index.html#download" data-keep-lang data-i18n="{n_dl}">Download</a>
      <a href="guide.html" data-keep-lang aria-current="page" data-i18n="{n_guide}">Guide</a>
    </nav>
    <div class="nav-actions">
      <div class="lang" role="group" aria-label="Language">
        <button type="button" data-lang="en" aria-pressed="true">EN</button>
        <button type="button" data-lang="nl" aria-pressed="false">NL</button>
      </div>
      <a class="btn dark small" href="https://github.com/Stormhoogervorst/seeksync">GitHub</a>
    </div>
  </div>
</header>

<main id="main">
  <section class="guide-hero">
    <div class="wrap">
      <p class="eyebrow" data-i18n="{eyebrow}">Guide</p>
      <h1 data-i18n="{h1}">From install to your first tracks</h1>
      <p class="lede" data-i18n="{lede}">This guide takes you through SeekSync from start to finish: installing it, connecting to Soulseek, adding channels, reading the list and every setting. The screenshots are from the app with made-up example data.</p>
    </div>
  </section>

  <div class="wrap guide-layout">
    <nav class="toc" aria-label="Contents">
      <details open>
        <summary data-i18n="{toc}">Contents</summary>
        <ol>
{toc_items}
        </ol>
      </details>
    </nav>
    <article class="doc">
"""

TAIL = """
      <section class="doc-end">
        <h2 data-i18n="{end_h}">Ready?</h2>
        <p data-i18n="{end_p}">Download SeekSync, add your first channel and let it work.</p>
        <p class="cta"><a class="btn primary big" href="index.html#download" data-keep-lang data-i18n="{end_btn}">Download SeekSync</a></p>
      </section>
    </article>
  </div>
</main>

<footer class="foot">
  <div class="wrap foot-row">
    <a class="brand" href="index.html" data-keep-lang><img src="img/logo.svg" alt="" width="28" height="28"><span>SeekSync</span></a>
    <p class="small" data-i18n="{foot}">Free and open source, GPL-3.0. Not affiliated with SoundCloud, Spotify, Soulseek, Nicotine+ or Rekordbox.</p>
    <p class="small"><a href="https://github.com/Stormhoogervorst/seeksync">GitHub</a> · <a href="https://github.com/Stormhoogervorst/seeksync/issues" data-i18n="{issues}">Issues</a> · <a href="https://github.com/Stormhoogervorst/seeksync/blob/main/CHANGELOG.md" data-i18n="{changelog}">Changelog</a></p>
  </div>
</footer>

<script src="i18n.js"></script>
<script src="guide.js"></script>
</body>
</html>
"""


def build():
    skip = key("", "Naar de inhoud")
    n_how = key("", "Hoe het werkt")
    n_feat = key("", "Functies")
    n_dl = key("", "Download")
    n_guide = key("", "Handleiding")
    eyebrow = key("", "Handleiding")
    h1 = key("", "Van installatie tot je eerste tracks")
    lede = key("", "Deze handleiding loopt van begin tot eind met je door SeekSync: installeren, verbinden met Soulseek, kanalen toevoegen, de lijst lezen en elke instelling. De screenshots komen uit de app met verzonnen voorbeelddata.")
    toc = key("", "Inhoud")
    end_h = key("", "Klaar?")
    end_p = key("", "Download SeekSync, voeg je eerste kanaal toe en laat het zijn werk doen.")
    end_btn = key("", "Download SeekSync")
    foot = key("", "Gratis en open source, GPL-3.0. Niet verbonden aan SoundCloud, Spotify, Soulseek, Nicotine+ of Rekordbox.")
    issues = key("", "Issues")
    changelog = key("", "Wijzigingen")

    toc_items = []
    body = []
    for n, (sid, en, nl, blocks) in enumerate(SECTIONS, 1):
        k = key(en, nl)
        toc_items.append(f'          <li><a href="#{sid}" data-i18n="{k}">{en}</a></li>')
        body.append(f'      <section class="doc-sec" id="{sid}">\n        <h2><span class="n">{n}</span><span data-i18n="{k}">{en}</span></h2>\n        '
                    + "\n        ".join(blocks) + "\n      </section>")
    html_out = HEAD.format(skip=skip, n_how=n_how, n_feat=n_feat, n_dl=n_dl, n_guide=n_guide, eyebrow=eyebrow, h1=h1, lede=lede,
                           toc=toc, toc_items="\n".join(toc_items)) + "\n".join(body) + TAIL.format(
        end_h=end_h, end_p=end_p, end_btn=end_btn, foot=foot, issues=issues, changelog=changelog)
    (SITE / "guide.html").write_text(html_out, "utf-8")

    js = ('/* Generated by scripts/build_guide.py: the Dutch text of the guide page. Do not edit by hand. */\n'
          '(function () {\n  "use strict";\n  var NL = ' + json.dumps(NL, ensure_ascii=False, indent=2) + ';\n'
          '  var toc = document.querySelector(".toc details");\n'
          '  if (toc && window.matchMedia && !window.matchMedia("(min-width: 981px)").matches) toc.open = false;\n'
          '  SeekSyncI18n.init({\n    nl: NL,\n    titleNl: "SeekSync handleiding: van installatie tot je eerste tracks",\n'
          '    descNl: "Een stap-voor-stap handleiding voor SeekSync: installeren, verbinden met Soulseek, SoundCloud-kanalen en Spotify-playlists toevoegen, de tracklijst lezen, regels en instellingen, en Rekordbox gebruiken."\n  });\n})();\n')
    (SITE / "guide.js").write_text(js, "utf-8")
    print(f"guide.html: {len(SECTIONS)} sections, {len(NL)} texts; guide.js written")


if __name__ == "__main__":
    build()
