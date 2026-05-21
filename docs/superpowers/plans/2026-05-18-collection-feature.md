# Collection Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the fully-built backend collection API to the frontend, adding a card grid view, hover-to-add from search, and multi-collection management — replacing all mock data in `/collection`.

**Architecture:** Backend gains image + price enrichment via two LEFT JOINs on `get_all_entries`. Frontend gains a new `api.ts` layer, a `CollectionGrid` component, an `AddToCollectionPopover` on search cards, and a wired-up `/collection` route that replaces `MOCK_COLLECTION` with real React Query data.

**Tech Stack:** FastAPI + asyncpg (backend), React 18 + TanStack Query v5 + CSS Modules + Vitest/RTL (frontend)

---

## File Map

| Action | Path |
|--------|------|
| Modify | `src/automana/core/repositories/card_catalog/collection_repository.py` |
| Modify | `src/automana/core/models/collections/collection.py` |
| Create | `src/frontend/src/features/collection/api.ts` |
| Create | `src/frontend/src/features/collection/components/CollectionGrid.tsx` |
| Create | `src/frontend/src/features/collection/components/CollectionGrid.module.css` |
| Create | `src/frontend/src/features/collection/components/__tests__/CollectionGrid.test.tsx` |
| Create | `src/frontend/src/features/collection/components/AddToCollectionPopover.tsx` |
| Create | `src/frontend/src/features/collection/components/AddToCollectionPopover.module.css` |
| Create | `src/frontend/src/features/collection/components/__tests__/AddToCollectionPopover.test.tsx` |
| Modify | `src/frontend/src/features/cards/components/SearchResults.tsx` |
| Modify | `src/frontend/src/features/cards/components/SearchResults.module.css` |
| Modify | `src/frontend/src/features/collection/components/CollectionTable.tsx` |
| Modify | `src/frontend/src/features/collection/components/__tests__/CollectionTable.test.tsx` |
| Modify | `src/frontend/src/routes/collection.tsx` |
| Modify | `src/frontend/src/routes/Collection.module.css` |

---

## Task 1: Backend — Enrich `get_all_entries` with image + price

**Files:**
- Modify: `src/automana/core/repositories/card_catalog/collection_repository.py` (lines 136–161)
- Modify: `src/automana/core/models/collections/collection.py`

- [ ] **Step 1.1: Update the `get_all_entries` query**

  In `collection_repository.py`, replace the `get_all_entries` method body (lines 136–161):

  ```python
  async def get_all_entries(self, collection_id: UUID, user_id: UUID) -> List[dict]:
      query = """
          SELECT ci.item_id,
                 ci.collection_id,
                 ci.unique_card_id AS card_version_id,
                 uc.card_name,
                 s.set_code,
                 cv.collector_number,
                 ci.finish_id,
                 cf.code AS finish,
                 ci.condition,
                 ci.purchase_price,
                 ci.currency_code,
                 ci.purchase_date,
                 ci.language_id,
                 cvi.image_uris->>'normal'  AS image_normal,
                 ps.price                    AS price,
                 ps.price_change_1d          AS price_change_1d
          FROM user_collection.collection_items ci
          JOIN user_collection.collections col
              ON col.collection_id = ci.collection_id AND col.user_id = $2
          JOIN card_catalog.card_version cv ON cv.card_version_id = ci.unique_card_id
          JOIN card_catalog.unique_cards_ref uc ON uc.unique_card_id = cv.unique_card_id
          JOIN card_catalog.sets s ON s.set_id = cv.set_id
          JOIN card_catalog.card_finished cf ON cf.finish_id = ci.finish_id
          LEFT JOIN card_catalog.card_version_illustration cvi
              ON cvi.card_version_id = cv.card_version_id
          LEFT JOIN pricing.mv_card_price_spark ps
              ON ps.card_version_id = ci.unique_card_id
          WHERE ci.collection_id = $1;
      """
      rows = await self.execute_query(query, (collection_id, user_id))
      return [dict(r) for r in rows]
  ```

- [ ] **Step 1.2: Add three fields to `PublicCollectionEntry`**

  In `src/automana/core/models/collections/collection.py`, append to `PublicCollectionEntry`:

  ```python
  class PublicCollectionEntry(BaseModel):
      item_id: UUID
      card_version_id: UUID
      card_name: str
      set_code: str
      collector_number: str
      finish: Finish
      purchase_date: date
      purchase_price: Decimal
      condition: Conditions
      currency_code: str
      language_id: Optional[int] = None
      image_normal: Optional[str] = None
      price: Optional[float] = None
      price_change_1d: float = 0.0
  ```

- [ ] **Step 1.3: Verify the endpoint returns the new fields**

  ```bash
  # 1. Create a user + get token (see docs/TESTING_API_FLOW.md)
  # 2. Create a collection:
  curl -s -X POST http://localhost:8000/api/catalog/mtg/collection/ \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"collection_name":"Test","description":""}' | python3 -m json.tool

  # 3. Add a card (use a real card_version_id from /api/catalog/mtg/cards/):
  curl -s -X POST http://localhost:8000/api/catalog/mtg/collection/$COLLECTION_ID/entries \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"card_version_id":"<uuid>","condition":"NM","finish":"NONFOIL","purchase_price":"5.00"}' \
    | python3 -m json.tool

  # 4. List entries — confirm image_normal and price appear:
  curl -s http://localhost:8000/api/catalog/mtg/collection/$COLLECTION_ID/entries \
    -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
  ```

  Expected: JSON entries include `"image_normal": "https://cards.scryfall.io/..."` and `"price": <float>`.

- [ ] **Step 1.4: Commit**

  ```bash
  git add src/automana/core/repositories/card_catalog/collection_repository.py \
          src/automana/core/models/collections/collection.py
  git commit -m "feat(collection): enrich get_all_entries with image_normal and price fields"
  ```

---

## Task 2: Frontend — Create collection API layer

**Files:**
- Create: `src/frontend/src/features/collection/api.ts`

