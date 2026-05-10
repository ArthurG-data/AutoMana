# Card Detail Page Redesign

**Date:** 2026-05-10
**Status:** Approved

## Overview

Redesign `CardDetailView` from the current compact two-column layout into a richer "Hero" layout that mirrors the information depth of Scryfall's card page — card identity, rules text, artist, format legality, and pricing — while keeping the existing Deep Sea color scheme and design tokens untouched.

---

## Layout

**Two-column Hero grid** — `grid-template-columns: 260px 1fr`

### Left column — card image

- Full-height panel with ambient radial glow (`rgba(61,232,210,0.08)` centered at 50% 35%)
- Background: `linear-gradient(160deg, #1e2e5a, #0d1526 55%, #1a2444)`
- Card image rendered via existing `<CardArt>` component filling the full column height
- **Fade effect**: a `::after` pseudo-element covers the right 55% of the column with `linear-gradient(to right, transparent 0%, #0b1425 100%)`, dissolving the image edge into the data panel background — no hard border between the columns

### Right column — scrollable data panel

Background `#0b1425`, `1px solid rgba(150,200,255,0.08)` border (left side omitted), `padding: 18px`.

Sections flow top-to-bottom with `1px solid rgba(150,200,255,0.09)` dividers between logical groups.

---

## Right Panel Sections (in order)

### 1. Set Info Box

Styled container with `border: 1px solid rgba(150,200,255,0.12)`, `border-radius: 10px`, `overflow: hidden`.

**Inner layout — two columns:**

| Column | Content |
|--------|---------|
| Icon col (44 px wide) | Keyrune set symbol (`<i class="ss ss-{set_code} ss-{rarity}">`) · background `rgba(224,169,106,0.08)` · right border |
| Text col | Full set name + `(SET_CODE)` in mono · Rarity · `#collector_number / set_size` · promo badges |

**Promo badges** — amber pill: `background: rgba(224,169,106,0.12)`, `border: 1px solid rgba(224,169,106,0.28)`, `color: #e0a96a`. One badge per promo type (e.g. `✦ Showcase`, `✦ Etched Foil`). Hidden when `promo_types` is empty.

**Rarity color** on the Keyrune icon: `ss-common` / `ss-uncommon` / `ss-rare` / `ss-mythic` CSS classes from Keyrune.

### 2. Card Identity

- **Name** — Fraunces serif, 24 px, `font-weight: 400`, `letter-spacing: -0.3px`
- **Mana cost** — one `<Pip>` per symbol + raw cost string in mono
- **Type line** — 11 px, `color: var(--hd-muted)`

### 3. Rules Text

`oracle-box` — `background: rgba(255,255,255,0.03)`, `border: 1px solid rgba(150,200,255,0.09)`, `border-radius: 7px`, `padding: 10px 12px`, `font-size: 12px`, `line-height: 1.65`.

Reminder/flavor text rendered as `<em>` in `color: var(--hd-sub)`.

Artist name + collector number rendered below the box in 11 px muted mono.

### 4. Finish Selector

Row of pill buttons — one per entry in `available_finishes`. Active pill: `background: rgba(61,232,210,0.11)`, `border-color: rgba(61,232,210,0.38)`, `color: var(--hd-accent)`. Inactive: muted border + `color: var(--hd-sub)`.

Selecting a finish updates the price display and chart data.

### 5. Market Price

- Label: `MARKET PRICE · {finish}` in 9 px mono uppercase
- Price: Fraunces 38 px teal, cents in 19 px muted
- Deltas: 1d / 7d / 30d stacked in 10 px mono, `▲` green / `▼` red

### 6. Price History Chart

Existing `<PriceCharts>` component (dual area chart — list avg teal, sold avg blue dashed). Range selector: 1W / 1M / 1Y / ALL. Chart height ~60 px in this layout.

### 7. Format Legality Grid

`grid-template-columns: repeat(4, 1fr)`, 8 formats: Standard · Pioneer · Modern · Legacy · Vintage · Pauper · Commander · Oathbreaker.

Cell backgrounds:
- Legal: `rgba(61,232,210,0.08)` / text `var(--hd-accent)`
- Not Legal: `rgba(150,200,255,0.04)` / text `var(--hd-sub)`
- Banned: `rgba(227,94,108,0.08)` / text `var(--hd-red)`

### 8. Action Buttons

`+ Add to collection` (accent filled, flex: 1) · `Watch` (ghost) · `Alert` (ghost)

---

## Data Requirements

Three fields need to reach the frontend `CardDetail` interface. Their current status differs per field:

| Field | Frontend type | Backend model | DB | Work needed |
|-------|--------------|---------------|----|-------------|
| `collector_number` | ❌ missing from `CardDetail` | ✅ `CardDetail.collector_number: Union[int, str]` | ✅ | Add to frontend `CardDetail` type; verify API serialiser already includes it |
| `promo_types` | ❌ missing from `CardDetail` | ✅ `CardDetail.promo_types: Optional[List[str]]` | ✅ | Add to frontend `CardDetail` type; verify API serialiser already includes it |
| `legality` | ❌ missing | ❌ not in model | ✅ `card_catalog.legalities` join table | Full stack: add to card detail DB query → Python model → API response → frontend type |

### Legality query sketch

The DB already has `card_catalog.legalities`, `card_catalog.formats`, and `card_catalog.legal_status_ref`. The card detail query needs a join that aggregates format legality into a JSON object keyed by format name (e.g. `{"modern": "legal", "standard": "not_legal", ...}`).

### Keyrune font

The Keyrune set symbol font (`keyrune` npm package) is **not currently installed**. It must be added as a frontend dependency and either bundled or loaded via CDN. It provides `ss ss-{set_code} ss-{rarity}` CSS classes that render the correct SVG glyph for every MTG set.

---

## Component Structure

```
CardDetailView               ← replaces current component entirely
├── ImagePanel               ← left col, manages fade overlay
│   └── CardArt              ← existing component
└── DataPanel                ← right col, scrollable
    ├── SetInfoBox           ← new sub-component
    ├── CardIdentity         ← name + mana + type
    ├── OracleTextBox        ← rules text + artist line
    ├── FinishSelector       ← existing pill logic, extracted
    ├── PriceDisplay         ← price + deltas
    ├── PriceCharts          ← existing component, unchanged
    ├── LegalityGrid         ← new sub-component
    └── CardActions          ← add / watch / alert buttons
```

---

## What Does NOT Change

- Color tokens (`tokens.css`) — untouched
- Fonts (Fraunces, JetBrains Mono, Space Grotesk) — untouched
- `PriceCharts` component — reused as-is
- `CardArt` component — reused as-is
- `Pip` component — reused as-is
- Route (`cards.$id.tsx`) — no changes needed
- All other pages/routes — unaffected

---

## Open Questions (resolved)

- **Fade direction**: straight horizontal (`to right`) confirmed, not diagonal
- **Set box style**: Icon column (Option 3) confirmed
- **Color schema**: existing Deep Sea tokens, no changes
