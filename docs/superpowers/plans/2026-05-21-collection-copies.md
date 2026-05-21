# Collection Copies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to own multiple physical copies of the same card (same version, finish, condition) in a collection, each tracked independently with its own purchase price, date, and status.

**Architecture:** Drop the DB unique constraint on `(collection_id, unique_card_id, finish_id, condition)` so each `add_entry` INSERT creates a new independent row. The `/entries` API returns flat rows unchanged. The frontend groups entries by `(card_version_id, finish, condition)` client-side, rendering one tile per group with a `×N` badge and an expandable mini-row list per copy.

**Tech Stack:** PostgreSQL (asyncpg), Python repository layer, React 18 + TypeScript, Vitest + React Testing Library

---

## File Map

**Create:**
- `src/automana/database/SQL/migrations/migration_43_drop_collection_items_unique_constraint.sql`
- `src/frontend/src/features/collection/groupEntries.ts`
- `src/frontend/src/features/collection/groupEntries.test.ts`

**Modify:**
- `src/automana/core/repositories/card_catalog/collection_repository.py` — remove `ON CONFLICT` clause from `add_entry`, remove `get_entry_by_key`
- `src/frontend/src/features/collection/components/CollectionGrid.tsx` — render groups, `×N` badge, expandable mini-rows
- `src/frontend/src/features/collection/components/CollectionGrid.module.css` — new classes for copy badge, expand button, copy list rows
- `src/frontend/src/features/collection/components/AddToCollectionPopover.tsx` — add optional `existingCopies` prop
- `src/frontend/src/features/collection/components/__tests__/CollectionGrid.test.tsx` — replace tests for grouped rendering
- `src/frontend/src/features/collection/components/__tests__/AddToCollectionPopover.test.tsx` — add existingCopies tests
- `src/frontend/src/features/cards/components/SearchResults.tsx` — compute and pass `existingCopies` to the popover

---

## Task 1: Create feature branch

**Files:** none

- [ ] **Step 1: Create and check out the branch**

```bash
git checkout dev && git pull origin dev
git checkout -b feat/collection-copies
```

Expected: prompt shows `feat/collection-copies`.

- [ ] **Step 2: Confirm clean state**

```bash
git status
```

Expected: `nothing to commit, working tree clean`

---

## Task 2: DB migration — drop unique constraint

**Files:**
- Create: `src/automana/database/SQL/migrations/migration_43_drop_collection_items_unique_constraint.sql`

- [ ] **Step 1: Create the migration file**

```sql
-- migration_43: allow multiple copies of the same card per collection
--
-- The unique constraint (collection_id, unique_card_id, finish_id, condition)
-- prevented a user from owning more than one physical copy of the same printing
-- in the same condition. Dropping it lets each INSERT create a new independent
-- row, enabling per-copy price/date/status tracking.
--
-- Existing rows are unaffected — they were already unique before this migration.

ALTER TABLE user_collection.collection_items
    DROP CONSTRAINT uq_collection_card_finish_condition;
```

Save to `src/automana/database/SQL/migrations/migration_43_drop_collection_items_unique_constraint.sql`.

- [ ] **Step 2: Apply the migration**

```bash
docker exec -i automana-postgres-dev psql -U automana_admin automana \
  < src/automana/database/SQL/migrations/migration_43_drop_collection_items_unique_constraint.sql
```

Expected output: `ALTER TABLE`

- [ ] **Step 3: Verify the constraint is gone**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -c "\d user_collection.collection_items"
```

Expected: no row mentioning `uq_collection_card_finish_condition` in the constraint list.

- [ ] **Step 4: Verify existing data is intact**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -c "SELECT COUNT(*) FROM user_collection.collection_items;"
```

Expected: same count as before; no rows deleted.

- [ ] **Step 5: Commit**

```bash
git add src/automana/database/SQL/migrations/migration_43_drop_collection_items_unique_constraint.sql
git commit -m "feat(db): migration_43 drop collection_items unique constraint to allow multiple copies"
```

---

## Task 3: Repository — remove conflict logic and get_entry_by_key

**Files:**
- Modify: `src/automana/core/repositories/card_catalog/collection_repository.py`

- [ ] **Step 1: Replace `add_entry` — remove the ON CONFLICT clause**

Open `src/automana/core/repositories/card_catalog/collection_repository.py`.

