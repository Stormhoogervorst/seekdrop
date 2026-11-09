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
    $("#deck-title").textContent = "SeekDrop stopped";
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
  renderNotices(s);
  if (!$("#drawer").hidden) { libraryStatus(); rekordboxStatus(); }
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

function renderNotices(s) {
  const p = s.politeness || {}, box = $("#notices");
  const items = [];
  const lib = s.library || {};
  if (lib.scanning) {
    items.push(["Reading your music folders", lib.total ? `${lib.done} of ${lib.total} new or changed files. Searching starts when this is done.` : "Looking for new files."]);
  }
  if (p.paused) items.push(["Downloads paused", p.paused]);
  if (p.share_warning) items.push(["Nothing shared", p.share_warning]);
  box.hidden = !items.length;
  box.innerHTML = items.map(([t, m]) => `<p><b>${esc(t)}.</b> ${esc(m)}</p>`).join("");
}

function renderBlocked() {
  const list = (ui.state.politeness || {}).blocked_peers || [];
  $("#set-blocked").hidden = !list.length;
  $("#set-blocked-list").innerHTML = list.map((b) =>
    `<li><span><b>${esc(b.username)}</b> <small>${esc(b.block_reason)}</small></span>
     <button type="button" class="btn soft" data-unblock="${esc(b.username)}">Unblock</button></li>`).join("");
}
$("#set-blocked-list").addEventListener("click", async (e) => {
  const name = e.target.dataset && e.target.dataset.unblock;
  if (!name) return;
  try {
    await api("POST", "/api/peers/unblock", { username: name });
    await refresh();
    renderBlocked();
  } catch (ex) { showError($("#set-error"), ex.message); }
});

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
    sub.textContent = s.soulseek.error || (viaNic ? "Open Nicotine+ and turn on the SeekDrop Bridge plugin." : "Check your account in Settings.");
    sub.classList.add("err");
  }
}