- [ ] **Step 2.1: Create `features/collection/api.ts`**

  ```typescript
  // src/frontend/src/features/collection/api.ts
  import { queryOptions } from '@tanstack/react-query'
  import { apiClient } from '../../lib/apiClient'

  export interface Collection {
    collection_id: string
    collection_name: string
    description: string
    is_active: boolean
    created_at: string
    username: string
  }

  export interface CollectionEntry {
    item_id: string
    card_version_id: string
    card_name: string
    set_code: string
    collector_number: string
    finish: 'NONFOIL' | 'FOIL' | 'ETCHED'
    condition: 'NM' | 'LP' | 'MP' | 'HP' | 'DMG' | 'SP'
    purchase_price: number
    purchase_date: string
    currency_code: string
    language_id?: number | null
    image_normal?: string | null
    price?: number | null
    price_change_1d: number
  }

  // ── Query options ────────────────────────────────────────────────────────────

  export function collectionsQueryOptions() {
    return queryOptions({
      queryKey: ['collection', 'list'] as const,
      queryFn: () =>
        apiClient<Collection[]>('/catalog/mtg/collection/'),
      staleTime: 5 * 60_000,
      gcTime: 15 * 60_000,
    })
  }

  export function collectionEntriesQueryOptions(collectionId: string) {
    return queryOptions({
      queryKey: ['collection', 'entries', collectionId] as const,
      queryFn: () =>
        apiClient<CollectionEntry[]>(`/catalog/mtg/collection/${collectionId}/entries`),
      staleTime: 60_000,
      gcTime: 10 * 60_000,
      enabled: Boolean(collectionId),
    })
  }

  // ── Mutations ────────────────────────────────────────────────────────────────

  export async function createCollection(name: string): Promise<Collection> {
    return apiClient<Collection>('/catalog/mtg/collection/', {
      method: 'POST',
      body: JSON.stringify({ collection_name: name, description: '' }),
    })
  }

  export async function addCollectionEntry(
    collectionId: string,
    cardVersionId: string,
    condition: CollectionEntry['condition'],
    finish: CollectionEntry['finish'],
  ): Promise<CollectionEntry> {
    return apiClient<CollectionEntry>(
      `/catalog/mtg/collection/${collectionId}/entries`,
      {
        method: 'POST',
        body: JSON.stringify({
          card_version_id: cardVersionId,
          condition,
          finish,
          purchase_price: '0.00',
        }),
      },
    )
  }

  export async function deleteCollectionEntry(
    collectionId: string,
    entryId: string,
  ): Promise<void> {
    await apiClient<void>(
      `/catalog/mtg/collection/${collectionId}/entries/${entryId}`,
      { method: 'DELETE' },
    )
  }
  ```

- [ ] **Step 2.2: TypeScript check**

  ```bash
  cd src/frontend && npx tsc --noEmit
  ```

  Expected: no errors related to `features/collection/api.ts`.

- [ ] **Step 2.3: Commit**

  ```bash
  git add src/frontend/src/features/collection/api.ts
  git commit -m "feat(collection): add frontend API layer — queryOptions + mutations"
  ```

---

## Task 3: CollectionGrid component

**Files:**
- Create: `src/frontend/src/features/collection/components/CollectionGrid.module.css`
- Create: `src/frontend/src/features/collection/components/CollectionGrid.tsx`
- Create: `src/frontend/src/features/collection/components/__tests__/CollectionGrid.test.tsx`

- [ ] **Step 3.1: Write the failing test**

  ```typescript
  // src/frontend/src/features/collection/components/__tests__/CollectionGrid.test.tsx
  import { render, screen, fireEvent } from '@testing-library/react'
  import { describe, it, expect, vi } from 'vitest'
  import { CollectionGrid } from '../CollectionGrid'
  import type { CollectionEntry } from '../../api'

  const ENTRIES: CollectionEntry[] = [
    {
      item_id: 'e1',
      card_version_id: 'cv1',
      card_name: 'Ragavan, Nimble Pilferer',
      set_code: 'MH2',
      collector_number: '138',
      finish: 'NONFOIL',
      condition: 'NM',
      purchase_price: 28,
      purchase_date: '2024-01-01',
      currency_code: 'USD',
      image_normal: null,
      price: 54.20,
      price_change_1d: 1.5,
    },
    {
      item_id: 'e2',
      card_version_id: 'cv2',
      card_name: 'Force of Will',
      set_code: 'ALL',
      collector_number: '28',
      finish: 'FOIL',
      condition: 'LP',
      purchase_price: 120,
      purchase_date: '2024-01-02',
      currency_code: 'USD',
      image_normal: null,
      price: 110,
      price_change_1d: -0.5,
    },
  ]

  describe('CollectionGrid', () => {
    it('renders a card for each entry', () => {
      render(<CollectionGrid entries={ENTRIES} onRemove={vi.fn()} />)
      expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeTruthy()
      expect(screen.getByText('Force of Will')).toBeTruthy()
    })

    it('shows set code and condition', () => {
      render(<CollectionGrid entries={[ENTRIES[0]]} onRemove={vi.fn()} />)
      expect(screen.getByText('MH2')).toBeTruthy()
      expect(screen.getByText('NM')).toBeTruthy()
    })

    it('shows market price', () => {
      render(<CollectionGrid entries={[ENTRIES[0]]} onRemove={vi.fn()} />)
      expect(screen.getByText('$54.20')).toBeTruthy()
    })

    it('shows P&L in green when profit', () => {
      render(<CollectionGrid entries={[ENTRIES[0]]} onRemove={vi.fn()} />)
      // profit: 54.20 - 28.00 = +$26.20
      expect(screen.getByText('+$26.20')).toBeTruthy()
    })

    it('shows P&L in red when loss', () => {
      render(<CollectionGrid entries={[ENTRIES[1]]} onRemove={vi.fn()} />)
      // loss: 110 - 120 = -$10.00
      expect(screen.getByText('-$10.00')).toBeTruthy()
    })

    it('calls onRemove with item_id when remove button clicked', () => {
      const onRemove = vi.fn()
      render(<CollectionGrid entries={[ENTRIES[0]]} onRemove={onRemove} />)
      fireEvent.click(screen.getByRole('button', { name: /remove ragavan/i }))
      expect(onRemove).toHaveBeenCalledWith('e1')
    })

    it('shows empty state when no entries', () => {
      render(<CollectionGrid entries={[]} onRemove={vi.fn()} />)
      expect(screen.getByText(/no cards yet/i)).toBeTruthy()
    })
  })
  ```

- [ ] **Step 3.2: Run test to verify it fails**

  ```bash
  cd src/frontend && npm run test -- --run features/collection/components/__tests__/CollectionGrid
  ```

  Expected: FAIL — `CollectionGrid` is not defined.

- [ ] **Step 3.3: Create `CollectionGrid.module.css`**

  ```css
  /* src/frontend/src/features/collection/components/CollectionGrid.module.css */
  .grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 14px;
    padding: 0;
  }
  @media (min-width: 980px)  { .grid { grid-template-columns: repeat(3, 1fr); } }
  @media (min-width: 1460px) { .grid { grid-template-columns: repeat(4, 1fr); } }
  @media (min-width: 1700px) { .grid { grid-template-columns: repeat(5, 1fr); } }

  .cardWrap {
    position: relative;
    display: flex;
    flex-direction: column;
  }
  .cardWrap:hover .removeBtn { opacity: 1; }

  .removeBtn {
    position: absolute;
    top: 6px;
    right: 6px;
    z-index: 10;
    background: rgba(0, 0, 0, 0.72);
    border: 1px solid rgba(255, 100, 100, 0.3);
    border-radius: 50%;
    width: 22px;
    height: 22px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #f87171;
    font-size: 12px;
    cursor: pointer;
    opacity: 0;
    transition: opacity 150ms ease;
    backdrop-filter: blur(4px);
    padding: 0;
  }
  .removeBtn:hover { background: rgba(200, 50, 50, 0.72); }

  .cardInfo { padding: 6px 4px; }

  .cardName {
    font-size: 12px;
    font-weight: 500;
    color: var(--hd-text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-bottom: 3px;
  }

  .badges {
    display: flex;
    gap: 4px;
    margin-bottom: 4px;
    flex-wrap: wrap;
  }

  .badge {
    font-size: 9px;
    font-family: var(--font-mono);
    font-weight: 700;
    padding: 1px 5px;
    border-radius: 3px;
    background: var(--hd-surface-2, #1f2937);
    color: var(--hd-sub);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .badgeFoil { color: #818cf8; }
  .badgeEtched { color: #f59e0b; }

  .priceRow {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 2px;
  }

  .price {
    font-size: 12px;
    font-weight: 600;
    font-family: var(--font-mono);
    color: var(--hd-text);
  }

  .pl {
    font-size: 11px;
    font-family: var(--font-mono);
    font-weight: 600;
  }
  .plUp { color: var(--hd-accent); }
  .plDown { color: var(--hd-red); }

  .empty {
    padding: 40px;
    text-align: center;
    color: var(--hd-muted);
    font-size: 14px;
    grid-column: 1 / -1;
  }
  ```