Replace the `add_entry` method body with this (the only change is removing the `ON CONFLICT ... DO NOTHING` line):

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
) -> Optional[dict]:
    query = """
        INSERT INTO user_collection.collection_items
            (collection_id, unique_card_id, finish_id, condition,
             purchase_price, currency_code, purchase_date, language_id,
             status, ebay_item_id)
        SELECT $1, $3, $4, $5, $6, $7, $8, $9, $10, $11
        FROM user_collection.collections
        WHERE collection_id = $1 AND user_id = $2
        RETURNING item_id, collection_id, unique_card_id AS card_version_id,
                  finish_id, condition, purchase_price, currency_code,
                  purchase_date, language_id, status, ebay_item_id;
    """
    rows = await self.execute_query(
        query,
        (collection_id, user_id, card_version_id, finish_id, condition,
         purchase_price, currency_code, purchase_date, language_id,
         status, ebay_item_id),
    )
    return dict(rows[0]) if rows else None
```

- [ ] **Step 2: Delete `get_entry_by_key`**

Remove the entire `get_entry_by_key` method (the one that queries by `collection_id, card_version_id, finish_id, condition`). It is no longer needed — `add_entry` always returns the new row directly, and a key-based lookup is ambiguous once duplicates are allowed.

- [ ] **Step 3: Smoke-test the backend starts cleanly**

```bash
dcdev-automana up -d --build backend
dcdev-automana logs --tail=20 backend
```

Expected: no `AttributeError` or `ImportError`; backend listening on port 8000.

- [ ] **Step 4: Verify duplicate inserts succeed**

Using the API testing flow from `docs/TESTING_API_FLOW.md` (create a throwaway user, authenticate, create a collection), add the same card twice:

```bash
# First add
curl -s -X POST http://localhost:8000/catalog/mtg/collection/<collection_id>/entries \
  -H "Content-Type: application/json" -b "session_id=<session>" \
  -d '{"set_code":"lea","collector_number":"265","condition":"NM","finish":"NONFOIL","purchase_price":"5.00"}'

# Second add — same card, same condition/finish
curl -s -X POST http://localhost:8000/catalog/mtg/collection/<collection_id>/entries \
  -H "Content-Type: application/json" -b "session_id=<session>" \
  -d '{"set_code":"lea","collector_number":"265","condition":"NM","finish":"NONFOIL","purchase_price":"7.00"}'
```

Expected: two responses each containing a distinct `item_id`.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/card_catalog/collection_repository.py
git commit -m "feat(backend): allow duplicate collection entries — remove unique conflict clause"
```

---

## Task 4: groupEntries utility

**Files:**
- Create: `src/frontend/src/features/collection/groupEntries.ts`
- Create: `src/frontend/src/features/collection/groupEntries.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `src/frontend/src/features/collection/groupEntries.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { groupEntries } from './groupEntries'
import type { CollectionEntry } from './api'

const makeEntry = (overrides: Partial<CollectionEntry> = {}): CollectionEntry => ({
  item_id: 'item-1',
  card_version_id: 'card-a',
  card_name: 'Sol Ring',
  set_code: 'lea',
  collector_number: '265',
  finish: 'NONFOIL',
  condition: 'NM',
  purchase_price: '5.00',
  purchase_date: '2024-01-01',
  currency_code: 'USD',
  price: null,
  price_change_1d: 0,
  status: 'purchased',
  ...overrides,
})

