// Lucide icons (lucide-static 0.460.0, ISC License, https://lucide.dev). 20px, 1.5px stroke.
const ICONS = {
 "activity": "<path d=\"M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2\"/>",
 "circle": "<circle cx=\"12\" cy=\"12\" r=\"10\"/>",
 "check": "<path d=\"M20 6 9 17l-5-5\"/>",
 "chevron-right": "<path d=\"m9 18 6-6-6-6\"/>",
 "circle-slash": "<circle cx=\"12\" cy=\"12\" r=\"10\"/> <line x1=\"9\" x2=\"15\" y1=\"15\" y2=\"9\"/>",
 "clock": "<circle cx=\"12\" cy=\"12\" r=\"10\"/> <polyline points=\"12 6 12 12 16 14\"/>",
 "disc-3": "<circle cx=\"12\" cy=\"12\" r=\"10\"/> <path d=\"M6 12c0-1.7.7-3.2 1.8-4.2\"/> <circle cx=\"12\" cy=\"12\" r=\"2\"/> <path d=\"M18 12c0 1.7-.7 3.2-1.8 4.2\"/>",
 "link": "<path d=\"M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71\"/> <path d=\"M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71\"/>",
 "loader-circle": "<path d=\"M21 12a9 9 0 1 1-6.219-8.56\"/>",
 "search": "<circle cx=\"11\" cy=\"11\" r=\"8\"/> <path d=\"m21 21-4.3-4.3\"/>",
 "settings": "<path d=\"M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z\"/> <circle cx=\"12\" cy=\"12\" r=\"3\"/>",
 "skip-forward": "<polygon points=\"5 4 15 12 5 20 5 4\"/> <line x1=\"19\" x2=\"19\" y1=\"5\" y2=\"19\"/>"
};

function icon(name, cls = "") {
  return `<svg class="ic ${cls}" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;
}

// Static markup: <i data-icon="settings"></i> becomes the SVG.
for (const el of document.querySelectorAll("[data-icon]")) el.outerHTML = icon(el.dataset.icon, el.className);