- [ ] **Step 3.4: Create `CollectionGrid.tsx`**

  ```typescript
  // src/frontend/src/features/collection/components/CollectionGrid.tsx
  import { CardArt } from '../../../components/design-system/CardArt'
  import type { CollectionEntry } from '../api'
  import styles from './CollectionGrid.module.css'

  interface CollectionGridProps {
    entries: CollectionEntry[]
    onRemove: (itemId: string) => void
  }

  function finishBadgeClass(finish: CollectionEntry['finish']): string {
    if (finish === 'FOIL') return `${styles.badge} ${styles.badgeFoil}`
    if (finish === 'ETCHED') return `${styles.badge} ${styles.badgeEtched}`
    return styles.badge
  }

  export function CollectionGrid({ entries, onRemove }: CollectionGridProps) {
    if (entries.length === 0) {
      return (
        <div className={styles.grid}>
          <p className={styles.empty}>
            No cards yet — search for cards and hit + Add to start
          </p>
        </div>
      )
    }

    return (
      <div className={styles.grid}>
        {entries.map((entry, i) => {
          const pl =
            entry.price != null
              ? entry.price - Number(entry.purchase_price)
              : null
          const plSign = pl != null && pl >= 0 ? '+' : ''

          return (
            <div key={entry.item_id} className={styles.cardWrap}>
              <button
                className={styles.removeBtn}
                onClick={() => onRemove(entry.item_id)}
                aria-label={`Remove ${entry.card_name}`}
              >
                ×
              </button>
              <CardArt
                name={entry.card_name}
                w="100%"
                hue={(i * 47) % 360}
                label={false}
                imageUrl={entry.image_normal ?? undefined}
                finish={entry.finish.toLowerCase() as 'non-foil' | 'foil' | 'etched'}
              />
              <div className={styles.cardInfo}>
                <div className={styles.cardName}>{entry.card_name}</div>
                <div className={styles.badges}>
                  <span className={styles.badge}>{entry.set_code.toUpperCase()}</span>
                  <span className={styles.badge}>{entry.condition}</span>
                  {entry.finish !== 'NONFOIL' && (
                    <span className={finishBadgeClass(entry.finish)}>
                      {entry.finish.toLowerCase()}
                    </span>
                  )}
                </div>
                <div className={styles.priceRow}>
                  <span className={styles.price}>
                    {entry.price != null ? `$${entry.price.toFixed(2)}` : 'N/A'}
                  </span>
                  {pl != null && (
                    <span className={`${styles.pl} ${pl >= 0 ? styles.plUp : styles.plDown}`}>
                      {plSign}${Math.abs(pl).toFixed(2)}
                    </span>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    )
  }
  ```

- [ ] **Step 3.5: Run the test to verify it passes**

  ```bash
  cd src/frontend && npm run test -- --run features/collection/components/__tests__/CollectionGrid
  ```

  Expected: all 7 tests pass.

- [ ] **Step 3.6: Commit**

  ```bash
  git add src/frontend/src/features/collection/components/CollectionGrid.tsx \
          src/frontend/src/features/collection/components/CollectionGrid.module.css \
          src/frontend/src/features/collection/components/__tests__/CollectionGrid.test.tsx
  git commit -m "feat(collection): add CollectionGrid component with P&L and remove action"
  ```

---

## Task 4: AddToCollectionPopover component

**Files:**
- Create: `src/frontend/src/features/collection/components/AddToCollectionPopover.module.css`
- Create: `src/frontend/src/features/collection/components/AddToCollectionPopover.tsx`
- Create: `src/frontend/src/features/collection/components/__tests__/AddToCollectionPopover.test.tsx`

- [ ] **Step 4.1: Write the failing test**

  ```typescript
  // src/frontend/src/features/collection/components/__tests__/AddToCollectionPopover.test.tsx
  import { render, screen, fireEvent } from '@testing-library/react'
  import { describe, it, expect, vi } from 'vitest'
  import { AddToCollectionPopover } from '../AddToCollectionPopover'
  import type { Collection } from '../../api'

  const COLLECTIONS: Collection[] = [
    {
      collection_id: 'col1',
      collection_name: 'My Collection',
      description: '',
      is_active: true,
      created_at: '2024-01-01T00:00:00',
      username: 'testuser',
    },
    {
      collection_id: 'col2',
      collection_name: 'Trade Binder',
      description: '',
      is_active: true,
      created_at: '2024-01-01T00:00:00',
      username: 'testuser',
    },
  ]

  describe('AddToCollectionPopover', () => {
    it('renders condition pills', () => {
      render(
        <AddToCollectionPopover
          cardVersionId="cv1"
          cardName="Ragavan"
          finish="non-foil"
          collections={COLLECTIONS}
          onAdd={vi.fn()}
          onClose={vi.fn()}
        />
      )
      expect(screen.getByRole('button', { name: 'NM' })).toBeTruthy()
      expect(screen.getByRole('button', { name: 'LP' })).toBeTruthy()
      expect(screen.getByRole('button', { name: 'MP' })).toBeTruthy()
      expect(screen.getByRole('button', { name: 'HP' })).toBeTruthy()
    })

    it('shows finish as read-only label', () => {
      render(
        <AddToCollectionPopover
          cardVersionId="cv1"
          cardName="Ragavan"
          finish="foil"
          collections={COLLECTIONS}
          onAdd={vi.fn()}
          onClose={vi.fn()}
        />
      )
      expect(screen.getByText('foil')).toBeTruthy()
    })

    it('shows collection options in select', () => {
      render(
        <AddToCollectionPopover
          cardVersionId="cv1"
          cardName="Ragavan"
          finish="non-foil"
          collections={COLLECTIONS}
          onAdd={vi.fn()}
          onClose={vi.fn()}
        />
      )
      expect(screen.getByRole('option', { name: 'My Collection' })).toBeTruthy()
      expect(screen.getByRole('option', { name: 'Trade Binder' })).toBeTruthy()
    })

    it('calls onAdd with selected values on submit', () => {
      const onAdd = vi.fn()
      render(
        <AddToCollectionPopover
          cardVersionId="cv1"
          cardName="Ragavan"
          finish="non-foil"
          collections={COLLECTIONS}
          onAdd={onAdd}
          onClose={vi.fn()}
        />
      )
      fireEvent.click(screen.getByRole('button', { name: 'LP' }))
      fireEvent.click(screen.getByRole('button', { name: /add to collection/i }))
      expect(onAdd).toHaveBeenCalledWith({
        collectionId: 'col1',
        condition: 'LP',
        finish: 'NONFOIL',
      })
    })

    it('calls onClose when cancel is clicked', () => {
      const onClose = vi.fn()
      render(
        <AddToCollectionPopover
          cardVersionId="cv1"
          cardName="Ragavan"
          finish="non-foil"
          collections={COLLECTIONS}
          onAdd={onAdd}
          onClose={onClose}
        />
      )
      fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
      expect(onClose).toHaveBeenCalled()
    })
  })
  ```

  Note: `onAdd` in the last test should be `vi.fn()`. Fix the reference:

  ```typescript
  it('calls onClose when cancel is clicked', () => {
    const onClose = vi.fn()
    render(
      <AddToCollectionPopover
        cardVersionId="cv1"
        cardName="Ragavan"
        finish="non-foil"
        collections={COLLECTIONS}
        onAdd={vi.fn()}
        onClose={onClose}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onClose).toHaveBeenCalled()
  })
  ```

