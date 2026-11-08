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

**Status: deels.** Downloads komen al eerst in een `incoming`-map in de app-data en worden daarna naar de muziekmap verplaatst (`engine._finalize`). Mist: controles en taggen vóór het verplaatsen, opruimen van achtergebleven bestanden in `incoming` bij het opstarten, en een verplaatsing die ook naar een andere schijf in één keer gebeurt (nu `shutil.move`, dat bij een externe schijf eerst kopieert, waardoor even een half bestand zichtbaar is).

Doel: half gedownloade of afgekeurde bestanden komen nooit in de muziekmap terecht. De watch folder van Rekordbox of Serato pikt anders halve bestanden op.

Bouwen:

- Downloads gaan eerst naar een staging-map in de app-data, niet naar de muziekmap.
- Pas na alle controles (stap 2 en 3) en het taggen (stap 10) wordt het bestand in één keer verplaatst naar de muziekmap.
- Bij het opstarten ruimt de app achtergebleven bestanden in staging op.

Klaar als:

- [ ] Een afgebroken download laat niets achter in de muziekmap.
- [ ] Een bestand verschijnt in één keer, met de definitieve naam.
- [ ] Een test bewijst beide punten.

### Stap 2: bestandscontrole en quarantaine

**Status: bestaat niet.** Er wordt alleen vóór de download gekeken naar lengte en bitrate uit de zoekresultaten. Mislukt een peer, dan probeert de app de volgende kandidaat, maar er is geen controle van het bestand, geen quarantaine en geen blokkeerlijst per track.

Doel: kapotte, afgekapte of verkeerde bestanden worden tegengehouden, met een reden die de gebruiker kan lezen.

Bouwen:

- Controle met `ffprobe` en `ffmpeg`: het bestand is helemaal te decoderen, het formaat klopt met de extensie, de lengte wijkt niet meer af dan een instelbare marge van de lengte op SoundCloud, en er zit geen lange stilte aan begin of eind (`silencedetect`).
- Afgekeurde bestanden gaan naar een quarantainemap, met de reden in de database. De gebruiker kan ze bekijken, toch goedkeuren of verwijderen.
- Na afkeuren zet de app deze combinatie van gebruiker en bestand op een blokkeerlijst voor deze track en probeert de volgende kandidaat.

Klaar als:

- [ ] Tests met een afgekapt bestand, een bestand met 30 seconden stilte en een MP3 met .flac-extensie worden alle drie afgekeurd, elk met een eigen reden.
- [ ] Zonder ffmpeg werkt de app nog, slaat de controle over en toont dat in de instellingen.

### Stap 3: nep-lossless herkennen

**Status: bestaat niet.**

Doel: een MP3 die is omgezet naar FLAC of WAV wordt herkend. Op een clubsysteem hoor je het verschil, en het is een veelvoorkomend probleem op Soulseek.

Bouwen:

- Spectrumanalyse: decodeer een paar stukken van het bestand naar PCM en bepaal met een FFT tot welke frequentie er nog energie zit.
- Echte lossless loopt door tot ongeveer 22 kHz. Een harde afkapping rond 16, 19 of 20 kHz wijst op een omgezette MP3 van ongeveer 128, 192 of 320 kbps.
- Doe hetzelfde voor MP3's die zeggen 320 kbps te zijn maar bij 16 kHz afkappen.
- Resultaat: echt, verdacht of nep, met de gemeten afkapfrequentie. Een instelling bepaalt of verdachte bestanden worden afgekeurd of met een label worden doorgelaten.

Klaar als:

- [ ] Tests met zelf gegenereerde signalen (ruis, ruis met een laagdoorlaatfilter op 16 kHz en op 19,5 kHz) worden juist ingedeeld.
- [ ] Een gemeten afkapfrequentie is per track zichtbaar in de interface.
- [ ] De analyse kost minder dan 5 seconden per track.

### Stap 4: kwaliteitsprofielen en automatisch upgraden

