# Finish Selector — Card Detail Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the available finishes (nonfoil / foil / etched) for a card version on the detail page, letting users switch between them and have the price chart re-fetch for the selected finish.

**Architecture:** The backend `card_repository.get()` query gains a correlated subquery that reads `card_version_finish` and returns `available_finishes: list[str]`. The `CardDetail` Pydantic model exposes the field. On the frontend, `CardDetailView` holds `selectedFinish` state and renders clickable finish chips; `PriceCharts` accepts a `finish` prop and forwards it to the price-history query.

**Tech Stack:** Python / asyncpg / Pydantic v2 (backend); React 18, TypeScript, TanStack Query, Vitest, MSW (frontend)

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `src/automana/core/repositories/card_catalog/card_repository.py` | Modify | `get()` adds correlated subquery for `available_finishes` |
| `src/automana/core/models/card_catalog/card.py` | Modify | `CardDetail` gets `available_finishes: Optional[List[str]]` |
| `src/frontend/src/features/cards/types.ts` | Modify | `CardDetail` interface gets `available_finishes?: string[]` |
| `src/frontend/src/mocks/data.ts` | Modify | `MOCK_CARD_DETAIL` entries get `available_finishes` |
| `src/frontend/src/features/cards/components/PriceCharts.tsx` | Modify | Accept `finish?: string`, pass to query |
| `src/frontend/src/features/cards/components/CardDetailView.tsx` | Modify | `selectedFinish` state + dynamic chip row |
| `tests/unit/core/repositories/card_catalog/test_card_repository_get.py` | Create | Unit tests for `get()` returning `available_finishes` |
| `tests/unit/core/models/card_catalog/test_card_detail_model.py` | Create | Unit tests for `CardDetail` `available_finishes` field |
| `src/frontend/src/features/cards/components/__tests__/PriceCharts.test.tsx` | Create | Tests `finish` prop reaches the query |
| `src/frontend/src/features/cards/components/__tests__/CardDetailView.test.tsx` | Create | Tests chip rendering and finish selection |

---

## Task 1: Backend — `card_repository.get()` returns `available_finishes`

**Files:**
- Modify: `src/automana/core/repositories/card_catalog/card_repository.py:82-97`
- Create: `tests/unit/core/repositories/card_catalog/test_card_repository_get.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/core/repositories/card_catalog/test_card_repository_get.py
"""Unit tests for CardReferenceRepository.get()"""
import pytest
from unittest.mock import AsyncMock
from uuid import UUID
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository

pytestmark = pytest.mark.unit

_CARD_ID = UUID("11111111-1111-1111-1111-111111111111")

_BASE_ROW = {
    "card_version_id": str(_CARD_ID),
    "card_name": "Sheoldred",
    "rarity_name": "rare",
    "set_name": "March of the Machine",
    "set_code": "mom",
    "cmc": 4,
    "oracle_text": "...",
    "released_at": "2023-04-21",
    "digital": False,
    "image_large": None,
}


def _make_repo(rows):
    repo = CardReferenceRepository.__new__(CardReferenceRepository)
    repo.execute_query = AsyncMock(return_value=rows)
    return repo


@pytest.mark.asyncio
async def test_get_returns_available_finishes():
    row = {**_BASE_ROW, "available_finishes": ["nonfoil", "foil"]}
    repo = _make_repo([row])
    result = await repo.get(card_id=_CARD_ID)
    assert result["available_finishes"] == ["nonfoil", "foil"]


@pytest.mark.asyncio
async def test_get_returns_empty_list_when_no_finish_rows():
    row = {**_BASE_ROW, "available_finishes": []}
    repo = _make_repo([row])
    result = await repo.get(card_id=_CARD_ID)
    assert result["available_finishes"] == []


@pytest.mark.asyncio
async def test_get_returns_none_when_card_not_found():
    repo = _make_repo([])
    result = await repo.get(card_id=UUID("00000000-0000-0000-0000-000000000000"))
    assert result is None
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/unit/core/repositories/card_catalog/test_card_repository_get.py -v
```