- [ ] **Step 4.2: Run test to verify it fails**

  ```bash
  cd src/frontend && npm run test -- --run features/collection/components/__tests__/AddToCollectionPopover
  ```

  Expected: FAIL — `AddToCollectionPopover` is not defined.

- [ ] **Step 4.3: Create `AddToCollectionPopover.module.css`**

  ```css
  /* src/frontend/src/features/collection/components/AddToCollectionPopover.module.css */
  .popover {
    position: absolute;
    bottom: calc(100% + 8px);
    left: 50%;
    transform: translateX(-50%);
    z-index: 100;
    background: var(--hd-surface, #111827);
    border: 1px solid var(--hd-border, #1f2937);
    border-radius: 8px;
    padding: 12px;
    width: 200px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6);
  }

  .header {
    font-size: 11px;
    font-weight: 600;
    color: var(--hd-text);
    margin-bottom: 10px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .label {
    font-size: 10px;
    font-family: var(--font-mono);
    color: var(--hd-sub);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 5px;
  }

  .pills {
    display: flex;
    gap: 4px;
    margin-bottom: 10px;
    flex-wrap: wrap;
  }

  .pill {
    padding: 3px 8px;
    border-radius: 4px;
    border: 1px solid var(--hd-border, #1f2937);
    background: transparent;
    color: var(--hd-sub);
    font-size: 10px;
    font-family: var(--font-mono);
    font-weight: 600;
    cursor: pointer;
    transition: all 120ms ease;
  }
  .pill:hover { border-color: var(--hd-accent); color: var(--hd-accent); }
  .pillActive {
    background: var(--hd-accent);
    border-color: var(--hd-accent);
    color: #fff;
  }

  .finishLabel {
    font-size: 10px;
    font-family: var(--font-mono);
    color: var(--hd-text);
    background: var(--hd-surface-2, #1f2937);
    border-radius: 4px;
    padding: 3px 8px;
    margin-bottom: 10px;
    display: inline-block;
    text-transform: lowercase;
  }

  .select {
    width: 100%;
    background: var(--hd-surface-2, #1f2937);
    border: 1px solid var(--hd-border, #2d3748);
    border-radius: 4px;
    color: var(--hd-text);
    font-size: 11px;
    padding: 5px 8px;
    margin-bottom: 10px;
    cursor: pointer;
  }

  .actions {
    display: flex;
    gap: 6px;
  }

  .btnCancel {
    flex: 1;
    padding: 5px;
    border-radius: 4px;
    border: 1px solid var(--hd-border, #1f2937);
    background: transparent;
    color: var(--hd-sub);
    font-size: 11px;
    cursor: pointer;
  }
  .btnCancel:hover { background: var(--hd-surface-2, #1f2937); }

  .btnAdd {
    flex: 2;
    padding: 5px;
    border-radius: 4px;
    border: none;
    background: var(--hd-accent);
    color: #fff;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
  }
  .btnAdd:hover { opacity: 0.9; }
  .btnAdd:disabled { opacity: 0.5; cursor: not-allowed; }
  ```

- [ ] **Step 4.4: Create `AddToCollectionPopover.tsx`**

  ```typescript
  // src/frontend/src/features/collection/components/AddToCollectionPopover.tsx
  import { useEffect, useRef, useState } from 'react'
  import type { Collection } from '../api'
  import styles from './AddToCollectionPopover.module.css'

  type Condition = 'NM' | 'LP' | 'MP' | 'HP'
  type FinishOut = 'NONFOIL' | 'FOIL' | 'ETCHED'

  function normaliseFinish(finish: string): FinishOut {
    const f = finish.toLowerCase()
    if (f === 'foil') return 'FOIL'
    if (f === 'etched') return 'ETCHED'
    return 'NONFOIL'
  }

  interface Props {
    cardVersionId: string
    cardName: string
    finish: string
    collections: Collection[]
    onAdd: (params: { collectionId: string; condition: Condition; finish: FinishOut }) => void
    onClose: () => void
  }

  const CONDITIONS: Condition[] = ['NM', 'LP', 'MP', 'HP']

  export function AddToCollectionPopover({
    cardName,
    finish,
    collections,
    onAdd,
    onClose,
  }: Props) {
    const [condition, setCondition] = useState<Condition>('NM')
    const [collectionId, setCollectionId] = useState(collections[0]?.collection_id ?? '')
    const ref = useRef<HTMLDivElement>(null)

    useEffect(() => {
      function handleClick(e: MouseEvent) {
        if (ref.current && !ref.current.contains(e.target as Node)) onClose()
      }
      function handleKey(e: KeyboardEvent) {
        if (e.key === 'Escape') onClose()
      }
      document.addEventListener('mousedown', handleClick)
      document.addEventListener('keydown', handleKey)
      return () => {
        document.removeEventListener('mousedown', handleClick)
        document.removeEventListener('keydown', handleKey)
      }
    }, [onClose])

    return (
      <div ref={ref} className={styles.popover} role="dialog" aria-label={`Add ${cardName} to collection`}>
        <div className={styles.header}>{cardName}</div>

        <div className={styles.label}>Condition</div>
        <div className={styles.pills}>
          {CONDITIONS.map((c) => (
            <button
              key={c}
              className={[styles.pill, condition === c ? styles.pillActive : ''].join(' ')}
              onClick={() => setCondition(c)}
            >
              {c}
            </button>
          ))}
        </div>

        <div className={styles.label}>Finish</div>
        <span className={styles.finishLabel}>{finish}</span>

        {collections.length > 1 && (
          <>
            <div className={styles.label}>Collection</div>
            <select
              className={styles.select}
              value={collectionId}
              onChange={(e) => setCollectionId(e.target.value)}
            >
              {collections.map((col) => (
                <option key={col.collection_id} value={col.collection_id}>
                  {col.collection_name}
                </option>
              ))}
            </select>
          </>
        )}

        <div className={styles.actions}>
          <button className={styles.btnCancel} onClick={onClose}>
            Cancel
          </button>
          <button
            className={styles.btnAdd}
            disabled={!collectionId}
            onClick={() =>
              onAdd({ collectionId, condition, finish: normaliseFinish(finish) })
            }
          >
            Add to Collection
          </button>
        </div>
      </div>
    )
  }
  ```

- [ ] **Step 4.5: Run the test to verify it passes**

  ```bash
  cd src/frontend && npm run test -- --run features/collection/components/__tests__/AddToCollectionPopover
  ```

  Expected: all 5 tests pass.

