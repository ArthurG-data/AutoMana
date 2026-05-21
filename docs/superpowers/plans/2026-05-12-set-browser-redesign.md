# Set Browser Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the set browser from compact rows to an icon-focused responsive grid with year and parent-child grouping.

**Architecture:** Backend adds `parent_set_code` field to SetBrowseItem; frontend rewrites SetBrowser with grid layout, introduces SetCard component for icon-focused design, implements year/parent-child grouping logic, and adds responsive CSS.

**Tech Stack:** React (SetBrowser, SetCard), CSS Grid, Pydantic (models), PostgreSQL (SQL query), React Query (existing hook).

---

## File Structure

**Backend:**
- `src/automana/features/cards/api/models.py` — Add `parent_set_code: str | None` to `SetBrowseItem`
- `src/automana/features/cards/repositories/set_repository.py` — Update `browse()` SQL query to include parent_set_code
- `tests/integration/api/test_set_browse_endpoint.py` — Verify response includes parent_set_code

**Frontend:**
- `src/frontend/src/features/cards/components/SetBrowser.tsx` — Rewrite main component with grouping logic and responsive grid
- `src/frontend/src/features/cards/components/SetCard.tsx` — New component for individual set card (parent and child variants)
- `src/frontend/src/features/cards/components/SetBrowser.module.css` — Replace row styles with responsive grid + nesting styles
- `src/frontend/src/features/cards/__tests__/SetBrowser.test.tsx` — Unit tests for grouping logic
- `src/frontend/src/features/cards/__tests__/SetCard.test.tsx` — Unit tests for card rendering

---

## Tasks

### Task 1: Add parent_set_code to SetBrowseItem Model

**Files:**
- Modify: `src/automana/features/cards/api/models.py`

- [ ] **Step 1: Open the SetBrowseItem model**

Navigate to `src/automana/features/cards/api/models.py` and locate the `SetBrowseItem` class.

- [ ] **Step 2: Add parent_set_code field**

Add this field to the model (after `icon_svg_uri`):

```python
parent_set_code: str | None = None
```

Full model should look like:
```python
class SetBrowseItem(BaseModel):
    set_id: UUID
    set_name: str
    set_code: str
    set_type: str
    card_count: int
    released_at: date
    icon_svg_uri: str | None = None
    parent_set_code: str | None = None
```

- [ ] **Step 3: Commit**

```bash
git add src/automana/features/cards/api/models.py
git commit -m "feat(models): add parent_set_code to SetBrowseItem"
```

---

### Task 2: Update set_repository.browse() SQL Query

**Files:**
- Modify: `src/automana/features/cards/repositories/set_repository.py:browse()`

- [ ] **Step 1: Locate the browse() method**

Open `src/automana/features/cards/repositories/set_repository.py` and find the `browse()` method. It should currently have a SQL query selecting from `joined_set_materialized`.

- [ ] **Step 2: Update the SELECT clause to include parent_set_code**

Replace the current query with:

```python
async def browse(self) -> list[SetBrowseItem]:
    query = """
    SELECT
        vsm.set_id,
        vsm.set_name,
        vsm.set_code,
        vsm.set_type,
        vsm.card_count,
        vsm.released_at,
        iqr.icon_query_uri AS icon_svg_uri,
        parent.set_code AS parent_set_code
    FROM card_catalog.joined_set_materialized vsm
    LEFT JOIN card_catalog.joined_set_materialized parent 
        ON parent.set_id = vsm.parent_set_id
    LEFT JOIN card_catalog.icon_set ics ON ics.set_id = vsm.set_id
    LEFT JOIN card_catalog.icon_query_ref iqr ON iqr.icon_query_id = ics.icon_query_id
    WHERE vsm.digital = FALSE
    ORDER BY vsm.released_at DESC
    """
    rows = await self.db.fetch(query)
    return [SetBrowseItem(**row) for row in rows]
```

**Note:** This assumes `joined_set_materialized` has a `parent_set_id` column. If not, check the schema and adjust the join accordingly (may need to join on `card_catalog.sets` instead).

- [ ] **Step 3: Commit**

