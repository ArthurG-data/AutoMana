# Card Detail Page Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign `CardDetailView` into a Hero layout with a gradient-faded image panel, scrollable data panel, set symbol (Keyrune), legality grid, oracle text, and artist info — matching the approved spec.

**Architecture:** Two-column CSS grid (`260px` image panel | `1fr` data panel); `SetInfoBox` and `LegalityGrid` as new self-contained components; backend `CardDetail` model and `card_repository.get()` extended to surface `legalities`, `promo_types`, `collector_number`, `mana_cost`, `type_line`, and `artist` from `v_card_versions_complete`.

**Tech Stack:** React 18, CSS Modules, Vitest + React Testing Library, FastAPI + Pydantic v2, PostgreSQL (`v_card_versions_complete` materialized view), Keyrune npm font

---

## File Map

| Status | File | Change |
|--------|------|--------|
| Modify | `src/automana/core/models/card_catalog/card.py` | Add 6 fields to `CardDetail` |
| Modify | `src/automana/core/repositories/card_catalog/card_repository.py` | Rewrite `get()` SQL to use `v_card_versions_complete` |
| Modify | `src/frontend/src/features/cards/types.ts` | Add `collector_number`, `promo_types`, `legalities` to `CardDetail` |
| Modify | `src/frontend/src/main.tsx` | Import Keyrune CSS |
| Create | `src/frontend/src/features/cards/components/SetInfoBox.tsx` | New component |
| Create | `src/frontend/src/features/cards/components/SetInfoBox.module.css` | New styles |
| Create | `src/frontend/src/features/cards/components/__tests__/SetInfoBox.test.tsx` | New tests |
| Create | `src/frontend/src/features/cards/components/LegalityGrid.tsx` | New component |
| Create | `src/frontend/src/features/cards/components/LegalityGrid.module.css` | New styles |
| Create | `src/frontend/src/features/cards/components/__tests__/LegalityGrid.test.tsx` | New tests |
| Modify | `src/frontend/src/features/cards/components/CardDetailView.tsx` | Full rewrite |
| Modify | `src/frontend/src/features/cards/components/CardDetailView.module.css` | Full rewrite |
| Modify | `src/frontend/src/features/cards/components/__tests__/CardDetailView.test.tsx` | Update mocks + add new assertions |

---

## Task 1: Extend CardDetail Python model

**Files:**
- Modify: `src/automana/core/models/card_catalog/card.py:36-50`

- [ ] **Step 1: Write the failing test**

Create `src/automana/tests/unit/models/test_card_detail_model.py`:

```python
import pytest
from uuid import UUID
from automana.core.models.card_catalog.card import CardDetail

MINIMAL = {
    "card_name": "Sheoldred",
    "set_name": "March of the Machine",
    "set_code": "mom",
    "cmc": 7,
    "rarity_name": "rare",
    "digital": False,
}


def test_card_detail_accepts_new_fields():
    card = CardDetail.model_validate({
        **MINIMAL,
        "mana_cost": "{5}{B}{B}",
        "type_line": "Legendary Creature — Phyrexian Praetor",
        "artist": "Chris Rahn",
        "collector_number": "245",
        "promo_types": ["showcase"],
        "legalities": {"modern": "legal", "standard": "not_legal"},
    })
    assert card.mana_cost == "{5}{B}{B}"
    assert card.type_line == "Legendary Creature — Phyrexian Praetor"
    assert card.artist == "Chris Rahn"
    assert card.collector_number == "245"
    assert card.promo_types == ["showcase"]
    assert card.legalities == {"modern": "legal", "standard": "not_legal"}


def test_card_detail_defaults_new_fields_to_none_or_empty():
    card = CardDetail.model_validate(MINIMAL)
    assert card.mana_cost is None
    assert card.type_line is None
    assert card.artist is None
    assert card.collector_number is None
    assert card.promo_types == []
    assert card.legalities == {}
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd /home/arthur/projects/AutoMana && pytest src/automana/tests/unit/models/test_card_detail_model.py -v
```

Expected: `ERROR` — `CardDetail` has no fields `mana_cost`, `type_line`, etc.

- [ ] **Step 3: Add the 6 new fields to CardDetail**

