# Collection — Card Catalog + Wishlist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `/collection` route — a card catalog where users track cards they own (`is_wishlist=false`) and cards they want (`is_wishlist=true`), with no financial columns, and re-add the Collection sidebar entry.

**Architecture:** A new `is_wishlist BOOLEAN` column separates ownership-intent from lifecycle status (purchased/listed/stashed/sold). The backend gains a filter param on `GET /entries`; the frontend gains an owned/wishlist toggle in `AddToCollectionPopover`, a `is_wishlist` pass-through in `useInfiniteEntries`, Portfolio updated to exclude wishlist entries, and a new simplified `/collection` route. All existing Collection components and API are reused — no new feature directories.

**Tech Stack:** FastAPI + asyncpg (backend), React 18 + TanStack Query v5 + CSS Modules + Vitest/RTL (frontend)

> **Supersedes:** `2026-05-18-collection-feature.md` (was written before Portfolio split; scope has changed)
> **Closes:** GitHub issue #308

---

## File Map

| Action | File |
|--------|------|
| Create | `src/automana/database/SQL/migrations/migration_50_collection_wishlist.sql` |
| Modify | `src/automana/core/models/collections/collection.py` |
| Modify | `src/automana/core/repositories/card_catalog/collection_repository.py` |
| Modify | `src/automana/core/services/card_catalog/collection_service.py` |
| Modify | `src/automana/api/routers/mtg/collection.py` |
| Modify | `src/frontend/src/features/collection/api.ts` |
| Modify | `src/frontend/src/features/collection/hooks/useInfiniteEntries.ts` |
| Modify | `src/frontend/src/features/collection/hooks/__tests__/useInfiniteEntries.test.ts` |
| Modify | `src/frontend/src/features/collection/components/CollectionGrid.tsx` |
| Modify | `src/frontend/src/features/collection/components/__tests__/CollectionGrid.test.tsx` |
| Modify | `src/frontend/src/features/collection/components/AddToCollectionPopover.tsx` |
| Modify | `src/frontend/src/features/collection/components/__tests__/AddToCollectionPopover.test.tsx` |
| Modify | `src/frontend/src/features/cards/components/SearchResults.tsx` |
| Modify | `src/frontend/src/routes/portfolio.tsx` |
| Create | `src/frontend/src/routes/collection.tsx` |
| Create | `src/frontend/src/routes/Collection.module.css` |
| Modify | `src/frontend/src/components/layout/Sidebar.tsx` |
| Modify | `src/frontend/src/routeTree.gen.ts` |

---

## Task 1: DB migration — add `is_wishlist` column

**Files:**
- Create: `src/automana/database/SQL/migrations/migration_50_collection_wishlist.sql`

- [ ] **Step 1: Write the migration file**

```sql
-- migration_50: add is_wishlist flag to collection_items
--
-- Separates intent (do I own this card vs do I want it) from lifecycle status
-- (purchased → listed → sold → stashed). Portfolio excludes is_wishlist=TRUE rows.
-- All existing rows default to FALSE (owned).

ALTER TABLE user_collection.collection_items
    ADD COLUMN IF NOT EXISTS is_wishlist BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_collection_items_wishlist
    ON user_collection.collection_items (is_wishlist);
```

- [ ] **Step 2: Apply the migration**

```bash
automana-run db:migrate
```

Expected: migration_50 applied, `is_wishlist` column now exists on `user_collection.collection_items`.

- [ ] **Step 3: Verify**

```bash
automana-run db:exec "SELECT column_name, data_type, column_default, is_nullable FROM information_schema.columns WHERE table_schema = 'user_collection' AND table_name = 'collection_items' AND column_name = 'is_wishlist';"
```

Expected output includes: `is_wishlist | boolean | false | NO`

- [ ] **Step 4: Commit**

```bash
git add src/automana/database/SQL/migrations/migration_50_collection_wishlist.sql
git commit -m "feat(db): add is_wishlist column to collection_items (migration_50)"
```

---

## Task 2: Backend models — add `is_wishlist` field

**Files:**
- Modify: `src/automana/core/models/collections/collection.py`

- [ ] **Step 1: Add `is_wishlist` to `AddCollectionEntryRequest`**

In `collection.py`, in the `AddCollectionEntryRequest` class, add after the `ebay_item_id` field:

```python
is_wishlist: bool = Field(
    default=False,
    description="True if this is a wishlist entry (want it), False if owned"
)
```

The full class becomes:

