# Roadmap: nieuwe functies stap voor stap (voor Claude Code)

Nov 8, 2026 · @Storm

## Zo werkt Claude Code met dit document

Bouw de stappen in deze volgorde, één stap per sessie, en ga pas door als alles onder "Klaar als" klopt. Exporteer dit document als Markdown en zet het als `ROADMAP.md` in de hoofdmap van de app, naast `CLAUDE.md`.

Werkregels voor elke stap:

1. Lees eerst `ROADMAP.md` en `CLAUDE.md`. Werk alleen aan de stap die gevraagd wordt.
2. Kijk eerst wat er al in de code zit. Bestaat een functie al gedeeltelijk, breid die dan uit in plaats van iets nieuws ernaast te bouwen.
3. Schrijf een kort plan: welke bestanden, welk datamodel, welke tests. Wacht op akkoord voordat je bouwt.
4. Schrijf tests met nepbestanden en nepresultaten. Tests doen nooit echte netwerkverzoeken naar SoundCloud of Soulseek.
5. Nieuwe externe programma's (ffmpeg, fpcalc) zijn optioneel. Ontbreken ze, dan blijft de app werken en toont hij een duidelijke melding.
6. Een keuze met grote gevolgen, zoals een nieuwe afhankelijkheid of een wijziging in de database, leg je eerst voor.
7. Na de stap: draai alle tests, probeer het met een echte track, vink de punten onder "Klaar als" af in `ROADMAP.md` en maak een commit met de naam van de stap.

Prompt om een stap te starten:

```
Lees ROADMAP.md en CLAUDE.md. Werk aan stap <nummer>: <naam>.
Maak eerst een kort plan op basis van de huidige code en wacht op mijn akkoord.
Bouw daarna, test, en vink de stap af in ROADMAP.md.
```

## Stap 0: inventarisatie van de huidige app

**Status: klaar (nov 2026).** Soulseek: twee routes, eigen login via aioslsk (`soulseek.py`) of via Nicotine+ met de meegeleverde plugin (`nicotine.py`), te kiezen in de instellingen. Geen slskd. Stap 4 en 8 moeten via beide routes werken.

Doel: Claude Code weet hoe de app nu werkt en welke functies uit deze roadmap er al (deels) zijn, voordat er iets gebouwd wordt.

Bouwen:

- Breng in kaart waar zoeken op SoundCloud, playlists ophalen, titels opschonen, matchen, zoeken en downloaden op Soulseek, opslag en de interface zitten.
- Schrijf dit kort op in `CLAUDE.md` onder "Architectuur": per onderdeel het bestand en wat het doet.
- Loop alle stappen in dit document langs en zet achter elke stap: bestaat al, bestaat deels of bestaat niet. Bij "deels": wat er mist.
- Noteer hoe de app met Soulseek praat (eigen login, slskd of Nicotine+). Stap 4 en 8 hangen daarvan af.

Klaar als:

- [x] `CLAUDE.md` beschrijft de architectuur in hooguit een halve pagina.
- [x] Elke stap in `ROADMAP.md` heeft een status: bestaat al, deels of niet.
- [x] Er is niets aan de code veranderd.

## Fase 1: betrouwbaarheid

Na deze fase komt er alleen nog gecontroleerde muziek in de map van de DJ: geen kapotte bestanden, geen nep-FLAC, en bij elke ontbrekende track een reden.

### Stap 1: staging-map, pas publiceren als alles klopt

**Status: klaar (nov 2026).** Downloads gaan van `incoming` naar `staging/<track>/` in de app-data, langs de controles in `Engine.checks` (stap 2, 3 en 10 haken daar in) en worden dan in één keer gepubliceerd (`publish_file`: rename, of bij een andere schijf kopiëren naar een verborgen `.…seekdrop-part` en dan hernoemen). Bij het opstarten worden `staging` en `.seekdrop-part`-resten opgeruimd, en na het herstel van transfers ook `incoming`. Getest met een echte playlist via Nicotine+.

Doel: half gedownloade of afgekeurde bestanden komen nooit in de muziekmap terecht. De watch folder van Rekordbox of Serato pikt anders halve bestanden op.

Bouwen:

- Downloads gaan eerst naar een staging-map in de app-data, niet naar de muziekmap.
- Pas na alle controles (stap 2 en 3) en het taggen (stap 10) wordt het bestand in één keer verplaatst naar de muziekmap.
- Bij het opstarten ruimt de app achtergebleven bestanden in staging op.

Klaar als:

- [x] Een afgebroken download laat niets achter in de muziekmap.
- [x] Een bestand verschijnt in één keer, met de definitieve naam.
- [x] Een test bewijst beide punten.