Expected: `KeyError: 'available_finishes'` on the first two tests (field not in query yet); third passes.

- [ ] **Step 3: Add correlated subquery to `get()`**

In `card_repository.py`, replace the `get()` query string (currently ends at `WHERE cv.card_version_id = $1;`) with:

```python
    async def get(self,
                  card_id: UUID,
                 ) -> dict[str, Any]|None:
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
        result = await self.execute_query(query, (card_id,))
        return result[0] if result else None
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
pytest tests/unit/core/repositories/card_catalog/test_card_repository_get.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/core/repositories/card_catalog/test_card_repository_get.py \
        src/automana/core/repositories/card_catalog/card_repository.py
git commit -m "feat(card_catalog): return available_finishes from card_repository.get()"
```

---

## Task 2: Backend — `CardDetail` model field

**Files:**
- Modify: `src/automana/core/models/card_catalog/card.py:36-45`
- Create: `tests/unit/core/models/card_catalog/test_card_detail_model.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/core/models/card_catalog/test_card_detail_model.py
"""Unit tests for CardDetail.available_finishes field."""
import pytest
from automana.core.models.card_catalog.card import CardDetail

pytestmark = pytest.mark.unit

_BASE = {
    "card_name": "Sheoldred",
    "set_name": "March of the Machine",
    "set_code": "mom",
    "cmc": 4,
    "rarity_name": "rare",
    "oracle_text": "",
    "digital": False,
    "image_normal": None,
}


def test_card_detail_available_finishes_populated():
    card = CardDetail.model_validate({**_BASE, "available_finishes": ["nonfoil", "foil"]})
    assert card.available_finishes == ["nonfoil", "foil"]


def test_card_detail_available_finishes_defaults_to_empty_list():
    card = CardDetail.model_validate(_BASE)
    assert card.available_finishes == []
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/unit/core/models/card_catalog/test_card_detail_model.py -v
```

Expected: `ValidationError` or `AttributeError` — field doesn't exist yet.

- [ ] **Step 3: Add field to `CardDetail`**

In `card.py`, update the `CardDetail` class (currently at line ~36):

```python
class CardDetail(BaseCard):
    image_large: Optional[str] = Field(default=None, title="URL to large-sized card image from Scryfall")
    available_finishes: Optional[List[str]] = Field(default_factory=list)
    price_history_list_avg: Optional[List[float]] = Field(
        default=None,
        title="Daily list average prices in dollars for selected time range"
    )
    price_history_sold_avg: Optional[List[float]] = Field(
        default=None,
        title="Daily sold average prices in dollars for selected time range"
    )
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
pytest tests/unit/core/models/card_catalog/test_card_detail_model.py -v
```

Expected: `2 passed`.

- [ ] **Step 5: Run full backend unit suite to check for regressions**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/core/models/card_catalog/test_card_detail_model.py \
        src/automana/core/models/card_catalog/card.py
git commit -m "feat(card_catalog): add available_finishes field to CardDetail model"
```

---

## Task 3: Frontend — TypeScript types and mock data

**Files:**
- Modify: `src/frontend/src/features/cards/types.ts`
- Modify: `src/frontend/src/mocks/data.ts`

No separate test file — TypeScript compilation is the gate. The mock data update keeps existing tests type-correct.

- [ ] **Step 1: Add `available_finishes` to `CardDetail` interface**

In `types.ts`, update the `CardDetail` interface:

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
}
```

- [ ] **Step 2: Add `available_finishes` to `MOCK_CARD_DETAIL`**

In `src/frontend/src/mocks/data.ts`, update the `'ragavan-mh2'` entry (and any other entries) to include `available_finishes`. Since `CardPrint` has a `set_code` field that doesn't exist in its type definition — use the existing `prints` data as a guide and add the new field:

```typescript
export const MOCK_CARD_DETAIL: Record<string, CardDetail> = {
  'ragavan-mh2': {
    ...MOCK_CARDS[0],
    available_finishes: ['nonfoil', 'foil', 'etched'],
    mana_cost: '{R}',
    type_line: 'Legendary Creature — Monkey Pirate',
    oracle_text: "Whenever Ragavan, Nimble Pilferer deals combat damage to a player, create a Treasure token and exile the top card of that player's library. Until end of turn, you may cast that card.\nDash {R}",
    artist: 'Simon Dominic',
    price_history: makeSpark(50, 84.5, 365),
    prints: [
      { id: 'ragavan-mh2-foil',   set: 'MH2', set_name: 'Modern Horizons 2', finish: 'foil',     price: 110.0, image_uri: null },
      { id: 'ragavan-mh2-etched', set: 'MH2', set_name: 'Modern Horizons 2', finish: 'etched',   price: 95.0,  image_uri: null },
      { id: 'ragavan-mh2-retro',  set: 'MH2', set_name: 'Modern Horizons 2', finish: 'non-foil', price: 88.0,  image_uri: null },
    ],
  },
}
```

- [ ] **Step 3: Check TypeScript compiles cleanly**

```bash
cd src/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/features/cards/types.ts \
        src/frontend/src/mocks/data.ts
git commit -m "feat(frontend): add available_finishes to CardDetail type and mock data"
```

---

## Task 4: Frontend — `PriceCharts` accepts `finish` prop

**Files:**
- Modify: `src/frontend/src/features/cards/components/PriceCharts.tsx`
- Create: `src/frontend/src/features/cards/components/__tests__/PriceCharts.test.tsx`

- [ ] **Step 1: Write failing test**

```typescript
// src/frontend/src/features/cards/components/__tests__/PriceCharts.test.tsx
import { describe, it, expect } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '../../../../mocks/server'
import { PriceCharts } from '../PriceCharts'
import type { CardDetail } from '../../types'

const mockCard: CardDetail = {
  card_version_id: '11111111-1111-1111-1111-111111111111',
  card_name: 'Sheoldred',
  set_code: 'mom',
  set_name: 'March of the Machine',
  finish: 'non-foil',
  rarity_name: 'rare',
  price_change_1d: 0,
  price_change_7d: 0,
  price_change_30d: 0,
  image_uri: null,
  spark: [],
  available_finishes: ['nonfoil', 'foil'],
}

const Wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider
    client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
  >
    {children}
  </QueryClientProvider>
)

describe('PriceCharts', () => {
  it('sends finish query param when finish prop is provided', async () => {
    let capturedFinish: string | null = null

    server.use(
      http.get('/api/catalog/mtg/card-reference/:id/price-history', ({ request }) => {
        capturedFinish = new URL(request.url).searchParams.get('finish')
        return HttpResponse.json({
          data: { price_history_list_avg: [], price_history_sold_avg: [] },
        })
      })
    )

    render(<PriceCharts card={mockCard} finish="foil" />, { wrapper: Wrapper })

    await waitFor(() => expect(capturedFinish).toBe('foil'))
  })

  it('omits finish query param when no finish prop is provided', async () => {
    let capturedFinish: string | null = 'sentinel'

    server.use(
      http.get('/api/catalog/mtg/card-reference/:id/price-history', ({ request }) => {
        capturedFinish = new URL(request.url).searchParams.get('finish')
        return HttpResponse.json({
          data: { price_history_list_avg: [], price_history_sold_avg: [] },
        })
      })
    )

    render(<PriceCharts card={mockCard} />, { wrapper: Wrapper })

    await waitFor(() => expect(capturedFinish).toBeNull())
  })
})
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd src/frontend && npx vitest run --reporter=verbose src/features/cards/components/__tests__/PriceCharts.test.tsx
```

Expected: TypeScript error — `PriceCharts` doesn't accept `finish` prop yet.