function renderChannels(s) {
  const nav = $("#channels");
  const total = s.channels.reduce((a, c) => a + c.done_count, 0);
  let html = `<button class="ch" data-ch="" aria-current="${!ui.channel}">
      <span class="ch-name">All channels</span><span class="ch-count${total ? "" : " zero"}">${total}</span>
      <span class="ch-meta">${s.channels.length} watched</span></button>`;
  for (const c of s.channels) {
    let meta = c.checking ? "Checking…" : `Checked ${ago(c.last_checked)}`;
    let cls = "ch-meta";
    if (c.last_error) { meta = c.last_error; cls += " err"; }
    if (!c.enabled) meta = "Paused";
    if (c.kind === "playlist") meta = `Playlist · ${meta}`;
    html += `<button class="ch${c.enabled ? "" : " off"}" data-ch="${c.id}" aria-current="${ui.channel === c.id}" title="${esc(c.url)}">
      <span class="ch-name">${esc(c.name)}</span>
      <span class="ch-count${c.done_count ? "" : " zero"}" title="Downloaded">${c.done_count}</span>
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
      <button class="linkbtn" data-chact="rules" title="Which uploads are fetched">Rules: ${esc(ch.rules_summary || "")}</button>
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
  collected: ["collected"],
};

function renderFilters(s) {
  const counts = { all: 0, active: 0, done: 0, waiting: 0, skipped: 0, collected: 0, quarantine: (s.rejects || []).length,
    duplicates: ui.dups ? ui.dups.length : "" };
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

// Real failures (not "not found yet"): the engine's "Error: …" and "Search failed…" messages.
function isError(msg) { return /^(Error:|Search failed)/.test(msg || ""); }

// Last day the app looks for a better copy (step 4).
function untilDate(createdAt) {
  const d = new Date((createdAt + (ui.state.upgrade_days || 30) * 86400) * 1000);
  return d.toLocaleDateString([], { day: "numeric", month: "short" });
}

// Where the audio stops (roadmap step 3), e.g. "21.9 kHz" or "Suspect: stops at 20.3 kHz".
function qualityOf(t) {
  if (!t.cutoff_hz) return "";
  const khz = `${(t.cutoff_hz / 1000).toFixed(1)} kHz`;
  if (t.quality === "suspect") return `Suspect: stops at ${khz}`;
  return t.cutoff_hz >= 22000 ? "Full range" : khz;
}

// cls picks the status style, ic the leading Lucide icon.
function statusOf(t) {
  switch (t.state) {
    case "wanted": return { cls: "work", ic: "clock", lbl: "In line to search" };
    case "searching": return { cls: "work spinning", ic: "loader-circle", lbl: "Searching Soulseek" };
    case "downloading": {
      if (t.transfer_state === "DOWNLOADING") return { cls: "live spinning", ic: "loader-circle", lbl: `Downloading ${Math.round(t.progress * 100)}%`, sub: t.peer };
      const q = t.place_in_queue ? `, place ${t.place_in_queue}` : "";
      return { cls: "work spinning", ic: "loader-circle", lbl: `Waiting for peer${q}`, sub: t.peer };
    }
    case "waiting": return { cls: isError(t.last_error) ? "err" : "wait", ic: "clock", lbl: t.last_error || "Not found yet", sub: `Tries again ${inTime(t.retry_in)}` };
    case "done": {
      const tier = (ui.state.tier_labels || {})[t.tier] || "";
      if (t.upgrade_path) return { cls: "done", ic: "check", lbl: "Better copy found", sub: `${(ui.state.tier_labels || {})[t.upgrade_tier] || "Higher quality"} instead of ${tier || "this file"}${t.in_rekordbox ? ". Replacing loses its cue points in Rekordbox" : ""}` };
      if (t.transfer_state) return { cls: "work spinning", ic: "loader-circle", lbl: "Getting a better copy", sub: tier ? `You have ${tier}` : "" };
      const bits = [tier, qualityOf(t), t.in_rekordbox ? "in Rekordbox" : "", (t.file_path || "").split(/[\\/]/).pop()];
      if (t.next_upgrade > 0) bits.splice(1, 0, `looking for better until ${untilDate(t.created_at)}`);
      return { cls: "done", ic: "check", lbl: "Downloaded", sub: bits.filter(Boolean).join(" · ") };
    }
    case "collected": return { cls: "done", ic: "check", lbl: "Already in your collection", sub: (t.file_path || "").split(/[\\/]/).slice(-2).join("/") };
    case "gave_up": return { cls: "gone", ic: "circle", lbl: "Stopped looking", sub: t.last_error };
    case "skipped": return { cls: "gone", ic: "circle", lbl: "Skipped", sub: t.last_error };
    default: return { cls: "", ic: "", lbl: t.state };
  }
}

function actionsOf(t) {
  const a = [];
  if (t.state === "done" && t.upgrade_path) {
    a.push(`<button class="rowbtn" data-act="replace" data-id="${t.id}">Replace</button>`);
    a.push(`<button class="rowbtn" data-act="keep" data-id="${t.id}">Keep</button>`);
  }
  if (t.state === "done" || t.state === "collected") a.push(`<button class="rowbtn" data-act="show" data-id="${t.id}">Show file</button>`);
  if (t.state === "collected") a.push(`<button class="rowbtn" data-act="retry" data-id="${t.id}">Get it anyway</button>`);
  if (["waiting", "gave_up", "skipped"].includes(t.state)) a.push(`<button class="rowbtn" data-act="retry" data-id="${t.id}">${t.state === "skipped" ? "Get it" : "Search now"}</button>`);
  if (t.attempts > 0 && ["wanted", "waiting", "gave_up", "skipped"].includes(t.state)) a.push(`<button class="rowbtn" data-act="why" data-id="${t.id}">Why not?</button>`);
  if (["wanted", "searching", "downloading", "waiting", "gave_up"].includes(t.state)) a.push(`<button class="rowbtn" data-act="skip" data-id="${t.id}">Skip</button>`);
  return a.join("");
}

// Files that failed the file checks (roadmap step 2): reason, where it came from, approve or delete.
function renderRejects(s) {
  const list = $("#list");
  const rows = s.rejects || [];
  let html;
  if (!rows.length) {
    html = `<div class="empty"><p>Nothing in quarantine. Files that fail the checks show up here.</p></div>`;
  } else {
    html = rows.map((r) => {
      const v = r.version ? ` <span class="v">(${esc(r.version)})</span>` : "";
      const file = (r.remote_file || "").split(/[\\/]/).pop();
      return `<div class="tr quarantined">
      <div class="art">${esc((r.artist || r.title || "?").trim().charAt(0).toUpperCase())}</div>
      <div class="t-main">
        <div class="t-title">${esc(r.title)}${v}</div>
        <div class="t-artist">${esc(r.artist || "Unknown artist")}<span> on ${esc(r.channel_name)}</span></div>
      </div>
      <div class="st err"><span class="st-line">${icon("circle-slash")}<span class="lbl" title="${esc(r.reason)}">${esc(r.reason)}</span></span><span class="sub" title="${esc(r.remote_file)}">${esc(r.peer)} · ${esc(file)}</span></div>
      <div class="acts">
        <button class="rowbtn" data-ract="approve" data-id="${r.id}">Approve anyway</button>
        <button class="rowbtn" data-ract="delete" data-id="${r.id}">Delete</button>
      </div>
    </div>`;
    }).join("");
  }
  if (list.dataset.k !== html) { list.innerHTML = html; list.dataset.k = html; }
}

function renderTracks(s) {
  const list = $("#list");
  if (ui.filter === "quarantine") return renderRejects(s);
  if (ui.filter === "duplicates") return renderDuplicates();
  let rows = s.tracks;
  if (ui.filter === "all") rows = rows.filter((t) => t.state !== "skipped");
  else rows = rows.filter((t) => GROUPS[ui.filter].includes(t.state));

  if (!rows.length) {
    let msg;
    if (!s.channels.length) {
      msg = `<h2>Add your first channel</h2><p>Paste the link to a SoundCloud profile on the left, for example a label, artist or promo channel. New uploads show up here and get searched on Soulseek.</p>`;
    } else if (ui.filter === "all") {
      msg = `<h2>Nothing new yet</h2><p>SeekDrop checks your channels ${inTime(s.next_check_in) ? "again " + inTime(s.next_check_in) : "regularly"}. New uploads appear here.</p>`;
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
    const bar = t.state === "downloading" && t.transfer_state === "DOWNLOADING" ? `<div class="bar" role="progressbar" aria-valuenow="${Math.round((t.progress || 0) * 100)}" aria-valuemin="0" aria-valuemax="100"><i style="width:${Math.round((t.progress || 0) * 100)}%"></i></div>` : "";
    return `<div class="tr ${t.state}">
      ${art}
      <div class="t-main">
        <div class="t-title" title="${esc(t.raw_title)}">${esc(t.title)}${v}</div>
        <div class="t-artist"><a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.artist || "Unknown artist")}</a>${chan}</div>
        ${bar}
      </div>
      <div class="st ${st.cls}"><span class="st-line">${st.ic ? icon(st.ic, st.cls.includes("spinning") ? "spin" : "") : ""}<span class="lbl">${esc(st.lbl)}</span></span>${st.sub ? `<span class="sub">${esc(st.sub)}</span>` : ""}</div>
      <div class="acts">${actionsOf(t)}</div>
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
  el.innerHTML = `<b>Plugin added.</b> Now open Nicotine+, go to Preferences, then Plugins, and turn on <b>SeekDrop Bridge</b>. If it was already on, turn it off and on again.`;
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
    if (act === "rules") return openRules(ch);
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
function pickFilter(e) {
  const b = e.target.closest("button[data-f]");
  if (!b) return;
  ui.filter = b.dataset.f;
  render();
}
$("#filters").addEventListener("click", pickFilter);