### Stap 2: bestandscontrole en quarantaine

**Status: klaar (nov 2026).** `checks.py` (ffprobe + één ffmpeg-decode met `silencedetect`, ±0,5 s per track) controleert decodeerbaarheid, afkappen, formaat tegen extensie, lengte tegen SoundCloud (instelbaar, standaard 10 s; een *Extended*-bestand mag langer zijn) en stilte aan begin of eind (instelbaar, standaard 10 s). Afgekeurd gaat naar `quarantine/` in de app-data en in de tabel `rejects`, die ook dient als blokkeerlijst (peer + bestand per track). In de interface: filter *Quarantine* met *Approve anyway* en *Delete*. ffmpeg wordt ook gezocht in `/opt/homebrew/bin` en `/usr/local/bin`, omdat macOS-apps het shell-PATH niet krijgen. Getest met echte tracks via Nicotine+.

Doel: kapotte, afgekapte of verkeerde bestanden worden tegengehouden, met een reden die de gebruiker kan lezen.

Bouwen:

- Controle met `ffprobe` en `ffmpeg`: het bestand is helemaal te decoderen, het formaat klopt met de extensie, de lengte wijkt niet meer af dan een instelbare marge van de lengte op SoundCloud, en er zit geen lange stilte aan begin of eind (`silencedetect`).
- Afgekeurde bestanden gaan naar een quarantainemap, met de reden in de database. De gebruiker kan ze bekijken, toch goedkeuren of verwijderen.
- Na afkeuren zet de app deze combinatie van gebruiker en bestand op een blokkeerlijst voor deze track en probeert de volgende kandidaat.

Klaar als:

- [x] Tests met een afgekapt bestand, een bestand met 30 seconden stilte en een MP3 met .flac-extensie worden alle drie afgekeurd, elk met een eigen reden.
- [x] Zonder ffmpeg werkt de app nog, slaat de controle over en toont dat in de instellingen.

### Stap 3: nep-lossless herkennen

**Status: klaar (nov 2026).** `checks.measure_cutoff` decodeert 4 stukken van 8 s (mono, 44,1 kHz), middelt het spectrum met numpy en zoekt van boven naar beneden een klif van 25 dB binnen ±1 kHz. Lossless: klif onder 19,5 kHz = nep (naar quarantaine), 19,5–20,8 kHz = verdacht, geen klif of daarboven = echt. MP3 die zegt ≥300 kbps te zijn: onder 18,5 kHz nep, onder 19,5 kHz verdacht. Instelling *suspect_quality*: verdacht met label doorlaten (standaard) of afkeuren. Opgeslagen in `tracks.cutoff_hz` en `tracks.quality`, zichtbaar per track ("Full range", "21.1 kHz", "Suspect: stops at 20.3 kHz"). 0,15–0,5 s per track. Op 11 echte Soulseek-downloads: alle FLAC's echt (21–22 kHz), alle 320 kbps-MP3's echt (≈20,3 kHz).

Doel: een MP3 die is omgezet naar FLAC of WAV wordt herkend. Op een clubsysteem hoor je het verschil, en het is een veelvoorkomend probleem op Soulseek.

Bouwen:

- Spectrumanalyse: decodeer een paar stukken van het bestand naar PCM en bepaal met een FFT tot welke frequentie er nog energie zit.
- Echte lossless loopt door tot ongeveer 22 kHz. Een harde afkapping rond 16, 19 of 20 kHz wijst op een omgezette MP3 van ongeveer 128, 192 of 320 kbps.
- Doe hetzelfde voor MP3's die zeggen 320 kbps te zijn maar bij 16 kHz afkappen.
- Resultaat: echt, verdacht of nep, met de gemeten afkapfrequentie. Een instelling bepaalt of verdachte bestanden worden afgekeurd of met een label worden doorgelaten.

Klaar als:

- [x] Tests met zelf gegenereerde signalen (ruis, ruis met een laagdoorlaatfilter op 16 kHz en op 19,5 kHz) worden juist ingedeeld.
- [x] Een gemeten afkapfrequentie is per track zichtbaar in de interface.
- [x] De analyse kost minder dan 5 seconden per track.

### Stap 4: kwaliteitsprofielen en automatisch upgraden