Open `src/automana/core/models/card_catalog/card.py`. The `CardDetail` class is at line 36. Replace the class body:

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
    mana_cost: Optional[str] = Field(default=None)
    type_line: Optional[str] = Field(default=None)
    artist: Optional[str] = Field(default=None)
    collector_number: Optional[str] = Field(default=None)
    promo_types: List[str] = Field(default_factory=list)
    legalities: Dict[str, str] = Field(default_factory=dict)
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
cd /home/arthur/projects/AutoMana && pytest src/automana/tests/unit/models/test_card_detail_model.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/models/card_catalog/card.py src/automana/tests/unit/models/test_card_detail_model.py
git commit -m "feat(card-detail): add mana_cost, type_line, artist, collector_number, promo_types, legalities to CardDetail model"
```

---

## Task 2: Rewrite card_repository.get() SQL query

**Files:**
- Modify: `src/automana/core/repositories/card_catalog/card_repository.py:82-132`

This replaces the old multi-join query that missed most fields with a query against `v_card_versions_complete` which already aggregates everything.

- [ ] **Step 1: Replace the get() method body**

Open `src/automana/core/repositories/card_catalog/card_repository.py`. Replace the `get()` method (lines 82–132) with:

```python
    async def get(self,
                  card_id: UUID,
                 ) -> dict[str, Any]|None:
        query = """
            SELECT
                v.card_version_id,
                v.card_name,
                v.rarity_name,
                v.set_name,
                v.set_code,
                v.cmc,
                v.oracle_text,
                v.mana_cost,
                v.type_line,
                v.collector_number,
                v.promo_types,
                v.legalities,
                v.is_multifaced,
                v.is_digital          AS digital,
                v.illustrations->0->>'artist_name'              AS artist,
                v.illustrations->0->'image_uris'->>'large'      AS image_large,
                ARRAY(
                    SELECT LOWER(cf.code)
                    FROM card_catalog.card_version_finish cvf
                    JOIN card_catalog.card_finished cf ON cf.finish_id = cvf.finish_id
                    WHERE cvf.card_version_id = v.card_version_id
                ) AS available_finishes,
                cv.card_back_id,
                COALESCE(
                    (
                        SELECT i.image_uris->>'large'
                        FROM   card_catalog.card_faces face
                        JOIN   card_catalog.face_illustration fi
                                   ON fi.face_id = face.card_faces_id
                        JOIN   card_catalog.illustrations i
                                   ON i.illustration_id = fi.illustration_id
                        WHERE  face.card_version_id = v.card_version_id
                          AND  face.face_index = 1
                        LIMIT  1
                    ),
                    CASE
                        WHEN v.is_multifaced = TRUE
                         AND v.illustrations->0->'image_uris'->>'large' LIKE '%/front/%'
                        THEN replace(
                            v.illustrations->0->'image_uris'->>'large',
                            '/front/', '/back/'
                        )
                    END
                ) AS back_face_image_uri
            FROM card_catalog.v_card_versions_complete v
            JOIN card_catalog.card_version cv ON cv.card_version_id = v.card_version_id
            WHERE v.card_version_id = $1;
        """
        result = await self.execute_query(query, (card_id,))
        return result[0] if result else None
```

- [ ] **Step 2: Verify the query returns correct columns by running a smoke test**

Start the dev backend and call the card detail endpoint manually, or verify the columns match the `CardDetail` model fields. The Pydantic model uses `from_attributes=True` and `populate_by_name=True`, so the column aliases (`digital`, `artist`, `image_large`, `back_face_image_uri`) must exactly match either the field name or its alias.

Check the field mapping in `BaseCard`:
- `name` has alias `card_name` → query returns `v.card_name` ✓
- `set` has alias `set_code` → query returns `v.set_code` ✓
- `rarity` has alias `rarity_name` → query returns `v.rarity_name` ✓
- `digital` has no alias → query returns `AS digital` ✓

**Note:** `v_card_versions_complete` is a **materialized view** — it is NOT refreshed automatically by the ingestion pipeline. A card inserted via Scryfall ingestion will not appear in card detail until `card_catalog.refresh_card_search_views()` is called manually or via the `refresh_card_search_views` service. This is a pre-existing limitation; the repository change is correct.

- [ ] **Step 3: Commit**

```bash
git add src/automana/core/repositories/card_catalog/card_repository.py
git commit -m "feat(card-detail): rewrite card_repository.get() to use v_card_versions_complete view"
```

---

## Task 3: Add new fields to frontend CardDetail type

**Files:**
- Modify: `src/frontend/src/features/cards/types.ts:28-42`

- [ ] **Step 1: Add the three missing fields to the CardDetail interface**

Open `src/frontend/src/features/cards/types.ts`. The `CardDetail` interface extends `CardSummary` at line 28. Add three lines after `back_face_image_uri`:

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
  available_finishes?: string[]
  is_multifaced?: boolean
  card_back_id?: string | null
  back_face_image_uri?: string | null
  collector_number?: string
  promo_types?: string[]
  legalities?: Record<string, string>
}
```

