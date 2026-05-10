# Card Face Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a ↻ flip icon to the card detail page that toggles between front and back face images for DFC cards (back image from DB) and regular cards (back image from Scryfall card-back CDN via `card_back_id`).

**Architecture:** Add `card_back_id` to `card_version` (migration + pipeline), extend the `card_repository.get()` query to return `is_multifaced`, `card_back_id`, and `back_face_image_uri`, then wire a new `FlippableCardArt` React component into `CardDetailView`. The info panel (name, type, oracle text) stays fixed on the front face regardless of flip state.

**Tech Stack:** PostgreSQL, Python/Pydantic, FastAPI, React 18, TypeScript, Vitest, CSS Modules

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `src/automana/database/SQL/migrations/migration_28_card_back_id.sql` | **Create** | ALTER TABLE to add `card_back_id` column |
| `src/automana/database/SQL/schemas/02_card_schema.sql` | **Modify** | Add `p_card_back_id` param + column write to `insert_full_card_version` |
| `src/automana/core/models/card_catalog/card.py` | **Modify** | Add `card_back_id` to `CreateCard` + `prepare_for_db()`, add 3 fields to `CardDetail` |
| `src/automana/core/repositories/card_catalog/card_queries.py` | **Modify** | Add `$42` positional arg for `card_back_id` |
| `src/automana/core/repositories/card_catalog/card_repository.py` | **Modify** | Extend `get()` SELECT with `is_multifaced`, `card_back_id`, `back_face_image_uri` |
| `src/frontend/src/features/cards/types.ts` | **Modify** | Add 3 optional fields to `CardDetail` TS type |
| `src/frontend/src/features/cards/utils/scryfallBackUrl.ts` | **Create** | Utility to build Scryfall card-back CDN URL from `card_back_id` |
| `src/frontend/src/features/cards/__tests__/scryfallBackUrl.test.ts` | **Create** | Unit tests for the URL builder |
| `src/frontend/src/components/design-system/FlippableCardArt.tsx` | **Create** | React component: card image with ↻ icon and CSS 3D flip |
| `src/frontend/src/components/design-system/FlippableCardArt.module.css` | **Create** | CSS 3D flip animation styles |
| `src/frontend/src/components/design-system/__tests__/FlippableCardArt.test.tsx` | **Create** | Unit tests for the flip component |
| `src/frontend/src/features/cards/components/CardDetailView.tsx` | **Modify** | Replace `CardArt` with `FlippableCardArt`, compute `backUrl` |
| `src/frontend/src/features/cards/components/__tests__/CardDetailView.test.tsx` | **Modify** | Update mock + add flip-related tests |

---

## Task 1: DB Migration — Add `card_back_id` Column

**Files:**
- Create: `src/automana/database/SQL/migrations/migration_28_card_back_id.sql`

- [ ] **Step 1: Create the migrations directory and migration file**

```sql
-- src/automana/database/SQL/migrations/migration_28_card_back_id.sql
ALTER TABLE card_catalog.card_version
  ADD COLUMN IF NOT EXISTS card_back_id UUID;
```

- [ ] **Step 2: Apply to dev database**

```bash
docker exec -i automana-postgres-dev psql -U automana_admin automana \
  < src/automana/database/SQL/migrations/migration_28_card_back_id.sql
```

Expected output: `ALTER TABLE`

- [ ] **Step 3: Verify the column exists**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c \
  "\d card_catalog.card_version" | grep card_back_id