describe('groupEntries', () => {
  it('returns empty array for empty input', () => {
    expect(groupEntries([])).toEqual([])
  })

  it('groups entries with identical card_version_id, finish, and condition', () => {
    const entries = [
      makeEntry({ item_id: 'item-1' }),
      makeEntry({ item_id: 'item-2' }),
      makeEntry({ item_id: 'item-3' }),
    ]
    const groups = groupEntries(entries)
    expect(groups).toHaveLength(1)
    expect(groups[0].copies).toHaveLength(3)
  })

  it('creates separate groups for different conditions', () => {
    const entries = [
      makeEntry({ item_id: 'item-1', condition: 'NM' }),
      makeEntry({ item_id: 'item-2', condition: 'LP' }),
    ]
    expect(groupEntries(entries)).toHaveLength(2)
  })

  it('creates separate groups for different finishes', () => {
    const entries = [
      makeEntry({ item_id: 'item-1', finish: 'NONFOIL' }),
      makeEntry({ item_id: 'item-2', finish: 'FOIL' }),
    ]
    expect(groupEntries(entries)).toHaveLength(2)
  })

  it('creates separate groups for different card_version_ids', () => {
    const entries = [
      makeEntry({ item_id: 'item-1', card_version_id: 'card-a' }),
      makeEntry({ item_id: 'item-2', card_version_id: 'card-b' }),
    ]
    expect(groupEntries(entries)).toHaveLength(2)
  })

  it('sets representative to the first entry in the group', () => {
    const entries = [makeEntry({ item_id: 'item-1' }), makeEntry({ item_id: 'item-2' })]
    expect(groupEntries(entries)[0].representative.item_id).toBe('item-1')
  })

  it('groups interleaved entries into the same bucket', () => {
    const entries = [
      makeEntry({ item_id: 'item-1', card_version_id: 'card-a' }),
      makeEntry({ item_id: 'item-2', card_version_id: 'card-b' }),
      makeEntry({ item_id: 'item-3', card_version_id: 'card-a' }),
    ]
    const groups = groupEntries(entries)
    expect(groups).toHaveLength(2)
    expect(groups[0].copies.map((c) => c.item_id)).toEqual(['item-1', 'item-3'])
    expect(groups[1].copies.map((c) => c.item_id)).toEqual(['item-2'])
  })

  it('builds key as card_version_id:finish:condition', () => {
    const entries = [makeEntry({ card_version_id: 'card-x', finish: 'FOIL', condition: 'LP' })]
    expect(groupEntries(entries)[0].key).toBe('card-x:FOIL:LP')
  })
})
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd src/frontend && npx vitest run src/features/collection/groupEntries.test.ts
```

Expected: `Cannot find module './groupEntries'`

- [ ] **Step 3: Implement groupEntries**

Create `src/frontend/src/features/collection/groupEntries.ts`:

```typescript
import type { CollectionEntry } from './api'

export interface EntryGroup {
  key: string
  representative: CollectionEntry
  copies: CollectionEntry[]
}

export function groupEntries(entries: CollectionEntry[]): EntryGroup[] {
  const map = new Map<string, EntryGroup>()
  for (const entry of entries) {
    const key = `${entry.card_version_id}:${entry.finish}:${entry.condition}`
    if (!map.has(key)) {
      map.set(key, { key, representative: entry, copies: [] })
    }
    map.get(key)!.copies.push(entry)
  }
  return Array.from(map.values())
}
```

- [ ] **Step 4: Run tests — expect all PASS**

```bash
cd src/frontend && npx vitest run src/features/collection/groupEntries.test.ts
```

Expected: 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/collection/groupEntries.ts \
        src/frontend/src/features/collection/groupEntries.test.ts
git commit -m "feat(frontend): add groupEntries utility for collection copy grouping"
```

---

## Task 5: CollectionGrid — grouped tiles, ×N badge, expandable mini-rows

**Files:**
- Modify: `src/frontend/src/features/collection/components/CollectionGrid.tsx`
- Modify: `src/frontend/src/features/collection/components/CollectionGrid.module.css`
- Modify: `src/frontend/src/features/collection/components/__tests__/CollectionGrid.test.tsx`

The current CSS already defines `.badge`, `.removeBtn`, `.cardWrap`, `.cardInfo`, `.cardName`, `.priceRow`, `.price`, `.pl`, `.plUp`, `.plDown`, `.empty`. New classes are added alongside — do not remove existing ones.

The current `CollectionGrid` renders one tile per flat entry with a per-tile remove button. The new version renders one tile per **group** (via `groupEntries`). The remove button moves into the expandable copy list.

- [ ] **Step 1: Write the new failing tests**