- [ ] **Step 2: Run the frontend type-check**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm run typecheck 2>/dev/null || npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/features/cards/types.ts
git commit -m "feat(card-detail): add collector_number, promo_types, legalities to frontend CardDetail type"
```

---

## Task 4: Install Keyrune and import CSS

**Files:**
- Modify: `src/frontend/package.json` (via npm install)
- Modify: `src/frontend/src/main.tsx:9`

- [ ] **Step 1: Install the keyrune package**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm install keyrune
```

Expected: `added N packages` with `keyrune` listed in `package.json` dependencies.

- [ ] **Step 2: Import Keyrune CSS in main.tsx**

Open `src/frontend/src/main.tsx`. After line 9 (`import './styles/global.css'`), add:

```typescript
import 'keyrune/css/keyrune.min.css'
```

Result:
```typescript
import './styles/global.css'
import 'keyrune/css/keyrune.min.css'
```

- [ ] **Step 3: Verify the dev server starts without errors**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm run build 2>&1 | tail -5
```

Expected: build succeeds (or `npm run dev` starts without CSS import errors).

- [ ] **Step 4: Commit**

```bash
git add src/frontend/package.json src/frontend/package-lock.json src/frontend/src/main.tsx
git commit -m "feat(card-detail): install keyrune font package and import CSS"
```

---

## Task 5: Create SetInfoBox component

**Files:**
- Create: `src/frontend/src/features/cards/components/SetInfoBox.tsx`
- Create: `src/frontend/src/features/cards/components/SetInfoBox.module.css`
- Create: `src/frontend/src/features/cards/components/__tests__/SetInfoBox.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `src/frontend/src/features/cards/components/__tests__/SetInfoBox.test.tsx`:

```tsx
// src/frontend/src/features/cards/components/__tests__/SetInfoBox.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SetInfoBox } from '../SetInfoBox'

describe('SetInfoBox', () => {
  it('renders set name', () => {
    render(
      <SetInfoBox setCode="mom" setName="March of the Machine" rarityName="rare" />
    )
    expect(screen.getByText('March of the Machine')).toBeTruthy()
  })

  it('renders set code in parentheses, uppercased', () => {
    render(
      <SetInfoBox setCode="mom" setName="March of the Machine" rarityName="rare" />
    )
    expect(screen.getByText('(MOM)')).toBeTruthy()
  })

  it('renders Keyrune icon with lowercase set_code and rarity classes', () => {
    const { container } = render(
      <SetInfoBox setCode="MOM" setName="March of the Machine" rarityName="mythic" />
    )
    const icon = container.querySelector('i')
    expect(icon?.className).toContain('ss-mom')
    expect(icon?.className).toContain('ss-mythic')
  })

  it('renders capitalized rarity label', () => {
    render(
      <SetInfoBox setCode="mom" setName="March of the Machine" rarityName="uncommon" />
    )
    expect(screen.getByText('Uncommon')).toBeTruthy()
  })

  it('renders collector number with # prefix when provided', () => {
    render(
      <SetInfoBox setCode="mom" setName="March of the Machine" rarityName="rare" collectorNumber="245" />
    )
    expect(screen.getByText('#245')).toBeTruthy()
  })

  it('omits collector number section when not provided', () => {
    const { queryByText } = render(
      <SetInfoBox setCode="mom" setName="March of the Machine" rarityName="rare" />
    )
    expect(queryByText(/^#/)).toBeNull()
  })

  it('renders one badge per promo type', () => {
    render(
      <SetInfoBox
        setCode="mom"
        setName="March of the Machine"
        rarityName="rare"
        promoTypes={['Showcase', 'Etched Foil']}
      />
    )
    expect(screen.getByText(/Showcase/)).toBeTruthy()
    expect(screen.getByText(/Etched Foil/)).toBeTruthy()
  })

  it('renders no badges when promoTypes is empty', () => {
    const { container } = render(
      <SetInfoBox setCode="mom" setName="March of the Machine" rarityName="rare" promoTypes={[]} />
    )
    expect(container.querySelectorAll('[class*="badge"]').length).toBe(0)
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm run test -- SetInfoBox --reporter=verbose 2>&1 | tail -10
```

