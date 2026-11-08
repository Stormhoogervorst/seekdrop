"use strict";

const token = new URLSearchParams(location.hash.slice(1)).get("token") || sessionStorage.getItem("cw-token") || "";
try { if (token) sessionStorage.setItem("cw-token", token); } catch (_) {}
// A key added to the URL later (e.g. /#token=dev on the dev server) needs a fresh start.
addEventListener("hashchange", () => {
  const t = new URLSearchParams(location.hash.slice(1)).get("token");
  if (t && t !== token) location.reload();
});

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const ui = { channel: null, filter: "all", state: null, settingsOpen: false, setupShown: false };

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: { "X-Token": token, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = {};
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 2600);
}

function showError(el, msg) {
  el.textContent = msg || "";
  el.hidden = !msg;
}

function ago(ts) {
  if (!ts) return "never";
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

function inTime(sec) {
  if (sec == null) return "";
  if (sec < 90) return "in a minute";
  if (sec < 3600) return `in ${Math.round(sec / 60)} min`;
  if (sec < 86400) return `in ${Math.round(sec / 3600)} h`;
  return `in ${Math.round(sec / 86400)} days`;
}

function clock(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/* ---------------- polling ---------------- */
let polling = false;
async function refresh() {
  if (polling) return;
  polling = true;
  try {
    const q = ui.channel ? `?channel=${ui.channel}` : "";
    ui.state = await api("GET", "/api/state" + q);
    render();
  } catch (e) {
    $("#deck-title").textContent = "Nicotine+ Sync stopped";
    $("#deck-sub").textContent = "Restart the app.";
    $("#ring").className = "ring err";
  } finally {
    polling = false;
  }
}
setInterval(refresh, 2000);

/* ---------------- rendering ---------------- */
function render() {
  const s = ui.state;
  if (!s.settings.configured) {
    if (!ui.setupShown) openSetup(s.settings);
    return;
  }
  $("#setup").hidden = true;
  $("#app").hidden = false;
  renderDeck(s);
  renderChannels(s);
  renderFilters(s);
  renderTracks(s);
  renderActivity(s);
  renderUpdate(s);
}

function renderUpdate(s) {
  const a = $("#update-link"), u = s.update;
  a.hidden = !u;
  if (u && a.dataset.v !== u.version) {
    a.dataset.v = u.version;
    a.href = u.url;
    a.textContent = `Get version ${u.version}`;
    a.title = `You have ${s.version}. Download the new version from GitHub.`;
  }
}

function renderDeck(s) {
  const ring = $("#ring"), title = $("#deck-title"), sub = $("#deck-sub");
  const st = s.stats;
  const working = (st.searching || 0) + (st.downloading || 0);
  const queued = st.wanted || 0;
  sub.classList.remove("err");
  const viaNic = s.settings.soulseek_mode === "nicotine";
  if (s.soulseek.status === "connected") {
    if (working) {
      ring.className = "ring busy";
      title.textContent = st.downloading ? `Downloading ${st.downloading}` : "Searching Soulseek";
    } else {
      ring.className = "ring on";
      title.textContent = "Watching";
    }
    const bits = [];
    if (queued) bits.push(`${queued} to search`);
    if (st.waiting) bits.push(`${st.waiting} not found yet`);
    bits.push(s.channels.length ? `next check ${inTime(s.next_check_in)}` : "add a channel to start");
    if (viaNic) bits.push(s.soulseek.username ? `through Nicotine+ as ${s.soulseek.username}` : "through Nicotine+");
    sub.textContent = bits.join(", ");
  } else if (s.soulseek.status === "connecting") {
    ring.className = "ring busy";
    title.textContent = viaNic ? "Connecting to Nicotine+" : "Connecting to Soulseek";
    sub.textContent = "";
  } else {
    ring.className = "ring err";
    title.textContent = viaNic ? "Not connected to Nicotine+" : "Not connected to Soulseek";
    sub.textContent = s.soulseek.error || (viaNic ? "Open Nicotine+ and turn on the Nicotine+ Sync Bridge plugin." : "Check your account in Settings.");
    sub.classList.add("err");
  }
}

function renderChannels(s) {
  const nav = $("#channels");
  const total = s.channels.reduce((a, c) => a + c.done_count, 0);
  let html = `<button class="ch" data-ch="" aria-current="${!ui.channel}">
      <span class="ch-name">All channels</span><span class="ch-count">${total}</span>
      <span class="ch-meta">${s.channels.length} watched</span></button>`;
  for (const c of s.channels) {
    let meta = c.checking ? "Checking…" : `Checked ${ago(c.last_checked)}`;
    let cls = "ch-meta";
    if (c.last_error) { meta = c.last_error; cls += " err"; }
    if (!c.enabled) meta = "Paused";
    if (c.kind === "playlist") meta = `Playlist · ${meta}`;
    html += `<button class="ch${c.enabled ? "" : " off"}" data-ch="${c.id}" aria-current="${ui.channel === c.id}" title="${esc(c.url)}">
      <span class="ch-name">${esc(c.name)}</span>
      <span class="ch-count" title="Downloaded">${c.done_count}</span>
      <span class="${cls}">${esc(meta)}</span></button>`;
  }
  if (!s.channels.length) html += `<p class="ch-empty">No channels yet. Paste a SoundCloud profile or playlist link above.</p>`;
  if (nav.innerHTML !== html) nav.innerHTML = html;

  const bar = $("#channel-bar");
  const ch = s.channels.find((c) => c.id === ui.channel);
  $("#view-title").textContent = ch ? ch.name : "All channels";
  if (ch) {
    bar.hidden = false;
    const html2 = `<a href="${esc(ch.url)}" target="_blank" rel="noopener">${esc(ch.url.replace("https://", ""))}</a>
      <button class="linkbtn" data-chact="check">Check now</button>
      <button class="linkbtn" data-chact="toggle">${ch.enabled ? "Pause" : "Resume"}</button>
      ${ch.kind === "playlist" ? "" : `<button class="linkbtn" data-chact="reposts">${ch.include_reposts ? "Ignore reposts" : "Include reposts"}</button>`}
      <button class="linkbtn" data-chact="remove">Remove ${ch.kind === "playlist" ? "playlist" : "channel"}</button>`;
    if (bar.dataset.k !== html2) { bar.innerHTML = html2; bar.dataset.k = html2; }
  } else {
    bar.hidden = true;
  }
}

const GROUPS = {
  active: ["wanted", "searching", "downloading"],
  done: ["done"],
  waiting: ["waiting", "gave_up"],
  skipped: ["skipped"],
};

function renderFilters(s) {
  const counts = { all: 0, active: 0, done: 0, waiting: 0, skipped: 0 };
  for (const t of s.tracks) {
    if (t.state !== "skipped") counts.all++;
    for (const [g, list] of Object.entries(GROUPS)) if (list.includes(t.state)) counts[g]++;
  }
  for (const b of document.querySelectorAll("#filters button")) {
    const f = b.dataset.f;
    const label = b.dataset.label || (b.dataset.label = b.textContent);
    b.innerHTML = `${esc(label)}<span class="n">${counts[f]}</span>`;
    b.setAttribute("aria-selected", String(ui.filter === f));
  }
}

function statusOf(t) {
  switch (t.state) {
    case "wanted": return { cls: "work", lbl: "In line to search" };
    case "searching": return { cls: "work", lbl: "Searching Soulseek" };
    case "downloading": {
      if (t.transfer_state === "DOWNLOADING") return { cls: "work", lbl: `Downloading ${Math.round(t.progress * 100)}%`, sub: t.peer };
      const q = t.place_in_queue ? `, place ${t.place_in_queue}` : "";
      return { cls: "work", lbl: `Waiting for peer${q}`, sub: t.peer };
    }
    case "waiting": return { cls: "wait", lbl: t.last_error || "Not found yet", sub: `Tries again ${inTime(t.retry_in)}` };
    case "done": return { cls: "done", lbl: "Downloaded", sub: (t.file_path || "").split(/[\\/]/).pop() };
    case "gave_up": return { cls: "gone", lbl: "Stopped looking", sub: t.last_error };
    case "skipped": return { cls: "gone", lbl: "Skipped", sub: t.last_error };
    default: return { cls: "", lbl: t.state };
  }
}

function actionsOf(t) {
  const a = [];
  if (t.state === "done") a.push(`<button class="linkbtn" data-act="show" data-id="${t.id}">Show file</button>`);
  if (["waiting", "gave_up", "skipped"].includes(t.state)) a.push(`<button class="linkbtn" data-act="retry" data-id="${t.id}">${t.state === "skipped" ? "Get it" : "Search now"}</button>`);
  if (["wanted", "searching", "downloading", "waiting", "gave_up"].includes(t.state)) a.push(`<button class="linkbtn" data-act="skip" data-id="${t.id}">Skip</button>`);
  return a.join("");
}

function renderTracks(s) {
  const list = $("#list");
  let rows = s.tracks;
  if (ui.filter === "all") rows = rows.filter((t) => t.state !== "skipped");
  else rows = rows.filter((t) => GROUPS[ui.filter].includes(t.state));

  if (!rows.length) {
    let msg;
    if (!s.channels.length) {
      msg = `<h2>Add your first channel</h2><p>Paste the link to a SoundCloud profile on the left, for example a label, artist or promo channel. New uploads show up here and get searched on Soulseek.</p>`;
    } else if (ui.filter === "all") {
      msg = `<h2>Nothing new yet</h2><p>Nicotine+ Sync checks your channels ${inTime(s.next_check_in) ? "again " + inTime(s.next_check_in) : "regularly"}. New uploads appear here.</p>`;
    } else {
      msg = `<p>No tracks here.</p>`;
    }
    const html = `<div class="empty">${msg}</div>`;
    if (list.innerHTML !== html) list.innerHTML = html;
    return;
  }

  const html = rows.map((t) => {
    const st = statusOf(t);
    const art = t.artwork
      ? `<div class="art" style="background-image:url('${esc(t.artwork)}')"></div>`
      : `<div class="art">${esc((t.artist || t.title || "?").trim().charAt(0).toUpperCase())}</div>`;
    const v = t.version ? ` <span class="v">(${esc(t.version)})</span>` : "";
    const chan = ui.channel ? "" : `<span> on ${esc(t.channel_name)}</span>`;
    const bar = t.state === "downloading" ? `<div class="bar"><i style="width:${Math.round((t.progress || 0) * 100)}%"></i></div>` : "";
    return `<div class="tr ${t.state}">
      ${art}
      <div class="t-main">
        <div class="t-title" title="${esc(t.raw_title)}">${esc(t.title)}${v}</div>
        <div class="t-artist"><a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.artist || "Unknown artist")}</a>${chan}</div>
      </div>
      <div class="st ${st.cls}"><span class="dot"></span><span class="lbl">${esc(st.lbl)}${st.sub ? `<span class="sub">${esc(st.sub)}</span>` : ""}</span></div>
      <div class="acts">${actionsOf(t)}</div>
      ${bar}
    </div>`;
  }).join("");
  if (list.dataset.k !== html) { list.innerHTML = html; list.dataset.k = html; }
}

function renderActivity(s) {
  const html = s.activity.map((a) => `<li class="${a.level === "warn" ? "warn" : ""}"><time>${clock(a.t)}</time><span>${esc(a.msg)}</span></li>`).join("")
    || `<li><span></span><span>Nothing yet.</span></li>`;
  const ul = $("#activity");
  if (ul.innerHTML !== html) ul.innerHTML = html;
}

/* ---------------- setup ---------------- */
function openSetup(settings) {
  ui.setupShown = true;
  $("#app").hidden = true;
  $("#setup").hidden = false;
  $("#s-terms").checked = settings.accepted_terms;
  const mode = settings.soulseek_mode || "builtin";
  for (const r of document.querySelectorAll('input[name="s-mode"]')) r.checked = r.value === mode;
  setupMode();
  if (ui.state.nicotine.plugin_installed) nicInstalledNote(ui.state.nicotine.plugins_dir);
  $("#s-user").value = settings.soulseek_username;
  $("#s-dir").value = settings.download_dir;
  $("#s-share").checked = settings.share_downloads;
}

function setupModeValue() {
  return document.querySelector('input[name="s-mode"]:checked')?.value || "builtin";
}
function setupMode() {
  const nic = setupModeValue() === "nicotine";
  $("#s-nicotine").hidden = !nic;
  $("#s-builtin").hidden = nic;
  $("#s-share-wrap").hidden = nic;
}
for (const r of document.querySelectorAll('input[name="s-mode"]')) r.addEventListener("change", setupMode);

function nicInstalledNote(dir) {
  const el = $("#s-nic-done");
  el.innerHTML = `<b>Plugin added.</b> Now open Nicotine+, go to Preferences, then Plugins, and turn on <b>Nicotine+ Sync Bridge</b>. If it was already on, turn it off and on again.`;
  el.title = dir;
  el.hidden = false;
  $("#s-nic-install").textContent = "Add plugin again";
}

async function installPlugin() {
  const r = await api("POST", "/api/nicotine/install");
  await refresh();
  return r;
}
$("#s-nic-install").addEventListener("click", async () => {
  try {
    const r = await installPlugin();
    showError($("#s-error"), "");
    nicInstalledNote(r.path);
  } catch (e) { showError($("#s-error"), e.message); }
});

$("#s-go").addEventListener("click", async () => {
  const err = $("#s-error");
  const mode = setupModeValue();
  const user = $("#s-user").value.trim(), pass = $("#s-pass").value;
  if (!$("#s-terms").checked) return showError(err, "Tick the box under step 1 to continue.");
  if (mode === "builtin" && (!user || (!pass && !ui.state?.settings.has_password))) return showError(err, "Fill in a Soulseek username and password.");
  if (mode === "nicotine" && !ui.state?.nicotine.plugin_installed) return showError(err, "Add the plugin to Nicotine+ first (step 2).");
  if (!$("#s-dir").value.trim()) return showError(err, "Choose a download folder.");
  showError(err, "");
  $("#s-go").disabled = true;
  try {
    const body = { accepted_terms: true, soulseek_mode: mode, download_dir: $("#s-dir").value };
    if (mode === "builtin") Object.assign(body, { soulseek_username: user, soulseek_password: pass, share_downloads: $("#s-share").checked });
    await api("PUT", "/api/settings", body);
    await refresh();
  } catch (e) {
    showError(err, e.message);
  } finally {
    $("#s-go").disabled = false;
  }
});

/* ---------------- channels ---------------- */
const isPlaylistUrl = (v) => /\/sets\/[^/?#]+/i.test(v);
$("#add-url").addEventListener("input", (e) => {
  const v = e.target.value.trim(), pl = isPlaylistUrl(v);
  $("#add-more").hidden = !v;
  $("#add-playlist-hint").hidden = !pl;
  $("#add-backlog-field").hidden = pl;
  $("#add-reposts-field").hidden = pl;
  $("#add-btn").textContent = pl ? "Add playlist" : "Add channel";
});
$("#add-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#add-btn"), err = $("#add-error");
  showError(err, "");
  btn.disabled = true;
  const pl = isPlaylistUrl($("#add-url").value);
  btn.textContent = pl ? "Looking up playlist…" : "Looking up channel…";
  try {
    const r = await api("POST", "/api/channels", {
      url: $("#add-url").value, backlog: Number($("#add-backlog").value), include_reposts: $("#add-reposts").checked,
    });
    $("#add-url").value = "";
    $("#add-more").hidden = true;
    ui.channel = r.id;
    toast(r.kind === "playlist" ? `Getting the tracks from ${r.name}` : `Watching ${r.name}`);
    refresh();
  } catch (ex) {
    showError(err, ex.message);
  } finally {
    btn.disabled = false;
    btn.textContent = isPlaylistUrl($("#add-url").value) ? "Add playlist" : "Add channel";
  }
});

$("#channels").addEventListener("click", (e) => {
  const b = e.target.closest("[data-ch]");
  if (!b) return;
  ui.channel = b.dataset.ch ? Number(b.dataset.ch) : null;
  $("#list").dataset.k = "";
  refresh();
});

$("#channel-bar").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-chact]");
  if (!b || !ui.channel) return;
  const ch = ui.state.channels.find((c) => c.id === ui.channel);
  const act = b.dataset.chact;
  try {
    if (act === "check") { await api("POST", `/api/channels/${ch.id}/check`); toast("Checking channel"); }
    if (act === "toggle") await api("PATCH", `/api/channels/${ch.id}`, { enabled: !ch.enabled });
    if (act === "reposts") await api("PATCH", `/api/channels/${ch.id}`, { include_reposts: !ch.include_reposts });
    if (act === "remove") {
      if (!confirmRemove(b, ch.name)) return;
      await api("DELETE", `/api/channels/${ch.id}`);
      ui.channel = null;
      toast(`Removed ${ch.name}`);
    }
  } catch (ex) { toast(ex.message); }
  refresh();
});