Replace the full contents of `src/frontend/src/features/collection/components/__tests__/CollectionGrid.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CollectionGrid } from '../CollectionGrid'
import type { CollectionEntry } from '../../api'

const makeEntry = (overrides: Partial<CollectionEntry> = {}): CollectionEntry => ({
  item_id: 'item-1',
  card_version_id: 'card-a',
  card_name: 'Sol Ring',
  set_code: 'lea',
  collector_number: '265',
  finish: 'NONFOIL',
  condition: 'NM',
  purchase_price: '5.00',
  purchase_date: '2024-01-01',
  currency_code: 'USD',
  price: 10.00,
  price_change_1d: 0,
  status: 'purchased',
  image_normal: null,
  ...overrides,
})

describe('CollectionGrid', () => {
  it('shows empty state when no entries', () => {
    render(<CollectionGrid entries={[]} onRemove={vi.fn()} />)
    expect(screen.getByText(/No cards yet/)).toBeInTheDocument()
  })

  it('renders one tile for a single entry', () => {
    render(<CollectionGrid entries={[makeEntry()]} onRemove={vi.fn()} />)
    expect(screen.getAllByText('Sol Ring')).toHaveLength(1)
  })

  it('renders one tile for multiple copies of the same card', () => {
    const entries = [
      makeEntry({ item_id: 'item-1' }),
      makeEntry({ item_id: 'item-2' }),
      makeEntry({ item_id: 'item-3' }),
    ]
    render(<CollectionGrid entries={entries} onRemove={vi.fn()} />)
    expect(screen.getAllByText('Sol Ring')).toHaveLength(1)
  })

  it('shows ×N badge when there are multiple copies', () => {
    const entries = [
      makeEntry({ item_id: 'item-1' }),
      makeEntry({ item_id: 'item-2' }),
      makeEntry({ item_id: 'item-3' }),
    ]
    render(<CollectionGrid entries={entries} onRemove={vi.fn()} />)
    expect(screen.getByText('×3')).toBeInTheDocument()
  })

  it('does not show ×N badge for a single copy', () => {
    render(<CollectionGrid entries={[makeEntry()]} onRemove={vi.fn()} />)
    expect(screen.queryByText(/×\d/)).not.toBeInTheDocument()
  })

  it('does not show copy list when collapsed', () => {
    const entries = [makeEntry({ item_id: 'item-1' }), makeEntry({ item_id: 'item-2' })]
    render(<CollectionGrid entries={entries} onRemove={vi.fn()} />)
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('shows mini-rows when the tile is expanded', () => {
    const entries = [makeEntry({ item_id: 'item-1' }), makeEntry({ item_id: 'item-2' })]
    render(<CollectionGrid entries={entries} onRemove={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Expand Sol Ring/i }))
    expect(screen.getByRole('list')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('collapses when the expand button is clicked again', () => {
    const entries = [makeEntry({ item_id: 'item-1' }), makeEntry({ item_id: 'item-2' })]
    render(<CollectionGrid entries={entries} onRemove={vi.fn()} />)
    const btn = screen.getByRole('button', { name: /Expand Sol Ring/i })
    fireEvent.click(btn)
    fireEvent.click(btn)
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('calls onRemove with the correct item_id from the copy list', () => {
    const onRemove = vi.fn()
    const entries = [makeEntry({ item_id: 'item-1' }), makeEntry({ item_id: 'item-2' })]
    render(<CollectionGrid entries={entries} onRemove={onRemove} />)
    fireEvent.click(screen.getByRole('button', { name: /Expand Sol Ring/i }))
    const removeBtns = screen.getAllByRole('button', { name: /Remove copy/i })
    fireEvent.click(removeBtns[1])
    expect(onRemove).toHaveBeenCalledWith('item-2')
  })

  it('renders two separate tiles for different card versions', () => {
    const entries = [
      makeEntry({ item_id: 'item-1', card_version_id: 'card-a', card_name: 'Sol Ring' }),
      makeEntry({ item_id: 'item-2', card_version_id: 'card-b', card_name: 'Black Lotus' }),
    ]
    render(<CollectionGrid entries={entries} onRemove={vi.fn()} />)
    expect(screen.getByText('Sol Ring')).toBeInTheDocument()
    expect(screen.getByText('Black Lotus')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd src/frontend && npx vitest run src/features/collection/components/__tests__/CollectionGrid.test.tsx
```

Expected: multiple failures about missing grouped rendering.

- [ ] **Step 3: Add new CSS classes to CollectionGrid.module.css**

Append to `src/frontend/src/features/collection/components/CollectionGrid.module.css`:

```css
.copyBadge {
  position: absolute;
  top: 0.35rem;
  left: 0.35rem;
  background: var(--hd-surface-2, #1f2937);
  color: var(--hd-sub);
  font-size: 9px;
  font-family: var(--font-mono);
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  pointer-events: none;
  z-index: 2;
}

.expandBtn {
  all: unset;
  display: block;
  width: 100%;
  cursor: pointer;
}

.copyList {
  list-style: none;
  margin: 0.3rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.copyRow {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
}

.copyPrice {
  flex: 1;
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--hd-text);
}
```

- [ ] **Step 4: Rewrite CollectionGrid.tsx**

Replace the full contents of `src/frontend/src/features/collection/components/CollectionGrid.tsx`:

```tsx
import { useState } from 'react'
import { CardArt } from '../../../components/design-system/CardArt'
import { formatUSD } from '../../../lib/format'
import type { CollectionEntry } from '../api'
import { groupEntries } from '../groupEntries'
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

function toCardArtFinish(finish: CollectionEntry['finish']): 'non-foil' | 'foil' | 'etched' {
  if (finish === 'NONFOIL') return 'non-foil'
  if (finish === 'FOIL') return 'foil'
  return 'etched'
}

export function CollectionGrid({ entries, onRemove }: CollectionGridProps) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null)
  const groups = groupEntries(entries)

  if (groups.length === 0) {
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
      {groups.map((group, i) => {
        const { key, representative: entry, copies } = group
        const isExpanded = expandedKey === key
        const pl =
          entry.price != null ? entry.price - Number(entry.purchase_price) : null
        const plLabel =
          pl != null ? `${pl >= 0 ? '+' : '-'}${formatUSD(Math.abs(pl))}` : null

        return (
          <div key={key} className={styles.cardWrap}>
            {copies.length > 1 && (
              <span className={styles.copyBadge}>×{copies.length}</span>
            )}
            <button
              className={styles.expandBtn}
              onClick={() => setExpandedKey(isExpanded ? null : key)}
              aria-label={
                isExpanded
                  ? `Collapse ${entry.card_name} copies`
                  : `Expand ${entry.card_name} copies`
              }
            >
              <CardArt
                name={entry.card_name}
                w="100%"
                hue={(i * 47) % 360}
                label={false}
                imageUrl={entry.image_normal ?? undefined}
                finish={toCardArtFinish(entry.finish)}
              />
            </button>
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
                <span className={styles.price}>{formatUSD(entry.price)}</span>
                {plLabel != null && (
                  <span className={`${styles.pl} ${pl! >= 0 ? styles.plUp : styles.plDown}`}>
                    {plLabel}
                  </span>
                )}
              </div>
            </div>
            {isExpanded && (
              <ul className={styles.copyList}>
                {copies.map((copy) => (
                  <li key={copy.item_id} className={styles.copyRow}>
                    <span className={styles.badge}>{copy.condition}</span>
                    <span className={styles.copyPrice}>
                      {formatUSD(Number(copy.purchase_price))}
                    </span>
                    <span className={styles.badge}>{copy.status}</span>
                    <button
                      className={styles.removeBtn}
                      onClick={() => onRemove(copy.item_id)}
                      aria-label={`Remove copy of ${copy.card_name}`}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 5: Run tests — expect all PASS**

```bash
cd src/frontend && npx vitest run src/features/collection/components/__tests__/CollectionGrid.test.tsx
```

Expected: all 10 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/collection/components/CollectionGrid.tsx \
        src/frontend/src/features/collection/components/CollectionGrid.module.css \
        src/frontend/src/features/collection/components/__tests__/CollectionGrid.test.tsx
git commit -m "feat(frontend): grouped collection grid with xN badge and expandable copy rows"
```

---

## Task 6: AddToCollectionPopover — show existing copy count

**Files:**
- Modify: `src/frontend/src/features/collection/components/AddToCollectionPopover.tsx`
- Modify: `src/frontend/src/features/collection/components/__tests__/AddToCollectionPopover.test.tsx`
- Modify: `src/frontend/src/features/cards/components/SearchResults.tsx`

`existingCopies` is optional (defaults to 0) so all existing tests continue to pass without modification.

- [ ] **Step 1: Add two new tests to the existing AddToCollectionPopover test suite**

Open `src/frontend/src/features/collection/components/__tests__/AddToCollectionPopover.test.tsx`.

The existing tests use `COLLECTIONS` and the `AddToCollectionPopover` component. **Append** these two tests to the existing `describe` block without removing any existing tests:

