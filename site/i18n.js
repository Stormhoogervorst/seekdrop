/* EN/NL switch shared by every page. The English text stays in the HTML (so it works without JavaScript and
   search engines read it); the Dutch text of a page is passed in as a dictionary keyed by data-i18n. */
(function () {
  "use strict";
  function store(key, value) {
    try { if (value === undefined) return localStorage.getItem(key); localStorage.setItem(key, value); } catch (e) { return null; }
  }
  window.SeekSyncI18n = {
    init: function (opts) {
      var NL = opts.nl || {}, doc = document;
      var els = [].slice.call(doc.querySelectorAll("[data-i18n]"));
      var alts = [].slice.call(doc.querySelectorAll("[data-i18n-alt]"));
      els.forEach(function (el) { el._en = el.innerHTML; });
      alts.forEach(function (el) { el._en = el.getAttribute("alt"); });
      var enTitle = doc.title;
      var descEl = doc.querySelector('meta[name="description"]');
      var enDesc = descEl ? descEl.getAttribute("content") : "";
      var current = "en";

      function setLang(lang) {
        current = lang === "nl" ? "nl" : "en";
        els.forEach(function (el) {
          var key = el.getAttribute("data-i18n");
          el.innerHTML = current === "nl" && NL[key] !== undefined ? NL[key] : el._en;
        });
        alts.forEach(function (el) {
          var key = el.getAttribute("data-i18n-alt");
          el.setAttribute("alt", current === "nl" && NL[key] !== undefined ? NL[key] : el._en);
        });
        doc.documentElement.lang = current;
        doc.title = current === "nl" && opts.titleNl ? opts.titleNl : enTitle;
        if (descEl) descEl.setAttribute("content", current === "nl" && opts.descNl ? opts.descNl : enDesc);
        [].forEach.call(doc.querySelectorAll(".lang button"), function (b) {
          b.setAttribute("aria-pressed", String(b.getAttribute("data-lang") === current));
        });
        [].forEach.call(doc.querySelectorAll("a[data-keep-lang]"), function (a) {
          var base = a.getAttribute("href").split("?")[0].split("#")[0];
          var hash = a.getAttribute("href").indexOf("#") > -1 ? "#" + a.getAttribute("href").split("#")[1] : "";
          a.setAttribute("href", base + (current === "nl" ? "?lang=nl" : "") + hash);
        });
        if (opts.onChange) opts.onChange(current);
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
      return { setLang: setLang, lang: function () { return current; } };
    }
  };
})();
