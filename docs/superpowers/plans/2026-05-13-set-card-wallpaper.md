# Set Card Cinematic Wallpaper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each set card in the browse grid shows a blurred art-crop of its highest-value card as a cinematic wallpaper background.

**Architecture:** Add `key_art_uri` to the `SetBrowseItem` Python model and TypeScript type, populate it via a `LEFT JOIN LATERAL` in `set_repository.browse()`, then render it as a blurred `background-image` div inside `SetCard`.

**Tech Stack:** Python / Pydantic (backend model), asyncpg SQL (repository), TypeScript / React (frontend), CSS Modules (styling), Vitest + React Testing Library (frontend tests), pytest + AsyncMock (backend tests)

---

## File Map

| File | Change |
|------|--------|
| `src/automana/core/models/card_catalog/set.py` | Add `key_art_uri: Optional[str]` to `SetBrowseItem` |
| `src/automana/core/repositories/card_catalog/set_repository.py` | Add `LEFT JOIN LATERAL` to `browse()` query |
| `tests/unit/core/test_set_browse.py` | Update ROWS fixture + add key_art_uri assertions |
| `tests/integration/api/test_set_browse_endpoint.py` | Assert `key_art_uri` key present in browse response |
| `src/frontend/src/features/cards/types.ts` | Add `key_art_uri: string \| null` to `SetBrowseItem` |
| `src/frontend/src/features/cards/components/SetCard.module.css` | Add `.bgArt`, overlay `::after`, z-index on icon/name |
| `src/frontend/src/features/cards/components/SetCard.tsx` | Render `.bgArt` div when `key_art_uri` is present |
| `src/frontend/src/features/cards/components/__tests__/SetCard.test.tsx` | Update mockSet + add bgArt render tests |

---

## Task 1: Add `key_art_uri` to the Python `SetBrowseItem` model

**Files:**
- Modify: `src/automana/core/models/card_catalog/set.py:91-103`
- Test: `tests/unit/core/test_set_browse.py`

- [ ] **Step 1: Update the unit test ROWS fixture and add assertions**

Open `tests/unit/core/test_set_browse.py`. Replace the entire file content:

```python
import pytest
from unittest.mock import AsyncMock
from datetime import date
from uuid import uuid4

ROWS = [
    {
        "set_id": uuid4(),
        "set_name": "Murders at Karlov Manor",
        "set_code": "mkm",
        "set_type": "expansion",
        "card_count": 286,
        "released_at": date(2024, 2, 9),
        "icon_svg_uri": "https://svgs.scryfall.io/sets/mkm.svg",
        "parent_set_code": None,
        "key_art_uri": "https://cards.scryfall.io/art_crop/front/a/b/ab12.jpg",
    },
    {
        "set_id": uuid4(),
        "set_name": "Arena Base Set",
        "set_code": "anb",
        "set_type": "alchemy",
        "card_count": 60,
        "released_at": date(2020, 6, 25),
        "icon_svg_uri": None,
        "parent_set_code": None,
        "key_art_uri": None,
    },
]


@pytest.mark.asyncio
async def test_browse_returns_set_browse_items():
    from automana.core.services.card_catalog import set_service
    from automana.core.models.card_catalog.set import SetBrowseItem

    mock_repo = AsyncMock()
    mock_repo.browse.return_value = ROWS

    result = await set_service.browse_sets(set_repository=mock_repo)

    assert len(result) == 2
    assert all(isinstance(item, SetBrowseItem) for item in result)
    assert result[0].set_code == "mkm"
    assert result[1].icon_svg_uri is None


@pytest.mark.asyncio
async def test_browse_passes_through_key_art_uri():
    from automana.core.services.card_catalog import set_service

    mock_repo = AsyncMock()
    mock_repo.browse.return_value = ROWS

    result = await set_service.browse_sets(set_repository=mock_repo)

    assert result[0].key_art_uri == "https://cards.scryfall.io/art_crop/front/a/b/ab12.jpg"
    assert result[1].key_art_uri is None


@pytest.mark.asyncio
async def test_browse_propagates_repo_error():
    from automana.core.services.card_catalog import set_service

    mock_repo = AsyncMock()
    mock_repo.browse.side_effect = RuntimeError("db gone")

    with pytest.raises(Exception):
        await set_service.browse_sets(set_repository=mock_repo)
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd /path/to/repo && pytest tests/unit/core/test_set_browse.py::test_browse_passes_through_key_art_uri -v
```