$("#list").addEventListener("click", async (e) => {
  const q = e.target.closest("[data-ract]");
  if (q) {
    try {
      if (q.dataset.ract === "approve") { await api("POST", `/api/rejects/${q.dataset.id}/approve`); toast("Moved to your music folder"); }
      if (q.dataset.ract === "delete") { await api("POST", `/api/rejects/${q.dataset.id}/delete`); toast("Deleted"); }
    } catch (ex) { toast(ex.message); }
    return refresh();
  }
  const b = e.target.closest("[data-act]");
  if (!b) return;
  const id = b.dataset.id;
  try {
    if (b.dataset.act === "show") await api("POST", "/api/open", { track: Number(id) });
    if (b.dataset.act === "retry") { await api("POST", `/api/tracks/${id}/retry`); toast("Searching again"); }
    if (b.dataset.act === "skip") await api("POST", `/api/tracks/${id}/skip`);
    if (b.dataset.act === "why") return openWhy(Number(id));
    if (b.dataset.act === "replace") { await api("POST", `/api/tracks/${id}/upgrade/replace`); toast("Replaced. The old file is in SeekDrop's trash."); }
    if (b.dataset.act === "keep") { await api("POST", `/api/tracks/${id}/upgrade/keep`); toast("Kept your file"); }
  } catch (ex) { toast(ex.message); }
  refresh();
});

