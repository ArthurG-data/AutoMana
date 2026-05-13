# Set Browser Redesign — Icon-Focused Grid Layout

**Date:** 2026-05-12  
**Status:** Approved  
**Replaces:** `2026-05-11-set-browser-design.md` (compact rows)

## Overview

Redesign the set browser from a compact row list to an icon-focused responsive grid. Sets are organized by **year** (newest first) with **parent-child grouping** (supplemental sets nested under their parent). Each card is small, icon-prominent, and displays release date alongside existing metadata.

## User Flow (Unchanged)

1. Navigate to `/search` with no `set` param → full-area **set browser** (icon grid by year)
2. Click a set card → `set=<set_code>` added to URL → browser collapses into **selected-set banner**; card grid + filters appear below
3. Click "Change set" in banner → `set` cleared from URL → back to set browser
4. Existing filters (rarity, finish, layout, promo type) remain available in sidebar while browsing

## Architecture

The redesign is primarily **frontend logic** (grouping, layout, responsive grid), but requires a **minor backend change**: adding `parent_set_code` field to the `SetBrowseItem` response so the frontend can identify parent-child relationships. This is a non-breaking addition to the existing endpoint.

**Data flow:**
- `SetBrowser` mounts → calls existing `setBrowseQueryOptions()` query
- Response is client-side grouped by year, then by parent-child relationship
- Render as responsive grid instead of rows

## Frontend: SetBrowser Component

### Data Grouping Logic

**Step 1: Year grouping**
- Extract year from `released_at` (e.g., "2024-02-09" → "2024")
- Group sets into buckets by year
- Sort years descending (newest first)

**Step 2: Parent-child hierarchy**
- Within each year, identify parent sets (those with no `parent_set_id` in the data, or indicated by a `parent_set_code` field)
- Group child sets under their parent
- Child sets without a parent are displayed as standalone cards (fallback for edge cases)

**Step 3: Filtering & search**
- Apply existing search and type filters BEFORE grouping
- Search narrows by set name or code (client-side)
- Type filter excludes non-matching sets
- Filtered sets are then grouped by year and parent-child

### Component Structure

```
SetBrowser
├─ Header (hero + controls)
├─ Controls
│  ├─ Search input
│  ├─ Type filter chips
│  └─ Group by toggle (None / Type / Year)
├─ Content
│  ├─ YearSection (for each year)
│  │  ├─ YearHeader
│  │  └─ SetGrid (responsive columns)
│  │     ├─ ParentSetCard
│  │     │  └─ ChildSetCards (nested below parent)
│  │     └─ StandaloneSetCard
```

### SetCard Component (Icon-Focused)

**Parent set card:**
- Container: responsive, 1:1 or 4:5 aspect ratio
- **Icon:** Large (48-56px), centered or left-aligned
- **Code:** Bold, prominent, monospace (e.g., "MKM")
- **Type:** Secondary text, accent-colored pill (e.g., "Expansion")
- **Count:** Monospace, right-aligned or below type (e.g., "286 cards")
- **Date:** Small, secondary color, below count (e.g., "Feb 9, 2024")
- **Hover state:** Subtle accent border + background tint, slight scale (1.02x)
- **Click:** Emit `onSelect(setCode)` → update URL with `?set=<code>`

**Child set card (nested below parent):**
- Indented or visually distinct (reduced opacity ~0.8, smaller icon 32px)
- Same layout structure but more compact
- Divider (1px solid, subtle color) separates parent from first child
- Clickable with same behavior as parent

### Responsive Behavior

- **Mobile (< 640px):** 2 columns
  - Card width: ~(100% - padding) / 2
  - Padding: 8-12px between cards
  - Parent cards use full-width or span 2 columns option if space allows
  
- **Tablet (640px - 1024px):** 3 columns
  - Card width: ~(100% - padding) / 3
  - Padding: 12-16px between cards
  
- **Desktop (> 1024px):** 4 columns
  - Card width: ~(100% - padding) / 4
  - Padding: 16px between cards

Child cards always align with their parent (no wrapping child across rows). If a parent spans multiple columns (on mobile, parent as full-width option), children are nested below maintaining alignment.

### Grouping Toggle Behavior

**"Year" (default)**
- Organize sets by year (newest first)
- Within each year, group by parent-child
- Shows year section headers

**"Type"**
- Organize sets by set_type (Expansion, Core, Masters, etc.)
- Within each type, preserve parent-child hierarchy AND year order
- Shows type section headers instead of year