Expected: `FAILED` — `SetBrowseItem` has no `key_art_uri` field yet.

- [ ] **Step 3: Add `key_art_uri` to `SetBrowseItem`**

Open `src/automana/core/models/card_catalog/set.py`. The `SetBrowseItem` class starts at line 91. Add one field:

```python
class SetBrowseItem(BaseModel):
    set_id: UUID = Field(title="Set UUID")
    set_name: str = Field(title="Full set name")
    set_code: str = Field(title="Three-to-five letter set code")
    set_type: str = Field(title="Category of set (expansion, masters, …)")
    card_count: int = Field(title="Number of card versions in this set")
    released_at: datetime.date = Field(title="Official release date")
    icon_svg_uri: Optional[str] = Field(default=None, title="Scryfall SVG icon URL")
    parent_set_code: Optional[str] = Field(default=None, title="Parent set code if this is a sub-set")
    key_art_uri: Optional[str] = Field(default=None, title="Art-crop image URL of highest-value card in set")

    class Config:
        from_attributes = True
```

- [ ] **Step 4: Run both unit tests to confirm they pass**

```bash
pytest tests/unit/core/test_set_browse.py -v
```

Expected: all 3 tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/models/card_catalog/set.py tests/unit/core/test_set_browse.py
git commit -m "feat(set-browse): add key_art_uri to SetBrowseItem model"
```

---

## Task 2: Add `LEFT JOIN LATERAL` to `set_repository.browse()`

**Files:**
- Modify: `src/automana/core/repositories/card_catalog/set_repository.py:206-234`

- [ ] **Step 1: Replace the `browse()` query**

Open `src/automana/core/repositories/card_catalog/set_repository.py`. Replace the `browse()` method (lines 206–234) with:

```python
async def browse(self) -> List[Dict]:
    # Falls back to the parent set's icon when the set has none of its own.
    # key_art picks the art-crop of the highest-priced booster card per set.
    query = """
        SELECT
            vsm.set_id,
            vsm.set_name,
            vsm.set_code,
            vsm.set_type,
            vsm.card_count,
            vsm.released_at,
            COALESCE(iqr.icon_query_uri, parent_iqr.icon_query_uri) AS icon_svg_uri,
            parent_s.set_code AS parent_set_code,
            key_art.key_art_uri
        FROM card_catalog.v_joined_set_materialized vsm
        JOIN card_catalog.sets s ON s.set_id = vsm.set_id
        LEFT JOIN card_catalog.sets parent_s ON parent_s.set_id = s.parent_set
        LEFT JOIN card_catalog.icon_set ics ON ics.set_id = vsm.set_id
        LEFT JOIN card_catalog.icon_query_ref iqr
               ON iqr.icon_query_id = ics.icon_query_id
        LEFT JOIN card_catalog.icon_set parent_ics
               ON parent_ics.set_id = s.parent_set
        LEFT JOIN card_catalog.icon_query_ref parent_iqr
               ON parent_iqr.icon_query_id = parent_ics.icon_query_id
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
        WHERE vsm.digital = FALSE
        ORDER BY vsm.released_at DESC
    """
    rows = await self.execute_query(query)
    return [dict(r) for r in rows]
```

- [ ] **Step 2: Commit**

```bash
git add src/automana/core/repositories/card_catalog/set_repository.py
git commit -m "feat(set-browse): add lateral join for key_art_uri in browse query"
```

---

## Task 3: Update integration test to assert `key_art_uri`

**Files:**
- Modify: `tests/integration/api/test_set_browse_endpoint.py`

- [ ] **Step 1: Add `key_art_uri` assertion to `test_browse_returns_200_with_expected_shape`**

Open `tests/integration/api/test_set_browse_endpoint.py`. Add `key_art_uri` to the shape check and a new test for its type:

```python
import pytest


@pytest.mark.asyncio
async def test_browse_returns_200_with_expected_shape(client):
    response = await client.get("/api/catalog/mtg/set-reference/browse")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    if body["data"]:
        item = body["data"][0]
        assert "set_code" in item
        assert "set_name" in item
        assert "set_type" in item
        assert "card_count" in item
        assert "released_at" in item
        assert "icon_svg_uri" in item
        assert "key_art_uri" in item