- [ ] **Step 3: Add `finish` prop to `PriceCharts`**

Replace the `PriceChartsProps` interface and the `useQuery` call in `PriceCharts.tsx`:

```typescript
interface PriceChartsProps {
  card: CardDetail
  finish?: string
}

export function PriceCharts({ card, finish }: PriceChartsProps) {
  const [selectedRange, setSelectedRange] = useState<'1w' | '1m' | '3m' | '1y' | 'all'>('all')

  const { data: priceData, isLoading } = useQuery(
    cardPriceHistoryQueryOptions(card.card_version_id, selectedRange, finish)
  )
  // ... rest of function body unchanged
```

- [ ] **Step 4: Run test — expect pass**

```bash
cd src/frontend && npx vitest run --reporter=verbose src/features/cards/components/__tests__/PriceCharts.test.tsx
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/cards/components/PriceCharts.tsx \
        src/frontend/src/features/cards/components/__tests__/PriceCharts.test.tsx
git commit -m "feat(frontend): PriceCharts accepts finish prop and forwards to price-history query"
```

---

## Task 5: Frontend — `CardDetailView` finish chip row

**Files:**
- Modify: `src/frontend/src/features/cards/components/CardDetailView.tsx`
- Create: `src/frontend/src/features/cards/components/__tests__/CardDetailView.test.tsx`

- [ ] **Step 1: Write failing tests**

```typescript
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
vi.mock('../../../../components/design-system/CardArt', () => ({
  CardArt: () => <div />,
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
})
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd src/frontend && npx vitest run --reporter=verbose src/features/cards/components/__tests__/CardDetailView.test.tsx
```

Expected: tests fail — hardcoded "Non-foil" chip doesn't match `available_finishes`.

- [ ] **Step 3: Update `CardDetailView`**

Replace the existing `printChips` section and add `selectedFinish` state. Full updated component:

```typescript
// src/frontend/src/features/cards/components/CardDetailView.tsx
import { useState } from 'react'
import { CardArt } from '../../../components/design-system/CardArt'
import { AreaChart } from '../../../components/design-system/AreaChart'
import { Pip, type ManaColor } from '../../../components/design-system/Pip'
import { Chip } from '../../../components/ui/Chip'
import { Button } from '../../../components/ui/Button'
import { PriceCharts } from './PriceCharts'
import type { CardDetail } from '../types'
import styles from './CardDetailView.module.css'

interface CardDetailViewProps {
  card: CardDetail
}

const RANGE_LABELS = ['1W', '1M', '3M', '1Y', 'ALL']

function parseMana(cost: string): ManaColor[] {
  return (cost.match(/[WUBRG]/g) ?? []) as ManaColor[]
}

export function CardDetailView({ card }: CardDetailViewProps) {
  const finishes = card.available_finishes?.length ? card.available_finishes : ['nonfoil']
  const [selectedFinish, setSelectedFinish] = useState(finishes[0])

  const delta1d = card.price_change_1d
  const delta7d = card.price_change_7d
  const delta30d = card.price_change_30d

  return (
    <div className={styles.layout}>
      <div className={styles.artCol}>
        <CardArt
          name={card.card_name}
          w={420}
          h={585}
          hue={20}
          label={false}
          imageUrl={card.image_large}
          style={{ borderRadius: 16 }}
        />
        <div className={styles.printChips}>
          {finishes.map((f) => (
            <button
              key={f}
              onClick={() => setSelectedFinish(f)}
              style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
            >
              <Chip
                color={f === selectedFinish ? 'var(--hd-accent)' : undefined}
                style={f === selectedFinish ? { border: '1px solid var(--hd-accent)' } : {}}
              >
                {f === selectedFinish ? '● ' : ''}{f}
              </Chip>
            </button>
          ))}
        </div>
      </div>

      <div className={styles.rightCol}>
        <div className={styles.infoCol}>
          <div className={styles.meta}>
            {card.set_code.toUpperCase()} · {card.rarity_name?.charAt(0).toUpperCase() + card.rarity_name?.slice(1)} · {card.type_line}
          </div>
          <h1 className={styles.name}>{card.card_name}</h1>

          {card.mana_cost && (
            <div className={styles.manaRow}>
              {parseMana(card.mana_cost).map((c, i) => <Pip key={i} color={c} size={18} />)}
              <span className={styles.manaCost}>{card.mana_cost}</span>
              <span className={styles.artist}>by {card.artist}</span>
            </div>
          )}

          <div className={styles.priceSection}>
            <div className={styles.priceLabel}>Market price</div>
            <div className={styles.priceRow}>
              <div className={styles.price}>
                {card.price != null ? (
                  <>
                    ${Math.floor(card.price)}<span className={styles.priceCents}>.{(card.price % 1).toFixed(2).slice(2)}</span>
                  </>
                ) : (
                  'N/A'
                )}
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

          {card.price_history && card.price_history.length > 0 ? (
            <div className={styles.chartSection}>
              <div className={styles.chartHeader}>
                <span className={styles.chartLabel}>Price · 1y</span>
                <div className={styles.rangeButtons}>
                  {RANGE_LABELS.map((r, i) => (
                    <button key={r} className={[styles.rangeBtn, i === 3 ? styles.rangeActive : ''].join(' ')}>{r}</button>
                  ))}
                </div>
              </div>
              <AreaChart
                points={card.price_history.slice(-365)}
                color="var(--hd-accent)"
                height={220}
                gridColor="rgba(150,200,255,0.05)"
              />
            </div>
          ) : null}

          <div className={styles.actions}>
            <Button variant="accent" style={{ flex: 1 }}>+ Add to collection</Button>
            <Button variant="ghost">Watch</Button>
            <Button variant="ghost">Set alert</Button>
          </div>
        </div>
        <PriceCharts card={card} finish={selectedFinish} />
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd src/frontend && npx vitest run --reporter=verbose src/features/cards/components/__tests__/CardDetailView.test.tsx
```