```python
class AddCollectionEntryRequest(BaseModel):
    card_version_id: Optional[UUID] = Field(default=None, description="Internal card_version_id (returned by /suggest)")
    scryfall_id: Optional[str] = Field(default=None, description="Scryfall UUID for the printing")
    set_code: Optional[str] = Field(default=None, max_length=10, description="Set code (e.g. 'dmu'), use with collector_number")
    collector_number: Optional[str] = Field(default=None, max_length=50, description="Collector number (e.g. '108'), use with set_code")

    condition: Conditions = Field(default=Conditions.NM)
    finish: Finish = Field(default=Finish.NONFOIL)
    purchase_price: Decimal = Field(default=Decimal('0.00'), ge=0, decimal_places=2)
    currency_code: str = Field(default='USD', max_length=3)
    purchase_date: date = Field(default_factory=date.today)
    language_id: Optional[int] = Field(default=None)
    status: EntryStatus = Field(default=EntryStatus.PURCHASED)
    ebay_item_id: Optional[str] = Field(default=None, max_length=30)
    is_wishlist: bool = Field(default=False, description="True if this is a wishlist entry (want it), False if owned")

    @model_validator(mode='after')
    def check_identifier(self) -> 'AddCollectionEntryRequest':
        has_internal = self.card_version_id is not None
        has_scryfall = self.scryfall_id is not None
        has_tuple = self.set_code is not None and self.collector_number is not None
        if not (has_internal or has_scryfall or has_tuple):
            raise ValueError(
                "Provide one of: card_version_id, scryfall_id, or set_code+collector_number"
            )
        return self
```

Note: `purchase_price` default changed from required to `Decimal('0.00')` — the column is nullable in the DB so this is safe.

- [ ] **Step 2: Add `is_wishlist` to `PublicCollectionEntry`**

In `PublicCollectionEntry`, add after `ebay_item_id`:

```python
is_wishlist: bool = False
```

- [ ] **Step 3: Run backend tests**

```bash
cd src/automana && python -m pytest tests/ -x -q --tb=short 2>&1 | tail -20
```

Expected: all pass (no Pydantic validation changes should break existing tests).

- [ ] **Step 4: Commit**

```bash
git add src/automana/core/models/collections/collection.py
git commit -m "feat(models): add is_wishlist field to collection entry models"
```

---

## Task 3: Repository — pass `is_wishlist` on insert; filter on list

**Files:**
- Modify: `src/automana/core/repositories/card_catalog/collection_repository.py`

- [ ] **Step 1: Update `add_entry` to insert `is_wishlist`**

In `add_entry`, add `is_wishlist: bool = False` to the signature and pass it in the INSERT. Replace the method:

```python
async def add_entry(
    self,
    collection_id: UUID,
    user_id: UUID,
    card_version_id: UUID,
    finish_id: int,
    condition: str,
    purchase_price,
    currency_code: str,
    purchase_date,
    language_id,
    status: str = 'purchased',
    ebay_item_id: Optional[str] = None,
    is_wishlist: bool = False,
) -> Optional[dict]:
    query = """
        INSERT INTO user_collection.collection_items
            (collection_id, unique_card_id, finish_id, condition,
             purchase_price, currency_code, purchase_date, language_id,
             status, ebay_item_id, is_wishlist)
        SELECT $1, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
        FROM user_collection.collections
        WHERE collection_id = $1 AND user_id = $2
        RETURNING item_id, collection_id, unique_card_id AS card_version_id,
                  finish_id, condition, purchase_price, currency_code,
                  purchase_date, language_id, status, ebay_item_id, is_wishlist;
    """
    rows = await self.execute_query(
        query,
        (collection_id, user_id, card_version_id, finish_id, condition,
         purchase_price, currency_code, purchase_date, language_id,
         status, ebay_item_id, is_wishlist),
    )
    return dict(rows[0]) if rows else None
```

- [ ] **Step 2: Update `get_entry` SELECT to include `is_wishlist`**

In `get_entry`, add `ci.is_wishlist` to the SELECT list (after `ci.ebay_item_id`):

```sql
ci.ebay_item_id,
ci.is_wishlist,
CASE
    WHEN ci.ebay_item_id IS NOT NULL
         AND eal.item_id IS NOT NULL
         AND eal.ended_at IS NULL
    THEN 'listed'
    ELSE ci.status
END AS status
```

- [ ] **Step 3: Update `get_all_entries` to support `is_wishlist` filter and include the column**

Replace `get_all_entries`:

```python
async def get_all_entries(
    self,
    collection_id: UUID,
    user_id: UUID,
    limit: int = 50,
    offset: int = 0,
    is_wishlist: Optional[bool] = None,
) -> List[dict]:
    wishlist_clause = ""
    if is_wishlist is True:
        wishlist_clause = "AND ci.is_wishlist = TRUE"
    elif is_wishlist is False:
        wishlist_clause = "AND ci.is_wishlist = FALSE"

    query = f"""
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
               ps.price_change_1d          AS price_change_1d,
               ci.ebay_item_id,
               ci.is_wishlist,
               CASE
                   WHEN ci.ebay_item_id IS NOT NULL
                        AND eal.item_id IS NOT NULL
                        AND eal.ended_at IS NULL
                   THEN 'listed'
                   ELSE ci.status
               END AS status
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
        LEFT JOIN app_integration.ebay_active_listings eal
            ON eal.item_id = ci.ebay_item_id
        WHERE ci.collection_id = $1
          {wishlist_clause}
        ORDER BY ci.purchase_date DESC, ci.item_id
        LIMIT $3 OFFSET $4;
    """
    rows = await self.execute_query(query, (collection_id, user_id, limit, offset))
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run backend tests**

```bash
cd src/automana && python -m pytest tests/ -x -q --tb=short 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/card_catalog/collection_repository.py
git commit -m "feat(repo): add is_wishlist to collection entry insert/query"
```

---

## Task 4: Service + Router — thread `is_wishlist` through

**Files:**
- Modify: `src/automana/core/services/card_catalog/collection_service.py`
- Modify: `src/automana/api/routers/mtg/collection.py`

- [ ] **Step 1: Update `add_entry` service to pass `is_wishlist`**

In `collection_service.py`, in the `add_entry` service function, update the `user_collection_repository.add_entry(...)` call to add `is_wishlist=request.is_wishlist`:

```python
row = await user_collection_repository.add_entry(
    collection_id=collection_id,
    user_id=user.unique_id,
    card_version_id=card_version_id,
    finish_id=finish_id,
    condition=request.condition.value,
    purchase_price=request.purchase_price,
    currency_code=request.currency_code,
    purchase_date=request.purchase_date,
    language_id=request.language_id,
    status=request.status.value,
    ebay_item_id=request.ebay_item_id,
    is_wishlist=request.is_wishlist,
)
```

- [ ] **Step 2: Update `list_entries` service to accept and pass `is_wishlist` filter**

In `collection_service.py`, update the `list_entries` function signature and body:

```python
@ServiceRegistry.register(
    "card_catalog.collection.list_entries",
    db_repositories=["user_collection"]
)
async def list_entries(
    user_collection_repository: CollectionRepository,
    collection_id: UUID,
    user: UserInDB,
    limit: int = 50,
    offset: int = 0,
    is_wishlist: Optional[bool] = None,
) -> List[PublicCollectionEntry]:
    col = await user_collection_repository.get(collection_id, user.unique_id)
    if not col:
        raise card_catalog_exceptions.CollectionNotFoundError(
            f"Collection {collection_id} not found"
        )
    rows = await user_collection_repository.get_all_entries(
        collection_id, user.unique_id, limit=limit, offset=offset, is_wishlist=is_wishlist
    )
    return [PublicCollectionEntry.model_validate(r) for r in rows]
```

Also add `from typing import Optional` to the imports if not already present.

- [ ] **Step 3: Update `GET /{collection_id}/entries` router to accept `is_wishlist` query param**

In `collection.py` (router), update the `list_entries` endpoint:

```python
@router.get(
    '/{collection_id}/entries',
    summary="List all entries in a collection",
    description="Returns cards in the specified collection. Supports limit/offset pagination and optional is_wishlist filter.",
    response_model=ApiResponse,
    operation_id="collection_entries_list",
    responses={
        404: {"description": "Collection not found"},
    },
)
async def list_entries(
    collection_id: UUID,
    current_user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Number of entries to skip"),
    is_wishlist: Optional[bool] = Query(None, description="Filter by wishlist flag. True=wishlist only, False=owned only, omit=all"),
):
    try:
        result = await service_manager.execute_service(
            "card_catalog.collection.list_entries",
            collection_id=collection_id,
            user=current_user,
            limit=limit,
            offset=offset,
            is_wishlist=is_wishlist,
        )
        return ApiResponse(data=result)
    except CollectionNotFoundError:
        raise HTTPException(status_code=404, detail="Collection not found")
```

Add `Optional` to the router imports from `typing`.

- [ ] **Step 4: Run backend tests**

```bash
cd src/automana && python -m pytest tests/ -x -q --tb=short 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/card_catalog/collection_service.py \
        src/automana/api/routers/mtg/collection.py
git commit -m "feat(api): expose is_wishlist filter on collection entries endpoint"
```

---

## Task 5: Frontend api.ts — add `is_wishlist` to types and functions

**Files:**
- Modify: `src/frontend/src/features/collection/api.ts`

- [ ] **Step 1: Write failing test first**

In `src/frontend/src/features/collection/hooks/__tests__/useInfiniteEntries.test.ts`, add a test that verifies `fetchEntriesPage` is called with the correct URL when `isWishlist=false`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useInfiniteEntries } from '../useInfiniteEntries'
import * as api from '../../api'

vi.mock('../../api', () => ({
  fetchEntriesPage: vi.fn().mockResolvedValue([]),
  PAGE_SIZE: 50,
}))

describe('useInfiniteEntries', () => {
  beforeEach(() => vi.clearAllMocks())

  it('calls fetchEntriesPage with isWishlist=false when specified', async () => {
    renderHook(() => useInfiniteEntries('col-1', false))
    await waitFor(() => {
      expect(api.fetchEntriesPage).toHaveBeenCalledWith('col-1', 0, 50, false)
    })
  })

  it('calls fetchEntriesPage with no isWishlist when not specified', async () => {
    renderHook(() => useInfiniteEntries('col-1'))
    await waitFor(() => {
      expect(api.fetchEntriesPage).toHaveBeenCalledWith('col-1', 0, 50, undefined)
    })
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd src/frontend && npx vitest run src/frontend/src/features/collection/hooks/__tests__/useInfiniteEntries.test.ts 2>&1 | tail -20
```