```bash
git add src/automana/features/cards/repositories/set_repository.py
git commit -m "feat(set-repository): include parent_set_code in browse() query"
```

---

### Task 3: Verify Backend Changes (Integration Test)

**Files:**
- Modify: `tests/integration/api/test_set_browse_endpoint.py`

- [ ] **Step 1: Open the integration test file**

Navigate to `tests/integration/api/test_set_browse_endpoint.py`.

- [ ] **Step 2: Add test to verify parent_set_code is returned**

Add this test to the file:

```python
async def test_set_browse_includes_parent_set_code(client: TestClient):
    response = client.get("/api/v1/set-reference/browse")
    assert response.status_code == 200
    data = response.json()
    
    # At least one item in response
    assert len(data) > 0
    
    # Check shape: all items have parent_set_code field (nullable)
    for item in data:
        assert "parent_set_code" in item
        assert isinstance(item["parent_set_code"], (str, type(None)))
        
    # Parent sets should have parent_set_code = null
    parent_sets = [item for item in data if item["parent_set_code"] is None and item["set_type"] == "expansion"]
    assert len(parent_sets) > 0  # At least one parent expansion set
```

- [ ] **Step 3: Run the test**

```bash
cd /home/arthur/projects/AutoMana
pytest tests/integration/api/test_set_browse_endpoint.py::test_set_browse_includes_parent_set_code -v
```

Expected: PASS (all sets have parent_set_code field, parents have null).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/api/test_set_browse_endpoint.py
git commit -m "test(set-browse): verify parent_set_code is included in response"
```

---

### Task 4: Create SetCard Component (Frontend)

**Files:**
- Create: `src/frontend/src/features/cards/components/SetCard.tsx`

- [ ] **Step 1: Create the file with icon-focused card layout**

Write `src/frontend/src/features/cards/components/SetCard.tsx`:

```typescript
import { useState } from 'react'
import type { SetBrowseItem } from '../types'
import styles from './SetCard.module.css'

const FALLBACK_ICON = (
  <svg className={styles.iconFallback} viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="2" fill="none"/>
  </svg>
)

function iconUrl(set: SetBrowseItem): string {
  return set.icon_svg_uri || `https://svgs.scryfall.io/sets/${set.set_code.toLowerCase()}.svg`
}

function formatDate(date: string | undefined): string {
  if (!date) return ''
  const [year, month, day] = date.split('-')
  const monthMap: Record<string, string> = {
    '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr', '05': 'May', '06': 'Jun',
    '07': 'Jul', '08': 'Aug', '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec'
  }
  return `${monthMap[month]} ${day}`
}

