# Design System — Music Downloader (Soulseek sync)

Extracted from a reference dashboard screenshot. Hex values marked **sampled** were read directly from the pixels. Values marked **est.** are estimates: small text in the screenshot is anti-aliased and compressed, so its exact color can't be read reliably.

**Look and feel:** a warm grey app background with white rounded cards. Everything is monochrome except one electric-yellow accent. One near-black card adds contrast. Headings are big, bold and tightly spaced, and every button is a pill. There are no shadows; depth comes only from the grey levels.

---

## 1. Color tokens

### Neutrals (surfaces)
| Token | Hex | Where it appears |
|---|---|---|
| `--bg-backdrop` | `#A2A2A2` | Area outside the app window (sampled) |
| `--bg-app` | `#E0E0E0` | App shell, sidebar, top bar (sampled) |
| `--surface` | `#FFFFFF` | Main cards (sampled) |
| `--surface-muted` | `#F0F0F0` | Stat tiles, table header, expanded list row, day circles, icon buttons, status pills (sampled) |
| `--surface-sunken` | `#E7E7E7` | Coin/icon avatar circles on a white card (sampled) |
| `--surface-strong` | `#67686B` | Dark-grey stat tile (sampled) |
| `--surface-inverse` | `#111111` | Black "balance" card, active nav icon, filled chips (sampled) |
| `--surface-inverse-raised` | `#353535` | Icon button on the black card (sampled) |

### Accent
| Token | Hex | Where it appears |
|---|---|---|
| `--accent` | `#FCF251` | Primary yellow: highlighted stat tile, tooltip, pending pill, logo (sampled) |
| `--accent-soft` | `#FEF99A` | Lighter yellow in the middle of the chart's glow bar (sampled) |
| `--accent-fg` | `#111111` | Text on yellow |
| `--accent-fg-muted` | `#9C9732` | Secondary label on yellow, e.g. "Pending withdrawals" (sampled) |