```tsx
  it('shows "You already have N" when existingCopies > 0', () => {
    render(
      <AddToCollectionPopover
        cardVersionId="cv1"
        cardName="Ragavan"
        finish="non-foil"
        collections={COLLECTIONS}
        existingCopies={3}
        onAdd={vi.fn()}
        onClose={vi.fn()}
      />
    )
    expect(screen.getByText(/You already have 3/)).toBeInTheDocument()
  })

  it('does not show existing copies text when existingCopies is 0', () => {
    render(
      <AddToCollectionPopover
        cardVersionId="cv1"
        cardName="Ragavan"
        finish="non-foil"
        collections={COLLECTIONS}
        existingCopies={0}
        onAdd={vi.fn()}
        onClose={vi.fn()}
      />
    )
    expect(screen.queryByText(/You already have/)).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: Run tests — expect the two new tests FAIL, existing tests PASS**

```bash
cd src/frontend && npx vitest run src/features/collection/components/__tests__/AddToCollectionPopover.test.tsx
```

Expected: 5 existing tests pass, 2 new tests fail.

- [ ] **Step 3: Update AddToCollectionPopover.tsx**

In `src/frontend/src/features/collection/components/AddToCollectionPopover.tsx`:

**1. Add `existingCopies` to the Props interface** (optional, defaults to 0):

```tsx
interface Props {
  cardVersionId: string
  cardName: string
  finish: string
  collections: Collection[]
  existingCopies?: number
  onAdd: (params: { collectionId: string; condition: CollectionEntry['condition']; finish: FinishOut }) => void
  onClose: () => void
}
```

**2. Destructure it with a default of 0**:

```tsx
export function AddToCollectionPopover({
  cardName,
  finish,
  collections,
  existingCopies = 0,
  onAdd,
  onClose,
}: Props) {
```

**3. Add the count hint just before `<div className={styles.actions}>`** in the main return (the branch that shows conditions/finish/collections — not the "no collections" early return):

```tsx
{existingCopies > 0 && (
  <p className={styles.label}>
    You already have <strong>{existingCopies}</strong> — add another?
  </p>
)}
```

- [ ] **Step 4: Run tests — expect all 7 PASS**

```bash
cd src/frontend && npx vitest run src/features/collection/components/__tests__/AddToCollectionPopover.test.tsx
```

Expected: all 7 tests pass.

- [ ] **Step 5: Wire up existingCopies in SearchResults.tsx**

Open `src/frontend/src/features/cards/components/SearchResults.tsx`.

The `AddToCollectionPopover` is rendered at the bottom of `renderCard`. It currently doesn't receive `existingCopies`.

**Add a query for the first collection's entries** (loaded lazily when the popover is open):

After the existing `const { data: collections = [] } = useQuery(...)` line, add:

```tsx
const firstCollectionId = collections[0]?.collection_id ?? ''
const { data: firstCollectionEntries = [] } = useQuery({
  ...collectionEntriesQueryOptions(firstCollectionId),
  enabled: Boolean(firstCollectionId) && isAuthed && Boolean(addTarget),
})
```

**Compute `existingCopies`** inside `renderCard`, just before the `AddToCollectionPopover` JSX:

```tsx
const existingCopies = firstCollectionEntries.filter(
  (e) => e.card_version_id === card.card_version_id
).length
```

**Pass the prop** to the popover:

```tsx
<AddToCollectionPopover
  cardVersionId={card.card_version_id}
  cardName={card.card_name}
  finish={card.finish}
  collections={collections as Collection[]}
  existingCopies={existingCopies}
  onAdd={handleAdd}
  onClose={() => setAddTarget(null)}
/>
```

- [ ] **Step 6: Run the full frontend test suite**

```bash
cd src/frontend && npx vitest run
```

Expected: all tests pass. Fix any TypeScript errors surfaced by the compiler.

- [ ] **Step 7: Commit**

```bash
git add src/frontend/src/features/collection/components/AddToCollectionPopover.tsx \
        src/frontend/src/features/collection/components/__tests__/AddToCollectionPopover.test.tsx \
        src/frontend/src/features/cards/components/SearchResults.tsx
git commit -m "feat(frontend): AddToCollectionPopover shows existing copy count"
```

---

## Task 7: End-to-end verification

**Files:** none

- [ ] **Step 1: Start the full dev stack**

```bash
dcdev-automana up -d
cd src/frontend && npm run dev
```

Open `http://localhost:5173` in a browser.

- [ ] **Step 2: Add two copies of the same card**

1. Go to Set Browser, find any card.
2. Click `+ Add` → add it (NM, NONFOIL) to a collection.
3. Click `+ Add` on the same card again.
4. Confirm the popover shows **"You already have 1 — add another?"**.
5. Click Add to Collection.

- [ ] **Step 3: Verify the collection grid shows a grouped tile**

Navigate to the Collection page:
- Confirm **one tile** appears for that card (not two).
- Confirm the `×2` badge is visible top-left.
- Click the tile → mini-row list appears with 2 rows (condition, price, status, ×).
- Click the tile again → list collapses.

- [ ] **Step 4: Verify remove works correctly**

Expand the tile. Click `×` on one row:
- That copy disappears.
- Badge updates to `×1`, then disappears when the last copy is removed.

- [ ] **Step 5: Run the full test suite one final time**

```bash
cd src/frontend && npx vitest run
```

Expected: all tests pass.

- [ ] **Step 6: Push the branch**

```bash
git push -u origin feat/collection-copies
```