- [ ] **Step 4.6: Commit**

  ```bash
  git add src/frontend/src/features/collection/components/AddToCollectionPopover.tsx \
          src/frontend/src/features/collection/components/AddToCollectionPopover.module.css \
          src/frontend/src/features/collection/components/__tests__/AddToCollectionPopover.test.tsx
  git commit -m "feat(collection): add AddToCollectionPopover — condition pills + finish label"
  ```

---

## Task 5: SearchResults — hover "+ Add" button

**Files:**
- Modify: `src/frontend/src/features/cards/components/SearchResults.module.css`
- Modify: `src/frontend/src/features/cards/components/SearchResults.tsx`

- [ ] **Step 5.1: Add hover overlay CSS to `SearchResults.module.css`**

  Append to the end of `SearchResults.module.css`:

  ```css
  /* ── Collection add overlay ────────────────────────────────── */
  .cardWrap { position: relative; }
  .cardWrap:hover .addBtn { opacity: 1; }

  .addBtn {
    position: absolute;
    bottom: calc(100% - 38px); /* sits at bottom of CardArt */
    right: 6px;
    background: var(--hd-accent);
    color: #fff;
    border: none;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 10px;
    font-weight: 700;
    font-family: var(--font-mono);
    cursor: pointer;
    opacity: 0;
    transition: opacity 150ms ease;
    z-index: 10;
    white-space: nowrap;
  }
  .addBtn:hover { opacity: 1 !important; }
  ```

- [ ] **Step 5.2: Update `SearchResults.tsx`**

  Replace the full file content. The changes are:
  1. Add `useState` import
  2. Import `AddToCollectionPopover` and related types
  3. Add `collections` prop to `SearchResultsProps`
  4. Wrap card render in a `.cardWrap` div with the add button and popover
  5. Add `handleAdd` to call `addCollectionEntry` and invalidate cache

  Full updated file:

  ```typescript
  // src/frontend/src/features/cards/components/SearchResults.tsx
  import { useEffect, useMemo, useRef, useState } from 'react'
  import { useNavigate } from '@tanstack/react-router'
  import { useQueryClient } from '@tanstack/react-query'
  import { CardArt } from '../../../components/design-system/CardArt'
  import { Sparkline } from '../../../components/design-system/Sparkline'
  import { AddToCollectionPopover } from '../../collection/components/AddToCollectionPopover'
  import {
    addCollectionEntry,
    collectionsQueryOptions,
    collectionEntriesQueryOptions,
  } from '../../collection/api'
  import { useAuthStore } from '../../../store/auth'
  import type { CardGroupBy, CardSummary } from '../types'
  import styles from './SearchResults.module.css'

  interface SearchResultsProps {
    cards: CardSummary[]
    total: number
    fetchNextPage: () => void
    hasNextPage?: boolean
    isFetchingNextPage?: boolean
    onSelect?: (card: CardSummary) => void
    selectedId?: string
    groupBy?: CardGroupBy
  }

  const RARITY_ORDER: Record<string, number> = {
    mythic: 0, rare: 1, uncommon: 2, common: 3,
  }
  const FINISH_ORDER: Record<string, number> = {
    'non-foil': 0, foil: 1, etched: 2,
  }

  interface CardGroup {
    key: string
    label: string
    cards: CardSummary[]
  }

  function buildGroups(cards: CardSummary[], groupBy: CardGroupBy | undefined): CardGroup[] {
    if (!groupBy) return [{ key: '__all__', label: '', cards }]

    const buckets = new Map<string, CardGroup>()
    for (const card of cards) {
      let key: string
      let label: string
      if (groupBy === 'set') {
        key = card.set_code
        label = `${card.set_name} · ${card.set_code.toUpperCase()}`
      } else if (groupBy === 'rarity') {
        key = card.rarity_name
        label = card.rarity_name.charAt(0).toUpperCase() + card.rarity_name.slice(1)
      } else {
        key = card.finish
        label = card.finish
      }
      if (!buckets.has(key)) buckets.set(key, { key, label, cards: [] })
      buckets.get(key)!.cards.push(card)
    }

    const groups = Array.from(buckets.values())
    if (groupBy === 'rarity') {
      groups.sort((a, b) => (RARITY_ORDER[a.key] ?? 99) - (RARITY_ORDER[b.key] ?? 99))
    } else if (groupBy === 'finish') {
      groups.sort((a, b) => (FINISH_ORDER[a.key] ?? 99) - (FINISH_ORDER[b.key] ?? 99))
    }
    return groups
  }

  export function SearchResults({
    cards,
    total,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    onSelect,
    selectedId,
    groupBy,
  }: SearchResultsProps) {
    const navigate = useNavigate()
    const queryClient = useQueryClient()
    const lastCardRef = useRef<HTMLButtonElement>(null)
    const [addTarget, setAddTarget] = useState<CardSummary | null>(null)

    // Only fetch collections when user is authenticated (search page is public)
    const isAuthed = Boolean(useAuthStore.getState().token)
    const { data: collections = [] } = useQuery({
      ...collectionsQueryOptions(),
      enabled: isAuthed,
    })

    useEffect(() => {
      if (!lastCardRef.current || !hasNextPage || isFetchingNextPage) return

      const observer = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting) {
            fetchNextPage()
          }
        },
        { rootMargin: '500px' }
      )
      observer.observe(lastCardRef.current)
      return () => observer.disconnect()
    }, [hasNextPage, isFetchingNextPage, fetchNextPage])

    const groups = useMemo(() => buildGroups(cards, groupBy), [cards, groupBy])
    const lastCardId = cards.length > 0 ? cards[cards.length - 1].card_version_id : null

    async function handleAdd(params: {
      collectionId: string
      condition: 'NM' | 'LP' | 'MP' | 'HP'
      finish: 'NONFOIL' | 'FOIL' | 'ETCHED'
    }) {
      if (!addTarget) return
      await addCollectionEntry(
        params.collectionId,
        addTarget.card_version_id,
        params.condition,
        params.finish,
      )
      queryClient.invalidateQueries({ queryKey: collectionEntriesQueryOptions(params.collectionId).queryKey })
      setAddTarget(null)
    }

    if (cards.length === 0) {
      return <div className={styles.empty}>No cards found. Try a different search.</div>
    }

    const renderCard = (card: CardSummary, i: number) => {
      const delta = card.price_change_1d
      const isLastCard = card.card_version_id === lastCardId
      return (
        <div key={card.card_version_id} className={styles.cardWrap}>
          <button
            ref={isLastCard ? lastCardRef : null}
            className={[
              styles.card,
              card.card_version_id === selectedId ? styles.cardSelected : '',
            ].filter(Boolean).join(' ')}
            onClick={() =>
              onSelect
                ? onSelect(card)
                : navigate({ to: '/cards/$id', params: { id: card.card_version_id } })
            }
          >
            <div style={{ position: 'relative' }}>
              <CardArt
                name={card.card_name}
                w="100%"
                hue={(i * 47) % 360}
                label={false}
                imageUrl={card.image_normal}
                finish={card.finish}
              />
              {(card.version_count ?? 1) > 1 && (
                <span className={styles.versionBadge}>{card.version_count} prints</span>
              )}
            </div>
            <div className={styles.cardInfo}>
              <div className={styles.cardName}>{card.card_name}</div>
              <div className={styles.cardSubtitle}>
                <span
                  className={`${styles.set} ${styles.setLink}`}
                  role="button"
                  tabIndex={0}
                  title={`Search ${card.set_code.toUpperCase()} only`}
                  onClick={(e) => {
                    e.stopPropagation()
                    navigate({ to: '/search', search: { set: card.set_code } })
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.stopPropagation()
                      e.preventDefault()
                      navigate({ to: '/search', search: { set: card.set_code } })
                    }
                  }}
                >
                  {card.set_name}
                </span>
                <span className={styles.rarity}>{card.rarity_name}</span>
              </div>
              <div className={styles.cardMeta}>
                <span className={[styles.price, delta >= 0 ? styles.up : styles.down].join(' ')}>
                  {card.price != null ? `$${card.price.toFixed(2)}` : 'N/A'}
                </span>
              </div>
              <Sparkline
                points={card.spark}
                color={delta >= 0 ? 'var(--hd-accent)' : 'var(--hd-red)'}
                width={100}
                height={24}
              />
            </div>
          </button>

          {/* "+ Add" hover button — outside the card button to avoid nested interactive */}
          <button
            className={styles.addBtn}
            onClick={(e) => {
              e.stopPropagation()
              setAddTarget(addTarget?.card_version_id === card.card_version_id ? null : card)
            }}
            aria-label={`Add ${card.card_name} to collection`}
          >
            + Add
          </button>

          {addTarget?.card_version_id === card.card_version_id && (
            <AddToCollectionPopover
              cardVersionId={card.card_version_id}
              cardName={card.card_name}
              finish={card.finish}
              collections={collections as import('../../collection/api').Collection[]}
              onAdd={handleAdd}
              onClose={() => setAddTarget(null)}
            />
          )}
        </div>
      )
    }

    return (
      <div className={styles.results}>
        <div className={styles.meta}>{total.toLocaleString()} results</div>
        {groupBy ? (
          groups.map((g) => (
            <section key={g.key} className={styles.group}>
              <header className={styles.groupHeader}>
                <span className={styles.groupTitle}>{g.label}</span>
                <span className={styles.groupCount}>{g.cards.length}</span>
              </header>
              <div className={styles.grid}>
                {g.cards.map((card, i) => renderCard(card, i))}
              </div>
            </section>
          ))
        ) : (
          <div className={styles.grid}>
            {cards.map((card, i) => renderCard(card, i))}
          </div>
        )}
        {isFetchingNextPage && (
          <div className={styles.loading}>Loading more cards...</div>
        )}
      </div>
    )
  }
  ```