```

Expected: `card_back_id | uuid | ...`

- [ ] **Step 4: Commit**

```bash
git add src/automana/database/SQL/migrations/migration_28_card_back_id.sql
git commit -m "feat(db): add card_back_id column to card_version"
```

---

## Task 2: Update `insert_full_card_version` SQL Procedure

**Files:**
- Modify: `src/automana/database/SQL/schemas/02_card_schema.sql`

> **Note:** The procedure currently ends with `p_cardmarket_id INT`. Add `p_card_back_id` as the final parameter with `DEFAULT NULL` so existing callers (without this arg) continue to work. Also update the INSERT to write the new column.

- [ ] **Step 1: Add `p_card_back_id` as the last parameter**

In `02_card_schema.sql`, find the `insert_full_card_version` parameter list. It ends with:

```sql
    p_tcgplayer_etched_id INT,
    p_cardmarket_id INT
)
```

Change it to:

```sql
    p_tcgplayer_etched_id INT,
    p_cardmarket_id INT,
    p_card_back_id UUID DEFAULT NULL
)
```

- [ ] **Step 2: Add `card_back_id` to the INSERT into `card_catalog.card_version`**

Find the INSERT block (around line 800). The column list currently ends with `lang`. Change:

```sql
    INSERT INTO card_catalog.card_version (
        unique_card_id, oracle_text, set_id,
        collector_number, rarity_id, border_color_id,
        frame_id, layout_id, is_promo, is_digital,
        is_oversized, full_art, textless, booster,
        variation, frame_effects, lang
    ) VALUES (
        v_unique_card_id, p_oracle_text, v_set_id,
        p_collector_number, v_rarity_id, v_border_color_id,
        v_frame_id, v_layout_id, p_is_promo, p_is_digital,
        p_oversized, p_full_art, p_textless, p_booster,
        p_variation,
        COALESCE(p_frame_effects, '{}'),
        COALESCE(p_lang, 'en')
    )
```

To:

```sql
    INSERT INTO card_catalog.card_version (
        unique_card_id, oracle_text, set_id,
        collector_number, rarity_id, border_color_id,
        frame_id, layout_id, is_promo, is_digital,
        is_oversized, full_art, textless, booster,
        variation, frame_effects, lang, card_back_id
    ) VALUES (
        v_unique_card_id, p_oracle_text, v_set_id,
        p_collector_number, v_rarity_id, v_border_color_id,
        v_frame_id, v_layout_id, p_is_promo, p_is_digital,
        p_oversized, p_full_art, p_textless, p_booster,
        p_variation,
        COALESCE(p_frame_effects, '{}'),
        COALESCE(p_lang, 'en'),
        p_card_back_id
    )
```

- [ ] **Step 3: Apply the updated procedure to dev DB**

```bash
docker exec -i automana-postgres-dev psql -U automana_admin automana \
  < src/automana/database/SQL/schemas/02_card_schema.sql
```

Expected: `CREATE FUNCTION` (or `CREATE OR REPLACE FUNCTION`)

- [ ] **Step 4: Verify the new parameter is present**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c \
  "SELECT pg_get_function_arguments('card_catalog.insert_full_card_version'::regproc);" \
  | grep card_back_id
```

Expected: line containing `p_card_back_id uuid DEFAULT NULL`

- [ ] **Step 5: Commit**

```bash
git add src/automana/database/SQL/schemas/02_card_schema.sql
git commit -m "feat(db): add p_card_back_id to insert_full_card_version procedure"
```

---

## Task 3: Extend `CreateCard` Model + `prepare_for_db()`

**Files:**
- Modify: `src/automana/core/models/card_catalog/card.py`

- [ ] **Step 1: Write the failing test**

Create a new file `tests/unit/models/test_create_card.py` (or add to any existing card model test). If no such file exists, create it:

```python
# tests/unit/models/test_create_card.py
from uuid import UUID
import pytest
from automana.core.models.card_catalog.card import CreateCard


MINIMAL_CARD = {
    "card_name": "Huntmaster of the Fells",
    "cmc": 4,
    "mana_cost": "{2}{R}{G}",
    "reserved": False,
    "oracle_text": "",
    "set_name": "Dark Ascension",
    "collector_number": "140",
    "rarity_name": "mythic",
    "border_color": "black",
    "frame": "2015",
    "layout": "transform",
    "promo": False,
    "digital": False,
    "keywords": [],
    "color_identity": ["R", "G"],
    "legalities": {},
    "artist": "Chris Rahn",
    "artist_ids": [UUID("00000000-0000-0000-0000-000000000001")],
    "illustration_id": UUID("00000000-0000-0000-0000-000000000001"),
    "image_uris": {},
    "games": [],
    "oversized": False,
    "booster": True,
    "full_art": False,
    "textless": False,
    "variation": False,
    "set": "dka",
    "set_id": UUID("00000000-0000-0000-0000-000000000002"),
    "id": UUID("00000000-0000-0000-0000-000000000003"),
}


def test_card_back_id_defaults_to_none():
    card = CreateCard(**MINIMAL_CARD)
    assert card.card_back_id is None


def test_card_back_id_accepted_when_provided():
    back_id = UUID("0aeebaf5-8c7d-4636-9e82-8c27447861f7")
    card = CreateCard(**MINIMAL_CARD, card_back_id=back_id)
    assert card.card_back_id == back_id


def test_prepare_for_db_has_42_values():
    card = CreateCard(**MINIMAL_CARD)
    result = card.prepare_for_db()
    assert len(result) == 42


def test_prepare_for_db_last_value_is_card_back_id():
    back_id = UUID("0aeebaf5-8c7d-4636-9e82-8c27447861f7")
    card = CreateCard(**MINIMAL_CARD, card_back_id=back_id)
    result = card.prepare_for_db()
    assert result[-1] == back_id


def test_prepare_for_db_last_value_none_when_not_set():
    card = CreateCard(**MINIMAL_CARD)
    result = card.prepare_for_db()
    assert result[-1] is None
```