// Two-click confirm (no blocking browser dialogs inside the app window).
function confirmRemove(btn, name) {
  if (btn.dataset.armed) return true;
  btn.dataset.armed = "1";
  btn.textContent = `Click again to stop watching ${name}. Downloaded files stay.`;
  setTimeout(() => { delete btn.dataset.armed; btn.textContent = "Remove channel"; }, 4000);
  return false;
}

/* ---------------- tracks ---------------- */
$("#filters").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-f]");
  if (!b) return;
  ui.filter = b.dataset.f;
  render();
});

$("#list").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-act]");
  if (!b) return;
  const id = b.dataset.id;
  try {
    if (b.dataset.act === "show") await api("POST", "/api/open", { track: Number(id) });
    if (b.dataset.act === "retry") { await api("POST", `/api/tracks/${id}/retry`); toast("Searching again"); }
    if (b.dataset.act === "skip") await api("POST", `/api/tracks/${id}/skip`);
  } catch (ex) { toast(ex.message); }
  refresh();
});

$("#check-now").addEventListener("click", async () => { await api("POST", "/api/check-now"); toast("Checking all channels"); refresh(); });
$("#open-folder").addEventListener("click", () => api("POST", "/api/open", {}).catch((e) => toast(e.message)));

/* ---------------- settings ---------------- */
function openSettings() {
  const s = ui.state.settings, f = $("#settings-form");
  for (const el of f.elements) {
    if (!el.name) continue;
    const v = s[el.name];
    if (el.type === "checkbox") el.checked = !!v;
    else if (el.name === "soulseek_password") el.value = "";
    else if (el.name === "share_dirs") el.value = (v || []).join("\n");
    else el.value = v ?? "";
  }
  $("#version").textContent = `Nicotine+ Sync ${ui.state.version}`;
  settingsMode();
  showError($("#set-error"), "");
  $("#drawer").hidden = $("#scrim").hidden = false;
  f.elements.soulseek_username.focus();
}
function settingsMode() {
  const mode = $("#set-mode").value;
  for (const el of document.querySelectorAll("#settings-form [data-mode]")) el.hidden = el.dataset.mode !== mode;
  const st = ui.state;
  const msg = !st.nicotine.plugin_installed
    ? "The plugin isn't in Nicotine+ yet. Add it, then turn on Nicotine+ Sync Bridge in Nicotine+ (Preferences, Plugins)."
    : st.settings.soulseek_mode === "nicotine" && st.soulseek.status === "connected"
      ? (st.soulseek.username ? `Connected through Nicotine+ as ${st.soulseek.username}.` : "Connected through Nicotine+.")
      : "Plugin added. Turn on Nicotine+ Sync Bridge in Nicotine+ (Preferences, Plugins). Save to switch.";
  $("#set-nic-status").textContent = msg;
  $("#set-nic-install").textContent = st.nicotine.plugin_installed ? "Add plugin to Nicotine+ again" : "Add plugin to Nicotine+";
}
$("#set-mode").addEventListener("change", settingsMode);
$("#set-nic-install").addEventListener("click", async () => {
  try {
    await installPlugin();
    toast("Plugin added. Turn it on in Nicotine+");
    settingsMode();
  } catch (e) { showError($("#set-error"), e.message); }
});