- [ ] **Step 5.3: Run TypeScript check**

  ```bash
  cd src/frontend && npx tsc --noEmit
  ```

  Expected: no errors.

- [ ] **Step 5.4: Run existing SearchResults tests (if any exist)**

  ```bash
  cd src/frontend && npm run test -- --run features/cards
  ```

  Expected: all existing tests pass.

- [ ] **Step 5.5: Commit**

  ```bash
  git add src/frontend/src/features/cards/components/SearchResults.tsx \
          src/frontend/src/features/cards/components/SearchResults.module.css
  git commit -m "feat(collection): add hover '+ Add' button to SearchResults cards"
  ```

---

## Task 6: Update CollectionTable + wire collection page to real data

**Files:**
- Modify: `src/frontend/src/features/collection/components/CollectionTable.tsx`
- Modify: `src/frontend/src/features/collection/components/__tests__/CollectionTable.test.tsx`
- Modify: `src/frontend/src/routes/collection.tsx`
- Modify: `src/frontend/src/routes/Collection.module.css`

- [ ] **Step 6.1: Update `CollectionTable` to accept `CollectionEntry[]`**

  Replace the full `CollectionTable.tsx`:

  ```typescript
  // src/frontend/src/features/collection/components/CollectionTable.tsx
  import type { CollectionEntry } from '../api'
  import styles from './CollectionTable.module.css'

  interface CollectionTableProps {
    entries: CollectionEntry[]
    onRemove?: (entryId: string) => void
  }

  function formatUSD(n: number | null | undefined): string {
    if (n == null) return 'N/A'
    return `$${n.toFixed(2)}`
  }

  export function CollectionTable({ entries, onRemove }: CollectionTableProps) {
    return (
      <div className={styles.wrapper} role="region" aria-label="Collection table">
        <table className={styles.table}>
          <thead className={styles.thead}>
            <tr>
              <th scope="col">Card name</th>
              <th scope="col">Set</th>
              <th scope="col">Finish</th>
              <th scope="col">Condition</th>
              <th scope="col" className={styles.right}>Purchase</th>
              <th scope="col" className={styles.right}>Market</th>
              <th scope="col" className={styles.right}>P/L</th>
              <th scope="col" className={styles.right}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 && (
              <tr>
                <td colSpan={8} className={styles.empty}>
                  No cards match your filters
                </td>
              </tr>
            )}
            {entries.map((entry) => {
              const pl =
                entry.price != null
                  ? entry.price - Number(entry.purchase_price)
                  : null
              const plSign = pl != null && pl >= 0 ? '+' : ''

              return (
                <tr key={entry.item_id} className={styles.row}>
                  <td>
                    <span className={styles.cardName}>{entry.card_name}</span>
                  </td>
                  <td>
                    <span className={styles.setCode}>{entry.set_code.toUpperCase()}</span>
                  </td>
                  <td>
                    <span className={styles.finish}>{entry.finish.toLowerCase()}</span>
                  </td>
                  <td>
                    <span className={styles.condition}>{entry.condition}</span>
                  </td>
                  <td className={styles.right}>
                    {formatUSD(Number(entry.purchase_price))}
                  </td>
                  <td className={styles.right}>
                    {formatUSD(entry.price ?? null)}
                  </td>
                  <td className={styles.right}>
                    {pl != null ? (
                      <span style={{ color: pl >= 0 ? 'var(--hd-accent)' : 'var(--hd-red)' }}>
                        {plSign}{formatUSD(Math.abs(pl))}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--hd-muted)' }}>—</span>
                    )}
                  </td>
                  <td className={styles.right}>
                    {onRemove && (
                      <button
                        className={styles.removeBtn}
                        onClick={() => onRemove(entry.item_id)}
                        aria-label={`Remove ${entry.card_name}`}
                      >
                        ×
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    )
  }
  ```