- [ ] **Step 2: Run the tests to see them fail**

```bash
cd /home/arthur/projects/AutoMana
python -m pytest tests/unit/models/test_create_card.py -v
```

Expected: `FAILED` — either `AttributeError: card_back_id` or `AssertionError: 41 != 42`

- [ ] **Step 3: Add `card_back_id` to `CreateCard` and `prepare_for_db()`**

In `src/automana/core/models/card_catalog/card.py`, in `class CreateCard`, after `cardmarket_id`:

```python
    cardmarket_id: Optional[int]=None
    card_back_id: Optional[UUID] = None
```

In `prepare_for_db()`, change the closing of the return tuple from:

```python
        self.tcgplayer_etched_id,
        self.cardmarket_id,
    )
```

To:

```python
        self.tcgplayer_etched_id,
        self.cardmarket_id,
        self.card_back_id,
    )
```

- [ ] **Step 4: Run the tests — they should pass**

```bash
python -m pytest tests/unit/models/test_create_card.py -v
```

Expected: 5 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/models/card_catalog/card.py tests/unit/models/test_create_card.py
git commit -m "feat(model): add card_back_id to CreateCard and prepare_for_db"
```

---

## Task 4: Update `insert_full_card_query`

**Files:**
- Modify: `src/automana/core/repositories/card_catalog/card_queries.py`

- [ ] **Step 1: Add `$42` for `card_back_id`**

In `card_queries.py`, find the end of `insert_full_card_query`. Change:

```python
        $40, -- tcgplayer_etched_id
        $41 -- cardmarket_id        
    );
"""
```

To:

```python
        $40, -- tcgplayer_etched_id
        $41, -- cardmarket_id
        $42  -- card_back_id
    );
"""
```

- [ ] **Step 2: Commit**

```bash
git add src/automana/core/repositories/card_catalog/card_queries.py
git commit -m "feat(repo): add card_back_id as \$42 in insert_full_card_query"
```

---

## Task 5: Extend `CardDetail` Pydantic Model

**Files:**
- Modify: `src/automana/core/models/card_catalog/card.py`

- [ ] **Step 1: Add three fields to `CardDetail`**

In `class CardDetail(BaseCard)`, after `price_history_sold_avg`:

```python
class CardDetail(BaseCard):
    image_large: Optional[str] = Field(default=None, title="URL to large-sized card image from Scryfall")
    available_finishes: List[str] = Field(default_factory=list)
    price_history_list_avg: Optional[List[float]] = Field(
        default=None,
        title="Daily list average prices in dollars for selected time range"
    )
    price_history_sold_avg: Optional[List[float]] = Field(
        default=None,
        title="Daily sold average prices in dollars for selected time range"
    )
    is_multifaced: bool = Field(default=False)
    card_back_id: Optional[UUID] = Field(default=None)
    back_face_image_uri: Optional[str] = Field(default=None)
