/* SeekDrop website: EN/NL switch and download buttons that point at the newest GitHub release. */
(function () {
  "use strict";
  var REPO = "Stormhoogervorst/seekdrop";
  var RELEASES = "https://github.com/" + REPO + "/releases/latest";

  var NL = {
    skip: "Naar de inhoud",
    nav_how: "Hoe het werkt", nav_features: "Functies", nav_download: "Download", nav_faq: "Vragen",
    github_short: "GitHub",
    eyebrow: "Gratis · Open source · Mac en Windows",
    h1: "Volg SoundCloud en Spotify. <span class=\"mark\">Haal de bestanden van Soulseek.</span>",
    lede: "SeekDrop houdt de labels, artiesten en playlists bij die jij volgt. Komt er een nieuwe track, dan zoekt het de beste kopie op Soulseek, controleert die, zet er tags in en legt hem in je muziekmap.",
    view_github: "Bekijk op GitHub",
    meta_default: "Nieuwste versie op GitHub · GPL-3.0-licentie",
    alt_main: "Het SeekDrop-venster: links de kanalen, rechts de tracks met hun status, zoals downloaden, zoeken op Soulseek en gedownload.",
    what_h: "Wat het doet",
    what_sub: "Voor DJ's en producers die niet elke dag twintig labelpagina's willen afstruinen.",
    c1_h: "Volgen",
    c1_p: "Voeg een SoundCloud-profiel of -playlist toe, of een openbare Spotify-playlist. SeekDrop kijkt elk uur en ziet nieuwe tracks.",
    c2_h: "Zoeken",
    c2_p: "Het ruimt de rommelige titel op, zoekt op Soulseek en beoordeelt elk resultaat op artiest, titel, remix, lengte, formaat, bitrate en snelheid.",
    c3_h: "Afleveren",
    c3_p: "Het bestand wordt gecontroleerd, getagd met hoes en benoemd zoals jij wilt, en komt in je muziekmap. Optioneel: een kant-en-klare lijst voor Rekordbox.",
    how_h: "Hoe het werkt",
    how_sub: "Van een link naar een getagd bestand, zonder dat jij iets hoeft te doen.",
    s1_h: "Plak een link",
    s1_p: "Een SoundCloud-profiel of -playlist, of een openbare Spotify-playlist. SeekDrop leest alleen titels, artiesten en lengtes. Het downloadt nooit audio van SoundCloud of Spotify.",
    s2_h: "Titels worden opgeschoond",
    s2_p: "<code>PREMIERE: Artist - Track (Someone Remix) [FREE DL]</code> wordt artiest <em>Artist</em>, titel <em>Track</em>, versie <em>Someone Remix</em>.",
    s3_h: "Jouw regels bepalen wat gewenst is",
    s3_p: "Kortste en langste lengte, remixes aan of uit, geen previews of DJ-mixen, woorden om te blokkeren. Tracks die je al hebt, worden herkend en overgeslagen.",
    s4_h: "Het zoekt netjes op Soulseek",
    s4_p: "Zoekopdrachten worden gespreid, downloads pauzeren als je schijf vol raakt, en gebruikers die kapotte of valse bestanden sturen worden gemeden.",
    s5_h: "Het bestand wordt gecontroleerd",
    s5_p: "Het moet helemaal afspelen, het formaat hebben dat de naam zegt, ongeveer even lang zijn als het origineel, en geen omgezette MP3 zijn die voor lossless doorgaat.",
    s6_h: "Getagd, benoemd, afgeleverd",
    s6_p: "Artiest, titel met versie, genre, jaar en hoes gaan in het bestand. Het krijgt de naam uit jouw sjabloon en komt in je muziekmap.",
    why_h: "Past er niets? Dan zegt het waarom",
    why_p: "Geen black box. Bij elke track die niet gevonden wordt, laat SeekDrop zien waarop het zocht en wat de dichtstbijzijnde bestanden zijn, elk met de reden van afwijzing: een radio edit die te kort is, 192 kbps terwijl jij 320 wilt, een andere remix.",
    why_l1: "Download een afgewezen bestand toch, met één klik.",
    why_l2: "Verbeter artiest, titel of versie als SeekDrop het verkeerd las.",
    why_l3: "Zoek met je eigen woorden, of stop met zoeken.",
    why_l4: "Nog niet op Soulseek? Het probeert opnieuw na 1, 3, 6 en 12 uur, daarna dagelijks tot 30 dagen.",
    alt_why: "Het paneel Why not? bij een track: waarop gezocht is, de drie dichtstbijzijnde bestanden en waarom elk is afgewezen, met knoppen om toch te downloaden.",
    feat_h: "Gemaakt voor hoe DJ's muziek verzamelen",
    f1_h: "Kent de ene versie van de andere",
    f1_p: "Original en Extended gaan samen. Een radio edit, dub, VIP of andermans remix wordt nooit aangezien voor de versie die jij wilt. Producers met meerdere namen kunnen aliassen krijgen.",
    f2_h: "Kwaliteitsprofielen en upgrades",
    f2_p: "Club, Balanced of Space saver. Komt een track eerst binnen als MP3 320 en wil je lossless, dan blijft SeekDrop 30 dagen zoeken en vraagt het eerst of het je bestand mag vervangen.",
    f3_h: "Vangt valse lossless",
    f3_p: "Het leest het spectrum van elk bestand. Een MP3 die naar FLAC is omgezet stopt bij een harde afkapgrens, en belandt met de reden in quarantaine, niet in je crate.",
    f4_h: "Regels per kanaal",
    f4_p: "Een labelkanaal en een promokanaal vragen om andere regels. Stel lengte, remixes, mixen en geblokkeerde woorden per kanaal in, plus één blokkeerlijst voor alles.",
    f5_h: "Weet wat je al hebt",
    f5_p: "Wijs je muziekmappen aan. Een track die er al staat, ook onder een andere naam, wordt gemarkeerd en niet opnieuw gedownload. Een Duplicates-overzicht toont dubbele bestanden. Je mappen worden alleen gelezen.",
    f6_h: "Klaar voor Rekordbox",
    f6_p: "Houd een Rekordbox-XML-bestand bij met een playlist per kanaal. Tracks die in je Rekordbox-collectie staan, worden nooit achter je rug vervangen, dus je cue points blijven veilig.",
    f7_h: "Tags en hoes",
    f7_p: "Artiest, titel met versie, genre, jaar en een hoes van 500 px in MP3, FLAC, AIFF en M4A. Optioneel zet je WAV om naar AIFF zodat DJ-software de tags leest.",
    f8_h: "Een goede Soulseek-gebruiker",
    f8_p: "Zoekopdrachten worden gespreid, een schijfbewaker pauzeert downloads, en het waarschuwt je als je niets deelt, want veel gebruikers blokkeren dat.",
    f9_h: "Privé door ontwerp",
    f9_p: "Alles blijft op je computer. Geen account, geen tracking, geen analytics. Het praat met SoundCloud, Spotify, Soulseek en GitHub (voor updates).",
    dl_h: "Download SeekDrop",
    dl_sub: "Gratis, open source (GPL-3.0). Downloads komen rechtstreeks van GitHub.",
    mac_req: "macOS 11 of nieuwer, Apple Silicon (M1 en later)",
    dl_mac: "Download de .dmg",
    mac_1: "Open de .dmg en sleep SeekDrop naar Programma's.",
    mac_2: "Open het. Zegt macOS dat het de app niet kan controleren: Systeeminstellingen, Privacy en beveiliging, daarna <strong>Open toch</strong> (Open Anyway). Maar één keer.",
    mac_3: "Updates installeer je vanuit de app (Settings, Updates).",
    win_req: "Windows 10 of 11",
    dl_win: "Download het installatieprogramma",
    win_1: "Start het installatieprogramma. Het kan SeekDrop starten als je inlogt.",
    win_2: "Windows kan een SmartScreen-waarschuwing tonen omdat de app niet is ondertekend: klik op <strong>Meer informatie</strong> en dan op <strong>Toch uitvoeren</strong>.",
    win_3: "Nieuwe versies: download het installatieprogramma opnieuw en start het over de oude heen.",
    all_releases: "Alle versies en de broncode op GitHub",
    conn_h: "Voor je begint: verbind met Soulseek",
    conn1_h: "Via Nicotine+",
    conn1_p: "Aan te raden als je het al gebruikt. SeekDrop installeert een kleine plugin, jij zet die aan in Nicotine+, en het gebruikt je account en je gedeelde mappen.",
    conn2_h: "Met een eigen account",
    conn2_p: "SeekDrop logt zelf in bij Soulseek, geen andere app nodig. Gebruik een apart account, zodat het je niet elders uitlogt.",
    ffmpeg: "Optioneel: installeer ffmpeg (op een Mac: <code>brew install ffmpeg</code>) om de bestandscontroles aan te zetten.",
    know_h: "Goed om te weten",
    k1_h: "Gebruik het verantwoord.",
    k1_p: "Soulseek is een netwerk waar mensen hun eigen muziekmappen delen. Download alleen muziek waarvan je het recht hebt die te hebben, zoals gratis downloads, promo's die naar jou zijn gestuurd, of tracks die je elders kocht. Jij bent verantwoordelijk voor wat je downloadt en deelt.",
    k2_h: "Geen audio van SoundCloud of Spotify.",
    k2_p: "Daar worden alleen titels, artiesten, lengtes en hoezen gelezen. De audio komt altijd van Soulseek.",
    k3_h: "Spotify heeft grenzen.",
    k3_p: "Alleen openbare playlists werken, en Spotify toont hooguit de eerste 100 tracks van een playlist. Privélijsten en Liked Songs kunnen niet gelezen worden.",
    k4_h: "Het werkt zolang het open staat.",
    k4_p: "SeekDrop controleert en downloadt alleen als de app draait.",
    k5_h: "Onafhankelijk project.",
    k5_p: "Niet gemaakt door of verbonden aan SoundCloud, Spotify, Soulseek, Nicotine+ of Rekordbox.",
    faq_h: "Vragen",
    q1: "Is het echt gratis?",
    a1: "Ja. SeekDrop is gratis en open source onder de GPL-3.0-licentie. Geen accounts, abonnementen of reclame.",
    q2: "Heb ik een Soulseek-account nodig?",
    a2: "Gebruik je bestaande Nicotine+ (die heeft een eigen account), of laat SeekDrop inloggen met een eigen account. Een naam die nog niet bestaat, wordt bij de eerste keer inloggen aangemaakt.",
    q3: "Werkt het met Serato of Traktor?",
    a3: "De bestanden en tags werken in elke DJ-software. Het kant-en-klare playlistbestand is voorlopig alleen voor Rekordbox. Serato-crates, M3U-playlists en Traktor zijn nog niet gebouwd.",
    q4: "Wat gebeurt er met een track die niet op Soulseek staat?",
    a4: "Hij blijft in de lijst staan als \"Not found yet\" en SeekDrop probeert het opnieuw na 1, 3, 6 en 12 uur, daarna dagelijks, tot 30 dagen. Je kunt altijd zelf opnieuw zoeken.",
    q5: "Overschrijft het muziek die ik al heb?",
    a5: "Nee. Je eigen mappen worden alleen gelezen. Een betere kopie van een track blijft naast je bestand staan tot je op Replace drukt, en een vervangen bestand gaat 30 dagen naar de prullenbak van SeekDrop.",
    q6: "Iets werkt niet. Waar meld ik dat?",
    a6: "Open een issue op <a href=\"https://github.com/Stormhoogervorst/seekdrop/issues\">GitHub</a> en voeg <code>seekdrop.log</code> uit de gegevensmap van de app toe.",
    end_h: "Stop met twintig labelpagina's afstruinen.",
    end_p: "Voeg je kanalen één keer toe. SeekDrop doet de rest.",
    end_btn: "Download SeekDrop",
    foot: "Gratis en open source, GPL-3.0. Niet verbonden aan SoundCloud, Spotify, Soulseek, Nicotine+ of Rekordbox.",
    issues: "Issues", changelog: "Wijzigingen"
  };

  var LABELS = {
    en: { mac: "Download for Mac", win: "Download for Windows", other: "Download SeekDrop",
          meta: function (v, s) { return "Version " + v + (s ? " · " + s : "") + " · GPL-3.0 licence"; } },
    nl: { mac: "Download voor Mac", win: "Download voor Windows", other: "Download SeekDrop",
          meta: function (v, s) { return "Versie " + v + (s ? " · " + s : "") + " · GPL-3.0-licentie"; } }
  };
  var TITLE_NL = "SeekDrop: volg SoundCloud en Spotify, haal de bestanden van Soulseek";
  var DESC_NL = "SeekDrop is een gratis desktopapp voor DJ's. Het volgt SoundCloud-kanalen en Spotify-playlists, vindt elke nieuwe track op Soulseek, controleert het bestand, tagt het en legt het in je muziekmap.";

  var state = { lang: "en", os: detectOs(), release: null };
  var doc = document;
  var els = [].slice.call(doc.querySelectorAll("[data-i18n]"));
  var alts = [].slice.call(doc.querySelectorAll("[data-i18n-alt]"));
  els.forEach(function (el) { el._en = el.innerHTML; });
  alts.forEach(function (el) { el._en = el.getAttribute("alt"); });
  var enTitle = doc.title;
  var descEl = doc.querySelector('meta[name="description"]');
  var enDesc = descEl ? descEl.getAttribute("content") : "";

  function detectOs() {
    var ua = navigator.userAgent || "";
    if (/Windows/i.test(ua)) return "win";
    if (/Macintosh|Mac OS X/i.test(ua) && !/iPhone|iPad|iPod/i.test(ua)) return "mac";
    return "other";
  }
  function store(key, value) { try { if (value === undefined) return localStorage.getItem(key); localStorage.setItem(key, value); } catch (e) { return null; } }

  function setLang(lang) {
    state.lang = lang;
    els.forEach(function (el) {
      var key = el.getAttribute("data-i18n");
      el.innerHTML = lang === "nl" && NL[key] !== undefined ? NL[key] : el._en;
    });
    alts.forEach(function (el) {
      var key = el.getAttribute("data-i18n-alt");
      el.setAttribute("alt", lang === "nl" && NL[key] !== undefined ? NL[key] : el._en);
    });
    doc.documentElement.lang = lang;
    doc.title = lang === "nl" ? TITLE_NL : enTitle;
    if (descEl) descEl.setAttribute("content", lang === "nl" ? DESC_NL : enDesc);
    [].forEach.call(doc.querySelectorAll(".lang button"), function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-lang") === lang));
    });
    renderDownloads();
  }

  function renderDownloads() {
    var L = LABELS[state.lang], main = doc.getElementById("dl-main"), label = doc.getElementById("dl-main-label");
    label.textContent = L[state.os];
    var r = state.release;
    var href = state.os === "mac" ? (r && r.mac) : state.os === "win" ? (r && r.win) : null;
    main.setAttribute("href", href || (state.os === "other" ? "#download" : RELEASES));
    if (r && r.version) {
      var size = state.os === "mac" ? r.macSize : state.os === "win" ? r.winSize : "";
      doc.getElementById("dl-meta").textContent = L.meta(r.version, size);
    }
    var mac = doc.getElementById("dl-mac"), win = doc.getElementById("dl-win");
    mac.setAttribute("href", (r && r.mac) || RELEASES);
    win.setAttribute("href", (r && r.win) || RELEASES);
    doc.getElementById("card-mac").classList.toggle("pick", state.os === "mac");
    doc.getElementById("card-win").classList.toggle("pick", state.os === "win");
  }

  function mb(bytes) { return bytes ? Math.round(bytes / 1048576) + " MB" : ""; }

  function loadRelease() {
    if (!window.fetch) return;
    fetch("https://api.github.com/repos/" + REPO + "/releases/latest", { headers: { Accept: "application/vnd.github+json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !d.tag_name) return;
        var rel = { version: String(d.tag_name).replace(/^v/, ""), mac: "", win: "", macSize: "", winSize: "" };
        (d.assets || []).forEach(function (a) {
          var n = String(a.name || "").toLowerCase();
          if (n.slice(-4) === ".dmg" && n.indexOf("macos") > -1) { rel.mac = a.browser_download_url; rel.macSize = mb(a.size); }
          if (n.slice(-4) === ".exe" && n.indexOf("windows") > -1) { rel.win = a.browser_download_url; rel.winSize = mb(a.size); }
        });
        state.release = rel;
        renderDownloads();
      })
      .catch(function () { /* offline or rate limited: the buttons keep pointing at the releases page */ });
  }

  [].forEach.call(doc.querySelectorAll(".lang button"), function (b) {
    b.addEventListener("click", function () {
      var l = b.getAttribute("data-lang");
      store("lang", l);
      setLang(l);
    });
  });

  var wanted = null;
  try { wanted = new URLSearchParams(location.search).get("lang"); } catch (e) { wanted = null; }
  wanted = wanted || store("lang") || ((navigator.language || "").toLowerCase().indexOf("nl") === 0 ? "nl" : "en");
  setLang(wanted === "nl" ? "nl" : "en");
  loadRelease();
})();