$("#check-now").addEventListener("click", async () => { await api("POST", "/api/check-now"); toast("Checking all channels"); refresh(); });
$("#open-folder").addEventListener("click", () => api("POST", "/api/open", {}).catch((e) => toast(e.message)));

/* ---------------- settings ---------------- */
function profileHelp() {
  const p = (ui.state.profiles || {})[$("#set-profile").value];
  $("#set-profile-help").textContent = p ? `${p.help} Order: ${p.ladder.join(", ")}.` : "";
}
$("#set-profile").addEventListener("change", profileHelp);

const LIST_FIELDS = ["share_dirs", "library_dirs", "block_keywords", "block_artists"];
const lines = (text) => text.split("\n").map((x) => x.trim()).filter(Boolean);

function openSettings() {
  const s = ui.state.settings, f = $("#settings-form");
  for (const el of f.elements) {
    if (!el.name) continue;
    const v = s[el.name];
    if (el.type === "checkbox") el.checked = !!v;
    else if (el.name === "soulseek_password") el.value = "";
    else if (LIST_FIELDS.includes(el.name)) el.value = (v || []).join("\n");
    else el.value = v ?? "";
  }
  $("#version").textContent = `SeekDrop ${ui.state.version}`;
  $("#set-checks-status").textContent = ui.state.checks && ui.state.checks.available
    ? "On. Every download is checked with ffmpeg before it goes to your music folder."
    : "Off: ffmpeg isn't installed, so downloads aren't checked. Install ffmpeg (on a Mac: brew install ffmpeg) and restart SeekDrop.";
  profileHelp();
  libraryStatus();
  rekordboxStatus();
  templatePreview();
  renderBlocked();
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
    ? "The plugin isn't in Nicotine+ yet. Add it, then turn on SeekDrop Bridge in Nicotine+ (Preferences, Plugins)."
    : st.settings.soulseek_mode === "nicotine" && st.soulseek.status === "connected"
      ? (st.soulseek.username ? `Connected through Nicotine+ as ${st.soulseek.username}.` : "Connected through Nicotine+.")
      : "Plugin added. Turn on SeekDrop Bridge in Nicotine+ (Preferences, Plugins). Save to switch.";
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

/* ---------------- Rekordbox (roadmap step 12) ---------------- */
function rekordboxStatus() {
  const r = (ui.state || {}).rekordbox || {};
  let msg;
  if (!r.enabled) msg = "Off.";
  else if (r.error) msg = `Couldn't write the file: ${r.error}`;
  else if (r.written_at) msg = `${r.tracks} track(s) in ${r.playlists} playlist(s), written ${ago(r.written_at)}.`;
  else msg = "Not written yet.";
  $("#set-rb-status").textContent = msg;
  $("#set-rb-status").title = r.path || "";
  const lib = r.library || {};
  $("#set-rb-lib-status").textContent = !lib.set ? "" : lib.error ? `Can't use it: ${lib.error}.`
    : `Read: ${lib.tracks.toLocaleString()} tracks in Rekordbox.`;
  $("#set-rb-update").disabled = !$("#settings-form").elements.rekordbox_export.checked;   // what is on screen counts
}
$("#settings-form").elements.rekordbox_export.addEventListener("change", rekordboxStatus);
$("#set-rb-update").addEventListener("click", async () => {
  try {
    // Save a changed on/off or path first, so "Update now" uses what is on screen.
    await api("PUT", "/api/settings", { rekordbox_export: $("#settings-form").elements.rekordbox_export.checked,
                                        rekordbox_xml_path: $("#settings-form").elements.rekordbox_xml_path.value });
    const r = await api("POST", "/api/rekordbox/update");
    toast(`Rekordbox file written: ${r.tracks} track(s)`);
  } catch (e) { toast(e.message); }
  await refresh();
  rekordboxStatus();
});
$("#set-rb-show").addEventListener("click", async () => {
  try { await api("POST", "/api/open", { rekordbox: true }); } catch (e) { toast(e.message); }
});

/* ---------------- your music folders (roadmap step 11) ---------------- */
function libraryStatus() {
  const l = (ui.state || {}).library || {};
  let msg = l.scanning ? `Reading… ${l.done} of ${l.total || "?"}`
    : `${(l.files || 0).toLocaleString()} files known${l.scanned_at ? `, scanned ${ago(l.scanned_at)}` : ""}.`;
  if ((l.missing || []).length) msg += ` Not found: ${l.missing.join(", ")}.`;
  if (l.error) msg += ` ${l.error}`;
  $("#set-library-status").textContent = msg;
}
$("#set-scan").addEventListener("click", async () => {
  try { await api("POST", "/api/library/scan"); toast("Scanning your music folders"); } catch (e) { toast(e.message); }
  setTimeout(refresh, 500);
});

let dupFetched = 0;
async function loadDuplicates() {
  if (Date.now() - dupFetched < 8000) return;
  dupFetched = Date.now();
  try {
    ui.dups = (await api("GET", "/api/duplicates")).groups;
    if (ui.filter === "duplicates") renderDuplicates();
    renderFilters(ui.state);
  } catch (e) { dupFetched = 0; }
}
function renderDuplicates() {
  const list = $("#list");
  loadDuplicates();
  const groups = ui.dups;
  let html;
  if (!groups) html = `<div class="empty"><p>Looking for duplicates…</p></div>`;
  else if (!groups.length) html = `<div class="empty"><p>No duplicates in your download folder. The same track in several files shows up here. SeekDrop never deletes anything by itself.</p></div>`;
  else {
    html = groups.map((g) => {
      const v = g.version ? ` <span class="v">(${esc(g.version)})</span>` : "";
      const files = g.files.map((f) => {
        const q = [(ui.state.tier_labels || {})[f.tier] || f.ext.toUpperCase(), f.bitrate ? `${f.bitrate} kbps` : "", mmss(f.duration), `${(f.size / 1048576).toFixed(1)} MB`].filter(Boolean).join(" · ");
        return `<div class="dup-file${f.best ? " best" : ""}">
          <span class="dup-name" title="${esc(f.path)}">${esc(f.path.split(/[\\/]/).slice(-2).join("/"))}</span>
          <span class="dup-q">${esc(q)}</span>
          <span class="dup-flag">${f.best ? "Best" : ""}</span>
          <button class="rowbtn" data-dup="${esc(f.path)}">Show file</button></div>`;
      }).join("");
      return `<div class="tr dup"><div class="t-main"><div class="t-title">${esc(g.title)}${v}</div>
        <div class="t-artist">${esc(g.artist || "Unknown artist")}</div></div><div class="dup-files">${files}</div></div>`;
    }).join("");
  }
  if (list.dataset.k !== html) { list.innerHTML = html; list.dataset.k = html; }
}
$("#list").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-dup]");
  if (!b) return;
  try { await api("POST", "/api/open", { path: b.dataset.dup }); } catch (ex) { toast(ex.message); }
});