@pytest.mark.asyncio
async def test_browse_key_art_uri_is_string_or_null(client):
    response = await client.get("/api/catalog/mtg/set-reference/browse")
    assert response.status_code == 200
    sets = response.json()["data"]
    for item in sets:
        assert item["key_art_uri"] is None or isinstance(item["key_art_uri"], str)


@pytest.mark.asyncio
async def test_browse_includes_parent_set_code(client):
    response = await client.get("/api/catalog/mtg/set-reference/browse")
    assert response.status_code == 200
    sets = response.json()["data"]
    assert len(sets) > 0
    for item in sets:
        assert "parent_set_code" in item
        assert item["parent_set_code"] is None or isinstance(item["parent_set_code"], str)
    child_sets = [s for s in sets if s["parent_set_code"] is not None]
    assert len(child_sets) > 0, "Expected at least one child set with a non-null parent_set_code"


@pytest.mark.asyncio
async def test_browse_excludes_digital_sets(client):
    response = await client.get("/api/catalog/mtg/set-reference/browse")
    assert response.status_code == 200
    sets = response.json()["data"]
    digital_codes = {"tic", "ana", "anb"}
    returned_codes = {s["set_code"] for s in sets}
    assert returned_codes.isdisjoint(digital_codes), (
        f"Digital sets found in browse response: {returned_codes & digital_codes}"
    )
```

- [ ] **Step 2: Commit**

```bash
git add tests/integration/api/test_set_browse_endpoint.py
git commit -m "test(set-browse): assert key_art_uri field in browse endpoint response"
```

---

## Task 4: Add `key_art_uri` to the TypeScript `SetBrowseItem` type

**Files:**
- Modify: `src/frontend/src/features/cards/types.ts`
- Modify: `src/frontend/src/features/cards/components/__tests__/SetCard.test.tsx`

- [ ] **Step 1: Update `SetCard.test.tsx` mockSet to include `key_art_uri: null`**

Open `src/frontend/src/features/cards/components/__tests__/SetCard.test.tsx`. Update `mockSet` (it must include the new field or TypeScript will error once the type is updated):

```typescript
const mockSet: SetBrowseItem = {
  set_id: '11111111-1111-1111-1111-111111111111',
  set_name: 'Murders at Karlov Manor',
  set_code: 'mkm',
  set_type: 'expansion',
  card_count: 286,
  released_at: '2024-02-09',
  icon_svg_uri: 'http://example.com/mkm.svg',
  parent_set_code: null,
  key_art_uri: null,
}
```

- [ ] **Step 2: Run the existing tests to confirm they still pass (before the type change)**

```bash
cd src/frontend && npm test -- SetCard
```

Expected: 7 tests `PASS`.

- [ ] **Step 3: Add `key_art_uri` to `SetBrowseItem` in `types.ts`**

Open `src/frontend/src/features/cards/types.ts`. Find `SetBrowseItem` (around line 105). Add the field:

```typescript
export interface SetBrowseItem {
  set_id: string
  set_name: string
  set_code: string
  set_type: string
  card_count: number
  released_at: string
  icon_svg_uri: string | null
  parent_set_code: string | null
  key_art_uri: string | null
}
```

- [ ] **Step 4: Run the tests again to confirm they still pass**

```bash
cd src/frontend && npm test -- SetCard
```

Expected: 7 tests `PASS`.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/cards/types.ts \
        src/frontend/src/features/cards/components/__tests__/SetCard.test.tsx
git commit -m "feat(set-browser): add key_art_uri to SetBrowseItem TypeScript type"
```

---

## Task 5: Add background art CSS to `SetCard.module.css`

**Files:**
- Modify: `src/frontend/src/features/cards/components/SetCard.module.css`

- [ ] **Step 1: Update `SetCard.module.css`**

Open `src/frontend/src/features/cards/components/SetCard.module.css`. Make the following changes:

**1. Add `position: relative` to `.artInner`** (it currently has no position — the absolute `.bgArt` needs a positioned parent):

```css
.artInner {
  width: 100%;
  height: 100%;
  background: linear-gradient(160deg, var(--hd-surface) 0%, rgba(var(--hd-blue-rgb), 0.12) 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 12px;
  position: relative;
}
```

**2. Add `.bgArt` and its hover variant** (after `.artInner`):