**Status: deels.** Instelling voorkeur lossless of MP3, plus minimale MP3-bitrate. Mist: profielen met ladder, ondergrens en doel, upgradelijst, vervangen en prullenbakmap.

Doel: de DJ kiest welke kwaliteit hij wil. Een verse drop komt eerst binnen in de beste beschikbare kwaliteit, en wordt later vervangen als er iets beters opduikt.

Bouwen:

- Een profiel is een gerangschikte ladder, bijvoorbeeld FLAC 24-bit, FLAC 16-bit, WAV/AIFF, MP3 320, MP3 256, met een ondergrens (minimaal acceptabel) en een doel (daarna stoppen met zoeken).
- Drie standaardprofielen: Club (lossless, ondergrens MP3 320), Gebalanceerd (doel MP3 320) en Ruimtebesparend.
- Tracks onder het doel komen op een upgradelijst en worden minder vaak opnieuw gezocht, bijvoorbeeld dagelijks tot 30 dagen.
- Een upgrade vervangt alleen als het nieuwe bestand gemeten beter is en stap 2 en 3 doorstaat. Het oude bestand gaat naar een prullenbakmap in de app, niet direct weg.

Let op: Rekordbox en Serato koppelen cue points aan het pad van het bestand. Een upgrade van .mp3 naar .flac verandert dat pad, waardoor de DJ zijn cues kwijtraakt. Geef daarom een instelling: automatisch upgraden, eerst vragen, of alleen upgraden als de track nog niet in de DJ-software staat (zie stap 12).

Klaar als:

- [ ] Een track die als MP3 320 binnenkwam, wordt in een test vervangen door een gevonden FLAC, en de MP3 staat in de prullenbak.
- [ ] Een slechtere of nep-lossless kandidaat vervangt nooit een bestaand bestand.
- [ ] De drie standaardprofielen staan in de instellingen.

### Stap 5: uitleg waarom niet, en zelf kiezen

**Status: deels.** Een track toont een korte reden ("Not on Soulseek yet", "Peers didn't deliver") en heeft de knoppen Search now en Skip. Mist: zoekpogingen met kandidaten en afwijsredenen opslaan, de knop "Waarom niet?", zelf een kandidaat kiezen en een eigen zoekterm.

Doel: bij elke track die niet binnenkomt, ziet de DJ waarom, en kan hij zelf een kandidaat kiezen of de zoekterm aanpassen.

Bouwen:

- Sla per zoekpoging op: de zoektermen, het aantal resultaten en de beste 10 kandidaten met de reden van afwijzing, zoals "192 kbps, onder de ondergrens", "3:12 lang, verwacht 6:45 (radio-edit?)" of "remix van iemand anders".
- In de interface: per track een knop "Waarom niet?" met die lijst.
- Acties: "Download deze toch" (gaat nog steeds door stap 2 en 3), "Zoek met andere term" en "Niet meer zoeken".

Klaar als:

- [ ] Elke track zonder download toont minstens één concrete reden.
- [ ] Een handmatig gekozen kandidaat wordt gedownload en gecontroleerd.
- [ ] Een aangepaste zoekterm blijft bewaard voor volgende pogingen.

## Fase 2: matching en Soulseek

Na deze fase vindt de app meer van de juiste tracks, pakt hij minder vaak de verkeerde versie, en gedraagt hij zich netjes op het Soulseek-netwerk.

### Stap 6: slimmere matching

**Status: deels.** `titles.py` en `matching.py` normaliseren accenten, hoofdletters, "&"/"and" en "feat.", herkennen versies (remix van een ander wordt geweigerd, Extended mag voor Original), labelnamen, catalogusnummers en DJ-pool-edits. Mist: andere schriften naar Latijn, aliassen per artiest, handmatige correcties per track, matchregels in één module (nu verdeeld over twee) en 30 echte titels uit de kanalen van de gebruiker in de tests.

Doel: minder gemiste tracks door schrijfwijzen en aliassen, en nooit de verkeerde versie.

Bouwen:

- Versiebewuste vergelijking: Original, Extended, Radio Edit, Remix van X, VIP, Dub, Bootleg en Edit zijn aparte versies. Extended mag voor Original, een remix van iemand anders nooit.
- Normaliseren van accenten, hoofdletters, "&" en "and", "feat." en "ft.", en schriften (bijvoorbeeld Cyrillisch of Japans naar Latijn) voordat er vergeleken wordt.
- Aliassen per artiest, door de gebruiker in te stellen: een producer met meerdere namen wordt onder elk van die namen gezocht.
- Handmatige correcties per track (artiest, titel, versie) gaan altijd voor de automatische opschoning.
- Zet alle matchregels in één module met een eigen testbestand vol echte voorbeeldtitels.

Klaar als:

- [ ] Minstens 30 echte SoundCloud-titels uit de kanalen van de gebruiker staan in de tests, met de verwachte artiest, titel en versie.
- [ ] Een alias en een handmatige correctie werken in een test van begin tot eind.

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

**Status: deels.** Vaste wachttijd van 8 s tussen zoekopdrachten, spampeers worden geweigerd, wachtrij en snelheid van de peer tellen mee in de score, en de eigen login deelt de downloadmap. Mist: maximum per paar minuten, reputatie per gebruiker, EP/album van één gebruiker, bewaking van schijfruimte en een waarschuwing als je niets deelt.

Doel: geen bans, minder mislukte downloads, en geen volle schijf.

Bouwen:

- Zoekopdrachten afremmen: een vaste wachttijd tussen zoekopdrachten en een maximum per paar minuten, instelbaar maar met een veilige standaard.
- Reputatie per gebruiker onthouden: snel en betrouwbaar telt mee in de score, vaak mislukt of nep-lossless geleverd telt tegen, met een automatische blokkeerlijst na herhaalde problemen.
- Een EP of album uit een playlist bij voorkeur in zijn geheel van één gebruiker halen, zodat de bestanden bij elkaar passen.
- Bewaking van vrije schijfruimte: onder een instelbare grens pauzeren de downloads en krijgt de gebruiker een melding.
- Een duidelijke waarschuwing in de app als de gebruiker niets deelt. Wie niets deelt, wordt op Soulseek vaak geblokkeerd.

Klaar als:

- [ ] Tests laten zien dat de afremming en de schijfruimtegrens werken.
- [ ] Een gebruiker die twee keer nep-lossless leverde, staat in een test onderaan de ranglijst.

### Stap 9: regels per kanaal

**Status: deels.** Voor alle kanalen samen: uploads boven 10 minuten en mixes, radioshows en podcasts (op titel) worden overgeslagen, met de reden zichtbaar en een knop om ze toch op te halen. Reposts zijn per kanaal aan of uit te zetten. Previews worden in `titles.py` herkend maar nog niet overgeslagen. Mist: regels per kanaal (lengte, remixes, trefwoorden), een globale blokkeerlijst en het instellen in de interface.

Doel: alleen downloaden wat de DJ wil. SoundCloud-kanalen uploaden ook mixen van een uur, podcasts, previews en snippets.

Bouwen:

- Per kanaal of playlist: minimale en maximale lengte (standaard bijvoorbeeld 2 tot 12 minuten), remixes wel of niet, reposts wel of niet, previews en clips overslaan.
- Trefwoorden die een track uitsluiten ("mix", "podcast", "live at") of juist verplicht maken.
- Een globale blokkeerlijst van trefwoorden en artiesten.
- Overgeslagen tracks blijven zichtbaar met de regel die ze tegenhield, zodat de gebruiker ze toch kan ophalen.

Klaar als:

- [ ] Een mix van 58 minuten en een clip van 30 seconden worden in een test overgeslagen, elk met de juiste regel als reden.
- [ ] Regels zijn per kanaal in te stellen en te wijzigen in de interface.

## Fase 3: collectie en DJ-software