```

- [ ] **Step 2: Commit**

```bash
git add src/automana/core/models/card_catalog/card.py
git commit -m "feat(model): add is_multifaced, card_back_id, back_face_image_uri to CardDetail"
```

---

## Task 6: Extend `card_repository.get()` Query

**Files:**
- Modify: `src/automana/core/repositories/card_catalog/card_repository.py`

- [ ] **Step 1: Extend the SELECT in `card_repository.get()`**

Find the `get()` method. The current SELECT ends around line 96–109. Replace the query string:

```python
        query = """
            SELECT
                cv.card_version_id,
                uc.card_name,
                r.rarity_name,
                s.set_name,
                s.set_code,
                uc.cmc,
                cv.oracle_text,
                s.released_at,
                s.digital,
                cvi.image_uris->>'large' AS image_large,
                ARRAY(
                    SELECT LOWER(cf.code)
                    FROM card_catalog.card_version_finish cvf
                    JOIN card_catalog.card_finished cf ON cf.finish_id = cvf.finish_id
                    WHERE cvf.card_version_id = cv.card_version_id
                ) AS available_finishes
            FROM card_catalog.unique_cards_ref uc
            JOIN card_catalog.card_version cv ON uc.unique_card_id = cv.unique_card_id
            JOIN card_catalog.rarities_ref r ON cv.rarity_id = r.rarity_id
            JOIN card_catalog.sets s ON cv.set_id = s.set_id
            LEFT JOIN card_catalog.card_version_illustration cvi
                ON cvi.card_version_id = cv.card_version_id
            WHERE cv.card_version_id = $1;
        """
```

With:

```python
        query = """
            SELECT
                cv.card_version_id,
                uc.card_name,
                r.rarity_name,
                s.set_name,
                s.set_code,
                uc.cmc,
                cv.oracle_text,
                s.released_at,
                s.digital,
                cvi.image_uris->>'large' AS image_large,
                ARRAY(
                    SELECT LOWER(cf.code)
                    FROM card_catalog.card_version_finish cvf
                    JOIN card_catalog.card_finished cf ON cf.finish_id = cvf.finish_id
                    WHERE cvf.card_version_id = cv.card_version_id
                ) AS available_finishes,
                cv.is_multifaced,
                cv.card_back_id,
                (
                    SELECT i.image_uris->>'large'
                    FROM   card_catalog.card_faces face
                    JOIN   card_catalog.face_illustration fi
                               ON fi.face_id = face.card_faces_id
                    JOIN   card_catalog.illustrations i
                               ON i.illustration_id = fi.illustration_id
                    WHERE  face.card_version_id = cv.card_version_id
                      AND  face.face_index = 1
                    LIMIT  1
                ) AS back_face_image_uri
            FROM card_catalog.unique_cards_ref uc
            JOIN card_catalog.card_version cv ON uc.unique_card_id = cv.unique_card_id
            JOIN card_catalog.rarities_ref r ON cv.rarity_id = r.rarity_id
            JOIN card_catalog.sets s ON cv.set_id = s.set_id
            LEFT JOIN card_catalog.card_version_illustration cvi
                ON cvi.card_version_id = cv.card_version_id
            WHERE cv.card_version_id = $1;
        """
```

- [ ] **Step 2: Smoke-test via the running API**

With the backend running (`dcdev-automana up -d`), hit a known card detail endpoint and verify the new fields appear:

```bash
curl -s -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/catalog/mtg/card-reference/<known-card-uuid> \
  | python3 -c "import sys,json; d=json.load(sys.stdin)['data']; print(d.get('is_multifaced'), d.get('card_back_id'), d.get('back_face_image_uri'))"
```

Expected output: three values (e.g., `False None None` for a regular card)

- [ ] **Step 3: Commit**

```bash
git add src/automana/core/repositories/card_catalog/card_repository.py
git commit -m "feat(repo): return is_multifaced, card_back_id, back_face_image_uri in card detail query"
```

---

## Task 7: Frontend — `scryfallBackUrl` Utility

**Files:**
- Create: `src/frontend/src/features/cards/utils/scryfallBackUrl.ts`
- Create: `src/frontend/src/features/cards/__tests__/scryfallBackUrl.test.ts`

> **Important — verify URL format before implementing:** Check a live Scryfall card object for the `card_back_id` value (always `0aeebaf5-8c7d-4636-9e82-8c27447861f7` for standard MTG). Navigate to `https://c2.scryfall.com/file/scryfall-card-backs/large/0a/ee/0aeebaf5-8c7d-4636-9e82-8c27447861f7.jpg` in a browser and confirm it loads the card back image. If it doesn't resolve, update the domain/path below before coding.

- [ ] **Step 1: Write the failing tests**