- [ ] **Step 6.2: Update `CollectionTable.test.tsx`**

  Replace the full test file:

  ```typescript
  // src/frontend/src/features/collection/components/__tests__/CollectionTable.test.tsx
  import { render, screen, fireEvent } from '@testing-library/react'
  import { describe, it, expect, vi } from 'vitest'
  import { CollectionTable } from '../CollectionTable'
  import type { CollectionEntry } from '../../api'

  const ENTRIES: CollectionEntry[] = [
    {
      item_id: 'e1',
      card_version_id: 'cv1',
      card_name: 'Ragavan, Nimble Pilferer',
      set_code: 'MH2',
      collector_number: '138',
      finish: 'NONFOIL',
      condition: 'NM',
      purchase_price: 28,
      purchase_date: '2024-01-01',
      currency_code: 'USD',
      image_normal: null,
      price: 54.20,
      price_change_1d: 1.5,
    },
    {
      item_id: 'e2',
      card_version_id: 'cv2',
      card_name: 'Force of Will',
      set_code: 'ALL',
      collector_number: '28',
      finish: 'FOIL',
      condition: 'LP',
      purchase_price: 120,
      purchase_date: '2024-01-02',
      currency_code: 'USD',
      image_normal: null,
      price: 110,
      price_change_1d: -0.5,
    },
  ]

  describe('CollectionTable', () => {
    it('renders table headers', () => {
      render(<CollectionTable entries={[]} />)
      expect(screen.getByText('Card name')).toBeTruthy()
      expect(screen.getByText('Set')).toBeTruthy()
      expect(screen.getByText('Market')).toBeTruthy()
      expect(screen.getByText('P/L')).toBeTruthy()
      expect(screen.getByText('Finish')).toBeTruthy()
    })

    it('shows empty state when no entries', () => {
      render(<CollectionTable entries={[]} />)
      expect(screen.getByText(/no cards match/i)).toBeTruthy()
    })

    it('renders card rows', () => {
      render(<CollectionTable entries={ENTRIES} />)
      expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeTruthy()
      expect(screen.getByText('Force of Will')).toBeTruthy()
    })

    it('shows set code, condition, and finish', () => {
      render(<CollectionTable entries={[ENTRIES[0]]} />)
      expect(screen.getByText('MH2')).toBeTruthy()
      expect(screen.getByText('NM')).toBeTruthy()
      expect(screen.getByText('nonfoil')).toBeTruthy()
    })

    it('shows positive P/L in green text', () => {
      render(<CollectionTable entries={[ENTRIES[0]]} />)
      // profit: 54.20 - 28 = +$26.20
      expect(screen.getByText('+$26.20')).toBeTruthy()
    })

    it('calls onRemove with item_id when remove is clicked', () => {
      const onRemove = vi.fn()
      render(<CollectionTable entries={[ENTRIES[0]]} onRemove={onRemove} />)
      fireEvent.click(screen.getByRole('button', { name: /remove ragavan/i }))
      expect(onRemove).toHaveBeenCalledWith('e1')
    })
  })
  ```

- [ ] **Step 6.3: Run updated table test**

  ```bash
  cd src/frontend && npm run test -- --run features/collection/components/__tests__/CollectionTable
  ```

  Expected: all 6 tests pass.

- [ ] **Step 6.4: Add tab row styles to `Collection.module.css`**

  Append to `src/frontend/src/routes/Collection.module.css`:

  ```css
  /* ── Collection tabs ─────────────────────────────────────── */
  .tabRow {
    display: flex;
    align-items: center;
    gap: 6px;
    overflow-x: auto;
    padding-bottom: 2px;
  }

  .tab {
    padding: 4px 14px;
    border-radius: 5px;
    border: 1px solid var(--hd-border, #1f2937);
    background: transparent;
    color: var(--hd-sub);
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    white-space: nowrap;
    transition: all 120ms ease;
  }
  .tab:hover { border-color: var(--hd-accent); color: var(--hd-accent); }
  .tabActive {
    background: var(--hd-accent);
    border-color: var(--hd-accent);
    color: #fff;
  }

  .tabNew {
    padding: 4px 12px;
    border-radius: 5px;
    border: 1px dashed var(--hd-border, #1f2937);
    background: transparent;
    color: var(--hd-sub);
    font-size: 12px;
    cursor: pointer;
    white-space: nowrap;
    transition: all 120ms ease;
  }
  .tabNew:hover { border-color: var(--hd-accent); color: var(--hd-accent); }

  .newCollectionInput {
    padding: 4px 10px;
    border-radius: 5px;
    border: 1px solid var(--hd-accent);
    background: var(--hd-surface-2, #1f2937);
    color: var(--hd-text);
    font-size: 12px;
    outline: none;
    width: 140px;
  }
  ```