function closeSettings() { $("#drawer").hidden = $("#scrim").hidden = true; }
$("#open-settings").addEventListener("click", openSettings);
$("#close-settings").addEventListener("click", closeSettings);
$("#scrim").addEventListener("click", closeSettings);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSettings(); });

$("#settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target, body = {};
  for (const el of f.elements) {
    if (!el.name) continue;
    if (el.type === "checkbox") body[el.name] = el.checked;
    else if (el.name === "share_dirs") body[el.name] = el.value.split("\n").map((x) => x.trim()).filter(Boolean);
    else body[el.name] = el.value;
  }
  try {
    const r = await api("PUT", "/api/settings", body);
    closeSettings();
    toast(r.changed.length ? "Settings saved" : "Nothing changed");
    refresh();
  } catch (ex) {
    showError($("#set-error"), ex.message);
  }
});

/* ---------------- native folder picker (app window only) ---------------- */
function enablePickers() {
  if (!(window.pywebview && window.pywebview.api && window.pywebview.api.pick_folder)) return;
  for (const b of document.querySelectorAll("[data-pick]")) {
    b.hidden = false;
    b.onclick = async () => {
      const input = document.getElementById(b.dataset.pick);
      const path = await window.pywebview.api.pick_folder(input.value);
      if (path) input.value = path;
    };
  }
}
window.addEventListener("pywebviewready", enablePickers);
enablePickers();

refresh();