Expected: FAIL — `fetchEntriesPage` called without `isWishlist` arg.

- [ ] **Step 3: Update `CollectionEntry` type and `fetchEntriesPage` in api.ts**

In `api.ts`, add `is_wishlist: boolean` to `CollectionEntry`:

```ts
export interface CollectionEntry {
  item_id: string
  card_version_id: string
  card_name: string
  set_code: string
  collector_number: string
  finish: 'NONFOIL' | 'FOIL' | 'ETCHED'
  condition: 'NM' | 'LP' | 'MP' | 'HP' | 'DMG' | 'SP'
  purchase_price: string
  purchase_date: string
  currency_code: string
  language_id?: number | null
  image_normal?: string | null
  price?: number | null
  price_change_1d: number
  status: EntryStatus
  ebay_item_id?: string | null
  is_wishlist: boolean
}
```

Update `fetchEntriesPage`:

```ts
export async function fetchEntriesPage(
  collectionId: string,
  offset: number,
  limit = PAGE_SIZE,
  isWishlist?: boolean,
): Promise<CollectionEntry[]> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  })
  if (isWishlist !== undefined) {
    params.set('is_wishlist', String(isWishlist))
  }
  return apiClient<CollectionEntry[]>(
    `/catalog/mtg/collection/${collectionId}/entries?${params}`,
  )
}
```

Update `addCollectionEntry` to accept and pass `is_wishlist`:

```ts
export async function addCollectionEntry(
  collectionId: string,
  cardVersionId: string,
  condition: CollectionEntry['condition'],
  finish: CollectionEntry['finish'],
  options?: { status?: EntryStatus; ebayItemId?: string; isWishlist?: boolean },
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
        status: options?.status ?? 'purchased',
        ebay_item_id: options?.ebayItemId ?? null,
        is_wishlist: options?.isWishlist ?? false,
      }),
    },
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd src/frontend && npx vitest run src/frontend/src/features/collection/hooks/__tests__/useInfiniteEntries.test.ts 2>&1 | tail -20
```

Expected: still FAIL — `useInfiniteEntries` hasn't been updated yet. That's fine — the api mock passes, but the hook doesn't pass `isWishlist` to `fetchEntriesPage`. Proceed to Task 6 to fix the hook.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/collection/api.ts \
        src/frontend/src/features/collection/hooks/__tests__/useInfiniteEntries.test.ts
git commit -m "feat(api): add is_wishlist to CollectionEntry type and fetchEntriesPage"
```

---

## Task 6: `useInfiniteEntries` hook — thread `isWishlist` through

**Files:**
- Modify: `src/frontend/src/features/collection/hooks/useInfiniteEntries.ts`

- [ ] **Step 1: Update hook signature and forward `isWishlist`**

Replace `useInfiniteEntries.ts` with:

```ts
import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchEntriesPage, PAGE_SIZE } from '../api'
import type { CollectionEntry } from '../api'

interface UseInfiniteEntriesResult {
  allEntries: CollectionEntry[]
  isFetchingMore: boolean
  hasMore: boolean
  fetchNextPage: () => Promise<void>
  removeEntry: (itemId: string) => void
  sentinelRef: React.RefObject<HTMLDivElement>
}