```typescript
// src/frontend/src/features/cards/__tests__/scryfallBackUrl.test.ts
import { describe, it, expect } from 'vitest'
import { buildScryfallBackUrl } from '../utils/scryfallBackUrl'

const STANDARD_BACK_ID = '0aeebaf5-8c7d-4636-9e82-8c27447861f7'

describe('buildScryfallBackUrl', () => {
  it('builds the correct CDN URL from the standard card back ID', () => {
    const url = buildScryfallBackUrl(STANDARD_BACK_ID)
    expect(url).toBe(
      'https://c2.scryfall.com/file/scryfall-card-backs/large/0a/ee/0aeebaf5-8c7d-4636-9e82-8c27447861f7.jpg'
    )
  })

  it('uses the first two chars as the first path segment', () => {
    const url = buildScryfallBackUrl('abcdef00-0000-0000-0000-000000000000')
    expect(url).toContain('/large/ab/cd/')
  })

  it('uses chars 2–4 as the second path segment', () => {
    const url = buildScryfallBackUrl('aabbcc00-0000-0000-0000-000000000000')
    expect(url).toContain('/large/aa/bb/')
  })

  it('appends the full UUID and .jpg extension', () => {
    const url = buildScryfallBackUrl(STANDARD_BACK_ID)
    expect(url).toMatch(/0aeebaf5-8c7d-4636-9e82-8c27447861f7\.jpg$/)
  })
})
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd src/frontend && npm test -- --reporter=verbose scryfallBackUrl
```

Expected: `Cannot find module '../utils/scryfallBackUrl'`

- [ ] **Step 3: Create the utility**

```typescript
// src/frontend/src/features/cards/utils/scryfallBackUrl.ts
export function buildScryfallBackUrl(cardBackId: string): string {
  const seg1 = cardBackId.slice(0, 2)
  const seg2 = cardBackId.slice(2, 4)
  return `https://c2.scryfall.com/file/scryfall-card-backs/large/${seg1}/${seg2}/${cardBackId}.jpg`
}
```

- [ ] **Step 4: Run tests — they should pass**

```bash
cd src/frontend && npm test -- --reporter=verbose scryfallBackUrl
```

Expected: 4 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/cards/utils/scryfallBackUrl.ts \
        src/frontend/src/features/cards/__tests__/scryfallBackUrl.test.ts
git commit -m "feat(frontend): add buildScryfallBackUrl utility"
```

---

## Task 8: Extend Frontend `CardDetail` TS Type

**Files:**
- Modify: `src/frontend/src/features/cards/types.ts`

- [ ] **Step 1: Add three optional fields to `CardDetail`**

In `types.ts`, `interface CardDetail extends CardSummary` currently ends with `price_history_sold_avg`. Add:

```typescript
export interface CardDetail extends CardSummary {
  mana_cost?: string
  type_line?: string
  oracle_text?: string
  artist?: string
  price_history?: number[]
  prints?: CardPrint[]
  image_large?: string | null
  price_history_list_avg?: number[]
  price_history_sold_avg?: number[]
  is_multifaced?: boolean
  card_back_id?: string | null
  back_face_image_uri?: string | null
}
```

- [ ] **Step 2: Commit**

```bash
git add src/frontend/src/features/cards/types.ts
git commit -m "feat(frontend): add face toggle fields to CardDetail type"
```

---

## Task 9: Create `FlippableCardArt` Component

**Files:**
- Create: `src/frontend/src/components/design-system/FlippableCardArt.tsx`
- Create: `src/frontend/src/components/design-system/FlippableCardArt.module.css`
- Create: `src/frontend/src/components/design-system/__tests__/FlippableCardArt.test.tsx`

- [ ] **Step 1: Write the failing tests**