```css
.bgArt {
  position: absolute;
  inset: 0;
  background-size: cover;
  background-position: center 30%;
  filter: blur(3px) brightness(0.35) saturate(1.2);
  transform: scale(1.05);
  z-index: 0;
  transition: filter 0.2s;
}

.card:hover .bgArt {
  filter: blur(3px) brightness(0.45) saturate(1.2);
}
```

**3. Add the gradient overlay** (after `.bgArt`):

```css
.artInner::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, transparent 40%, rgba(5, 13, 26, 0.85) 100%);
  pointer-events: none;
  z-index: 1;
}
```

**4. Give the icon and set name `position: relative; z-index: 2`** so they sit above `.bgArt` and `::after`:

```css
.iconImg {
  width: 48px;
  height: 48px;
  object-fit: contain;
  flex-shrink: 0;
  position: relative;
  z-index: 2;
}

.iconFallback {
  width: 40px;
  height: 40px;
  opacity: 0.25;
  color: var(--hd-muted);
  flex-shrink: 0;
  position: relative;
  z-index: 2;
}

.setName {
  font-size: 10px;
  color: var(--hd-sub);
  text-align: center;
  line-height: 1.3;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  position: relative;
  z-index: 2;
}
```

- [ ] **Step 2: Run the frontend tests**

```bash
cd src/frontend && npm test -- SetCard
```

Expected: 7 tests `PASS` (CSS changes don't break existing behaviour).

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/features/cards/components/SetCard.module.css
git commit -m "feat(set-browser): add bgArt CSS for cinematic wallpaper background"
```

---

## Task 6: Render the background art in `SetCard.tsx`

**Files:**
- Modify: `src/frontend/src/features/cards/components/SetCard.tsx`
- Modify: `src/frontend/src/features/cards/components/__tests__/SetCard.test.tsx`

- [ ] **Step 1: Add failing tests for bgArt rendering**

Open `src/frontend/src/features/cards/components/__tests__/SetCard.test.tsx`. Append these two tests inside the `describe('SetCard', () => {` block:

```typescript
it('does not render bgArt div when key_art_uri is null', () => {
  const { container } = render(<SetCard set={mockSet} onSelect={vi.fn()} />)
  expect(container.querySelector('[class*="bgArt"]')).toBeNull()
})

it('renders bgArt div with backgroundImage when key_art_uri is provided', () => {
  const setWithArt: SetBrowseItem = {
    ...mockSet,
    key_art_uri: 'https://cards.scryfall.io/art_crop/front/a/b/ab12.jpg',
  }
  const { container } = render(<SetCard set={setWithArt} onSelect={vi.fn()} />)
  const bgArt = container.querySelector('[class*="bgArt"]') as HTMLElement
  expect(bgArt).not.toBeNull()
  expect(bgArt.style.backgroundImage).toBe(
    'url(https://cards.scryfall.io/art_crop/front/a/b/ab12.jpg)'
  )
})
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd src/frontend && npm test -- SetCard
```

Expected: 7 pass, 2 fail (`bgArt` element not found).

- [ ] **Step 3: Update `SetCard.tsx` to render `.bgArt`**

Open `src/frontend/src/features/cards/components/SetCard.tsx`. Replace the `<div className={styles.artInner}>` block with:

```tsx
<div className={styles.artInner}>
  {set.key_art_uri && (
    <div
      className={styles.bgArt}
      style={{ backgroundImage: `url(${set.key_art_uri})` }}
    />
  )}
  {iconBroken ? (
    <svg className={styles.iconFallback} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
      <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
    </svg>
  ) : (
    <img
      className={styles.iconImg}
      src={iconUrl(set)}
      alt=""
      aria-hidden
      onError={() => setIconBroken(true)}
    />
  )}
  <div className={styles.setName}>{set.set_name}</div>
</div>
```

- [ ] **Step 4: Run all frontend tests**

```bash
cd src/frontend && npm test -- SetCard
```

Expected: 9 tests `PASS`.

- [ ] **Step 5: Run the full frontend test suite to check for regressions**

```bash
cd src/frontend && npm test
```

Expected: all tests `PASS`.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/cards/components/SetCard.tsx \
        src/frontend/src/features/cards/components/__tests__/SetCard.test.tsx
git commit -m "feat(set-browser): render cinematic wallpaper art background in SetCard"
```