export function useInfiniteEntries(
  collectionId: string | null,
  isWishlist?: boolean,
): UseInfiniteEntriesResult {
  const [allEntries, setAllEntries] = useState<CollectionEntry[]>([])
  const [isFetchingMore, setIsFetchingMore] = useState(false)
  const [hasMore, setHasMore] = useState(true)
  const offsetRef = useRef(0)
  const sentinelRef = useRef<HTMLDivElement>(null)
  const isFetchingRef = useRef(false)

  useEffect(() => {
    if (!collectionId) {
      setAllEntries([])
      setHasMore(false)
      return
    }
    let cancelled = false
    offsetRef.current = 0
    isFetchingRef.current = true
    setAllEntries([])
    setHasMore(true)
    setIsFetchingMore(true)
    fetchEntriesPage(collectionId, 0, PAGE_SIZE, isWishlist).then((page) => {
      if (cancelled) return
      setAllEntries(page)
      offsetRef.current = page.length
      setHasMore(page.length === PAGE_SIZE)
      isFetchingRef.current = false
      setIsFetchingMore(false)
    })
    return () => { cancelled = true; isFetchingRef.current = false }
  }, [collectionId, isWishlist])

  const fetchNextPage = useCallback(async () => {
    if (!collectionId || isFetchingRef.current || !hasMore) return
    isFetchingRef.current = true
    setIsFetchingMore(true)
    const page = await fetchEntriesPage(collectionId, offsetRef.current, PAGE_SIZE, isWishlist)
    setAllEntries((prev) => [...prev, ...page])
    offsetRef.current += page.length
    setHasMore(page.length === PAGE_SIZE)
    isFetchingRef.current = false
    setIsFetchingMore(false)
  }, [collectionId, hasMore, isWishlist])

  useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) fetchNextPage()
      },
      { rootMargin: '200px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [fetchNextPage])

  const removeEntry = useCallback((itemId: string) => {
    setAllEntries((prev) => prev.filter((e) => e.item_id !== itemId))
  }, [])

  return { allEntries, isFetchingMore, hasMore, fetchNextPage, removeEntry, sentinelRef }
}
```

- [ ] **Step 2: Run the hook test to verify it passes**

```bash
cd src/frontend && npx vitest run src/frontend/src/features/collection/hooks/__tests__/useInfiniteEntries.test.ts 2>&1 | tail -20
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/features/collection/hooks/useInfiniteEntries.ts
git commit -m "feat(hooks): thread isWishlist filter through useInfiniteEntries"
```

---

## Task 7: Portfolio route — exclude wishlist entries

**Files:**
- Modify: `src/frontend/src/routes/portfolio.tsx`

- [ ] **Step 1: Update `useInfiniteEntries` call to pass `isWishlist={false}`**

In `portfolio.tsx`, find the call to `useInfiniteEntries`:

```tsx
const {
  allEntries: entries,
  isFetchingMore,
  hasMore,
  removeEntry,
  sentinelRef,
} = useInfiniteEntries(activeCollectionId)
```

Change to:

```tsx
const {
  allEntries: entries,
  isFetchingMore,
  hasMore,
  removeEntry,
  sentinelRef,
} = useInfiniteEntries(activeCollectionId, false)
```

- [ ] **Step 2: Run frontend tests**

```bash
cd src/frontend && npx vitest run 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/routes/portfolio.tsx
git commit -m "fix(portfolio): exclude wishlist entries from portfolio view"
```

---

## Task 8: `CollectionGrid` — add `showFinancials` prop

**Files:**
- Modify: `src/frontend/src/features/collection/components/CollectionGrid.tsx`
- Modify: `src/frontend/src/features/collection/components/__tests__/CollectionGrid.test.tsx`

- [ ] **Step 1: Write a failing test for `showFinancials={false}`**

Add to `CollectionGrid.test.tsx` (after the existing tests):

```ts
it('hides price and P/L when showFinancials is false', () => {
  const entry = makeEntry({ price: 10.00, purchase_price: '5.00' })
  render(<CollectionGrid entries={[entry]} onRemove={vi.fn()} showFinancials={false} />)
  expect(screen.queryByText(/\$10/)).toBeNull()
  expect(screen.queryByText(/\+\$5/)).toBeNull()
})