Expected: `Cannot find module '../SetInfoBox'`

- [ ] **Step 3: Create the component**

Create `src/frontend/src/features/cards/components/SetInfoBox.tsx`:

```tsx
// src/frontend/src/features/cards/components/SetInfoBox.tsx
import styles from './SetInfoBox.module.css'

interface SetInfoBoxProps {
  setCode: string
  setName: string
  rarityName: string
  collectorNumber?: string
  promoTypes?: string[]
}

export function SetInfoBox({
  setCode,
  setName,
  rarityName,
  collectorNumber,
  promoTypes = [],
}: SetInfoBoxProps) {
  const rarity = rarityName.toLowerCase()

  return (
    <div className={styles.box}>
      <div className={styles.iconCol}>
        <i
          className={`ss ss-${setCode.toLowerCase()} ss-${rarity}`}
          aria-hidden="true"
        />
      </div>
      <div className={styles.textCol}>
        <div className={styles.setLine}>
          <span className={styles.setName}>{setName}</span>
          <span className={styles.setCode}>({setCode.toUpperCase()})</span>
        </div>
        <div className={styles.rarityLine}>
          {rarityName.charAt(0).toUpperCase() + rarityName.slice(1)}
        </div>
        {collectorNumber != null && (
          <div className={styles.collectorLine}>#{collectorNumber}</div>
        )}
        {promoTypes.length > 0 && (
          <div className={styles.badges}>
            {promoTypes.map((pt) => (
              <span key={pt} className={styles.badge}>✦ {pt}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Create the CSS module**

Create `src/frontend/src/features/cards/components/SetInfoBox.module.css`:

```css
/* src/frontend/src/features/cards/components/SetInfoBox.module.css */
.box {
  display: flex;
  border: 1px solid rgba(150,200,255,0.12);
  border-radius: 10px;
  overflow: hidden;
}

.iconCol {
  width: 44px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(224,169,106,0.08);
  border-right: 1px solid rgba(150,200,255,0.12);
  font-size: 22px;
}

.textCol {
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.setLine {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
}

.setName {
  font-family: var(--font-body);
  color: var(--hd-text);
  font-weight: 500;
}

.setCode {
  font-family: var(--font-mono);
  color: var(--hd-sub);
  font-size: 11px;
}

.rarityLine {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--hd-muted);
  text-transform: uppercase;
  letter-spacing: 0.8px;
}

.collectorLine {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--hd-sub);
}

.badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.badge {
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 20px;
  background: rgba(224,169,106,0.12);
  border: 1px solid rgba(224,169,106,0.28);
  color: #e0a96a;
}
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm run test -- SetInfoBox --reporter=verbose 2>&1 | tail -15
```

Expected: `8 passed`

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/cards/components/SetInfoBox.tsx src/frontend/src/features/cards/components/SetInfoBox.module.css src/frontend/src/features/cards/components/__tests__/SetInfoBox.test.tsx
git commit -m "feat(card-detail): add SetInfoBox component with Keyrune icon and promo badges"
```

---

## Task 6: Create LegalityGrid component

**Files:**
- Create: `src/frontend/src/features/cards/components/LegalityGrid.tsx`
- Create: `src/frontend/src/features/cards/components/LegalityGrid.module.css`
- Create: `src/frontend/src/features/cards/components/__tests__/LegalityGrid.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `src/frontend/src/features/cards/components/__tests__/LegalityGrid.test.tsx`:

```tsx
// src/frontend/src/features/cards/components/__tests__/LegalityGrid.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LegalityGrid } from '../LegalityGrid'