```tsx
// src/frontend/src/components/design-system/__tests__/FlippableCardArt.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { FlippableCardArt } from '../FlippableCardArt'

vi.mock('../CardArt', () => ({
  CardArt: ({ name, imageUrl }: { name: string; imageUrl?: string | null }) => (
    <div data-testid="card-art" data-name={name} data-image={imageUrl ?? ''} />
  ),
}))

describe('FlippableCardArt', () => {
  it('renders the front image in the front face', () => {
    render(
      <FlippableCardArt
        name="Huntmaster of the Fells"
        frontUrl="https://example.com/front.jpg"
        backUrl="https://example.com/back.jpg"
      />
    )
    const arts = screen.getAllByTestId('card-art')
    expect(arts[0].dataset.image).toBe('https://example.com/front.jpg')
  })

  it('renders the back image in the back face', () => {
    render(
      <FlippableCardArt
        name="Huntmaster of the Fells"
        frontUrl="https://example.com/front.jpg"
        backUrl="https://example.com/back.jpg"
      />
    )
    const arts = screen.getAllByTestId('card-art')
    expect(arts[1].dataset.image).toBe('https://example.com/back.jpg')
  })

  it('renders a flip button when backUrl is provided', () => {
    render(
      <FlippableCardArt
        name="Huntmaster of the Fells"
        frontUrl="https://example.com/front.jpg"
        backUrl="https://example.com/back.jpg"
      />
    )
    expect(screen.getByRole('button', { name: /flip/i })).toBeTruthy()
  })

  it('does not render a flip button when backUrl is null', () => {
    render(
      <FlippableCardArt
        name="Jace, the Mind Sculptor"
        frontUrl="https://example.com/front.jpg"
        backUrl={null}
      />
    )
    expect(screen.queryByRole('button', { name: /flip/i })).toBeNull()
  })

  it('does not render a back face when backUrl is null', () => {
    render(
      <FlippableCardArt
        name="Jace, the Mind Sculptor"
        frontUrl="https://example.com/front.jpg"
        backUrl={null}
      />
    )
    const arts = screen.getAllByTestId('card-art')
    expect(arts).toHaveLength(1)
  })

  it('adds the flipped data attribute after clicking the flip button', () => {
    render(
      <FlippableCardArt
        name="Huntmaster of the Fells"
        frontUrl="https://example.com/front.jpg"
        backUrl="https://example.com/back.jpg"
      />
    )
    const card = screen.getByTestId('flip-card')
    expect(card.dataset.flipped).toBe('false')
    fireEvent.click(screen.getByRole('button', { name: /flip/i }))
    expect(card.dataset.flipped).toBe('true')
  })

  it('toggles flipped state back after clicking flip twice', () => {
    render(
      <FlippableCardArt
        name="Huntmaster of the Fells"
        frontUrl="https://example.com/front.jpg"
        backUrl="https://example.com/back.jpg"
      />
    )
    const card = screen.getByTestId('flip-card')
    const btn = screen.getByRole('button', { name: /flip/i })
    fireEvent.click(btn)
    fireEvent.click(btn)
    expect(card.dataset.flipped).toBe('false')
  })
})
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd src/frontend && npm test -- --reporter=verbose FlippableCardArt
```

Expected: `Cannot find module '../FlippableCardArt'`

- [ ] **Step 3: Create the CSS module**

```css
/* src/frontend/src/components/design-system/FlippableCardArt.module.css */

.wrapper {
  position: relative;
  display: inline-block;
  perspective: 1000px;
}

.card {
  position: relative;
  transform-style: preserve-3d;
  transition: transform 0.4s ease;
}

.card.flipped {
  transform: rotateY(180deg);
}

.front,
.back {
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}

.back {
  position: absolute;
  top: 0;
  left: 0;
  transform: rotateY(180deg);
}

.flipBtn {
  position: absolute;
  bottom: 10px;
  right: 10px;
  background: rgba(0, 0, 0, 0.65);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 50%;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  color: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  z-index: 2;
  transition: background 0.15s, transform 0.15s;
}

.flipBtn:hover {
  background: rgba(0, 0, 0, 0.85);
  transform: scale(1.1);
}
```

- [ ] **Step 4: Create the component**

> Two-face approach: front and back `CardArt` instances both exist in the DOM; CSS `backface-visibility: hidden` hides the non-active face. This avoids the mirrored-image problem that a single-face 180° rotation would produce.

