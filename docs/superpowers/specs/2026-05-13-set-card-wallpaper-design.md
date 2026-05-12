# Set Card Cinematic Wallpaper Background

**Date:** 2026-05-13
**Branch:** feat+set-browser-redesign
**Status:** Approved

## Goal

Each set card in the browse grid should display a cinematic, blurred card art as its background — similar to MTG's official set wallpapers. The art is the highest-value card from that set, giving each card a visually distinctive and recognisable identity.

## Architecture

Three files change. No new endpoints, no pipeline changes, no extra API calls.

```
browse query (set_repository.py)
  → returns key_art_uri per set row
  → SetBrowseItem gains key_art_uri: string | null
  → SetCard renders blurred art background when present
  → fallback: existing gradient when key_art_uri is null
```

## Backend

### `set_repository.py` — `browse()` method

Add a `LEFT JOIN LATERAL` to the existing query. It runs once per set and picks the English, non-digital booster card with the highest `list_avg_cents` in `pricing.print_price_latest`, then extracts `image_uris->>'art_crop'` from `card_version_illustration`.

Scryfall's `art_crop` key is the cropped illustration without card borders — ideal for a full-bleed wallpaper fill.

```sql
LEFT JOIN LATERAL (
    SELECT cvi.image_uris->>'art_crop' AS key_art_uri
    FROM card_catalog.card_version cv
    JOIN card_catalog.card_version_illustration cvi
         ON cvi.card_version_id = cv.card_version_id
    JOIN pricing.print_price_latest ppl
         ON ppl.card_version_id = cv.card_version_id
    WHERE cv.set_id = s.set_id
      AND cv.lang = 'en'
      AND cv.is_digital = FALSE
      AND cv.booster = TRUE
      AND cvi.image_uris->>'art_crop' IS NOT NULL
    ORDER BY ppl.list_avg_cents DESC NULLS LAST
    LIMIT 1
) key_art ON true
```

`key_art.key_art_uri` is added to the SELECT list. Sets with no matching card (no price data, no booster cards) return `NULL` and fall back to the existing gradient on the frontend.

### `set_repository.py` — existing query context

The existing `browse()` query already has `JOIN card_catalog.sets s ON s.set_id = vsm.set_id`. The lateral join references `s.set_id` — no additional join needed.

## Frontend

### `types.ts`

Add one field to `SetBrowseItem`:

```ts
key_art_uri: string | null
```

### `SetCard.module.css`

Add `.bgArt` (absolute, full-cover, blurred) and a gradient overlay via `::after`. Icon and set name get `z-index: 2` to float above the art.

```css
.artInner {
  position: relative; /* already a flex container — add relative */
}

.bgArt {
  position: absolute;
  inset: 0;
  background-size: cover;
  background-position: center 30%;
  filter: blur(3px) brightness(0.35) saturate(1.2);
  transform: scale(1.05); /* hides blur edge artifacts */
  z-index: 0;
  transition: filter 0.2s;
}

.card:hover .bgArt {
  filter: blur(3px) brightness(0.45) saturate(1.2);
}

.artInner::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, transparent 40%, rgba(5, 13, 26, 0.85) 100%);
  pointer-events: none;
  z-index: 1;
}

.iconImg,
.iconFallback,
.setName {
  position: relative;
  z-index: 2;
}
```

### `SetCard.tsx`

Conditionally render `.bgArt` inside `.artInner` when `key_art_uri` is present:

```tsx
<div className={styles.artInner}>
  {set.key_art_uri && (
    <div
      className={styles.bgArt}
      style={{ backgroundImage: `url(${set.key_art_uri})` }}
    />
  )}
  {/* existing icon + setName */}
</div>
```

The existing `linear-gradient` background on `.artInner` stays in place. When `.bgArt` is rendered it sits at `z-index: 0` and covers the gradient completely. When `.bgArt` is absent (null art), the gradient shows through as before. No selector change needed.

## Fallback

When `key_art_uri` is `null` (sets with no price data or no booster cards), `.artInner` keeps the existing `linear-gradient` background unchanged. The card looks identical to the current design.

## Child cards

Child set cards (promo/box sets) inherit the same logic — they will get their own top-priced card art if available, or fall back to the gradient. No special casing needed.

## Hover behaviour

On hover, `brightness` increases from `0.35` to `0.45` — a subtle brightening that makes the card feel responsive without distracting from the icon.

## Scope

- No new API endpoint
- No migration
- No pipeline change
- No changes to any other component