Na deze fase komen tracks netjes getagd binnen, downloadt de app niets wat de DJ al heeft, en staan nieuwe tracks direct klaar in Rekordbox of Serato.

### Stap 10: tags, artwork en bestandsnamen

**Status: bestaat niet.** Alleen de bestandsnaam `Artiest - Titel (Versie)` en een map per kanaal staan vast. Er worden geen tags of hoezen geschreven (mutagen is nog geen afhankelijkheid).

Doel: DJ-software toont de juiste artiest, titel, versie, label en hoes, ongeacht hoe slordig het bestand op Soulseek heette.

Bouwen:

- Tags schrijven met `mutagen`: artiest, titel met versie erin ("Track (Extended Mix)", zoals DJ's gewend zijn), release, label, genre, jaar, de hoes ingebed (minimaal 500 bij 500 pixels) en de SoundCloud-link als commentaar.
- Voor MP3 ID3v2.3 gebruiken, omdat DJ-software dat het best ondersteunt. AIFF krijgt ID3 in het bestand zelf.
- WAV ondersteunt tags slecht in DJ-software. Geef een instelling om WAV automatisch om te zetten naar AIFF. Dat is ook lossless, met dezelfde audio.
- Geen BPM of toonsoort berekenen: dat doet de DJ-software zelf beter.
- Sjablonen voor map- en bestandsnamen, bijvoorbeeld `{kanaal}/{artiest} - {titel} ({versie})`, met een voorbeeld in de instellingen.

Klaar als:

- [ ] Een getest MP3-, FLAC- en AIFF-bestand hebben na afloop de juiste tags en hoes, gecontroleerd met mutagen.
- [ ] Een WAV wordt met de instelling aan omgezet naar AIFF zonder kwaliteitsverlies (zelfde PCM-data).

### Stap 11: kijken of de DJ de track al heeft

**Status: bestaat niet.** De app onthoudt alleen welke SoundCloud-tracks hij al kent; hij kijkt niet in de muziekcollectie.

Doel: nooit downloaden wat al in de collectie staat, en geen dubbele bestanden.

Bouwen:

- De gebruiker kiest een of meer muziekmappen. De app scant die en houdt een index bij van artiest, titel, versie, lengte en eventueel fingerprint.
- Voor elke nieuwe track eerst in die index zoeken. Gevonden: status "Al in je collectie", met het pad.
- Scannen gebeurt de eerste keer volledig en daarna alleen op gewijzigde bestanden.
- Een overzicht van dubbele bestanden in de eigen downloads, met de beste versie gemarkeerd. Niets automatisch verwijderen.

Klaar als:

- [ ] Een track die al in de muziekmap staat onder een iets andere naam, wordt in een test herkend en niet gedownload.
- [ ] Een tweede scan van 10.000 ongewijzigde bestanden duurt maar een paar seconden.

### Stap 12: koppeling met DJ-software

**Status: bestaat niet.**

Doel: nieuwe tracks staan zonder handwerk in de DJ-software, per kanaal of playlist gegroepeerd. Dit is het sterkste verkoopargument richting DJ's.

Bouwen, in deze volgorde:

1. M3U-playlist per kanaal en per playlist, automatisch bijgewerkt. Werkt in vrijwel alle DJ-software.
2. Rekordbox: een XML-bestand met tracks en playlists dat Rekordbox kan inlezen via Voorkeuren, Geavanceerd, "rekordbox xml".
3. Serato: crates schrijven in de map `_Serato_/Subcrates`.
4. Pas daarna eventueel Traktor (NML).

- Bijhouden welke tracks al in de DJ-software staan. Stap 4 gebruikt dat om bij upgrades geen cue points te breken.
- Nooit de database van de DJ-software zelf aanpassen. Alleen bestanden schrijven die de software zelf inleest.

Klaar als:

- [ ] M3U, Rekordbox-XML en een Serato-crate worden in tests geschreven en weer ingelezen met dezelfde inhoud.
- [ ] De gebruiker heeft de koppeling handmatig getest in Rekordbox en Serato.

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