**"None"**
- Flat responsive grid, no section headers
- All sets mixed together, sorted by `released_at DESC`
- Parent-child hierarchy is still visually indicated (nesting/indentation) but not functionally grouped

### Data Dependency: Parent-Child Relationship

The backend `SetBrowseItem` response must include a way to identify parent-child relationships. Options:

**Option 1 (Preferred):** Add `parent_set_code: str | null` to `SetBrowseItem`
- Child sets have `parent_set_code` pointing to parent's `set_code`
- Parent sets have `parent_set_code = null`
- Frontend groups by matching `parent_set_code`

**Option 2:** Add `parent_set_id: UUID | null` to `SetBrowseItem`
- Same logic, but using UUID instead of code

**Option 3 (Minimal):** Sort backend response by `(parent_set_code, released_at)` and assume consecutive sets with same parent are siblings
- Frontend groups by shared parent value
- Slightly more fragile but requires no additional field

**Recommendation:** Option 1 (parent_set_code). It's explicit, matches user intent, and makes the frontend grouping logic clear.

## Backend: SetBrowseItem Model Update

Add field to Pydantic model:
```python
class SetBrowseItem(BaseModel):
    set_id: UUID
    set_name: str
    set_code: str
    set_type: str
    card_count: int
    released_at: date
    icon_svg_uri: str | None
    parent_set_code: str | None  # NEW
```

Update SQL query in `set_repository.browse()` to include `parent_set_code`:
```sql
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
```

*Note:* Assumes `joined_set_materialized` has a `parent_set_id` column. If not, use the `sets` table or adjust the join accordingly.

## Frontend: SetBrowser CSS Module

New styles for responsive grid and nesting:

```css
.wrap {
  /* existing hero + controls styles */
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 16px;
  padding: 0 16px;
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

.yearSection {
  margin-bottom: 32px;
}

.yearHeader {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--text-primary);
}

.parentSetCard {
  /* base card styles */
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 12px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 8px;
}

.parentSetCard:hover {
  border-color: var(--accent-color);
  background-color: rgba(var(--accent-rgb), 0.03);
  transform: scale(1.02);
}

.parentSetCard .icon {
  width: 48px;
  height: 48px;
}

.parentSetCard .code {
  font-family: monospace;
  font-weight: 600;
  font-size: 13px;
}

.parentSetCard .type {
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--accent-bg);
  padding: 2px 6px;
  border-radius: 3px;
}

.parentSetCard .count {
  font-family: monospace;
  font-size: 12px;
  color: var(--text-muted);
}

.parentSetCard .date {
  font-size: 10px;
  color: var(--text-muted);
}

.childSetCards {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 8px;
  padding: 0 12px;
  border-top: 1px solid var(--border-color);
  padding-top: 8px;
  margin-top: 8px;
}

.childSetCard {
  opacity: 0.8;
  padding: 8px;
  /* similar to parentSetCard but smaller */
}

.childSetCard .icon {
  width: 32px;
  height: 32px;
}

.childSetCard:hover {
  opacity: 1;
}
```

## Error Handling

| Scenario | Behavior |
|---|---|
| Set has no icon URI | Render fallback SVG (existing behavior) |
| Browse endpoint fails | Toast error + "Retry" button (existing behavior) |
| No parent-child data available (`parent_set_code` is null for all) | Display all sets as standalone cards (flat grid) |
| Inline filter finds no matches | "No sets match" message below search input (existing behavior) |
| Set selected, 0 cards match filters | Existing "No cards found" empty state in SearchResults |

## Testing

**Frontend:**
- `SetBrowser` groups sets correctly by year (descending)
- Parent-child relationships are identified and rendered with indentation
- Responsive columns work at breakpoints (2/3/4)
- Search filters sets before grouping
- Type filter excludes non-matching sets
- Group by toggle switches between Year / Type / None correctly
- Clicking a set card updates URL and emits selection
- Hover states work on both parent and child cards

**Backend:**
- `set_repository.browse()` returns all rows with `parent_set_code` populated correctly
- `GET /api/v1/set-reference/browse` returns 200 with correct shape
- Parent sets have `parent_set_code = null`
- Child sets have `parent_set_code` matching their parent's `set_code`
- Results are sorted `released_at DESC`

## Migration Notes

- Old design: `2026-05-11-set-browser-design.md` (compact rows) — archive for reference
- No database schema changes required
- No data migrations required
- Pure frontend redesign + backend field addition (non-breaking)