### Text
| Token | Hex | Where it appears |
|---|---|---|
| `--text-primary` | `#0A0A0A` | Headings, big numbers (sampled ~#030303–#101010) |
| `--text-body` | `#454545` | Table cells, day letters (sampled) |
| `--text-muted` | `#8E8E90` | Labels, subtitles, table headers, placeholders (sampled ~#878787–#949496) |
| `--text-on-strong` | `#B8B9BC` | Label on the dark-grey tile (est.) |
| `--text-inverse` | `#FFFFFF` | Text on black |
| `--text-inverse-muted` | `#8A8A8A` | "You sell" / "You get" on the black card (est.) |

### Semantic
| Token | Hex | Where it appears |
|---|---|---|
| `--positive` | `#3DAA4C` | "+6.2%", "Buy" (est.; the sampled anti-aliased pixels were ~#78AF76) |
| `--negative` | `#D64545` | "Sell" (est.; sampled ~#A4676C) |
| `--warning` | `--accent` | The Pending status reuses the yellow |

### Lines and icons
| Token | Hex | Where it appears |
|---|---|---|
| `--border` | `#E1E1E1` | Dividers inside cards (sampled) |
| `--border-strong` | `#111111` | 1.5px outline on ghost pill buttons |
| `--divider-on-app` | `#CFCFCF` | Vertical/horizontal dividers on the grey shell (sampled) |
| `--icon-muted` | `#848484` | Inactive sidebar icons (sampled) |
| `--chart-stem` | `#D4D4D4` | Thin lollipop stems in the bar chart (est.) |
| `--border-inverse` | `#2A2A2A` | Input-group border on the black card (est.) |

---

## 2. Typography

- **Font:** a neo-grotesk sans with tight letter-spacing. Closest free matches are **Inter Tight** or **Geist** (Inter will also work). Use one family for the whole UI.
- **Numbers:** turn on `font-variant-numeric: tabular-nums` for prices, sizes and counts.

| Role | Size / line-height | Weight | Tracking | Example |
|---|---|---|---|---|
| Display | 48 / 52 | 600 | -0.03em | "Income per week" |
| Hero stat | 56 / 56 | 600 | -0.04em | "+2.6%" |
| H2 (card title) | 24 / 30 | 500 | -0.02em | "Crypto watchlist", "Overview" |
| Stat value | 26 / 32 | 500 | -0.02em | "$1,200" |
| Balance value | 26 / 32 | 500 | -0.01em | "$15,430.28" |
| Body / row | 16 / 22 | 500 | -0.01em | Table rows, list rows |
| Label | 14 / 18 | 400 | 0 | "Trading volume:", subtitles |
| Caption | 13 / 16 | 400 | 0 | Table headers, tile labels |
| Chip | 13 / 16 | 600 | 0 | "Cashout", "Fees" |

---

## 3. Spacing, radius, borders

- **Spacing scale (4px base):** 4, 8, 12, 16, 20, 24, 28, 32, 40, 48
- **Card padding:** 28px
- **Gap between cards:** 12px (cards sit close together)
- **Gap between stat tiles:** 10px

| Token | Value | Where it appears |
|---|---|---|
| `--radius-app` | 28px | Outer app window |
| `--radius-card` | 20px | Main cards |
| `--radius-tile` | 6px | Stat tiles (only slightly rounded, which sets them apart from the cards) |
| `--radius-inner` | 12px | Expanded list row, table header bar, input group |
| `--radius-pill` | 999px | All buttons, chips, status pills, icon buttons, avatars |

- **Shadows:** none. Separate layers with grey levels only.
- **Borders:** cards have no border. Ghost buttons use a 1.5px `--border-strong` outline.

---

## 4. Layout

- **Sidebar:** about 100px wide, sitting on `--bg-app` with no card behind it. From top to bottom it holds:
  - the logo tile (48px, yellow square, radius 10)
  - the nav icons, vertically centred and separated by short 20px horizontal dividers
  - the avatar, pinned to the bottom
- **Active nav item:** a 48px black circle with a white icon. Inactive items are bare `--icon-muted` icons.
- **Top bar:**
  - Left side: page title (H2), a vertical divider, then a search field with an icon and placeholder and no box.
  - Right side: a circular icon button (44px, `--surface-muted`), then a ghost pill CTA.
- **Content grid:** 12 columns, about 2/3 + 1/3. The wide card sits on the left with the narrow card to its right, and the same split repeats in the next row.

---

## 5. Components

**Card:** `--surface`, radius 20, padding 28, no shadow. The title sits top-left and actions top-right (a dropdown such as "Week ⌄", or an icon).

**Stat tile** (3 in a row, equal width, height ~104):
- Variants: `accent` (yellow), `strong` (dark grey `#67686B` with white value), `muted` (`#F0F0F0`).
- Contents: a small label top-left, a chip top-right, and the value bottom-left.
- **Chip inside a tile:** a pill, 13px semibold, padding 4×10.
  - On the yellow and muted tiles: black background with white text.
  - On the dark-grey tile: white background with black text.

**Lollipop bar chart** (the signature element):
- Each day has a thin 1px stem in `--chart-stem` with a 6px dot on top, and a 44px circular day label at the bottom (`--surface-muted`).
- The **active** day becomes a 72px-wide pill-shaped glow column. It fades vertically from transparent at the top through `--accent-soft` to `--accent` at the bottom. The day label turns into a black circle with white text, the stem turns black, and a yellow pill tooltip with the value (16px semibold) floats above it.

**Expandable list row** (watchlist):
- Row height 72.
- Left: a 44px circular icon, black for the selected row and `--surface-sunken` for the others.
- Then the name (semibold), the value, the change % in `--positive`, and a chevron.
- When expanded, the row becomes an `--surface-muted` block (radius 12) holding key/value pairs: labels in `--text-muted` on the left, values in `--text-body` on the right, and an `--border` divider under the header. A white circular chevron-up button marks the open state.

**Table:**
- Header bar: `--surface-muted`, radius 12, height 46, caption-size text in `--text-muted`.
- Rows: 78px tall with no dividers. Each row starts with a 44px circular asset icon.
- **Type column:** green or red text with a double-chevron icon.

**Status pill:** height 36, padding 0×14, radius pill, 16px medium text, with a leading icon.
- `completed`: `--surface-muted` background, ✓ icon
- `pending`: `--accent` background, spinner icon

**Buttons:**
- *Ghost pill:* transparent background, 1.5px black border, black 16px medium text, optional trailing arrow (↗ or →). Height 44 (or 46 when full width).
- *Solid inverse:* on the black card, a white full-width pill with black text ("Exchange").
- *Icon button:* a 44px circle in `--surface-muted`. On the black card it uses `--surface-inverse-raised` with a white icon.

**Dark panel** (balance/exchange card):
- `--surface-inverse` background, radius 20.
- Top: a circular icon button on the left, and a right-aligned label above the big value.
- Below that, an input group with a 1px `--border-inverse` outline, radius 12, split into two rows by a divider.
- **Each input-group row:** a muted label on the left and a token selector on the right (small 24px circle icon + name + chevron).
- At the bottom, a full-width white pill CTA.

**Icons:** outline icons, 1.5px stroke, 20px. Lucide matches well.

---

## 6. Drop-in tokens

### CSS variables
```css
:root {
  --bg-backdrop: #A2A2A2;
  --bg-app: #E0E0E0;
  --surface: #FFFFFF;
  --surface-muted: #F0F0F0;
  --surface-sunken: #E7E7E7;
  --surface-strong: #67686B;
  --surface-inverse: #111111;
  --surface-inverse-raised: #353535;

  --accent: #FCF251;
  --accent-soft: #FEF99A;
  --accent-fg: #111111;
  --accent-fg-muted: #9C9732;

  --text-primary: #0A0A0A;
  --text-body: #454545;
  --text-muted: #8E8E90;
  --text-on-strong: #B8B9BC;
  --text-inverse: #FFFFFF;
  --text-inverse-muted: #8A8A8A;

  --positive: #3DAA4C;
  --negative: #D64545;

  --border: #E1E1E1;
  --border-strong: #111111;
  --border-inverse: #2A2A2A;
  --divider-on-app: #CFCFCF;
  --icon-muted: #848484;
  --chart-stem: #D4D4D4;

  --radius-app: 28px;
  --radius-card: 20px;
  --radius-inner: 12px;
  --radius-tile: 6px;
  --radius-pill: 999px;

  --font-sans: "Inter Tight", "Geist", Inter, system-ui, sans-serif;

  --glow-accent: linear-gradient(to bottom, rgba(252,242,81,0) 0%, #FEF99A 45%, #FCF251 100%);
}
```

### Tailwind (`theme.extend`)
```js
colors: {
  backdrop: '#A2A2A2',
  app: '#E0E0E0',
  surface: { DEFAULT: '#FFFFFF', muted: '#F0F0F0', sunken: '#E7E7E7', strong: '#67686B', inverse: '#111111', 'inverse-raised': '#353535' },
  accent: { DEFAULT: '#FCF251', soft: '#FEF99A', fg: '#111111', 'fg-muted': '#9C9732' },
  ink: { DEFAULT: '#0A0A0A', body: '#454545', muted: '#8E8E90', 'on-strong': '#B8B9BC', 'inverse-muted': '#8A8A8A' },
  positive: '#3DAA4C',
  negative: '#D64545',
  line: { DEFAULT: '#E1E1E1', app: '#CFCFCF', inverse: '#2A2A2A', stem: '#D4D4D4' },
},
borderRadius: { app: '28px', card: '20px', inner: '12px', tile: '6px' },
fontFamily: { sans: ['"Inter Tight"', 'Geist', 'Inter', 'system-ui', 'sans-serif'] },
letterSpacing: { display: '-0.03em', hero: '-0.04em', title: '-0.02em' },
```

---

## 7. Mapping to the music app (suggested)

| Reference element | Use it for |
|---|---|
| "Income per week" + lollipop chart | Downloads per day this week; the yellow glow marks today or the peak day |
| 3 stat tiles | **Queued** (yellow, chip "Start"), **Active transfers** (dark, chip "Live"), **Library size** (muted, chip "Library") |
| Watchlist with expandable rows | Active transfers or followed artists. Expanded rows show peer, bitrate/format, speed, queue position |
| Trading history table | Download history: Track · Format (FLAC/MP3 badge) · Size · Status pill · Peer · Date |
| Status pills | `completed` (grey ✓), `downloading` (yellow spinner), `failed` (add: `#FDE4E4` bg, `--negative` text) |
| Black balance card | Search & grab panel: "Search" / "Prefer format" inputs and a white "Download" button, or a Soulseek connection status card |
| Ghost pill top-right | "Sync now" or "Connect Soulseek" |

**Rules to keep it on-brand:**
- Yellow is the only color. Use it for at most one highlighted element per card.
- Green and red appear only in small text.
- Never add shadows.
- All interactive elements are pills or circles.
- Cards are big and roomy; the radius jumps sharply between cards (20) and stat tiles (6).