```tsx
// src/frontend/src/components/design-system/FlippableCardArt.tsx
import { useState } from 'react'
import { CardArt } from './CardArt'
import styles from './FlippableCardArt.module.css'

interface FlippableCardArtProps {
  name: string
  frontUrl: string | null
  backUrl: string | null
  w?: number | string
  h?: number | string
  style?: React.CSSProperties
}

export function FlippableCardArt({
  name,
  frontUrl,
  backUrl,
  w = 200,
  h,
  style = {},
}: FlippableCardArtProps) {
  const [faceUp, setFaceUp] = useState(true)

  return (
    <div className={styles.wrapper} style={{ width: w, ...style }}>
      <div
        data-testid="flip-card"
        data-flipped={String(!faceUp)}
        className={`${styles.card} ${!faceUp ? styles.flipped : ''}`}
      >
        <div className={styles.front}>
          <CardArt name={name} w={w} h={h} label={false} imageUrl={frontUrl} />
        </div>
        {backUrl && (
          <div className={styles.back}>
            <CardArt name={name} w={w} h={h} label={false} imageUrl={backUrl} />
          </div>
        )}
      </div>
      {backUrl && (
        <button
          className={styles.flipBtn}
          onClick={() => setFaceUp(f => !f)}
          aria-label="Flip card"
        >
          ↻
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Run tests — they should pass**

```bash
cd src/frontend && npm test -- --reporter=verbose FlippableCardArt
```

Expected: 6 tests PASSED

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/components/design-system/FlippableCardArt.tsx \
        src/frontend/src/components/design-system/FlippableCardArt.module.css \
        src/frontend/src/components/design-system/__tests__/FlippableCardArt.test.tsx
git commit -m "feat(frontend): add FlippableCardArt component with CSS 3D flip"
```

---

## Task 10: Update `CardDetailView`

**Files:**
- Modify: `src/frontend/src/features/cards/components/CardDetailView.tsx`
- Modify: `src/frontend/src/features/cards/components/__tests__/CardDetailView.test.tsx`

- [ ] **Step 1: Update the test file**

Replace the existing `vi.mock` for `CardArt` and add flip-related assertions. The full updated test file:

```tsx
// src/frontend/src/features/cards/components/__tests__/CardDetailView.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CardDetailView } from '../CardDetailView'
import type { CardDetail } from '../../types'

vi.mock('../PriceCharts', () => ({
  PriceCharts: ({ finish }: { finish?: string }) => (
    <div data-testid="price-charts" data-finish={finish ?? ''} />
  ),
}))
vi.mock('../../../../components/design-system/FlippableCardArt', () => ({
  FlippableCardArt: ({
    frontUrl,
    backUrl,
  }: {
    name?: string
    frontUrl?: string | null
    backUrl?: string | null
    w?: number | string
    h?: number | string
    style?: React.CSSProperties
  }) => (
    <div
      data-testid="flippable-card-art"
      data-front={frontUrl ?? ''}
      data-back={backUrl ?? ''}
    />
  ),
}))
vi.mock('../../../../components/design-system/AreaChart', () => ({
  AreaChart: () => <div />,
}))
vi.mock('../../../../components/design-system/Pip', () => ({
  Pip: () => <span />,
}))

const mockCard: CardDetail = {
  card_version_id: '11111111-1111-1111-1111-111111111111',
  card_name: 'Sheoldred',
  set_code: 'mom',
  set_name: 'March of the Machine',
  finish: 'non-foil',
  rarity_name: 'rare',
  price: 42.5,
  price_change_1d: 1.2,
  price_change_7d: -0.5,
  price_change_30d: 3.1,
  image_uri: null,
  spark: [],
  available_finishes: ['nonfoil', 'foil'],
  image_large: 'https://example.com/front.jpg',
}

describe('CardDetailView', () => {
  it('renders a chip for each available finish', () => {
    render(<CardDetailView card={mockCard} />)
    expect(screen.getByText('nonfoil')).toBeTruthy()
    expect(screen.getByText('foil')).toBeTruthy()
  })

  it('defaults selected finish to first available finish', () => {
    render(<CardDetailView card={mockCard} />)
    expect(screen.getByTestId('price-charts').dataset.finish).toBe('nonfoil')
  })

  it('updates selected finish and passes it to PriceCharts when chip clicked', () => {
    render(<CardDetailView card={mockCard} />)
    fireEvent.click(screen.getByText('foil'))
    expect(screen.getByTestId('price-charts').dataset.finish).toBe('foil')
  })

  it('falls back to nonfoil chip when available_finishes is empty', () => {
    render(<CardDetailView card={{ ...mockCard, available_finishes: [] }} />)
    expect(screen.getByText('nonfoil')).toBeTruthy()
  })

  it('falls back to nonfoil chip when available_finishes is undefined', () => {
    const { available_finishes: _, ...cardWithoutFinishes } = mockCard
    render(<CardDetailView card={cardWithoutFinishes as CardDetail} />)
    expect(screen.getByText('nonfoil')).toBeTruthy()
  })

  it('passes image_large as frontUrl to FlippableCardArt', () => {
    render(<CardDetailView card={mockCard} />)
    const art = screen.getByTestId('flippable-card-art')
    expect(art.dataset.front).toBe('https://example.com/front.jpg')
  })

  it('passes back_face_image_uri as backUrl for DFC cards', () => {
    render(
      <CardDetailView
        card={{
          ...mockCard,
          is_multifaced: true,
          back_face_image_uri: 'https://example.com/back.jpg',
        }}
      />
    )
    const art = screen.getByTestId('flippable-card-art')
    expect(art.dataset.back).toBe('https://example.com/back.jpg')
  })

  it('constructs Scryfall back URL for regular cards with card_back_id', () => {
    render(
      <CardDetailView
        card={{
          ...mockCard,
          is_multifaced: false,
          card_back_id: '0aeebaf5-8c7d-4636-9e82-8c27447861f7',
        }}
      />
    )
    const art = screen.getByTestId('flippable-card-art')
    expect(art.dataset.back).toContain('scryfall-card-backs')
    expect(art.dataset.back).toContain('0aeebaf5-8c7d-4636-9e82-8c27447861f7')
  })

  it('passes null backUrl when card has no card_back_id and is not multifaced', () => {
    render(
      <CardDetailView
        card={{ ...mockCard, is_multifaced: false, card_back_id: null }}
      />
    )
    const art = screen.getByTestId('flippable-card-art')
    expect(art.dataset.back).toBe('')
  })
})
```