**Status: klaar (nov 2026), op één punt na.** `quality.py`: ladder (FLAC 24, FLAC 16, WAV/AIFF, MP3 320/256/192) en drie profielen (Club, Balanced, Space saver) met ondergrens en doel; vervangt de oude instellingen (worden automatisch omgezet). De matching weigert kandidaten onder de ondergrens; na de download meet `checks.measured_tier` wat het bestand echt is (verdacht lossless telt als MP3 320) en weigert het onder de ondergrens. Tracks onder het doel (alleen lossy) krijgen `next_upgrade` en worden dagelijks opnieuw gezocht tot 30 dagen; alleen gemeten betere kopieën die stap 2 en 3 doorstaan tellen. Instelling *upgrade_mode*: eerst vragen (standaard, *Replace*/*Keep* in de lijst), automatisch, of uit. Het oude bestand gaat naar `trash/` in de app-data (30 dagen). Kolommen `tier`, `next_upgrade`, `upgrade_path`, `upgrade_tier`. Echt getest via Nicotine+: FLAC 16-bit kwam binnen zonder vervolg, MP3 320 kreeg een upgrade-zoektocht die een betere kopie vond (die bleef in de wachtrij van de peer); onderweg werden in het echt een nep-320 en bestanden met de verkeerde lengte tegengehouden. Nog open: de optie "alleen upgraden als de track nog niet in de DJ-software staat" volgt in stap 12.

Doel: de DJ kiest welke kwaliteit hij wil. Een verse drop komt eerst binnen in de beste beschikbare kwaliteit, en wordt later vervangen als er iets beters opduikt.

Bouwen:

- Een profiel is een gerangschikte ladder, bijvoorbeeld FLAC 24-bit, FLAC 16-bit, WAV/AIFF, MP3 320, MP3 256, met een ondergrens (minimaal acceptabel) en een doel (daarna stoppen met zoeken).
- Drie standaardprofielen: Club (lossless, ondergrens MP3 320), Gebalanceerd (doel MP3 320) en Ruimtebesparend.
- Tracks onder het doel komen op een upgradelijst en worden minder vaak opnieuw gezocht, bijvoorbeeld dagelijks tot 30 dagen.
- Een upgrade vervangt alleen als het nieuwe bestand gemeten beter is en stap 2 en 3 doorstaat. Het oude bestand gaat naar een prullenbakmap in de app, niet direct weg.

Let op: Rekordbox en Serato koppelen cue points aan het pad van het bestand. Een upgrade van .mp3 naar .flac verandert dat pad, waardoor de DJ zijn cues kwijtraakt. Geef daarom een instelling: automatisch upgraden, eerst vragen, of alleen upgraden als de track nog niet in de DJ-software staat (zie stap 12).

Klaar als:

- [x] Een track die als MP3 320 binnenkwam, wordt in een test vervangen door een gevonden FLAC, en de MP3 staat in de prullenbak.
- [x] Een slechtere of nep-lossless kandidaat vervangt nooit een bestaand bestand.
- [x] De drie standaardprofielen staan in de instellingen.

### Stap 5: uitleg waarom niet, en zelf kiezen

**Status: klaar (nov 2026).** `matching.score_candidate` geeft elke afwijzing een leesbare reden (`Candidate.rejected`) en een fase (hoe dicht bij een match); `closest()` kiest de 10 dichtstbijzijnde, `summary()` maakt er één regel van. Per zoekpoging slaat de engine zoektermen met aantallen en de 10 kandidaten op (tabel `searches`, laatste 3 per track). De reden in de lijst is nu concreet ("No results for …", "54 results, none matched: closest was 3:54 long, expected 5:50 (radio edit?)"). Paneel *Why not?* met *Download this anyway* (gaat door staging en stap 2/3), *Search with another term* (bewaard in `tracks.custom_query`, voortaan als eerste geprobeerd) en *Stop looking*. Echt getest via Nicotine+: DC01 toonde per kandidaat de reden; een zelf gekozen AIFF werd gedownload en door de lengtecontrole naar quarantaine gestuurd.

Doel: bij elke track die niet binnenkomt, ziet de DJ waarom, en kan hij zelf een kandidaat kiezen of de zoekterm aanpassen.

Bouwen:

- Sla per zoekpoging op: de zoektermen, het aantal resultaten en de beste 10 kandidaten met de reden van afwijzing, zoals "192 kbps, onder de ondergrens", "3:12 lang, verwacht 6:45 (radio-edit?)" of "remix van iemand anders".
- In de interface: per track een knop "Waarom niet?" met die lijst.
- Acties: "Download deze toch" (gaat nog steeds door stap 2 en 3), "Zoek met andere term" en "Niet meer zoeken".

Klaar als:

- [x] Elke track zonder download toont minstens één concrete reden.
- [x] Een handmatig gekozen kandidaat wordt gedownload en gecontroleerd.
- [x] Een aangepaste zoekterm blijft bewaard voor volgende pogingen.

## Fase 2: matching en Soulseek

Na deze fase vindt de app meer van de juiste tracks, pakt hij minder vaak de verkeerde versie, en gedraagt hij zich netjes op het Soulseek-netwerk.

### Stap 6: slimmere matching

**Status: klaar (nov 2026).** Alle vergelijkingsregels staan in `matching.py`: `version_of()` maakt van een versie een soort plus remixer (Original, Extended, Radio Edit, Remix/Rework/Refix/Flip, VIP, Dub, Bootleg, Edit, Instrumental, Acapella) en `version_conflict()` beslist: Extended mag voor Original, dezelfde remixer met remix/rework mag, een andere remixer of een ander soort nooit ("Larse Vocal" is niet "Larse VIP"). `titles.normalize` zet andere schriften om naar Latijn met `anyascii` (nieuwe afhankelijkheid, ISC) en voegt afkortingen samen ("A.B.C." → abc); bij niet-Latijnse titels wordt eerst in het originele schrift gezocht. Shows met een datum of "@ locatie" in de titel worden als set herkend. Aliassen per artiest in Settings (`artist_aliases`): extra zoekopdrachten en een bestand onder een alias telt als de artiest. Handmatige correcties per track (`fix_artist`, `fix_title`, `fix_version`, via *Why not?*) gaan voor de automatische opschoning. `tests/test_matching_real.py`: 34 echte titels en 12 shows van soundcloud.com/silvabumpa plus 21 versiegevallen. Echt getest via Nicotine+: bij *Larse VIP* zijn nu alle 10 beste kandidaten echte VIP-bestanden (in stap 5 waren dat nog *Larse Vocal*).

Doel: minder gemiste tracks door schrijfwijzen en aliassen, en nooit de verkeerde versie.

Bouwen:

- Versiebewuste vergelijking: Original, Extended, Radio Edit, Remix van X, VIP, Dub, Bootleg en Edit zijn aparte versies. Extended mag voor Original, een remix van iemand anders nooit.
- Normaliseren van accenten, hoofdletters, "&" en "and", "feat." en "ft.", en schriften (bijvoorbeeld Cyrillisch of Japans naar Latijn) voordat er vergeleken wordt.
- Aliassen per artiest, door de gebruiker in te stellen: een producer met meerdere namen wordt onder elk van die namen gezocht.
- Handmatige correcties per track (artiest, titel, versie) gaan altijd voor de automatische opschoning.
- Zet alle matchregels in één module met een eigen testbestand vol echte voorbeeldtitels.

Klaar als:

- [x] Minstens 30 echte SoundCloud-titels uit de kanalen van de gebruiker staan in de tests, met de verwachte artiest, titel en versie.
- [x] Een alias en een handmatige correctie werken in een test van begin tot eind.

### Stap 7: AcoustID als extra controle (optioneel)

**Status: bestaat niet.**

Doel: een extra check dat het gedownloade bestand echt de gezochte track is.

Bouwen:

- Fingerprint met `fpcalc` (Chromaprint) en opzoeken via de AcoustID-API. Daarvoor is een gratis API-sleutel nodig.
- Gebruik het als signaal, niet als harde eis. Verse SoundCloud-drops staan vaak nog niet in de AcoustID-database. Geen resultaat is dus geen afkeuring. Een duidelijk andere track wel.

Klaar als:

- [ ] Een bestand dat volgens AcoustID een andere artiest en titel is, gaat naar quarantaine met die reden.
- [ ] Zonder `fpcalc` of zonder API-sleutel slaat de app deze stap over.

### Stap 8: netjes op Soulseek

**Status: klaar (nov 2026).** `politeness.py`: `SearchThrottle` (vaste wachttijd, standaard 8 s en minimaal 4 s, en maximaal 20 zoekopdrachten per 5 minuten; instelbaar maar nooit onder de ondergrens) voor zowel de gewone zoektocht als de upgradezoektocht. Schijfruimte: onder `min_free_gb` (standaard 5) starten er geen nieuwe downloads en toont de interface een melding; zodra er ruimte is, gaat het vanzelf door. Reputatie: tabel `peer_stats` (gelukt, mislukt, nep); mislukt, vastgelopen of wachtrij te lang telt als mislukt, een nep-lossless of nep-320 als nep. Score: −30 per nep, −8 per mislukking, bonus voor betrouwbare peers. Blokkade van 30 dagen bij 3× nep of 5× mislukt zonder succes, met de reden in "Why not?" en een knop *Unblock* in Settings. EP/album: een kandidaat uit dezelfde map van dezelfde peer als eerdere tracks uit die playlist (of van dezelfde artiest) krijgt +12, dezelfde peer +6; een voorkeur, geen eis, want de platte SoundCloud-lijsten hebben geen albuminfo. Waarschuwing bij niets delen: eigen login uit de instellingen en de inhoud van de gedeelde mappen, Nicotine+ via plugin 0.5.1 (`shared_folders` in `/status`, getest tegen de Nicotine+ 3.3.11-kern; het aantal bestanden is niet beschikbaar zonder de eigen scan van Nicotine+, dus alleen mappen tellen).

Doel: geen bans, minder mislukte downloads, en geen volle schijf.

Bouwen:

- Zoekopdrachten afremmen: een vaste wachttijd tussen zoekopdrachten en een maximum per paar minuten, instelbaar maar met een veilige standaard.
- Reputatie per gebruiker onthouden: snel en betrouwbaar telt mee in de score, vaak mislukt of nep-lossless geleverd telt tegen, met een automatische blokkeerlijst na herhaalde problemen.
- Een EP of album uit een playlist bij voorkeur in zijn geheel van één gebruiker halen, zodat de bestanden bij elkaar passen.
- Bewaking van vrije schijfruimte: onder een instelbare grens pauzeren de downloads en krijgt de gebruiker een melding.
- Een duidelijke waarschuwing in de app als de gebruiker niets deelt. Wie niets deelt, wordt op Soulseek vaak geblokkeerd.

Klaar als:

- [x] Tests laten zien dat de afremming en de schijfruimtegrens werken.
- [x] Een gebruiker die twee keer nep-lossless leverde, staat in een test onderaan de ranglijst.

### Stap 9: regels per kanaal

**Status: klaar (nov 2026), op één punt na.** `rules.py` met `check()` (alle regels op één plek, de reden komt terug als tekst) en een regelpaneel per kanaal of playlist (knop *Rules* in de kanaalbalk, met een samenvatting). Per kanaal: kortste en langste lengte (standaard 2 tot 12 minuten, 0 = geen grens), remixes wel of niet (remix, rework, refix, flip en bootleg; VIP, dub en edit blijven altijd toegestaan), previews en clips overslaan, mixes en radioshows overslaan, trefwoorden die uitsluiten, trefwoorden waarvan er minstens één verplicht is, en reposts. Globaal in Settings: een blokkeerlijst van woorden en artiesten die altijd wint. Overgeslagen tracks blijven in *Skipped* met de regel als reden (`tracks.skip_rule`, `channels.rules`) en *Get it* haalt ze toch op en blijft gelden bij latere wijzigingen. Wijzig je regels, dan komen tracks die nu wel mogen terug en worden nog niet gezochte tracks die niet meer mogen overgeslagen (`Engine.reapply_rules`); downloads, lopende tracks en wat je zelf overgeslagen hebt blijven met rust. De oude vaste regels (10 minuten, mixen) zijn nu de standaardregels; bestaande overgeslagen tracks zijn omgezet. Nog niet echt getest met een echt kanaal.

Doel: alleen downloaden wat de DJ wil. SoundCloud-kanalen uploaden ook mixen van een uur, podcasts, previews en snippets.

Bouwen:

- Per kanaal of playlist: minimale en maximale lengte (standaard bijvoorbeeld 2 tot 12 minuten), remixes wel of niet, reposts wel of niet, previews en clips overslaan.
- Trefwoorden die een track uitsluiten ("mix", "podcast", "live at") of juist verplicht maken.
- Een globale blokkeerlijst van trefwoorden en artiesten.
- Overgeslagen tracks blijven zichtbaar met de regel die ze tegenhield, zodat de gebruiker ze toch kan ophalen.

Klaar als:

- [x] Een mix van 58 minuten en een clip van 30 seconden worden in een test overgeslagen, elk met de juiste regel als reden.
- [x] Regels zijn per kanaal in te stellen en te wijzigen in de interface.

## Fase 3: collectie en DJ-software

Na deze fase komen tracks netjes getagd binnen, downloadt de app niets wat de DJ al heeft, en staan nieuwe tracks direct klaar in Rekordbox of Serato.

### Stap 10: tags, artwork en bestandsnamen

**Status: klaar (nov 2026), op één punt na.** `tagging.py` schrijft na alle checks en vóór de publicatie (`Engine.finish_file`, ook voor upgrades en *Approve anyway*): MP3 ID3v2.3, AIFF en WAV ID3 in het bestand, FLAC Vorbis-comments plus een plaatje, M4A MP4-tags. Artiest, titel met versie ("Track (Extended Mix)"), genre, jaar (releasedatum, anders uploaddatum), de SoundCloud-link als commentaar, en optioneel het kanaal als label (`label_from_channel`, alleen voor profielen). SoundCloud geeft geen label of album, dus het album blijft leeg. Wat de uploader zelf inbedde (BPM, toonsoort) blijft staan. Hoes: SoundCloud-artwork op 500 px (alleen van `sndcdn.com`, time-out en groottegrens); een bestaande hoes van minstens 500 px blijft. Een fout bij het taggen houdt een goed bestand niet tegen. `wav_to_aiff` (standaard uit): zuiver Python, 16/24/32 bit integer-PCM, byte-voor-byte dezelfde samples (ook EXTENSIBLE-headers); float en 8 bit blijven WAV. Sjabloon `filename_template` (standaard `{channel}/{artist} - {title} ({version})`, ook `{year}` en `{genre}`) met een voorbeeld in de instellingen; het oude vinkje "map per kanaal" is omgezet. Kolom `tracks.sc_meta` (genre en releasedatum van SoundCloud); `mutagen` staat nu in `pyproject.toml` (zat al in de build via aioslsk). Echt getest: artwork van een publieke SoundCloud-track (500×500) in een MP3, FLAC en AIFF. **Nog niet getest:** een volledige download van Soulseek met tags in de muziekmap, en de bestanden in Rekordbox of Serato zelf.

Doel: DJ-software toont de juiste artiest, titel, versie, label en hoes, ongeacht hoe slordig het bestand op Soulseek heette.

Bouwen:

- Tags schrijven met `mutagen`: artiest, titel met versie erin ("Track (Extended Mix)", zoals DJ's gewend zijn), release, label, genre, jaar, de hoes ingebed (minimaal 500 bij 500 pixels) en de SoundCloud-link als commentaar.
- Voor MP3 ID3v2.3 gebruiken, omdat DJ-software dat het best ondersteunt. AIFF krijgt ID3 in het bestand zelf.
- WAV ondersteunt tags slecht in DJ-software. Geef een instelling om WAV automatisch om te zetten naar AIFF. Dat is ook lossless, met dezelfde audio.
- Geen BPM of toonsoort berekenen: dat doet de DJ-software zelf beter.
- Sjablonen voor map- en bestandsnamen, bijvoorbeeld `{kanaal}/{artiest} - {titel} ({versie})`, met een voorbeeld in de instellingen.

Klaar als:

- [x] Een getest MP3-, FLAC- en AIFF-bestand hebben na afloop de juiste tags en hoes, gecontroleerd met mutagen.
- [x] Een WAV wordt met de instelling aan omgezet naar AIFF zonder kwaliteitsverlies (zelfde PCM-data).

### Stap 11: kijken of de DJ de track al heeft

**Status: klaar (nov 2026), op één punt na.** `library.py` en de tabel `library`: instelling `library_dirs` (mappen die je al hebt; de downloadmap van SeekDrop telt altijd mee), een index per audiobestand (mp3, flac, wav, aiff, m4a, ogg, opus) met artiest, titel, versie, lengte, formaat, bitrate en kwaliteitsniveau, uit de tags of anders uit de bestandsnaam (tracknummers vooraf worden genegeerd). Eerste scan volledig, daarna alleen nieuwe en gewijzigde bestanden (grootte en wijzigingstijd); een map die niet bereikbaar is (losse schijf) houdt zijn rijen, een map die je uit de lijst haalt verliest ze. Herkenning (`library.find`): zelfde titel, artiest (of alias) en versie volgens dezelfde regels als de Soulseek-matching, en een lengte die niet meer dan 25% (en 20 s) afwijkt, behalve tussen Original en Extended. Een nieuwe track die er al is, krijgt de status `collected` (*Already in your collection*, met pad, *Show file* en *Get it anyway*), wordt niet gezocht en niet gedownload; na elke scan worden wachtende tracks opnieuw vergeleken en keert een track terug naar *wanted* als het bestand weg is. Zoeken wacht tot de scan klaar is, en een net gepubliceerd bestand staat meteen in de index (dezelfde track via een tweede kanaal wordt dus ook herkend). Tabbladen *In collection* en *Duplicates*: groepen van dezelfde artiest, titel en versie in de downloadmap, de beste kopie gemarkeerd (volgens je kwaliteitsprofiel), niets wordt verwijderd of verplaatst. Geen vingerafdruk (volgt met stap 7). Echt getest op `~/Music`: 290 bestanden in 0,7 s, tweede scan 0,00 s en niets opnieuw gelezen, een echte titel met tracknummer herkend. **Nog niet getest:** de hele keten met een echt kanaal in de draaiende app.

Doel: nooit downloaden wat al in de collectie staat, en geen dubbele bestanden.

Bouwen:

- De gebruiker kiest een of meer muziekmappen. De app scant die en houdt een index bij van artiest, titel, versie, lengte en eventueel fingerprint.
- Voor elke nieuwe track eerst in die index zoeken. Gevonden: status "Al in je collectie", met het pad.
- Scannen gebeurt de eerste keer volledig en daarna alleen op gewijzigde bestanden.
- Een overzicht van dubbele bestanden in de eigen downloads, met de beste versie gemarkeerd. Niets automatisch verwijderen.

Klaar als:

- [x] Een track die al in de muziekmap staat onder een iets andere naam, wordt in een test herkend en niet gedownload.
- [x] Een tweede scan van 10.000 ongewijzigde bestanden duurt maar een paar seconden.

### Stap 12: koppeling met DJ-software

**Status: deels (nov 2026): alleen Rekordbox gebouwd.** `rekordbox.py` schrijft een Rekordbox-XML (`DJ_PLAYLISTS`) met elke gedownloade track die nog op schijf staat en een playlist per kanaal of playlist, in een map "SeekDrop". Attributen en de codering van `Location` (`file://localhost/…` met de veilige tekenset van Rekordbox zelf) zijn gecontroleerd tegen de namen in de geïnstalleerde Rekordbox 7. Instellingen `rekordbox_export` (standaard uit) en `rekordbox_xml_path` (standaard `SeekDrop for Rekordbox.xml` in de downloadmap); het bestand wordt ~30 s na een download, upgrade, goedkeuring of verwijderd kanaal opnieuw geschreven (één keer voor een reeks), atomisch (tijdelijk bestand, dan hernoemen; bij een fout blijft het oude staan). Knoppen *Update now* en *Show file* en de stappen voor Rekordbox staan in Settings. Alleen eigen downloads, niet wat al in je collectie stond. Rekordbox' eigen database wordt nooit aangeraakt. **Niet gebouwd:** M3U, Serato-crates en Traktor (op verzoek overgeslagen), en "alleen upgraden als de track niet in Rekordbox staat" (nodig: een Rekordbox-export lezen; `rekordbox.read` kan dat al).

Doel: nieuwe tracks staan zonder handwerk in de DJ-software, per kanaal of playlist gegroepeerd. Dit is het sterkste verkoopargument richting DJ's.

Bouwen, in deze volgorde:

1. M3U-playlist per kanaal en per playlist, automatisch bijgewerkt. Werkt in vrijwel alle DJ-software.
2. Rekordbox: een XML-bestand met tracks en playlists dat Rekordbox kan inlezen via Voorkeuren, Geavanceerd, "rekordbox xml".
3. Serato: crates schrijven in de map `_Serato_/Subcrates`.
4. Pas daarna eventueel Traktor (NML).

- Bijhouden welke tracks al in de DJ-software staan. Stap 4 gebruikt dat om bij upgrades geen cue points te breken.
- Nooit de database van de DJ-software zelf aanpassen. Alleen bestanden schrijven die de software zelf inleest.

Klaar als:

- [ ] M3U, Rekordbox-XML en een Serato-crate worden in tests geschreven en weer ingelezen met dezelfde inhoud. (Rekordbox-XML: ja, 21 tests; M3U en Serato: niet gebouwd.)
- [ ] De gebruiker heeft de koppeling handmatig getest in Rekordbox en Serato. (Nog niet: kan alleen de gebruiker.)

### Stap 13: meldingen

**Status: bestaat niet.** Er zijn alleen meldingen in de app zelf (activiteitenlijst en korte pop-ups) en een melding bij een nieuwe versie.

Doel: de DJ weet wat er binnenkwam zonder de app te openen.

Bouwen:

- Meldingen via de melding van het besturingssysteem, Telegram en een Discord-webhook.
- Per soort in te stellen: nieuwe track binnen, upgrade gedaan, track niet gevonden na de laatste poging, verbinding met Soulseek kwijt.
- Een dagelijkse samenvatting als alternatief voor losse meldingen.

Klaar als:

- [ ] Elke soort melding is te testen met een knop "Stuur testmelding".
- [ ] Tokens en webhook-URL's komen niet in logbestanden.

### Stap 14: back-up en instellingen meenemen

**Status: bestaat niet.** Wel: bij een naamswijziging neemt de app de oude gegevensmap over.

Doel: een nieuwe computer of een kapotte database kost de DJ niet zijn kanalen, regels en geschiedenis.

Bouwen:

- Automatische back-up van database en instellingen, bijvoorbeeld wekelijks, met de laatste 5 bewaard.
- Exporteren en importeren van kanalen, regels en instellingen als één bestand, zonder wachtwoorden.
- Herstellen vanuit een back-up via de interface.

Klaar als:

- [ ] Een export op computer A en een import op computer B leveren dezelfde kanalen en regels op.
- [ ] Een back-up herstellen werkt in een test.

## Fase 4: meer bronnen

Na deze fase werkt de app niet alleen met SoundCloud, maar ook met playlists uit bestanden, Spotify en Beatport. Daarmee groeit de doelgroep.

### Stap 15: playlists uit bestanden

**Status: bestaat niet.**

Doel: elke lijst met tracks kan de app in, zonder afhankelijk te zijn van een externe API.

Bouwen:

- Importeren van CSV, TSV, TXT (één "Artiest - Titel" per regel) en M3U.
- Bij CSV laat de app de gebruiker kiezen welke kolom artiest, titel en versie is.
- Een geïmporteerde lijst gedraagt zich als een kanaal: dezelfde regels, retries en export naar DJ-software.

Klaar als:

- [ ] Een CSV-export van Rekordbox en een TXT-lijst worden in tests goed ingelezen.

### Stap 16: Spotify-playlists

**Status: bestaat niet.**

Doel: een DJ plakt een Spotify-playlistlink en de app haalt de tracks op via Soulseek.

Bouwen:

- Ophalen via de officiële Spotify Web API met een eigen app-registratie.
- Controleer eerst de actuele API-voorwaarden. Voor zover bekend kunnen nieuwe apps sinds eind 2024 de eigen redactionele en algoritmische playlists van Spotify niet meer ophalen, wel playlists van gebruikers.
- Playlists opnieuw controleren op nieuwe tracks, net als een SoundCloud-kanaal.

Klaar als:

- [ ] Een openbare playlist van een gebruiker wordt ingelezen met artiest, titel, versie en lengte.
- [ ] Een playlist die niet op te halen is, geeft een duidelijke melding met de reden.

### Stap 17: Beatport-charts

**Status: bestaat niet.**

Doel: de top 100 van een genre of de chart van een DJ volgen. Voor DJ's waarschijnlijk de waardevolste bron na SoundCloud.

Bouwen:

- Beatport heeft geen open API. Zoek eerst uit wat de voorwaarden toestaan voordat je pagina's automatisch uitleest.
- Begin met de veiligste versie: de gebruiker plakt een chartlink of de tracklijst, en de app leest die in.
- Neem van Beatport ook de koopknop over (zie stap 18).

Klaar als:

- [ ] Er is een korte notitie in `CLAUDE.md` over wat Beatport toestaat.
- [ ] Een geplakte chart wordt ingelezen als lijst, met dezelfde regels als een kanaal.

### Stap 18: legale route naast Soulseek

**Status: bestaat niet.** De app downloadt nooit audio van SoundCloud. De officiële download- en kooplink worden nog niet uitgelezen of getoond.

Doel: als het kan, krijgt de DJ de track via een officiële weg. Dat is beter voor de artiest en verkleint het juridische risico van het product.

Bouwen:

- Heeft de artiest op SoundCloud de downloadknop aangezet, dan gebruikt de app die officiële download eerst, in plaats van Soulseek.
- Toon de koop- of downloadlink die de artiest bij de track zette (vaak Bandcamp, Beatport of een free-download-pagina) als knop "Kopen" of "Gratis download".
- Geen audio rippen van de stream van SoundCloud of andere diensten.

Klaar als:

- [ ] Een track met officiële download wordt in een test via die route opgehaald, en Soulseek wordt dan niet gebruikt.
- [ ] Tracks met een koop- of downloadlink tonen die knop in de interface.

## Buiten scope

Deze functies uit SoulSync bouwen we bewust niet. Stelt een sessie voor om er een toe te voegen, dan eerst overleggen.

- Audio rippen van Tidal, Qobuz, Deezer, Amazon Music, YouTube of de stream van SoundCloud: in strijd met de voorwaarden van die diensten, en een juridisch risico voor een betaald product.
- Torrent en Usenet: zelfde risico, en niet de doelgroep.
- Video, films en series, podcasts en audioboeken.
- Mediaservers (Plex, Jellyfin, Navidrome), scrobbelen, een webspeler, aanbevelingen, luisterstatistieken en jaaroverzichten: dat is voor thuisluisteraars, niet voor DJ's.
- Chat en spelletjes voor Soulseek-rooms.
- Een visuele bouwer voor automatiseringen: goede standaardinstellingen en regels per kanaal (stap 9) zijn genoeg.

Gebaseerd op de README van [SoulSync](https://github.com/Nezreka/SoulSync).