const allLegal = {
  standard: 'legal',
  pioneer: 'legal',
  modern: 'legal',
  legacy: 'legal',
  vintage: 'legal',
  pauper: 'legal',
  commander: 'legal',
  oathbreaker: 'legal',
}

describe('LegalityGrid', () => {
  it('renders all 8 format labels', () => {
    render(<LegalityGrid legalities={allLegal} />)
    expect(screen.getByText('standard')).toBeTruthy()
    expect(screen.getByText('pioneer')).toBeTruthy()
    expect(screen.getByText('modern')).toBeTruthy()
    expect(screen.getByText('legacy')).toBeTruthy()
    expect(screen.getByText('vintage')).toBeTruthy()
    expect(screen.getByText('pauper')).toBeTruthy()
    expect(screen.getByText('commander')).toBeTruthy()
    expect(screen.getByText('oathbreaker')).toBeTruthy()
  })

  it('shows "legal" status text for legal formats', () => {
    render(<LegalityGrid legalities={allLegal} />)
    const cells = screen.getAllByText('legal')
    expect(cells.length).toBe(8)
  })

  it('shows "not legal" for not_legal formats (underscore replaced with space)', () => {
    render(<LegalityGrid legalities={{ ...allLegal, standard: 'not_legal', pauper: 'not_legal' }} />)
    const notLegalCells = screen.getAllByText('not legal')
    expect(notLegalCells.length).toBe(2)
  })

  it('shows "banned" status text for banned formats', () => {
    render(<LegalityGrid legalities={{ ...allLegal, modern: 'banned' }} />)
    expect(screen.getByText('banned')).toBeTruthy()
  })

  it('defaults missing formats to not_legal', () => {
    render(<LegalityGrid legalities={{}} />)
    const notLegalCells = screen.getAllByText('not legal')
    expect(notLegalCells.length).toBe(8)
  })

  it('shows "restricted" status text for restricted formats', () => {
    render(<LegalityGrid legalities={{ ...allLegal, vintage: 'restricted' }} />)
    expect(screen.getByText('restricted')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm run test -- LegalityGrid --reporter=verbose 2>&1 | tail -10
```

Expected: `Cannot find module '../LegalityGrid'`

- [ ] **Step 3: Create the component**

Create `src/frontend/src/features/cards/components/LegalityGrid.tsx`:

```tsx
// src/frontend/src/features/cards/components/LegalityGrid.tsx
import styles from './LegalityGrid.module.css'

const FORMATS = [
  'standard', 'pioneer', 'modern', 'legacy',
  'vintage', 'pauper', 'commander', 'oathbreaker',
] as const

interface LegalityGridProps {
  legalities: Record<string, string>
}

export function LegalityGrid({ legalities }: LegalityGridProps) {
  return (
    <div className={styles.grid}>
      {FORMATS.map((fmt) => {
        const status = legalities[fmt] ?? 'not_legal'
        const statusClass =
          status === 'legal' ? styles.legal
          : status === 'banned' ? styles.banned
          : status === 'restricted' ? styles.restricted
          : styles.notLegal
        return (
          <div key={fmt} className={`${styles.cell} ${statusClass}`}>
            <div className={styles.label}>{fmt}</div>
            <div className={styles.status}>{status.replace('_', ' ')}</div>
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 4: Create the CSS module**

Create `src/frontend/src/features/cards/components/LegalityGrid.module.css`:

```css
/* src/frontend/src/features/cards/components/LegalityGrid.module.css */
.grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 4px;
}

.cell {
  padding: 6px 8px;
  border-radius: 5px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.label {
  font-family: var(--font-mono);
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--hd-sub);
}

.status {
  font-family: var(--font-mono);
  font-size: 10px;
  text-transform: capitalize;
}

.legal { background: rgba(61,232,210,0.08); }
.legal .status { color: var(--hd-accent); }

.notLegal { background: rgba(150,200,255,0.04); }
.notLegal .status { color: var(--hd-sub); }

.banned { background: rgba(227,94,108,0.08); }
.banned .status { color: var(--hd-red); }

.restricted { background: rgba(255,200,80,0.08); }
.restricted .status { color: #ffc850; }
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm run test -- LegalityGrid --reporter=verbose 2>&1 | tail -15
```

Expected: `6 passed`

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/cards/components/LegalityGrid.tsx src/frontend/src/features/cards/components/LegalityGrid.module.css src/frontend/src/features/cards/components/__tests__/LegalityGrid.test.tsx
git commit -m "feat(card-detail): add LegalityGrid component for 8-format legality display"
```

---

## Task 7: Rewrite CardDetailView

**Files:**
- Modify: `src/frontend/src/features/cards/components/CardDetailView.tsx`
- Modify: `src/frontend/src/features/cards/components/CardDetailView.module.css`
- Modify: `src/frontend/src/features/cards/components/__tests__/CardDetailView.test.tsx`

- [ ] **Step 1: Update the test file first**

Replace the entire content of `src/frontend/src/features/cards/components/__tests__/CardDetailView.test.tsx`:

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
vi.mock('../SetInfoBox', () => ({
  SetInfoBox: () => <div data-testid="set-info-box" />,
}))
vi.mock('../LegalityGrid', () => ({
  LegalityGrid: ({ legalities }: { legalities: Record<string, string> }) => (
    <div data-testid="legality-grid" data-has-entries={Object.keys(legalities).length > 0 ? 'true' : 'false'} />
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
  collector_number: '245',
  promo_types: [],
  legalities: { modern: 'legal', standard: 'not_legal' },
}

describe('CardDetailView', () => {
  it('renders a button for each available finish', () => {
    render(<CardDetailView card={mockCard} />)
    expect(screen.getByText('nonfoil')).toBeTruthy()
    expect(screen.getByText('foil')).toBeTruthy()
  })

  it('defaults selected finish to first available finish', () => {
    render(<CardDetailView card={mockCard} />)
    expect(screen.getByTestId('price-charts').dataset.finish).toBe('nonfoil')
  })

  it('updates selected finish and passes it to PriceCharts when button clicked', () => {
    render(<CardDetailView card={mockCard} />)
    fireEvent.click(screen.getByText('foil'))
    expect(screen.getByTestId('price-charts').dataset.finish).toBe('foil')
  })

  it('falls back to nonfoil when available_finishes is empty', () => {
    render(<CardDetailView card={{ ...mockCard, available_finishes: [] }} />)
    expect(screen.getByText('nonfoil')).toBeTruthy()
  })

  it('falls back to nonfoil when available_finishes is undefined', () => {
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

  it('renders SetInfoBox', () => {
    render(<CardDetailView card={mockCard} />)
    expect(screen.getByTestId('set-info-box')).toBeTruthy()
  })

  it('renders LegalityGrid when legalities has entries', () => {
    render(<CardDetailView card={mockCard} />)
    const grid = screen.getByTestId('legality-grid')
    expect(grid).toBeTruthy()
    expect(grid.dataset.hasEntries).toBe('true')
  })

  it('does not render LegalityGrid when legalities is empty', () => {
    render(<CardDetailView card={{ ...mockCard, legalities: {} }} />)
    expect(screen.queryByTestId('legality-grid')).toBeNull()
  })

  it('does not render LegalityGrid when legalities is undefined', () => {
    const { legalities: _, ...cardNoLegalities } = mockCard
    render(<CardDetailView card={cardNoLegalities as CardDetail} />)
    expect(screen.queryByTestId('legality-grid')).toBeNull()
  })
})
```

- [ ] **Step 2: Run the updated tests to see which fail (they should all fail until we rewrite the component)**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm run test -- CardDetailView --reporter=verbose 2>&1 | tail -20
```

Expected: several failures because `SetInfoBox` and `LegalityGrid` are not yet imported in `CardDetailView.tsx`, and the legality tests will fail.

- [ ] **Step 3: Rewrite CardDetailView.tsx**

Replace the entire content of `src/frontend/src/features/cards/components/CardDetailView.tsx`:

```tsx
// src/frontend/src/features/cards/components/CardDetailView.tsx
import { useState } from 'react'
import { FlippableCardArt } from '../../../components/design-system/FlippableCardArt'
import { buildScryfallBackUrl } from '../utils/scryfallBackUrl'
import { Pip, type ManaColor } from '../../../components/design-system/Pip'
import { Button } from '../../../components/ui/Button'
import { PriceCharts } from './PriceCharts'
import { SetInfoBox } from './SetInfoBox'
import { LegalityGrid } from './LegalityGrid'
import type { CardDetail } from '../types'
import styles from './CardDetailView.module.css'

interface CardDetailViewProps {
  card: CardDetail
}

function parseMana(cost: string): ManaColor[] {
  return (cost.match(/[WUBRG]/g) ?? []) as ManaColor[]
}

export function CardDetailView({ card }: CardDetailViewProps) {
  const finishes = card.available_finishes?.length ? card.available_finishes : ['nonfoil']
  const [selectedFinish, setSelectedFinish] = useState(finishes[0])

  const backUrl = card.is_multifaced
    ? (card.back_face_image_uri ?? null)
    : card.card_back_id
      ? buildScryfallBackUrl(card.card_back_id)
      : null

  const delta1d = card.price_change_1d
  const delta7d = card.price_change_7d
  const delta30d = card.price_change_30d

  return (
    <div className={styles.layout}>
      <div className={styles.imagePanel}>
        <FlippableCardArt
          name={card.card_name}
          w={240}
          frontUrl={card.image_large ?? null}
          backUrl={backUrl}
        />
        <div className={styles.imageFade} aria-hidden="true" />
      </div>

      <div className={styles.dataPanel}>
        <SetInfoBox
          setCode={card.set_code}
          setName={card.set_name}
          rarityName={card.rarity_name}
          collectorNumber={card.collector_number}
          promoTypes={card.promo_types}
        />

        <div className={styles.identity}>
          <h1 className={styles.name}>{card.card_name}</h1>
          {card.mana_cost && (
            <div className={styles.manaRow}>
              {parseMana(card.mana_cost).map((c, i) => <Pip key={i} color={c} size={18} />)}
              <span className={styles.manaCost}>{card.mana_cost}</span>
            </div>
          )}
          {card.type_line && <div className={styles.typeLine}>{card.type_line}</div>}
        </div>

        {card.oracle_text && (
          <div className={styles.oracleBox}>
            <p>{card.oracle_text}</p>
            {card.artist && (
              <div className={styles.artistLine}>
                Illus. {card.artist}
                {card.collector_number && <span> · #{card.collector_number}</span>}
              </div>
            )}
          </div>
        )}

        <div className={styles.finishSelector}>
          {finishes.map((f) => (
            <button
              key={f}
              onClick={() => setSelectedFinish(f)}
              aria-pressed={f === selectedFinish}
              className={f === selectedFinish ? styles.finishActive : styles.finishBtn}
            >
              {f}
            </button>
          ))}
        </div>

        <div className={styles.priceSection}>
          <div className={styles.priceLabel}>MARKET PRICE · {selectedFinish}</div>
          <div className={styles.priceRow}>
            <div className={styles.price}>
              {card.price != null ? (
                <>
                  ${Math.floor(card.price)}
                  <span className={styles.priceCents}>
                    .{(card.price % 1).toFixed(2).slice(2)}
                  </span>
                </>
              ) : 'N/A'}
            </div>
            <div className={styles.deltas}>
              <span className={delta1d >= 0 ? styles.up : styles.down}>
                {delta1d >= 0 ? '▲' : '▼'} {Math.abs(delta1d).toFixed(2)}% 1d
              </span>
              <span className={delta7d >= 0 ? styles.up : styles.down}>
                {delta7d >= 0 ? '▲' : '▼'} {Math.abs(delta7d).toFixed(2)}% 7d
              </span>
              <span className={delta30d >= 0 ? styles.up : styles.down}>
                {delta30d >= 0 ? '▲' : '▼'} {Math.abs(delta30d).toFixed(2)}% 30d
              </span>
            </div>
          </div>
        </div>

        <PriceCharts card={card} finish={selectedFinish} />

        {card.legalities && Object.keys(card.legalities).length > 0 && (
          <LegalityGrid legalities={card.legalities} />
        )}

        <div className={styles.actions}>
          <Button variant="accent" style={{ flex: 1 }}>+ Add to collection</Button>
          <Button variant="ghost">Watch</Button>
          <Button variant="ghost">Alert</Button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Rewrite CardDetailView.module.css**

Replace the entire content of `src/frontend/src/features/cards/components/CardDetailView.module.css`:

```css
/* src/frontend/src/features/cards/components/CardDetailView.module.css */
.layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  min-height: 100vh;
}

.imagePanel {
  position: relative;
  background: linear-gradient(160deg, #1e2e5a, #0d1526 55%, #1a2444);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 32px;
}

.imageFade {
  position: absolute;
  top: 0;
  right: 0;
  width: 55%;
  height: 100%;
  background: linear-gradient(to right, transparent 0%, #0b1425 100%);
  pointer-events: none;
}

.dataPanel {
  background: #0b1425;
  border-left: 1px solid rgba(150,200,255,0.08);
  overflow-y: auto;
  padding: 24px 18px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.identity { display: flex; flex-direction: column; gap: 8px; }
.name { font-family: var(--font-serif); font-size: 24px; font-weight: 400; letter-spacing: -0.3px; margin: 0; }
.manaRow { display: flex; gap: 6px; align-items: center; }
.manaCost { font-family: var(--font-mono); font-size: 12px; color: var(--hd-muted); }
.typeLine { font-family: var(--font-mono); font-size: 11px; color: var(--hd-muted); }

.oracleBox {
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(150,200,255,0.09);
  border-radius: 7px;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.65;
}
.oracleBox p { margin: 0; }
.artistLine { font-family: var(--font-mono); font-size: 11px; color: var(--hd-sub); margin-top: 8px; }

.finishSelector { display: flex; gap: 8px; flex-wrap: wrap; }
.finishBtn {
  padding: 5px 14px;
  border-radius: 20px;
  border: 1px solid rgba(150,200,255,0.15);
  background: transparent;
  color: var(--hd-sub);
  font-family: var(--font-mono);
  font-size: 11px;
  cursor: pointer;
}
.finishActive {
  padding: 5px 14px;
  border-radius: 20px;
  border: 1px solid rgba(61,232,210,0.38);
  background: rgba(61,232,210,0.11);
  color: var(--hd-accent);
  font-family: var(--font-mono);
  font-size: 11px;
  cursor: pointer;
}

.priceSection { display: flex; flex-direction: column; gap: 6px; }
.priceLabel { font-family: var(--font-mono); font-size: 9px; color: var(--hd-sub); letter-spacing: 1.4px; text-transform: uppercase; }
.priceRow { display: flex; align-items: baseline; gap: 16px; }
.price { font-family: var(--font-serif); font-size: 38px; font-weight: 400; letter-spacing: -1px; line-height: 1; color: var(--hd-accent); }
.priceCents { color: var(--hd-muted); font-size: 19px; }
.deltas { display: flex; flex-direction: column; gap: 3px; font-family: var(--font-mono); font-size: 10px; }
.up { color: var(--hd-accent); }
.down { color: var(--hd-red); }

.actions { display: flex; gap: 10px; padding-top: 4px; }

@media (max-width: 768px) {
  .layout { grid-template-columns: 1fr; }
  .imagePanel { min-height: 320px; }
  .imageFade { display: none; }
}
```

- [ ] **Step 5: Run all CardDetailView tests**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm run test -- CardDetailView --reporter=verbose 2>&1 | tail -20
```

Expected: `13 passed` (all original tests pass + 4 new ones)

- [ ] **Step 6: Run the full frontend test suite to check for regressions**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm run test 2>&1 | tail -10
```

Expected: same pass/fail count as before (pre-existing failures not introduced by this work)

- [ ] **Step 7: Commit**

```bash
git add src/frontend/src/features/cards/components/CardDetailView.tsx src/frontend/src/features/cards/components/CardDetailView.module.css src/frontend/src/features/cards/components/__tests__/CardDetailView.test.tsx
git commit -m "feat(card-detail): rewrite CardDetailView with Hero layout, SetInfoBox, LegalityGrid, oracle text, and gradient image fade"
```