- [ ] **Step 2: Run the updated tests — expect failures for the new tests**

```bash
cd src/frontend && npm test -- --reporter=verbose CardDetailView
```

Expected: existing 5 tests pass, new 4 tests FAIL (component still imports `CardArt`)

- [ ] **Step 3: Update `CardDetailView.tsx`**

Replace the imports and the `<CardArt>` block. Full relevant diff:

At the top of `CardDetailView.tsx`, change:

```tsx
import { CardArt } from '../../../components/design-system/CardArt'
```

To:

```tsx
import { FlippableCardArt } from '../../../components/design-system/FlippableCardArt'
import { buildScryfallBackUrl } from '../utils/scryfallBackUrl'
```

Inside `CardDetailView`, before the return, add:

```tsx
  const backUrl = card.is_multifaced
    ? (card.back_face_image_uri ?? null)
    : card.card_back_id
      ? buildScryfallBackUrl(card.card_back_id)
      : null
```

Replace:

```tsx
        <CardArt
          name={card.card_name}
          w={420}
          h={585}
          hue={20}
          label={false}
          imageUrl={card.image_large}
          style={{ borderRadius: 16 }}
        />
```

With:

```tsx
        <FlippableCardArt
          name={card.card_name}
          w={420}
          h={585}
          frontUrl={card.image_large ?? null}
          backUrl={backUrl}
          style={{ borderRadius: 16 }}
        />
```

- [ ] **Step 4: Run all tests — they should all pass**

```bash
cd src/frontend && npm test -- --reporter=verbose CardDetailView
```

Expected: 9 tests PASSED

Run the full frontend test suite to check for regressions:

```bash
cd src/frontend && npm test
```

Expected: all tests PASSED (no regressions in other components)

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/cards/components/CardDetailView.tsx \
        src/frontend/src/features/cards/components/__tests__/CardDetailView.test.tsx
git commit -m "feat(frontend): wire FlippableCardArt into CardDetailView"
```

---

## Final Smoke Test

After all tasks are complete, start the dev server and verify visually:

```bash
dcdev-automana up -d
cd src/frontend && npm run dev
```

1. Open `http://localhost:5173`
2. Search for a **DFC card** (e.g., "Huntmaster of the Fells" or "Delver of Secrets") — navigate to its detail page and click ↻. The card should flip with a 3D rotation to the back face.
3. Search for a **regular card** (e.g., "Lightning Bolt") — navigate to its detail page and click ↻. The card should flip to the standard MTG card back.
4. For a **regular card with no `card_back_id`** in the DB yet — no ↻ icon should appear (graceful degradation).