it('shows price and P/L by default', () => {
  const entry = makeEntry({ price: 10.00, purchase_price: '5.00' })
  render(<CollectionGrid entries={[entry]} onRemove={vi.fn()} />)
  expect(screen.getByText('$10.00')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd src/frontend && npx vitest run src/frontend/src/features/collection/components/__tests__/CollectionGrid.test.tsx 2>&1 | tail -20
```

Expected: FAIL — `showFinancials` prop doesn't exist yet.

- [ ] **Step 3: Add `showFinancials` prop to `CollectionGrid`**

In `CollectionGrid.tsx`, update the interface and component:

```tsx
interface CollectionGridProps {
  entries: CollectionEntry[]
  onRemove: (itemId: string) => void
  showFinancials?: boolean
}

export function CollectionGrid({ entries, onRemove, showFinancials = true }: CollectionGridProps) {
  // ... existing code unchanged until the copy row ...

  // In the copy row rendering, wrap price/P/L in a condition:
  <li key={copy.item_id} className={styles.copyRow}>
    <span className={styles.badge}>{copy.condition}</span>
    {copy.finish !== 'NONFOIL' && (
      <span className={finishBadgeClass(copy.finish)}>
        {copy.finish.toLowerCase()}
      </span>
    )}
    {showFinancials && (
      <>
        <span className={styles.copyPrice}>{formatUSD(copy.price)}</span>
        {plLabel != null && (
          <span className={`${styles.pl} ${pl! >= 0 ? styles.plUp : styles.plDown}`}>
            {plLabel}
          </span>
        )}
      </>
    )}
    <span className={`${styles.badge} ${styles.badgeStatus}`}>{copy.status}</span>
    <button
      className={styles.removeBtn}
      onClick={() => onRemove(copy.item_id)}
      aria-label={`Remove copy of ${copy.card_name}`}
    >
      ×
    </button>
  </li>
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd src/frontend && npx vitest run src/frontend/src/features/collection/components/__tests__/CollectionGrid.test.tsx 2>&1 | tail -20
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/collection/components/CollectionGrid.tsx \
        src/frontend/src/features/collection/components/__tests__/CollectionGrid.test.tsx
git commit -m "feat(CollectionGrid): add showFinancials prop to hide price/PL"
```

---

## Task 9: `AddToCollectionPopover` — add owned/wishlist toggle

**Files:**
- Modify: `src/frontend/src/features/collection/components/AddToCollectionPopover.tsx`
- Modify: `src/frontend/src/features/collection/components/__tests__/AddToCollectionPopover.test.tsx`

- [ ] **Step 1: Write failing tests for the toggle**

Add to `AddToCollectionPopover.test.tsx`:

```ts
it('shows Owned and Wishlist toggle buttons', () => {
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
  expect(screen.getByRole('button', { name: 'Owned' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Wishlist' })).toBeTruthy()
})

it('calls onAdd with isWishlist=true when Wishlist is selected', () => {
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
  fireEvent.click(screen.getByRole('button', { name: 'Wishlist' }))
  fireEvent.click(screen.getByRole('button', { name: /Add/ }))
  expect(onAdd).toHaveBeenCalledWith(
    expect.objectContaining({ isWishlist: true })
  )
})

it('calls onAdd with isWishlist=false by default (Owned)', () => {
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
  fireEvent.click(screen.getByRole('button', { name: /Add/ }))
  expect(onAdd).toHaveBeenCalledWith(
    expect.objectContaining({ isWishlist: false })
  )
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd src/frontend && npx vitest run src/frontend/src/features/collection/components/__tests__/AddToCollectionPopover.test.tsx 2>&1 | tail -20
```

Expected: FAIL.

- [ ] **Step 3: Update `AddToCollectionPopover`**

```tsx
// New onAdd signature — add isWishlist to the params
interface Props {
  cardVersionId: string
  cardName: string
  finish: string
  collections: Collection[]
  existingCopies?: number
  onAdd: (params: {
    collectionId: string
    condition: CollectionEntry['condition']
    finish: FinishOut
    isWishlist: boolean
  }) => void
  onClose: () => void
}

// Add to local state (after condition state):
const [isWishlist, setIsWishlist] = useState(false)

// Add owned/wishlist toggle to the JSX (before the condition pills, or after the header):
<div className={styles.label}>Type</div>
<div className={styles.pills}>
  <button
    className={[styles.pill, !isWishlist ? styles.pillActive : ''].join(' ')}
    onClick={() => setIsWishlist(false)}
  >
    Owned
  </button>
  <button
    className={[styles.pill, isWishlist ? styles.pillActive : ''].join(' ')}
    onClick={() => setIsWishlist(true)}
  >
    Wishlist
  </button>
</div>

// Update the Add button onClick:
onClick={() =>
  onAdd({ collectionId, condition, finish: normaliseFinish(finish), isWishlist })
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd src/frontend && npx vitest run src/frontend/src/features/collection/components/__tests__/AddToCollectionPopover.test.tsx 2>&1 | tail -20
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/collection/components/AddToCollectionPopover.tsx \
        src/frontend/src/features/collection/components/__tests__/AddToCollectionPopover.test.tsx
git commit -m "feat(popover): add owned/wishlist toggle to AddToCollectionPopover"
```

---

## Task 10: `SearchResults` — pass `isWishlist` through `handleAdd`

**Files:**
- Modify: `src/frontend/src/features/cards/components/SearchResults.tsx`

- [ ] **Step 1: Update `handleAdd` to accept and forward `isWishlist`**

In `SearchResults.tsx`, find `handleAdd` and update its signature and body:

```tsx
async function handleAdd(params: {
  collectionId: string
  condition: 'NM' | 'LP' | 'MP' | 'HP' | 'DMG' | 'SP'
  finish: 'NONFOIL' | 'FOIL' | 'ETCHED'
  isWishlist: boolean
}) {
  if (!addTarget) return
  await addCollectionEntry(
    params.collectionId,
    addTarget.card_version_id,
    params.condition,
    params.finish,
    { isWishlist: params.isWishlist },
  )
  queryClient.invalidateQueries({ queryKey: collectionEntriesQueryOptions(params.collectionId).queryKey })
  toast(`${addTarget.card_name} ${params.isWishlist ? 'added to wishlist' : 'added to collection'}`)
  setAddTarget(null)
}
```

- [ ] **Step 2: Run frontend tests**

```bash
cd src/frontend && npx vitest run 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/features/cards/components/SearchResults.tsx
git commit -m "feat(search): pass isWishlist through handleAdd to addCollectionEntry"
```

---

## Task 11: New `/collection` route — card catalog with owned/wishlist tabs

**Files:**
- Create: `src/frontend/src/routes/collection.tsx`
- Create: `src/frontend/src/routes/Collection.module.css`

- [ ] **Step 1: Create `Collection.module.css`**

```css
/* src/frontend/src/routes/Collection.module.css */

.page {
  padding: 24px 32px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  height: 100%;
  overflow-y: auto;
}

.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.titleBlock {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.eyebrow {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--hd-sub);
}

.title {
  font-size: 22px;
  font-weight: 600;
  color: var(--hd-text);
  margin: 0;
}

.tabRow {
  display: flex;
  gap: 4px;
  align-items: center;
  border-bottom: 1px solid var(--hd-border);
  padding-bottom: 0;
}

.tab {
  padding: 6px 14px;
  border-radius: 6px 6px 0 0;
  border: none;
  background: transparent;
  color: var(--hd-sub);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}

.tab:hover {
  color: var(--hd-text);
  background: var(--hd-surface-2);
}

.tabActive {
  color: var(--hd-text);
  background: var(--hd-surface-2);
  border-bottom: 2px solid var(--hd-accent);
}

.collectionTabRow {
  display: flex;
  gap: 4px;
  align-items: center;
  flex-wrap: wrap;
}

.collectionTab {
  padding: 4px 12px;
  border-radius: 20px;
  border: 1px solid var(--hd-border);
  background: transparent;
  color: var(--hd-sub);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.collectionTab:hover {
  color: var(--hd-text);
  border-color: var(--hd-accent);
}

.collectionTabActive {
  color: var(--hd-text);
  background: var(--hd-accent);
  border-color: var(--hd-accent);
}

.tabNew {
  padding: 4px 12px;
  border-radius: 20px;
  border: 1px dashed var(--hd-border);
  background: transparent;
  color: var(--hd-sub);
  font-size: 12px;
  cursor: pointer;
}

.tabNew:hover {
  color: var(--hd-text);
  border-color: var(--hd-accent);
}

.newCollectionInput {
  padding: 4px 10px;
  border-radius: 20px;
  border: 1px solid var(--hd-accent);
  background: var(--hd-surface);
  color: var(--hd-text);
  font-size: 12px;
  outline: none;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.searchBox {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--hd-surface-2);
  border: 1px solid var(--hd-border);
  border-radius: 8px;
  padding: 6px 10px;
  flex: 1;
  max-width: 340px;
}

.searchInput {
  background: transparent;
  border: none;
  outline: none;
  color: var(--hd-text);
  font-size: 13px;
  width: 100%;
}

.searchInput::placeholder {
  color: var(--hd-sub);
}

.loading {
  color: var(--hd-sub);
  font-size: 13px;
  padding: 24px 0;
  text-align: center;
}

.loadingMore {
  color: var(--hd-sub);
  font-size: 12px;
  padding: 12px 0;
  text-align: center;
}

.sentinel {
  height: 1px;
}
```

- [ ] **Step 2: Create `collection.tsx`**

```tsx
// src/frontend/src/routes/collection.tsx
import React, { useDeferredValue, useMemo, useState, useCallback } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { ToastContainer } from '../components/design-system/Toast'
import { Icon } from '../components/design-system/Icon'
import { CollectionGrid } from '../features/collection/components/CollectionGrid'
import {
  collectionsQueryOptions,
  createCollection,
  deleteCollectionEntry,
} from '../features/collection/api'
import { cn } from '../lib/cn'
import { useInfiniteEntries } from '../features/collection/hooks/useInfiniteEntries'
import { useToast } from '../lib/useToast'
import styles from './Collection.module.css'

export const Route = createFileRoute('/collection')({
  component: CollectionCatalogPage,
})

type CatalogTab = 'all' | 'owned' | 'wishlist'

const CATALOG_TABS: { value: CatalogTab; label: string }[] = [
  { value: 'all',      label: 'All' },
  { value: 'owned',    label: 'Owned' },
  { value: 'wishlist', label: 'Wishlist' },
]

function CollectionCatalogPage() {
  const queryClient = useQueryClient()
  const { toasts, toast } = useToast()
  const [query, setQuery] = useState('')
  const [catalogTab, setCatalogTab] = useState<CatalogTab>('all')
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null)
  const [newCollectionName, setNewCollectionName] = useState('')
  const [creatingNew, setCreatingNew] = useState(false)

  const deferredQuery = useDeferredValue(query)

  const { data: collections = [] } = useQuery(collectionsQueryOptions())
  const activeCollectionId = selectedCollectionId ?? collections[0]?.collection_id ?? null

  const {
    allEntries: entries,
    isFetchingMore,
    hasMore,
    removeEntry,
    sentinelRef,
  } = useInfiniteEntries(activeCollectionId)

  const isLoading = entries.length === 0 && isFetchingMore

  const filtered = useMemo(() => {
    let result = entries

    if (catalogTab === 'owned')    result = result.filter((e) => !e.is_wishlist)
    if (catalogTab === 'wishlist') result = result.filter((e) => e.is_wishlist)

    if (deferredQuery.trim()) {
      const q = deferredQuery.toLowerCase()
      result = result.filter(
        (e) => e.card_name.toLowerCase().includes(q) || e.set_code.toLowerCase().includes(q),
      )
    }

    return result
  }, [entries, catalogTab, deferredQuery])

  async function handleRemove(itemId: string) {
    if (!activeCollectionId) return
    await deleteCollectionEntry(activeCollectionId, itemId)
    removeEntry(itemId)
    toast('Card removed')
  }

  async function handleCreateCollection() {
    if (!newCollectionName.trim()) return
    const col = await createCollection(newCollectionName.trim())
    queryClient.invalidateQueries({ queryKey: collectionsQueryOptions().queryKey })
    setSelectedCollectionId(col.collection_id)
    setCreatingNew(false)
    setNewCollectionName('')
  }

  return (
    <AppShell active="collection">
      <TopBar title="Collection" />

      <div className={styles.page}>
        <header className={styles.header}>
          <div className={styles.titleBlock}>
            <div className={styles.eyebrow}>automana / collection</div>
            <h1 className={styles.title}>Your Collection</h1>
          </div>
        </header>

        <div className={styles.collectionTabRow}>
          {collections.map((col) => (
            <button
              key={col.collection_id}
              className={cn(
                styles.collectionTab,
                col.collection_id === activeCollectionId && styles.collectionTabActive,
              )}
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

        <div className={styles.tabRow}>
          {CATALOG_TABS.map((t) => (
            <button
              key={t.value}
              className={cn(styles.tab, catalogTab === t.value && styles.tabActive)}
              onClick={() => setCatalogTab(t.value)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className={styles.toolbar}>
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
        </div>

        {isLoading ? (
          <div className={styles.loading}>Loading…</div>
        ) : (
          <CollectionGrid
            entries={filtered}
            onRemove={handleRemove}
            showFinancials={false}
          />
        )}

        {isFetchingMore && <div className={styles.loadingMore}>Loading more…</div>}
        {hasMore && !isFetchingMore && <div ref={sentinelRef} className={styles.sentinel} />}
      </div>

      <ToastContainer toasts={toasts} />
    </AppShell>
  )
}
```

- [ ] **Step 3: Run TypeScript check**

```bash
cd src/frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/routes/collection.tsx \
        src/frontend/src/routes/Collection.module.css
git commit -m "feat: add /collection route — card catalog with owned/wishlist tabs"
```

---

## Task 12: Sidebar + routeTree — add Collection nav entry

**Files:**
- Modify: `src/frontend/src/components/layout/Sidebar.tsx`
- Modify: `src/frontend/src/routeTree.gen.ts`

- [ ] **Step 1: Add `cards` icon entry to `NAV_ITEMS` in Sidebar**

In `Sidebar.tsx`, update `NAV_ITEMS`:

```tsx
const NAV_ITEMS: NavItem[] = [
  { kind: 'search',   label: 'Search',     id: 'search'     },
  { kind: 'wallet',   label: 'Portfolio',  id: 'portfolio'  },
  { kind: 'cards',    label: 'Collection', id: 'collection' },
  { kind: 'bag',      label: 'Listings',   id: 'listings'   },
  { kind: 'tag',      label: 'eBay',       id: 'ebay'       },
]
```

- [ ] **Step 2: Update `routeTree.gen.ts`**

Add the import at the top (near line 14, after the Portfolio import):

```ts
import { Route as CollectionRouteImport } from './routes/collection'
```

Add the route registration (after the PortfolioRoute block, around line 44):

```ts
const CollectionRoute = CollectionRouteImport.update({
  id: '/collection',
  path: '/collection',
  getParentRoute: () => rootRouteImport,
} as any)
```

Add `CollectionRoute` to the route array and all type maps. Run:

```bash
grep -n "PortfolioRoute\|'/portfolio'" src/frontend/src/routeTree.gen.ts
```

For every place `PortfolioRoute` appears in arrays (`routeTree`, `routesByFileId`, etc.) and type maps (`RoutesByPath`, `FileRoutesByPath`, etc.), add a parallel `CollectionRoute` entry with path `/collection`. Mirror exactly the pattern used for `PortfolioRoute`.

- [ ] **Step 3: Run TypeScript check**

```bash
cd src/frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors.

- [ ] **Step 4: Run full frontend test suite**

```bash
cd src/frontend && npx vitest run 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/components/layout/Sidebar.tsx \
        src/frontend/src/routeTree.gen.ts
git commit -m "feat(nav): add Collection sidebar entry and routeTree registration"
```

---

## Task 13: Verify and final commit

- [ ] **Step 1: Check no stale `/collection` references in wrong places**

```bash
grep -rn "to: '/collection'\|to=\"/collection\"" src/frontend/src \
  | grep -v "routes/collection.tsx\|Sidebar.tsx\|routeTree"
```

Expected: no output (only the route definition and nav should reference `/collection`).

- [ ] **Step 2: Verify no stale `CollectionRoute`-related TypeScript errors**

```bash
cd src/frontend && npx tsc --noEmit 2>&1
```

Expected: no errors.

- [ ] **Step 3: Run full frontend test suite**

```bash
cd src/frontend && npx vitest run 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 4: Run backend tests**

```bash
cd src/automana && python -m pytest tests/ -x -q --tb=short 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 5: Final acceptance check (manual)**

Navigate to `/collection` in the browser:
- Sidebar shows cards icon between Portfolio and Listings
- Page loads "Your Collection" heading, eyebrow "automana / collection"
- "All / Owned / Wishlist" tabs render and filter correctly
- "Search" bar filters by card name / set code
- Collection tabs (if user has multiple collections) work
- Clicking "+" adds cards with owned/wishlist toggle in the popover
- Portfolio at `/portfolio` still works and excludes wishlist entries