let templateTimer = null;
function templatePreview() {
  clearTimeout(templateTimer);
  templateTimer = setTimeout(async () => {
    const out = $("#set-template-example");
    try {
      const r = await api("POST", "/api/template/preview", { template: $("#set-template").value });
      out.textContent = r.error || `Example: ${r.example}`;
      out.classList.toggle("error", !!r.error);
    } catch (e) { out.textContent = ""; }
  }, 200);
}
$("#set-template").addEventListener("input", templatePreview);

function closeSettings() { $("#drawer").hidden = $("#why").hidden = $("#rules").hidden = $("#scrim").hidden = true; ui.why = null; }

/* ---------------- rules per channel (roadmap step 9) ---------------- */
function fillRules(r, reposts) {
  const f = $("#rules-form");
  for (const el of f.elements) {
    if (!el.name) continue;
    if (el.name === "include_reposts") el.checked = !!reposts;
    else if (el.type === "checkbox") el.checked = !!r[el.name];
    else if (el.name === "exclude" || el.name === "require") el.value = (r[el.name] || []).join("\n");
    else el.value = r[el.name] ?? "";
  }
}
function openRules(ch) {
  ui.rulesFor = ch.id;
  $("#rules-title").textContent = `Rules for ${ch.name}`;
  $("#rules-reposts-wrap").hidden = ch.kind === "playlist";
  fillRules(ch.rules, ch.include_reposts);
  showError($("#rules-error"), "");
  $("#rules").hidden = $("#scrim").hidden = false;
}
$("#close-rules").addEventListener("click", closeSettings);
$("#rules-reset").addEventListener("click", () => {
  const ch = ui.state.channels.find((c) => c.id === ui.rulesFor);
  fillRules(ui.state.rule_defaults, ch && ch.include_reposts);
});
$("#rules-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target, rules = {};
  let reposts = null;
  for (const el of f.elements) {
    if (!el.name) continue;
    if (el.name === "include_reposts") reposts = el.checked;
    else if (el.type === "checkbox") rules[el.name] = el.checked;
    else if (el.name === "exclude" || el.name === "require") rules[el.name] = lines(el.value);
    else rules[el.name] = Number(el.value || 0);
  }
  const body = { rules };
  const ch = ui.state.channels.find((c) => c.id === ui.rulesFor);
  if (ch && ch.kind !== "playlist" && reposts !== null) body.include_reposts = reposts;
  try {
    const r = await api("PATCH", `/api/channels/${ui.rulesFor}`, body);
    closeSettings();
    const bits = [];
    if (r.revived) bits.push(`${r.revived} track(s) are wanted again`);
    if (r.skipped) bits.push(`${r.skipped} skipped`);
    toast(bits.length ? `Rules saved: ${bits.join(", ")}` : "Rules saved");
    refresh();
  } catch (ex) { showError($("#rules-error"), ex.message); }
});