function prettyType(t: string): string {
  const labels: Record<string, string> = {
    expansion: 'Expansion',
    core: 'Core',
    masters: 'Masters',
    commander: 'Commander',
    draft_innovation: 'Draft Innovation',
    alchemy: 'Alchemy',
    funny: 'Funny',
    promo: 'Promo',
    starter: 'Starter',
    duel_deck: 'Duel Deck',
    from_the_vault: 'From the Vault',
    premium_deck: 'Premium Deck',
    spellbook: 'Spellbook',
    archenemy: 'Archenemy',
    planechase: 'Planechase',
    vanguard: 'Vanguard',
    treasure_chest: 'Treasure Chest',
    box: 'Box Set',
    token: 'Token',
    memorabilia: 'Memorabilia',
    jumpstart: 'Jumpstart',
    minigame: 'Minigame',
  }
  return labels[t] ?? t.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

interface SetCardProps {
  set: SetBrowseItem
  isChild?: boolean
  onSelect: (code: string) => void
}

export function SetCard({ set, isChild = false, onSelect }: SetCardProps) {
  const [iconBroken, setIconBroken] = useState(false)
  
  return (
    <button 
      className={`${styles.card} ${isChild ? styles.childCard : ''}`}
      onClick={() => onSelect(set.set_code)}
      type="button"
    >
      <div className={styles.icon}>
        {iconBroken
          ? FALLBACK_ICON
          : <img src={iconUrl(set)} alt="" aria-hidden onError={() => setIconBroken(true)} />}
      </div>
      
      <div className={styles.code}>{set.set_code}</div>
      
      <div className={styles.type}>{prettyType(set.set_type)}</div>
      
      <div className={styles.count}>{set.card_count}</div>
      
      {set.released_at && (
        <div className={styles.date}>{formatDate(set.released_at.toString())}</div>
      )}
    </button>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add src/frontend/src/features/cards/components/SetCard.tsx
git commit -m "feat(SetCard): create icon-focused card component"
```

---

### Task 5: Create SetCard.module.css

**Files:**
- Create: `src/frontend/src/features/cards/components/SetCard.module.css`

- [ ] **Step 1: Create the CSS module**

Write `src/frontend/src/features/cards/components/SetCard.module.css`:

```css
.card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  background: transparent;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: center;
  aspect-ratio: 1;
}

.card:hover {
  border-color: var(--accent-color, #5b8dee);
  background-color: rgba(91, 141, 238, 0.03);
  transform: scale(1.02);
}

.card:active {
  transform: scale(0.98);
}

.icon {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.icon img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.iconFallback {
  width: 100%;
  height: 100%;
  opacity: 0.5;
}

.code {
  font-family: 'Courier New', monospace;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #000);
}

.type {
  font-size: 11px;
  color: var(--text-secondary, #666);
  background: var(--accent-bg, rgba(91, 141, 238, 0.1));
  padding: 2px 6px;
  border-radius: 3px;
  white-space: nowrap;
}

.count {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: var(--text-muted, #999);
}

.date {
  font-size: 10px;
  color: var(--text-muted, #999);
  margin-top: 2px;
}

.childCard {
  opacity: 0.8;
  padding: 8px;
  aspect-ratio: auto;
  min-height: 120px;
}

.childCard:hover {
  opacity: 1;
}

.childCard .icon {
  width: 32px;
  height: 32px;
}

.childCard .code {
  font-size: 12px;
}

.childCard .type {
  font-size: 10px;
}

.childCard .count {
  font-size: 11px;
}
```

- [ ] **Step 2: Commit**

```bash
git add src/frontend/src/features/cards/components/SetCard.module.css
git commit -m "feat(SetCard): add icon-focused styling"
```

---

### Task 6: Rewrite SetBrowser Component

**Files:**
- Modify: `src/frontend/src/features/cards/components/SetBrowser.tsx`

- [ ] **Step 1: Replace the entire SetBrowser component**

Open `src/frontend/src/features/cards/components/SetBrowser.tsx` and replace with:

```typescript
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { setBrowseQueryOptions } from '../api'
import type { SetBrowseItem } from '../types'
import { SetCard } from './SetCard'
import styles from './SetBrowser.module.css'

type GroupBy = 'none' | 'type' | 'year'

interface YearGroup {
  year: string
  sets: SetBrowseItem[]
}

interface SetGroup {
  parent: SetBrowseItem
  children: SetBrowseItem[]
}

function yearOf(released?: string | null): string {
  return released ? released.slice(0, 4) : 'Unknown'
}

function groupByParentChild(sets: SetBrowseItem[]): SetGroup[] {
  const parentMap = new Map<string | null, SetBrowseItem[]>()
  
  for (const set of sets) {
    const parentCode = set.parent_set_code
    if (!parentMap.has(parentCode)) {
      parentMap.set(parentCode, [])
    }
    parentMap.get(parentCode)!.push(set)
  }
  
  const groups: SetGroup[] = []
  const processedChildren = new Set<string>()
  
  for (const set of sets) {
    if (processedChildren.has(set.set_code)) continue
    if (set.parent_set_code !== null) continue
    
    const children = (parentMap.get(set.set_code) || []).filter(s => s.set_code !== set.set_code)
    groups.push({ parent: set, children })
    children.forEach(c => processedChildren.add(c.set_code))
  }
  
  return groups
}

interface SetBrowserProps {
  onSelect: (setCode: string) => void
}

export function SetBrowser({ onSelect }: SetBrowserProps) {
  const { data: sets = [], isLoading, isError } = useQuery(setBrowseQueryOptions())
  const [search, setSearch] = useState('')
  const [selectedTypes, setSelectedTypes] = useState<Set<string>>(new Set())
  const [groupBy, setGroupBy] = useState<GroupBy>('year')

  const availableTypes = useMemo(() => {
    const counts = new Map<string, number>()
    for (const s of sets) counts.set(s.set_type, (counts.get(s.set_type) ?? 0) + 1)
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([type, count]) => ({ type, count }))
  }, [sets])

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase()
    return sets.filter((s) => {
      if (selectedTypes.size > 0 && !selectedTypes.has(s.set_type)) return false
      if (q && !s.set_name.toLowerCase().includes(q) && !s.set_code.toLowerCase().includes(q)) return false
      return true
    })
  }, [sets, selectedTypes, search])

  const grouped = useMemo(() => {
    if (groupBy === 'none') {
      return [{ year: '__all__', sets: visible }]
    }
    
    if (groupBy === 'year') {
      const buckets = new Map<string, SetBrowseItem[]>()
      for (const s of visible) {
        const year = yearOf(s.released_at)
        if (!buckets.has(year)) buckets.set(year, [])
        buckets.get(year)!.push(s)
      }
      const sortedYears = Array.from(buckets.keys()).sort((a, b) => b.localeCompare(a))
      return sortedYears.map((year) => ({
        year,
        sets: buckets.get(year)!,
      }))
    }
    
    // groupBy === 'type'
    const buckets = new Map<string, SetBrowseItem[]>()
    for (const s of visible) {
      const type = s.set_type
      if (!buckets.has(type)) buckets.set(type, [])
      buckets.get(type)!.push(s)
    }
    const sortedTypes = Array.from(buckets.keys()).sort()
    return sortedTypes.map((type) => ({
      year: type,
      sets: buckets.get(type)!,
    }))
  }, [visible, groupBy])

  function toggleType(t: string) {
    setSelectedTypes((prev) => {
      const next = new Set(prev)
      if (next.has(t)) next.delete(t)
      else next.add(t)
      return next
    })
  }

  if (isError) {
    return (
      <div className={styles.wrap}>
        <p className={styles.empty}>Failed to load sets. Please refresh.</p>
      </div>
    )
  }

  return (
    <div className={styles.wrap}>
      <header className={styles.hero}>
        <h1 className={styles.heroTitle}>Browse Magic Sets</h1>
        <span className={styles.heroAccent} aria-hidden />
        <p className={styles.heroSub}>
          {isLoading
            ? 'Loading…'
            : (
              <>
                <strong>{visible.length.toLocaleString()}</strong>
                {selectedTypes.size > 0 && ` of ${sets.length.toLocaleString()}`}
                {' '}sets
              </>
            )}
        </p>
      </header>

      <div className={styles.controls}>
        <div className={styles.searchRow}>
          <svg className={styles.searchIcon} width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <circle cx="11" cy="11" r="7"/>
            <path d="M21 21l-4.35-4.35"/>
          </svg>
          <input
            className={styles.searchInput}
            placeholder="Search sets by name or code…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search sets"
          />
          {search && (
            <button
              type="button"
              className={styles.searchClear}
              onClick={() => setSearch('')}
              aria-label="Clear search"
            >
              ×
            </button>
          )}
        </div>

        <div className={styles.controlBlock}>
          <span className={styles.controlLabel}>Type</span>
          <div className={styles.chipRow}>
            <button
              className={`${styles.chip} ${selectedTypes.size === 0 ? styles.chipActive : ''}`}
              onClick={() => setSelectedTypes(new Set())}
              type="button"
            >
              All
              <span className={styles.chipCount}>{sets.length}</span>
            </button>
            {availableTypes.map(({ type, count }) => (
              <button
                key={type}
                className={`${styles.chip} ${selectedTypes.has(type) ? styles.chipActive : ''}`}
                onClick={() => toggleType(type)}
                type="button"
              >
                {type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                <span className={styles.chipCount}>{count}</span>
              </button>
            ))}
          </div>
        </div>

        <div className={styles.controlBlock}>
          <span className={styles.controlLabel}>Group by</span>
          <div className={styles.chipRow}>
            {(['year', 'type', 'none'] as GroupBy[]).map((g) => (
              <button
                key={g}
                className={`${styles.chip} ${groupBy === g ? styles.chipActive : ''}`}
                onClick={() => setGroupBy(g)}
                type="button"
              >
                {g === 'none' ? 'None' : g === 'type' ? 'Type' : 'Year'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {visible.length === 0 ? (
        <p className={styles.empty}>No sets match the current filters.</p>
      ) : (
        grouped.map((g) => (
          <section key={g.year} className={styles.section}>
            <header className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>{groupBy === 'type' ? g.year.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : g.year}</h2>
              <span className={styles.sectionCount}>{g.sets.length}</span>
            </header>
            <div className={styles.grid}>
              {groupByParentChild(g.sets).map((group) => (
                <div key={group.parent.set_code} className={styles.parentGroup}>
                  <SetCard set={group.parent} onSelect={onSelect} />
                  {group.children.length > 0 && (
                    <div className={styles.childrenGrid}>
                      {group.children.map((child) => (
                        <SetCard key={child.set_code} set={child} isChild onSelect={onSelect} />
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add src/frontend/src/features/cards/components/SetBrowser.tsx
git commit -m "feat(SetBrowser): rewrite with icon-focused grid and parent-child grouping"
```

---

### Task 7: Update SetBrowser.module.css

**Files:**
- Modify: `src/frontend/src/features/cards/components/SetBrowser.module.css`

- [ ] **Step 1: Replace SetBrowser.module.css with responsive grid styles**

Open `src/frontend/src/features/cards/components/SetBrowser.module.css` and replace entirely with:

```css
.wrap {
  width: 100%;
  padding-bottom: 40px;
}

.hero {
  padding: 32px 24px;
  text-align: center;
  background: linear-gradient(135deg, rgba(91, 141, 238, 0.05), rgba(255, 193, 7, 0.02));
  border-bottom: 1px solid var(--border-color, #e0e0e0);
}

.heroTitle {
  margin: 0 0 8px 0;
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary, #000);
}

.heroAccent {
  display: block;
  width: 60px;
  height: 3px;
  background: var(--accent-color, #5b8dee);
  margin: 12px auto;
  border-radius: 2px;
}

.heroSub {
  margin: 8px 0 0 0;
  font-size: 14px;
  color: var(--text-secondary, #666);
}

.controls {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  border-bottom: 1px solid var(--border-color, #e0e0e0);
  background: var(--bg-secondary, #fafafa);
}

.searchRow {
  position: relative;
  display: flex;
  align-items: center;
}

.searchIcon {
  position: absolute;
  left: 12px;
  color: var(--text-muted, #999);
  pointer-events: none;
}

.searchInput {
  width: 100%;
  padding: 8px 12px 8px 36px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 6px;
  font-size: 14px;
  outline: none;
  transition: all 0.2s;
}

.searchInput:focus {
  border-color: var(--accent-color, #5b8dee);
  background: var(--bg-primary, #fff);
  box-shadow: 0 0 0 2px rgba(91, 141, 238, 0.1);
}

.searchClear {
  position: absolute;
  right: 12px;
  background: none;
  border: none;
  font-size: 18px;
  color: var(--text-muted, #999);
  cursor: pointer;
  padding: 4px 8px;
}

.controlBlock {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.controlLabel {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-secondary, #666);
  letter-spacing: 0.5px;
}

.chipRow {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--bg-primary, #fff);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.chip:hover {
  border-color: var(--accent-color, #5b8dee);
  background: rgba(91, 141, 238, 0.05);
}

.chipActive {
  background: var(--accent-color, #5b8dee);
  color: white;
  border-color: var(--accent-color, #5b8dee);
}

.chipCount {
  font-size: 12px;
  opacity: 0.7;
}

.empty {
  padding: 40px 24px;
  text-align: center;
  color: var(--text-muted, #999);
  font-size: 14px;
}

.section {
  padding: 32px 24px;
}

.sectionHeader {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 2px solid var(--border-color, #e0e0e0);
}

.sectionTitle {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary, #000);
}

.sectionCount {
  font-size: 12px;
  color: var(--text-muted, #999);
  background: var(--bg-secondary, #fafafa);
  padding: 4px 8px;
  border-radius: 4px;
}

/* Responsive grid */
.grid {
  display: grid;
  gap: 16px;
}

@media (max-width: 639px) {
  .grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
  }
}

@media (min-width: 640px) and (max-width: 1023px) {
  .grid {
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
  }
}

@media (min-width: 1024px) {
  .grid {
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
  }
}

/* Parent-child grouping */
.parentGroup {
  display: contents;
}

.childrenGrid {
  grid-column: 1 / -1;
  display: grid;
  gap: 8px;
  padding: 0 12px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-color, #e0e0e0);
}

@media (max-width: 639px) {
  .childrenGrid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (min-width: 640px) and (max-width: 1023px) {
  .childrenGrid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (min-width: 1024px) {
  .childrenGrid {
    grid-template-columns: repeat(4, 1fr);
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add src/frontend/src/features/cards/components/SetBrowser.module.css
git commit -m "feat(SetBrowser.css): add responsive grid and parent-child nesting styles"
```

---

### Task 8: Update SetBrowseItem Type (If Needed)

**Files:**
- Modify: `src/frontend/src/features/cards/types.ts` (or wherever SetBrowseItem is defined)

- [ ] **Step 1: Verify SetBrowseItem type includes parent_set_code**

Open `src/frontend/src/features/cards/types.ts` and check the `SetBrowseItem` type definition.

- [ ] **Step 2: Add parent_set_code if missing**

If not present, add:

```typescript
export interface SetBrowseItem {
  set_id: string
  set_name: string
  set_code: string
  set_type: string
  card_count: number
  released_at: string
  icon_svg_uri: string | null
  parent_set_code: string | null  // ADD THIS
}
```

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/features/cards/types.ts
git commit -m "feat(types): add parent_set_code to SetBrowseItem interface"
```

---

### Task 9: Write Unit Tests for SetBrowser Grouping Logic

**Files:**
- Create: `src/frontend/src/features/cards/__tests__/SetBrowser.test.tsx`

- [ ] **Step 1: Create the test file**

Write `src/frontend/src/features/cards/__tests__/SetBrowser.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SetBrowser } from '../components/SetBrowser'

// Mock the query hook
vi.mock('../api', () => ({
  setBrowseQueryOptions: () => ({
    queryKey: ['sets-browse'],
    queryFn: async () => [
      {
        set_id: '1',
        set_name: 'Murders at Karlov Manor',
        set_code: 'mkm',
        set_type: 'expansion',
        card_count: 286,
        released_at: '2024-02-09',
        icon_svg_uri: 'http://example.com/mkm.svg',
        parent_set_code: null,
      },
      {
        set_id: '2',
        set_name: 'Murders at Karlov Manor Promos',
        set_code: 'pmkm',
        set_type: 'promo',
        card_count: 5,
        released_at: '2024-02-09',
        icon_svg_uri: 'http://example.com/pmkm.svg',
        parent_set_code: 'mkm',
      },
      {
        set_id: '3',
        set_name: 'Wilds of Eldraine',
        set_code: 'woe',
        set_type: 'expansion',
        card_count: 271,
        released_at: '2023-09-08',
        icon_svg_uri: 'http://example.com/woe.svg',
        parent_set_code: null,
      },
    ],
  }),
}))

describe('SetBrowser', () => {
  const queryClient = new QueryClient()
  const mockOnSelect = vi.fn()

  it('renders year sections', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <SetBrowser onSelect={mockOnSelect} />
      </QueryClientProvider>
    )
    
    expect(await screen.findByText('2024')).toBeInTheDocument()
    expect(await screen.findByText('2023')).toBeInTheDocument()
  })

  it('groups parent and child sets', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <SetBrowser onSelect={mockOnSelect} />
      </QueryClientProvider>
    )
    
    expect(await screen.findByText('Murders at Karlov Manor')).toBeInTheDocument()
    expect(await screen.findByText('Murders at Karlov Manor Promos')).toBeInTheDocument()
  })

  it('calls onSelect when set card is clicked', async () => {
    const { click } = render(
      <QueryClientProvider client={queryClient}>
        <SetBrowser onSelect={mockOnSelect} />
      </QueryClientProvider>
    )
    
    const mkm = await screen.findByText('MKM')
    click(mkm)
    
    expect(mockOnSelect).toHaveBeenCalledWith('mkm')
  })

  it('filters sets by search term', async () => {
    const { getByPlaceholderText } = render(
      <QueryClientProvider client={queryClient}>
        <SetBrowser onSelect={mockOnSelect} />
      </QueryClientProvider>
    )
    
    const input = getByPlaceholderText('Search sets by name or code…')
    await userEvent.type(input, 'Wilds')
    
    expect(await screen.findByText('2023')).toBeInTheDocument()
    expect(screen.queryByText('2024')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd /home/arthur/projects/AutoMana/src/frontend
npm test -- SetBrowser.test.tsx
```

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/features/cards/__tests__/SetBrowser.test.tsx
git commit -m "test(SetBrowser): add unit tests for grouping and filtering"
```

---

### Task 10: Write Unit Tests for SetCard Component

**Files:**
- Create: `src/frontend/src/features/cards/__tests__/SetCard.test.tsx`

- [ ] **Step 1: Create test file**

Write `src/frontend/src/features/cards/__tests__/SetCard.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SetCard } from '../components/SetCard'
import type { SetBrowseItem } from '../types'

const mockSet: SetBrowseItem = {
  set_id: '1',
  set_name: 'Murders at Karlov Manor',
  set_code: 'mkm',
  set_type: 'expansion',
  card_count: 286,
  released_at: '2024-02-09',
  icon_svg_uri: 'http://example.com/mkm.svg',
  parent_set_code: null,
}

describe('SetCard', () => {
  const mockOnSelect = vi.fn()

  it('renders set code', () => {
    render(<SetCard set={mockSet} onSelect={mockOnSelect} />)
    expect(screen.getByText('MKM')).toBeInTheDocument()
  })

  it('renders set type', () => {
    render(<SetCard set={mockSet} onSelect={mockOnSelect} />)
    expect(screen.getByText('Expansion')).toBeInTheDocument()
  })

  it('renders card count', () => {
    render(<SetCard set={mockSet} onSelect={mockOnSelect} />)
    expect(screen.getByText('286')).toBeInTheDocument()
  })

  it('renders release date', () => {
    render(<SetCard set={mockSet} onSelect={mockOnSelect} />)
    expect(screen.getByText('Feb 09')).toBeInTheDocument()
  })

  it('calls onSelect when clicked', async () => {
    const user = userEvent.setup()
    const { container } = render(<SetCard set={mockSet} onSelect={mockOnSelect} />)
    
    const button = container.querySelector('button')!
    await user.click(button)
    
    expect(mockOnSelect).toHaveBeenCalledWith('mkm')
  })

  it('applies childCard style when isChild is true', () => {
    const { container } = render(<SetCard set={mockSet} isChild onSelect={mockOnSelect} />)
    const card = container.querySelector('.childCard')
    expect(card).toBeInTheDocument()
  })

  it('renders fallback icon on broken image', async () => {
    const user = userEvent.setup()
    const { container } = render(<SetCard set={mockSet} onSelect={mockOnSelect} />)
    
    const img = container.querySelector('img') as HTMLImageElement
    expect(img).toBeInTheDocument()
    
    // Simulate broken image
    img.dispatchEvent(new Event('error'))
    
    const fallback = container.querySelector('.iconFallback')
    expect(fallback).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests**

```bash
cd /home/arthur/projects/AutoMana/src/frontend
npm test -- SetCard.test.tsx
```

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/features/cards/__tests__/SetCard.test.tsx
git commit -m "test(SetCard): add unit tests for card rendering and interactions"
```

---

### Task 11: Manual Testing (Browser)

**Files:**
- N/A (manual testing)

- [ ] **Step 1: Start the development server**

```bash
cd /home/arthur/projects/AutoMana/src/frontend
npm run dev
```

Open http://localhost:5173 in your browser.

- [ ] **Step 2: Navigate to `/search` with no set parameter**

Go to http://localhost:5173/search (or the relevant path in your app).

- [ ] **Step 3: Verify layout and interactions**

Check:
- Sets are displayed in a responsive grid (2 columns on mobile, 3 on tablet, 4 on desktop)
- Sets are grouped by year (newest first)
- Parent sets appear with child sets nested/indented below
- Set cards display icon, code, type, count, and release date
- Hovering over a card shows subtle accent border + tint
- Clicking a set card updates the URL with `?set=<code>`
- Search input filters by name or code
- Type filter chips work correctly
- Group by toggle switches between Year / Type / None

- [ ] **Step 4: Test on different screen sizes**

Use browser DevTools to test responsive layout at 640px, 1024px breakpoints.

- [ ] **Step 5: No automated step; manual verification only**

If all checks pass, proceed to next task.

---

### Task 12: Backend Integration Test (Full API)

**Files:**
- N/A (run existing test)

- [ ] **Step 1: Run backend integration test**

```bash
cd /home/arthur/projects/AutoMana
pytest tests/integration/api/test_set_browse_endpoint.py -v
```

Expected: All tests pass, including new `test_set_browse_includes_parent_set_code` test.

- [ ] **Step 2: Verify parent-child relationships in response**

Manually call the API (e.g., via curl or Postman):

```bash
curl http://localhost:8000/api/v1/set-reference/browse | jq '.[] | select(.parent_set_code != null) | {set_code, parent_set_code}' | head -20
```

Expected: See several sets with parent_set_code filled in (e.g., promo sets pointing to their parent expansion).

- [ ] **Step 3: No commit needed; this is verification**

If API returns data correctly, move to next task.

---

### Task 13: Full E2E Test (Optional)

**Files:**
- N/A (manual or existing E2E test)

- [ ] **Step 1: Test the full flow**

1. Open http://localhost:5173/search
2. Verify set browser loads with grid layout
3. Search for a set (e.g., "Murders")
4. Click a set card
5. Verify URL updates to `?set=mkm`
6. Verify selected-set banner appears above grid
7. Verify card grid is populated with cards from that set
8. Click "Change set" to go back to browser

- [ ] **Step 2: No automated step**

If flow works as expected, feature is complete.

---

### Task 14: Cleanup & Final Commit

**Files:**
- N/A

- [ ] **Step 1: Remove any debug console.logs or commented code**

Search the modified files for any debug statements left behind.

- [ ] **Step 2: Verify all tests pass**

```bash
cd /home/arthur/projects/AutoMana
pytest tests/integration/api/test_set_browse_endpoint.py -v
cd /home/arthur/projects/AutoMana/src/frontend
npm test
```

Both should pass.

- [ ] **Step 3: Final check: no hardcoded values or placeholders**

Review SetBrowser.tsx, SetCard.tsx, and CSS modules for any hardcoded colors, sizes, or breakpoints that should be configurable. Should be fine for MVP, but flag for future.

- [ ] **Step 4: Done!**

All tasks complete. Feature is ready for review/merge.

---

## Spec Coverage Checklist

- [x] Year grouping with newest first
- [x] Parent-child hierarchical display
- [x] Icon-focused card design (icon, code, type, count, date)
- [x] Responsive columns (2/3/4)
- [x] Search filtering (by name/code)
- [x] Type filtering
- [x] Group by toggle (Year / Type / None)
- [x] Parent-child nesting within groups
- [x] Backend: add parent_set_code to SetBrowseItem
- [x] Frontend: SetCard component
- [x] Frontend: SetBrowser rewrite with grouping logic
- [x] Responsive CSS Grid
- [x] Unit tests (SetBrowser, SetCard)
- [x] Integration test (API response)
- [x] Manual E2E testing
