# Card Face Toggle — Design Spec

**Date:** 2026-05-10  
**Status:** Approved

## Overview

Add a face-toggle interaction to the card detail page (`/cards/:id`). When a card has two faces, the user can click a ↻ icon overlaid on the card image to flip between front and back. Only the image updates on flip; the info panel (name, type, oracle text) stays fixed on the front face.

Two card types are handled:

- **DFC cards** (`is_multifaced = true`): front image is already in the API; back image comes from `face_illustration → illustrations.image_uris` for `face_index = 1`.
- **Regular single-faced cards**: front image is already in the API; back image is Scryfall's card-back design URL, constructed from a new `card_back_id` field stored per card version.

The toggle only appears on the card detail page. Search result grid cards are unchanged.

---

## Database

### Migration

```sql
ALTER TABLE card_catalog.card_version
  ADD COLUMN IF NOT EXISTS card_back_id UUID;
```

No index needed — this is a display-only field read in single-row lookups.

### Schema change file

New migration file: `src/automana/database/SQL/migrations/migration_28_card_back_id.sql`  
(The `migrations/` directory does not yet exist in the src tree — create it.)

---

## Scryfall Pipeline

`card_back_id` is a top-level UUID field present on every Scryfall card object. It needs to be threaded through the ingestion path:

1. **`insert_full_card_version` SQL procedure** (`database/SQL/schemas/02_card_schema.sql`) — add parameter `p_card_back_id UUID` and write it to the `card_version` row.
2. **`insert_full_card_query`** (`core/repositories/card_catalog/card_queries.py`) — the query currently passes 41 positional parameters (`$1`–`$41`). Add `$42` for `card_back_id`.
3. **`CreateCard` Pydantic model** (`core/models/card_catalog/card.py`) — add `card_back_id: Optional[UUID] = None` so it is extracted from the Scryfall payload and passed to the repository.
4. **Scryfall data loader** (`core/services/app_integration/scryfall/data_loader.py`) — verify `card_back_id` is included in the field set forwarded to `CreateCard`. Scryfall exposes it as a top-level UUID field on every card object.

---

## Backend API

### `card_repository.get()` query

Extend the existing `SELECT` with three new expressions:

```sql
cv.is_multifaced,
cv.card_back_id,
(
  SELECT i.image_uris->>'large'
  FROM   card_catalog.card_faces cf
  JOIN   card_catalog.face_illustration fi ON fi.face_id = cf.card_faces_id
  JOIN   card_catalog.illustrations i     ON i.illustration_id = fi.illustration_id
  WHERE  cf.card_version_id = cv.card_version_id
    AND  cf.face_index = 1
  LIMIT  1
) AS back_face_image_uri
```

The subquery returns `NULL` for single-faced cards — no branching needed in Python.

### `CardDetail` Pydantic model (`core/models/card_catalog/card.py`)

```python
is_multifaced: bool = False
card_back_id: Optional[UUID] = None
back_face_image_uri: Optional[str] = None
```

No router change needed — these fields are added to the existing `CardDetail` response model and serialised automatically.

---

## Frontend

### TypeScript type (`features/cards/types.ts`)

```ts
export interface CardDetail extends CardSummary {
  // ... existing fields ...
  is_multifaced?: boolean
  card_back_id?: string | null
  back_face_image_uri?: string | null
}
```

### Utility — `buildScryfallBackUrl`

New file: `features/cards/utils/scryfallBackUrl.ts`

```ts
export function buildScryfallBackUrl(cardBackId: string): string {
  const seg1 = cardBackId.slice(0, 2)
  const seg2 = cardBackId.slice(2, 4)
  return `https://c2.scryfall.com/file/scryfall-card-backs/large/${seg1}/${seg2}/${cardBackId}.jpg`
}
```

> **Verify during implementation:** confirm the exact Scryfall card-back CDN URL format by inspecting a live Scryfall API response for `card_back_id`. The standard card back UUID is `0aeebaf5-8c7d-4636-9e82-8c27447861f7` — test the constructed URL resolves to an image.

### New component — `FlippableCardArt`

New file: `components/design-system/FlippableCardArt.tsx`

**Props:**
```ts
interface FlippableCardArtProps {
  name: string
  frontUrl: string | null
  backUrl: string | null
  w?: number | string
  h?: number | string
  style?: React.CSSProperties
}
```

**Behaviour:**
- Local `faceUp: boolean` state, initialised `true`.
- Renders `CardArt` with `imageUrl = faceUp ? frontUrl : backUrl`.
- If `backUrl` is null/undefined: renders `CardArt` normally with no icon (graceful degradation — card has no toggleable back).
- The ↻ button is absolutely positioned bottom-right of the card image container.
- Clicking ↻ toggles `faceUp` and applies a CSS `rotateY(180deg)` transition on the image wrapper (`transform-style: preserve-3d`, `transition: transform 0.4s`).

### `CardDetailView` update

Replace:
```tsx
<CardArt
  name={card.card_name}
  w={420} h={585}
  imageUrl={card.image_large}
  ...
/>
```

With:
```tsx
const backUrl = card.is_multifaced
  ? (card.back_face_image_uri ?? null)
  : card.card_back_id
    ? buildScryfallBackUrl(card.card_back_id)
    : null

<FlippableCardArt
  name={card.card_name}
  w={420} h={585}
  frontUrl={card.image_large ?? null}
  backUrl={backUrl}
  style={{ borderRadius: 16 }}
/>
```

---

## Data Flow

```
Scryfall JSON
  └─ card_back_id ──► card_version.card_back_id ──► API ──► buildScryfallBackUrl() ──► FlippableCardArt (regular)

card_faces (face_index=1)
  └─► face_illustration
        └─► illustrations.image_uris['large'] ──► API ──► FlippableCardArt (DFC)
```

---

## Out of Scope

- Flip on search result grid cards
- Updating the info panel (name / type / oracle text) on flip — front-face info is shown regardless
- Storing per-card back image URLs in the DB for regular cards (Scryfall URL constructed client-side from `card_back_id`)
- Any animation beyond the CSS 3D flip on the image