/* ---------------- "Why not?" (roadmap step 5) ---------------- */
const mmss = (s) => s ? `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}` : "";
function candMeta(c) {
  const fmt = (c.ext || "").toUpperCase() + (c.bitrate ? ` ${c.bitrate} kbps` : "") + (c.bit_depth ? ` ${c.bit_depth}-bit` : "");
  return [c.username, fmt.trim(), mmss(c.duration), c.free_slots ? "free slot" : (c.queue ? `queue ${c.queue}` : "")].filter(Boolean).join(" · ");
}
async function openWhy(id) {
  let d;
  try { d = await api("GET", `/api/tracks/${id}/why`); } catch (ex) { return toast(ex.message); }
  ui.why = id;
  const t = d.track, last = d.searches[0];
  const v = t.version ? ` <span class="v">(${esc(t.version)})</span>` : "";
  let html = `<p class="why-title"><b>${esc(t.title)}</b>${v}<br><span class="hint">${esc(t.artist || "")} · ${esc(mmss(t.duration))} on SoundCloud</span></p>`;
  if (!last) {
    html += `<p class="hint">No search yet.</p>`;
  } else {
    html += `<p class="why-summary">${esc(last.summary || t.last_error || "Found a match, but the download didn't work out.")}</p>`;
    html += `<h3>Searched for</h3><ul class="why-queries">${last.queries.map((q) => `<li><span>${esc(q.query)}</span><span class="n">${q.results} results</span></li>`).join("")}</ul>`;
    html += `<h3>Closest files</h3>`;
    html += last.candidates.length ? `<ul class="why-cands">${last.candidates.map((c, i) => `
      <li class="${c.rejected ? "no" : "yes"}">
        <div class="cand-main">
          <div class="cand-name" title="${esc(c.filename)}">${esc(c.filename.split(/[\\/]/).pop())}</div>
          <div class="cand-meta">${esc(candMeta(c))}</div>
          <div class="cand-why">${c.rejected ? esc(c.rejected) : "Match"}</div>
        </div>
        <button class="rowbtn" data-pick="${i}" ${d.busy || t.state === "done" ? "disabled" : ""}>Download this anyway</button>
      </li>`).join("")}</ul>` : `<p class="hint">Nothing came back.</p>`;
    if (d.searches.length > 1) html += `<p class="hint">Earlier: ${d.searches.slice(1).map((s) => esc(s.summary || "found a match")).join(" · ")}</p>`;
  }
  html += `<h3>Correct this track</h3>
    <form class="why-fix" id="why-fix">
      <label class="field"><span>Artist</span><input class="plain" name="artist" value="${esc(t.fix_artist || t.artist || "")}" spellcheck="false"></label>
      <label class="field"><span>Title</span><input class="plain" name="title" value="${esc(t.fix_title || t.title || "")}" spellcheck="false"></label>
      <label class="field"><span>Version</span><input class="plain" name="version" value="${esc(t.fix_version || t.version || "")}" placeholder="Original" spellcheck="false"></label>
      <button class="btn soft" type="submit">Save and search again</button>
    </form>
    <p class="hint">Your correction wins over how SeekDrop read the SoundCloud title.</p>
    <h3>Search with another term</h3>
    <form class="why-query" id="why-query"><input class="plain" name="q" value="${esc(t.custom_query || "")}" placeholder="e.g. artist title remixer" spellcheck="false">
    <button class="btn soft" type="submit">Search</button></form>
    <p class="hint">Saved for this track and tried first from now on.</p>
    <div class="why-foot"><button class="btn soft" id="why-stop" ${t.state === "skipped" ? "disabled" : ""}>Stop looking</button></div>`;
  const body = $("#why-body");
  body.innerHTML = html;
  body.querySelectorAll("[data-pick]").forEach((b) => b.addEventListener("click", async () => {
    try { await api("POST", `/api/tracks/${id}/pick`, { candidate: last.candidates[Number(b.dataset.pick)] }); toast("Downloading. It's still checked first."); closeSettings(); }
    catch (ex) { toast(ex.message); }
    refresh();
  }));
  $("#why-query").addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await api("POST", `/api/tracks/${id}/query`, { query: e.target.q.value }); toast(e.target.q.value.trim() ? "Searching with your term" : "Back to the automatic terms"); closeSettings(); }
    catch (ex) { toast(ex.message); }
    refresh();
  });
  $("#why-fix").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    try { await api("POST", `/api/tracks/${id}/fix`, { artist: f.artist.value, title: f.title.value, version: f.version.value }); toast("Saved. Searching again."); closeSettings(); }
    catch (ex) { toast(ex.message); }
    refresh();
  });
  $("#why-stop").addEventListener("click", async () => {
    try { await api("POST", `/api/tracks/${id}/stop`); toast("Stopped looking"); closeSettings(); } catch (ex) { toast(ex.message); }
    refresh();
  });
  $("#why").hidden = $("#scrim").hidden = false;
}
$("#close-why").addEventListener("click", closeSettings);
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
    else if (LIST_FIELDS.includes(el.name)) body[el.name] = lines(el.value);
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
function enableAddFolder() {
  if (!(window.pywebview && window.pywebview.api && window.pywebview.api.pick_folder)) return;
  for (const b of document.querySelectorAll("[data-add-to]")) {
    b.hidden = false;
    b.onclick = async () => {
      const box = document.getElementById(b.dataset.addTo);
      const path = await window.pywebview.api.pick_folder("");
      if (!path) return;
      const lines = box.value.split("\n").map((l) => l.trim()).filter(Boolean);
      if (!lines.includes(path)) lines.push(path);
      box.value = lines.join("\n");
    };
  }
}
window.addEventListener("pywebviewready", () => { enablePickers(); enableAddFolder(); });
enablePickers();
enableAddFolder();

refresh();