- [ ] **Step 6.5: Replace `collection.tsx` with wired-up version**

  Replace the full file. Key changes:
  - Remove `MOCK_COLLECTION`, `computeMetrics`, `formatUSD`, `CollectionCard` imports
  - Add `useQuery`, `useQueryClient` imports
  - Add `collectionsQueryOptions`, `collectionEntriesQueryOptions`, `createCollection`, `deleteCollectionEntry` imports
  - Add collection tabs state + `selectedCollectionId`
  - Replace `filtered` to filter over real `entries`
  - Replace `CollectionTable cards={filtered}` with `CollectionTable entries={filtered}`
  - Add `<CollectionGrid>` for grid view
  - Remove color split (no color data in real API)

  ```typescript
  // src/frontend/src/routes/collection.tsx
  import React, { useDeferredValue, useMemo, useState } from 'react'
  import { createFileRoute, useNavigate } from '@tanstack/react-router'
  import { useQuery, useQueryClient } from '@tanstack/react-query'
  import { AppShell } from '../components/layout/AppShell'
  import { TopBar } from '../components/layout/TopBar'
  import { Button } from '../components/ui/Button'
  import { Icon } from '../components/design-system/Icon'
  import { CollectionTable } from '../features/collection/components/CollectionTable'
  import { CollectionGrid } from '../features/collection/components/CollectionGrid'
  import {
    collectionsQueryOptions,
    collectionEntriesQueryOptions,
    createCollection,
    deleteCollectionEntry,
  } from '../features/collection/api'
  import type { CollectionEntry } from '../features/collection/api'
  import styles from './Collection.module.css'

  export const Route = createFileRoute('/collection')({
    component: CollectionPage,
  })

  type ViewMode = 'list' | 'grid'

  function formatUSD(n: number): string {
    return `$${n.toFixed(2)}`
  }

  function CollectionPage() {
    const navigate = useNavigate()
    const queryClient = useQueryClient()
    const [query, setQuery] = useState('')
    const [viewMode, setViewMode] = useState<ViewMode>('grid')
    const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null)
    const [newCollectionName, setNewCollectionName] = useState('')
    const [creatingNew, setCreatingNew] = useState(false)

    const deferredQuery = useDeferredValue(query)

    const { data: collections = [] } = useQuery(collectionsQueryOptions())

    const activeCollectionId = selectedCollectionId ?? collections[0]?.collection_id ?? null

    const { data: entries = [], isLoading } = useQuery(
      collectionEntriesQueryOptions(activeCollectionId ?? ''),
    )

    const filtered = useMemo(() => {
      if (!deferredQuery.trim()) return entries
      const q = deferredQuery.toLowerCase()
      return entries.filter(
        (e) =>
          e.card_name.toLowerCase().includes(q) ||
          e.set_code.toLowerCase().includes(q),
      )
    }, [entries, deferredQuery])

    const metrics = useMemo(() => {
      const totalValue = entries.reduce((s, e) => s + (e.price ?? 0), 0)
      const costBasis = entries.reduce((s, e) => s + Number(e.purchase_price), 0)
      return { totalValue, costBasis, pl: totalValue - costBasis, count: entries.length }
    }, [entries])

    async function handleRemove(itemId: string) {
      if (!activeCollectionId) return
      await deleteCollectionEntry(activeCollectionId, itemId)
      queryClient.invalidateQueries({
        queryKey: collectionEntriesQueryOptions(activeCollectionId).queryKey,
      })
    }

    async function handleCreateCollection() {
      if (!newCollectionName.trim()) return
      const col = await createCollection(newCollectionName.trim())
      queryClient.invalidateQueries({ queryKey: collectionsQueryOptions().queryKey })
      setSelectedCollectionId(col.collection_id)
      setCreatingNew(false)
      setNewCollectionName('')
    }

    const plSign = metrics.pl >= 0 ? '+' : ''

    return (
      <AppShell active="collection">
        <TopBar title="Collection" />

        <div className={styles.page}>
          {/* ── Header ──────────────────────────────── */}
          <header className={styles.header}>
            <div className={styles.titleBlock}>
              <div className={styles.eyebrow}>automana / collection</div>
              <h1 className={styles.title}>Your vault</h1>
            </div>
            <div className={styles.headerActions}>
              <Button
                variant="accent"
                size="sm"
                icon={<Icon kind="tag" size={13} color="currentColor" />}
                onClick={() => navigate({ to: '/listings' })}
              >
                Bulk list
              </Button>
            </div>
          </header>

          {/* ── Collection tabs ──────────────────────── */}
          <div className={styles.tabRow}>
            {collections.map((col) => (
              <button
                key={col.collection_id}
                className={[
                  styles.tab,
                  col.collection_id === activeCollectionId ? styles.tabActive : '',
                ].filter(Boolean).join(' ')}
                onClick={() => setSelectedCollectionId(col.collection_id)}
              >
                {col.collection_name}
              </button>
            ))}
            {creatingNew ? (
              <input
                className={styles.newCollectionInput}
                autoFocus
                placeholder="Collection name…"
                value={newCollectionName}
                onChange={(e) => setNewCollectionName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCreateCollection()
                  if (e.key === 'Escape') setCreatingNew(false)
                }}
                onBlur={() => { if (!newCollectionName.trim()) setCreatingNew(false) }}
              />
            ) : (
              <button className={styles.tabNew} onClick={() => setCreatingNew(true)}>
                + New
              </button>
            )}
          </div>

          {/* ── Metrics strip ─────────────────────── */}
          <section aria-label="Portfolio metrics">
            <div className={styles.metricsStrip}>
              <div className={styles.metricCard}>
                <div className={styles.metricLabel}>Total value</div>
                <div className={styles.metricValue}>{formatUSD(metrics.totalValue)}</div>
                <div className={styles.metricSub}>across {metrics.count} cards</div>
              </div>
              <div className={styles.metricCard}>
                <div className={styles.metricLabel}>Cost basis</div>
                <div className={styles.metricValue}>{formatUSD(metrics.costBasis)}</div>
                <div className={styles.metricSub}>total invested</div>
              </div>
              <div className={styles.metricCard}>
                <div className={styles.metricLabel}>Unrealized P/L</div>
                <div
                  className={[
                    styles.metricValue,
                    metrics.pl >= 0 ? styles.positive : styles.negative,
                  ].join(' ')}
                >
                  {plSign}{formatUSD(Math.abs(metrics.pl))}
                </div>
                <div className={styles.metricSub}>vs cost basis</div>
              </div>
              <div className={styles.metricCard}>
                <div className={styles.metricLabel}>Cards owned</div>
                <div className={styles.metricValue}>{metrics.count}</div>
                <div className={styles.metricSub}>unique entries</div>
              </div>
            </div>
          </section>

          {/* ── Toolbar ───────────────────────────── */}
          <div className={styles.toolbar} role="toolbar" aria-label="Collection filters">
            <div className={styles.searchBox}>
              <Icon kind="search" size={14} color="var(--hd-sub)" />
              <input
                className={styles.searchInput}
                type="search"
                placeholder="Search cards, sets…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search collection"
              />
            </div>
            <div className={styles.toolbarRight}>
              <div className={styles.viewToggle} role="group" aria-label="View mode">
                <button
                  className={[
                    styles.viewBtn,
                    viewMode === 'grid' ? styles.viewBtnActive : '',
                  ].filter(Boolean).join(' ')}
                  onClick={() => setViewMode('grid')}
                  aria-pressed={viewMode === 'grid'}
                  aria-label="Grid view"
                  title="Grid view"
                >
                  <Icon kind="grid" size={14} color="currentColor" />
                </button>
                <button
                  className={[
                    styles.viewBtn,
                    viewMode === 'list' ? styles.viewBtnActive : '',
                  ].filter(Boolean).join(' ')}
                  onClick={() => setViewMode('list')}
                  aria-pressed={viewMode === 'list'}
                  aria-label="List view"
                  title="List view"
                >
                  <Icon kind="list" size={14} color="currentColor" />
                </button>
              </div>
            </div>
          </div>

          {/* ── Main content ──────────────────────── */}
          {isLoading ? (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--hd-sub)' }}>
              Loading…
            </div>
          ) : viewMode === 'grid' ? (
            <CollectionGrid entries={filtered} onRemove={handleRemove} />
          ) : (
            <CollectionTable entries={filtered} onRemove={handleRemove} />
          )}
        </div>
      </AppShell>
    )
  }
  ```

- [ ] **Step 6.6: TypeScript check**

  ```bash
  cd src/frontend && npx tsc --noEmit
  ```

  Expected: no errors. If `CollectionTable.module.css` is missing a `.removeBtn`, `.finish`, or `.condition` class, add them now:

  ```css
  /* Append to CollectionTable.module.css if missing */
  .finish { font-size: 11px; color: var(--hd-sub); font-family: var(--font-mono); text-transform: lowercase; }
  .condition { font-size: 11px; font-family: var(--font-mono); font-weight: 600; color: var(--hd-text); }
  .removeBtn { background: none; border: none; color: var(--hd-sub); cursor: pointer; font-size: 14px; padding: 2px 6px; border-radius: 3px; }
  .removeBtn:hover { color: var(--hd-red); background: rgba(248,113,113,0.1); }
  ```

- [ ] **Step 6.7: Run all collection tests**

  ```bash
  cd src/frontend && npm run test -- --run features/collection
  ```

  Expected: all tests in `features/collection` pass.

- [ ] **Step 6.8: Commit**

  ```bash
  git add src/frontend/src/routes/collection.tsx \
          src/frontend/src/routes/Collection.module.css \
          src/frontend/src/features/collection/components/CollectionTable.tsx \
          src/frontend/src/features/collection/components/__tests__/CollectionTable.test.tsx
  git commit -m "feat(collection): wire collection page to real API — grid/table toggle + multi-collection tabs"
  ```

---

## End-to-End Verification

1. Start the backend: `dcdev-automana up -d`

2. Create a test user and get a token (see `docs/TESTING_API_FLOW.md`)

3. Open browser to `http://localhost:5173` and log in

4. Navigate to `/search` — search for any card — hover it — confirm "+ Add" button appears

5. Click "+ Add" — pick condition NM — click "Add to Collection"
   - Expected: success (no error), popover closes

6. Navigate to `/collection`
   - Expected: "My Collection" tab visible, card appears in grid with art (if image loaded), price, and P&L

7. Click the table toggle — confirm the card appears in row format

8. Click "+ New" — type a collection name — press Enter — confirm new tab appears

9. Click "×" on the card in grid view — confirm it disappears

10. Delete test user (see `docs/TESTING_API_FLOW.md`)