Expected: `5 passed`.

- [ ] **Step 5: Run full frontend test suite to check for regressions**

```bash
cd src/frontend && npm test
```

Expected: all tests pass (or pre-existing skipped tests remain skipped).

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/cards/components/CardDetailView.tsx \
        src/frontend/src/features/cards/components/__tests__/CardDetailView.test.tsx
git commit -m "feat(frontend): finish selector chips on card detail page"
```

---

## Task 6: Smoke test end-to-end

Prerequisites: dev database is running and the Scryfall pipeline has populated `card_version_finish`.

- [ ] **Step 1: Confirm `card_version_finish` has data**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -c "SELECT cf.code, COUNT(*) FROM card_catalog.card_version_finish cvf JOIN card_catalog.card_finished cf ON cf.finish_id = cvf.finish_id GROUP BY cf.code ORDER BY COUNT(*) DESC;"
```

Expected: rows for `NONFOIL`, `FOIL`, `ETCHED`, etc. If the table is empty, run the Scryfall pipeline first (see CLAUDE.md rebuild sequence) before continuing.

- [ ] **Step 2: Hit the card detail endpoint manually**

Pick any `card_version_id` from the DB:

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -c "SELECT cv.card_version_id FROM card_catalog.card_version cv LIMIT 1;"
```

Then fetch via the API (replace `<UUID>`):

```bash
curl -s http://localhost:8000/api/catalog/mtg/card-reference/<UUID> | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('available_finishes', 'MISSING'))"
```

Expected: a list like `['nonfoil', 'foil']`.

- [ ] **Step 3: Open the card detail page in the browser**

Navigate to `http://localhost:5173/cards/<UUID>`. Verify:
- Finish chips appear under the card art
- Each chip matches the finishes returned by the API
- Clicking a chip highlights it and the price chart re-fetches for that finish (watch network tab for `?finish=foil`)
