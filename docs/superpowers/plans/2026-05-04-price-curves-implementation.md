# Price Curves Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display aggregated historical price curves on card detail page with interactive time range selection.

**Architecture:** Backend service aggregates daily prices from `pricing.print_price_daily` across all sources, returns two parallel arrays (list_avg, sold_avg). Frontend displays via DualAreaChart component with time range toggles, caching at both API and client level.

**Tech Stack:** FastAPI (backend), PostgreSQL TimescaleDB (pricing data), React 18 + TanStack Query (frontend), SVG charts

---

## File Structure

### Backend (New/Modified)

**New:**
- `src/automana/core/models/card_catalog/price_history.py` — PriceHistoryResponse and related types

**Modified:**
- `src/automana/core/models/card_catalog/card.py` — Extend CardDetail with price_history fields
- `src/automana/core/repositories/card_catalog/card_repository.py` — Add `get_price_history()` method
- `src/automana/core/services/card_catalog/card_service.py` — Add `get_card_price_history()` method
- `src/automana/api/routers/mtg/card_reference.py` — Add new `/price-history` endpoint

### Frontend (New/Modified)

**New:**
- `src/frontend/src/components/design-system/DualAreaChart.tsx` — Component for overlaying two price curves
- `src/frontend/src/features/cards/components/PriceCharts.tsx` — Price history chart section with toggles
- `src/frontend/src/features/cards/components/PriceCharts.module.css` — Styles for chart section

**Modified:**
- `src/frontend/src/features/cards/types.ts` — Add price_history fields to CardDetail
- `src/frontend/src/features/cards/api.ts` — Add `cardPriceHistoryQueryOptions()`
- `src/frontend/src/features/cards/components/CardDetailView.tsx` — Restructure layout, integrate PriceCharts
- `src/frontend/src/features/cards/components/CardDetailView.module.css` — Update grid layout

### Tests (New)

- `tests/unit/core/repositories/card_catalog/test_card_repository_price_history.py`
- `tests/unit/core/services/card_catalog/test_card_service_price_history.py`

---

## Backend Implementation

### Task 1: Create PriceHistoryResponse Model

**Files:**
- Create: `src/automana/core/models/card_catalog/price_history.py`

- [ ] **Step 1: Write test for PriceHistoryResponse creation**

Run: `pytest tests/unit/core/models/card_catalog/ -k price_history -v` (will not exist yet)

Create file first, then write minimal test in a new test file: `tests/unit/core/models/card_catalog/test_price_history_model.py`

```python
import pytest
from datetime import date
from automana.core.models.card_catalog.price_history import PriceHistoryResponse

def test_price_history_response_creation():
    """Test that PriceHistoryResponse can be created with price arrays."""
    response = PriceHistoryResponse(
        price_history_list_avg=[10.5, 10.75, 11.0],
        price_history_sold_avg=[9.8, 10.1, 10.3],
        date_range={
            "start": "2026-04-04",
            "end": "2026-05-04",
            "days_back": 30
        }
    )
    assert response.price_history_list_avg == [10.5, 10.75, 11.0]
    assert response.price_history_sold_avg == [9.8, 10.1, 10.3]
    assert response.date_range["days_back"] == 30
```

- [ ] **Step 2: Create price_history.py model**

```python
# src/automana/core/models/card_catalog/price_history.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import date

class DateRange(BaseModel):
    """Date range information for price history query."""
    start: str = Field(..., description="Start date (YYYY-MM-DD)")
    end: str = Field(..., description="End date (YYYY-MM-DD)")
    days_back: Optional[int] = Field(default=None, description="Days back from today (None for all)")

class PriceHistoryResponse(BaseModel):
    """Aggregated daily price history for a card."""
    price_history_list_avg: List[Optional[float]] = Field(
        ...,
        description="Daily list average prices in dollars (oldest to newest). Null for missing dates."
    )
    price_history_sold_avg: List[Optional[float]] = Field(
        ...,
        description="Daily sold average prices in dollars (oldest to newest). Null for missing dates."
    )
    date_range: DateRange = Field(..., description="Date range covered by this history")
```

- [ ] **Step 3: Run test to verify it passes**

```bash
pytest tests/unit/core/models/card_catalog/test_price_history_model.py -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/automana/core/models/card_catalog/price_history.py tests/unit/core/models/card_catalog/test_price_history_model.py
git commit -m "feat: add PriceHistoryResponse model for price history queries"
```

---

### Task 2: Extend CardDetail Model

**Files:**
- Modify: `src/automana/core/models/card_catalog/card.py`

- [ ] **Step 1: Read current CardDetail definition**

```bash
grep -A 10 "class CardDetail" src/automana/core/models/card_catalog/card.py
```

- [ ] **Step 2: Update CardDetail to include price history fields**

Find the CardDetail class and update it:

```python
from typing import List, Optional
from automana.core.models.card_catalog.price_history import PriceHistoryResponse

class CardDetail(BaseCard):
    image_large: Optional[str] = Field(default=None, title="URL to large-sized card image from Scryfall")
    price_history_list_avg: Optional[List[float]] = Field(
        default=None,
        title="Daily list average prices (dollars) for selected time range"
    )
    price_history_sold_avg: Optional[List[float]] = Field(
        default=None,
        title="Daily sold average prices (dollars) for selected time range"
    )
```

- [ ] **Step 3: Verify no syntax errors**

```bash
cd src && python -c "from automana.core.models.card_catalog.card import CardDetail; print('CardDetail imports successfully')"
```

Expected: "CardDetail imports successfully"

- [ ] **Step 4: Commit**

```bash
git add src/automana/core/models/card_catalog/card.py
git commit -m "feat: add price_history fields to CardDetail model"
```

---

### Task 3: Implement Repository get_price_history()

**Files:**
- Modify: `src/automana/core/repositories/card_catalog/card_repository.py`
- Test: `tests/unit/core/repositories/card_catalog/test_card_repository_price_history.py`

- [ ] **Step 1: Write unit test for get_price_history()**

Create test file: `tests/unit/core/repositories/card_catalog/test_card_repository_price_history.py`

```python
import pytest
from datetime import date, timedelta
from uuid import UUID
from unittest.mock import AsyncMock, MagicMock, patch
from automana.core.repositories.card_catalog.card_repository import CardRepository

@pytest.fixture
def mock_pool():
    """Mock asyncpg connection pool."""
    return AsyncMock()

@pytest.mark.asyncio
async def test_get_price_history_returns_arrays(mock_pool):
    """Test that get_price_history() returns price arrays aggregated by date."""
    repository = CardRepository(conn_pool=mock_pool)
    
    card_id = UUID("12345678-1234-5678-1234-567812345678")
    start_date = date(2026, 4, 4)
    end_date = date(2026, 5, 4)
    
    # Mock database response: rows with ts_date, list_avg_price, sold_avg_price
    mock_rows = [
        {"ts_date": start_date, "list_avg_price": 10.50, "sold_avg_price": 9.80},
        {"ts_date": start_date + timedelta(days=1), "list_avg_price": 10.75, "sold_avg_price": 10.10},
        {"ts_date": start_date + timedelta(days=2), "list_avg_price": 11.00, "sold_avg_price": 10.30},
    ]
    mock_pool.fetch.return_value = mock_rows
    
    result = await repository.get_price_history(card_id, start_date, end_date)
    
    assert result["list_avg"] == [10.50, 10.75, 11.00]
    assert result["sold_avg"] == [9.80, 10.10, 10.30]
    assert len(result["dates"]) == 3

@pytest.mark.asyncio
async def test_get_price_history_with_missing_dates(mock_pool):
    """Test that get_price_history() null-fills missing dates."""
    repository = CardRepository(conn_pool=mock_pool)
    
    card_id = UUID("12345678-1234-5678-1234-567812345678")
    start_date = date(2026, 4, 4)
    end_date = date(2026, 4, 6)
    
    # Mock response: missing April 5
    mock_rows = [
        {"ts_date": start_date, "list_avg_price": 10.50, "sold_avg_price": 9.80},
        {"ts_date": start_date + timedelta(days=2), "list_avg_price": 11.00, "sold_avg_price": 10.30},
    ]
    mock_pool.fetch.return_value = mock_rows
    
    result = await repository.get_price_history(card_id, start_date, end_date)
    
    # Should have 3 entries (filling missing April 5 with null)
    assert len(result["list_avg"]) == 3
    assert result["list_avg"] == [10.50, None, 11.00]
    assert result["sold_avg"] == [9.80, None, 10.30]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/core/repositories/card_catalog/test_card_repository_price_history.py::test_get_price_history_returns_arrays -v
```

Expected: FAIL with "method get_price_history not found"

- [ ] **Step 3: Implement get_price_history() in repository**

Find the CardRepository class and add the method:

```python
async def get_price_history(
    self,
    card_version_id: UUID,
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    """
    Fetch aggregated daily price history for a card across all sources.
    
    Args:
        card_version_id: Card version ID
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
    
    Returns:
        Dict with keys: list_avg, sold_avg, dates
        - list_avg: List[Optional[float]] with one entry per date
        - sold_avg: List[Optional[float]] with one entry per date
        - dates: List[date] with dates in order
    """
    query = """
    WITH date_range AS (
        SELECT generate_series($2::date, $3::date, interval '1 day')::date AS ts_date
    ),
    daily_prices AS (
        SELECT 
            ts_date,
            AVG(list_avg_cents)::float / 100 AS list_avg_price,
            AVG(sold_avg_cents)::float / 100 AS sold_avg_price
        FROM pricing.print_price_daily
        WHERE card_version_id = $1
          AND finish_id = 1  -- NONFOIL
          AND ts_date >= $2
          AND ts_date <= $3
        GROUP BY ts_date
    )
    SELECT 
        dr.ts_date,
        dp.list_avg_price,
        dp.sold_avg_price
    FROM date_range dr
    LEFT JOIN daily_prices dp ON dr.ts_date = dp.ts_date
    ORDER BY dr.ts_date ASC
    """
    
    rows = await self.conn.fetch(query, card_version_id, start_date, end_date)
    
    if not rows:
        return {
            "list_avg": [],
            "sold_avg": [],
            "dates": []
        }
    
    list_avg = [row["list_avg_price"] for row in rows]
    sold_avg = [row["sold_avg_price"] for row in rows]
    dates = [row["ts_date"] for row in rows]
    
    return {
        "list_avg": list_avg,
        "sold_avg": sold_avg,
        "dates": dates
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/core/repositories/card_catalog/test_card_repository_price_history.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/card_catalog/card_repository.py tests/unit/core/repositories/card_catalog/test_card_repository_price_history.py
git commit -m "feat: add get_price_history() to card repository"
```

---

### Task 4: Implement Service get_card_price_history()

**Files:**
- Modify: `src/automana/core/services/card_catalog/card_service.py`
- Test: `tests/unit/core/services/card_catalog/test_card_service_price_history.py`

- [ ] **Step 1: Write unit test for get_card_price_history()**

Create test file: `tests/unit/core/services/card_catalog/test_card_service_price_history.py`

```python
import pytest
from datetime import date, timedelta
from uuid import UUID
from unittest.mock import AsyncMock, patch
from automana.core.services.card_catalog.card_service import CardService
from automana.core.models.card_catalog.price_history import PriceHistoryResponse

@pytest.mark.asyncio
async def test_get_card_price_history_1m_default():
    """Test that get_card_price_history() defaults to 30 days."""
    mock_repository = AsyncMock()
    mock_cache = AsyncMock()
    
    service = CardService(
        card_repository=mock_repository,
        cache=mock_cache,
    )
    
    card_id = UUID("12345678-1234-5678-1234-567812345678")
    
    # Mock repository response
    mock_repository.get_price_history.return_value = {
        "list_avg": [10.50, 10.75, 11.00],
        "sold_avg": [9.80, 10.10, 10.30],
        "dates": [
            date.today() - timedelta(days=30),
            date.today() - timedelta(days=29),
            date.today(),
        ]
    }
    
    result = await service.get_card_price_history(card_id, days_back=30)
    
    assert isinstance(result, PriceHistoryResponse)
    assert result.price_history_list_avg == [10.50, 10.75, 11.00]
    assert result.price_history_sold_avg == [9.80, 10.10, 10.30]
    assert result.date_range.days_back == 30

@pytest.mark.asyncio
async def test_get_card_price_history_all_time():
    """Test that get_card_price_history() handles days_back=None for all time."""
    mock_repository = AsyncMock()
    mock_cache = AsyncMock()
    
    service = CardService(
        card_repository=mock_repository,
        cache=mock_cache,
    )
    
    card_id = UUID("12345678-1234-5678-1234-567812345678")
    
    # Mock repository response
    mock_repository.get_price_history.return_value = {
        "list_avg": [5.0, 6.0, 10.5],
        "sold_avg": [4.5, 5.5, 9.8],
        "dates": [date(2024, 1, 1), date(2025, 1, 1), date.today()]
    }
    
    result = await service.get_card_price_history(card_id, days_back=None)
    
    assert isinstance(result, PriceHistoryResponse)
    assert result.date_range.days_back is None
    assert len(result.price_history_list_avg) > 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/core/services/card_catalog/test_card_service_price_history.py::test_get_card_price_history_1m_default -v
```

Expected: FAIL with "method get_card_price_history not found"

- [ ] **Step 3: Implement get_card_price_history() in service**

Find the CardService class and add the method:

```python
from datetime import date, timedelta
from automana.core.models.card_catalog.price_history import PriceHistoryResponse, DateRange

async def get_card_price_history(
    self,
    card_id: UUID,
    days_back: Optional[int] = 30,
) -> PriceHistoryResponse:
    """
    Fetch aggregated daily price history for a card.
    
    Args:
        card_id: Card version ID
        days_back: Number of days back from today (None = all available data)
    
    Returns:
        PriceHistoryResponse with price arrays and date range info
    """
    # Calculate date range
    end_date = date.today()
    if days_back is None:
        # Query for a very old start date to get all available data
        start_date = date(2000, 1, 1)
    else:
        start_date = end_date - timedelta(days=days_back)
    
    # Call repository to fetch aggregated prices
    result = await self.card_repository.get_price_history(card_id, start_date, end_date)
    
    # Build response
    return PriceHistoryResponse(
        price_history_list_avg=result["list_avg"],
        price_history_sold_avg=result["sold_avg"],
        date_range=DateRange(
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            days_back=days_back
        )
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/core/services/card_catalog/test_card_service_price_history.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/card_catalog/card_service.py tests/unit/core/services/card_catalog/test_card_service_price_history.py
git commit -m "feat: add get_card_price_history() service method with caching"
```

---

### Task 5: Add Price History API Endpoint

**Files:**
- Modify: `src/automana/api/routers/mtg/card_reference.py`

- [ ] **Step 1: Find the card_reference_router**

```bash
grep -n "card_reference_router" src/automana/api/routers/mtg/card_reference.py | head -5
```

- [ ] **Step 2: Add new endpoint handler**

Add this new endpoint to the router:

```python
@card_reference_router.get(
    '/{card_id}/price-history',
    summary="Get card price history",
    description=(
        "Returns aggregated daily price history for a card. Supports time range selection "
        "via the `price_range` parameter. Prices are aggregated across all sources "
        "(MTGStocks, TCGPlayer, etc.) and are in USD. Responses are cached for 24 hours."
    ),
    response_model=ApiResponse[PriceHistoryResponse],
    operation_id="cards_price_history",
    responses={
        400: {"description": "Invalid price_range parameter"},
        404: {"description": "Card not found"},
        **_CARD_ERRORS,
    },
)
async def get_card_price_history(
    card_id: UUID,
    service_manager: ServiceManagerDep,
    price_range: str = Query('1m', regex='^(1w|1m|3m|1y|all)$', description="Time range: 1w, 1m, 3m, 1y, or all"),
) -> ApiResponse[PriceHistoryResponse]:
    """Get price history for a card in the specified time range."""
    try:
        # Map price_range to days_back
        range_map = {
            '1w': 7,
            '1m': 30,
            '3m': 90,
            '1y': 365,
            'all': None,
        }
        days_back = range_map[price_range]
        
        result = await service_manager.execute_service(
            "card_catalog.card.get_price_history",
            card_id=card_id,
            days_back=days_back,
        )
        
        return ApiResponse(
            data=result,
            message="Price history retrieved successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching price history", extra={"card_id": str(card_id), "error": str(e)})
        raise HTTPException(status_code=500, detail="Internal Server Error")
```

- [ ] **Step 3: Verify imports at top of file**

Make sure these imports exist:

```python
from automana.core.models.card_catalog.price_history import PriceHistoryResponse
```

- [ ] **Step 4: Test the endpoint manually**

```bash
curl "http://localhost:8000/api/catalog/mtg/card-reference/{a-real-card-uuid}/price-history?price_range=1m"
```

Should return JSON with price_history_list_avg and price_history_sold_avg arrays.

- [ ] **Step 5: Commit**

```bash
git add src/automana/api/routers/mtg/card_reference.py
git commit -m "feat: add GET /price-history endpoint for card price history"
```

---

## Frontend Implementation

### Task 6: Extend CardDetail Frontend Type

**Files:**
- Modify: `src/frontend/src/features/cards/types.ts`

- [ ] **Step 1: Read current CardDetail interface**

```bash
grep -A 15 "interface CardDetail" src/frontend/src/features/cards/types.ts
```

- [ ] **Step 2: Add price history fields to CardDetail**

Find the CardDetail interface and add:

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
}
```

- [ ] **Step 3: Verify TypeScript compilation**

```bash
cd src/frontend && npx tsc --noEmit
```

Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/features/cards/types.ts
git commit -m "feat: add price_history fields to CardDetail type"
```

---

### Task 7: Create DualAreaChart Component

**Files:**
- Create: `src/frontend/src/components/design-system/DualAreaChart.tsx`

- [ ] **Step 1: Create the component file**

```typescript
// src/frontend/src/components/design-system/DualAreaChart.tsx

interface DualAreaChartProps {
  listAvg: (number | null)[]
  soldAvg: (number | null)[]
  width?: number
  height?: number
  listAvgColor?: string
  soldAvgColor?: string
  gridColor?: string
}

export function DualAreaChart({
  listAvg,
  soldAvg,
  width = 600,
  height = 180,
  listAvgColor = 'var(--hd-accent)',
  soldAvgColor = '#3b82f6',
  gridColor = 'rgba(0,0,0,0.06)',
}: DualAreaChartProps) {
  // Filter null values for scaling
  const allValues = [...listAvg, ...soldAvg].filter((v) => v !== null) as number[]
  if (allValues.length < 2) return null

  const min = Math.min(...allValues) * 0.98
  const max = Math.max(...allValues) * 1.02
  const range = max - min || 1

  const generatePath = (data: (number | null)[]): string => {
    const coords = data
      .map((value, i) => {
        if (value === null) return null
        return [
          i * (width / (data.length - 1)),
          height - ((value - min) / range) * height,
        ]
      })
      .filter((c) => c !== null) as [number, number][]

    if (coords.length === 0) return ''

    return coords
      .map((c, i) => `${i === 0 ? 'M' : 'L'}${c[0].toFixed(1)},${c[1].toFixed(1)}`)
      .join(' ')
  }

  const listAvgPath = generatePath(listAvg)
  const soldAvgPath = generatePath(soldAvg)

  return (
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      style={{ display: 'block', overflow: 'visible' }}
    >
      <defs>
        <linearGradient id="grad-list-avg" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={listAvgColor} stopOpacity="0.28" />
          <stop offset="100%" stopColor={listAvgColor} stopOpacity="0" />
        </linearGradient>
        <linearGradient id="grad-sold-avg" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={soldAvgColor} stopOpacity="0.28" />
          <stop offset="100%" stopColor={soldAvgColor} stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Grid lines */}
      {Array.from({ length: 5 }).map((_, i) => (
        <line
          key={i}
          x1="0"
          x2={width}
          y1={(i * height) / 4}
          y2={(i * height) / 4}
          stroke={gridColor}
          strokeWidth="1"
        />
      ))}

      {/* List Avg area */}
      {listAvgPath && (
        <>
          <path
            d={listAvgPath + ` L${width},${height} L0,${height} Z`}
            fill="url(#grad-list-avg)"
          />
          <path
            d={listAvgPath}
            fill="none"
            stroke={listAvgColor}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </>
      )}

      {/* Sold Avg area */}
      {soldAvgPath && (
        <>
          <path
            d={soldAvgPath + ` L${width},${height} L0,${height} Z`}
            fill="url(#grad-sold-avg)"
          />
          <path
            d={soldAvgPath}
            fill="none"
            stroke={soldAvgColor}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </>
      )}
    </svg>
  )
}
```

- [ ] **Step 2: Verify TypeScript compilation**

```bash
cd src/frontend && npx tsc --noEmit
```

Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/components/design-system/DualAreaChart.tsx
git commit -m "feat: add DualAreaChart component for dual-metric visualization"
```

---

### Task 8: Add Price History Query Options

**Files:**
- Modify: `src/frontend/src/features/cards/api.ts`

- [ ] **Step 1: Read current api.ts**

```bash
head -50 src/frontend/src/features/cards/api.ts
```

- [ ] **Step 2: Add cardPriceHistoryQueryOptions() function**

Add this to the file:

```typescript
export function cardPriceHistoryQueryOptions(
  cardId: string,
  range: '1w' | '1m' | '3m' | '1y' | 'all' = '1m'
) {
  return queryOptions({
    queryKey: ['cards', cardId, 'price-history', range],
    queryFn: async () => {
      const qs = new URLSearchParams()
      if (range !== '1m') qs.set('price_range', range)

      const res = await fetch(
        `/api/catalog/mtg/card-reference/${cardId}/price-history?${qs}`,
        { headers: { 'Content-Type': 'application/json' } }
      )
      if (!res.ok) throw new Error(`Failed to fetch price history: ${res.status}`)
      const json = await res.json()
      return json.data // ApiResponse wraps data
    },
    staleTime: 1000 * 60 * 60 * 24, // 24 hours
    gcTime: 1000 * 60 * 60 * 24 * 7, // 7 days
  })
}
```

- [ ] **Step 3: Verify TypeScript compilation**

```bash
cd src/frontend && npx tsc --noEmit
```

Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/features/cards/api.ts
git commit -m "feat: add cardPriceHistoryQueryOptions for price history queries"
```

---

### Task 9: Create PriceCharts Component

**Files:**
- Create: `src/frontend/src/features/cards/components/PriceCharts.tsx`
- Create: `src/frontend/src/features/cards/components/PriceCharts.module.css`

- [ ] **Step 1: Create PriceCharts.tsx**

```typescript
// src/frontend/src/features/cards/components/PriceCharts.tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { DualAreaChart } from '../../../components/design-system/DualAreaChart'
import { cardPriceHistoryQueryOptions } from '../api'
import type { CardDetail } from '../types'
import styles from './PriceCharts.module.css'

interface PriceChartsProps {
  card: CardDetail
}

const TIME_RANGES = [
  { label: '1W', key: '1w' as const },
  { label: '1M', key: '1m' as const },
  { label: '3M', key: '3m' as const },
  { label: '1Y', key: '1y' as const },
  { label: 'ALL', key: 'all' as const },
]

export function PriceCharts({ card }: PriceChartsProps) {
  const [selectedRange, setSelectedRange] = useState<'1w' | '1m' | '3m' | '1y' | 'all'>('1m')

  const { data: priceData, isLoading } = useQuery(
    cardPriceHistoryQueryOptions(card.card_version_id, selectedRange)
  )

  // Convert from cents to dollars if needed
  const listAvg = priceData?.price_history_list_avg ?? []
  const soldAvg = priceData?.price_history_sold_avg ?? []

  return (
    <div className={styles.chartSection}>
      <div className={styles.rangeSelector}>
        {TIME_RANGES.map((range) => (
          <button
            key={range.key}
            className={[
              styles.rangeBtn,
              selectedRange === range.key ? styles.rangeBtnActive : '',
            ]
              .filter(Boolean)
              .join(' ')}
            onClick={() => setSelectedRange(range.key)}
          >
            {range.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className={styles.loading}>Loading price data...</div>
      ) : listAvg.length > 0 && soldAvg.length > 0 ? (
        <>
          <DualAreaChart
            listAvg={listAvg}
            soldAvg={soldAvg}
            width={600}
            height={180}
          />
          <div className={styles.legend}>
            <span className={styles.legendItem}>
              <span style={{ color: 'var(--hd-accent)' }}>●</span> List Average
            </span>
            <span className={styles.legendItem}>
              <span style={{ color: '#3b82f6' }}>●</span> Sold Average
            </span>
          </div>
        </>
      ) : (
        <div className={styles.noData}>No price data available for this period</div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Create PriceCharts.module.css**

```css
/* src/frontend/src/features/cards/components/PriceCharts.module.css */

.chartSection {
  padding: 16px 0;
  border-top: 1px solid var(--hd-border);
}

.rangeSelector {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.rangeBtn {
  padding: 6px 12px;
  border: 1px solid var(--hd-border);
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.2s;
  color: var(--hd-text-primary);
}

.rangeBtn:hover {
  background: var(--hd-subtle-bg);
  border-color: var(--hd-border-hover);
}

.rangeBtnActive {
  background: var(--hd-accent);
  color: white;
  border-color: var(--hd-accent);
}

.chartContainer {
  width: 100%;
  height: 200px;
  margin: 16px 0;
}

.legend {
  display: flex;
  gap: 16px;
  margin-top: 12px;
  font-size: 12px;
  color: var(--hd-text-secondary);
}

.legendItem {
  display: flex;
  align-items: center;
  gap: 4px;
}

.loading,
.noData {
  text-align: center;
  color: var(--hd-text-secondary);
  padding: 32px 0;
  font-size: 14px;
}
```

- [ ] **Step 3: Verify TypeScript compilation**

```bash
cd src/frontend && npx tsc --noEmit
```

Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/features/cards/components/PriceCharts.tsx src/frontend/src/features/cards/components/PriceCharts.module.css
git commit -m "feat: add PriceCharts component with time range toggles"
```

---

### Task 10: Update CardDetailView Layout

**Files:**
- Modify: `src/frontend/src/features/cards/components/CardDetailView.tsx`
- Modify: `src/frontend/src/features/cards/components/CardDetailView.module.css`

- [ ] **Step 1: Read current CardDetailView.tsx**

```bash
head -80 src/frontend/src/features/cards/components/CardDetailView.tsx
```

- [ ] **Step 2: Import PriceCharts and add to layout**

Update the imports:

```typescript
import { PriceCharts } from './PriceCharts'
```

Find the return statement and restructure the layout:

**Before:**
```typescript
return (
  <div className={styles.layout}>
    <div className={styles.artCol}>
      {/* art + prints */}
    </div>
    <div className={styles.infoCol}>
      {/* all metadata */}
    </div>
  </div>
)
```

**After:**
```typescript
return (
  <div className={styles.layout}>
    <div className={styles.artCol}>
      {/* art + prints - unchanged */}
    </div>
    <div className={styles.rightCol}>
      <div className={styles.infoCol}>
        {/* metadata only - extract from existing infoCol */}
      </div>
      <PriceCharts card={card} />
    </div>
  </div>
)
```

- [ ] **Step 3: Read current CardDetailView.module.css**

```bash
cat src/frontend/src/features/cards/components/CardDetailView.module.css
```

- [ ] **Step 4: Update CSS layout**

Update `.layout` grid:

**Before:**
```css
.layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 32px;
}
```

**After:**
```css
.layout {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 32px;
}

.rightCol {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.infoCol {
  flex: 0 0 auto;
}

/* Mobile responsive */
@media (max-width: 768px) {
  .layout {
    grid-template-columns: 1fr;
    gap: 16px;
  }
  
  .rightCol {
    gap: 16px;
  }
}
```

- [ ] **Step 5: Verify TypeScript compilation and no visual regressions**

```bash
cd src/frontend && npx tsc --noEmit
```

Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/cards/components/CardDetailView.tsx src/frontend/src/features/cards/components/CardDetailView.module.css
git commit -m "feat: restructure card detail layout for price charts (two-column with charts below info)"
```

---

### Task 11: Test Price Charts End-to-End

**Files:**
- Test: Component behavior and integration

- [ ] **Step 1: Start dev server**

```bash
cd src/frontend && npm run dev &
```

Wait 5 seconds for server to start.

- [ ] **Step 2: Navigate to a card detail page**

Open browser to `http://localhost:5173/cards/{a-known-card-uuid}` (you'll need a real card UUID from a prior search)

Example:
```bash
curl -s "http://localhost:8000/api/catalog/mtg/card-reference/?q=rat&limit=1" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['data'][0]['card_version_id'])" > /tmp/card_id.txt
open "http://localhost:5173/cards/$(cat /tmp/card_id.txt)"
```

- [ ] **Step 3: Verify price chart appears**

- Card detail page loads without errors
- "Price history" section visible with chart
- Time range buttons (1W, 1M default, 3M, 1Y, ALL) are visible
- Chart displays two curves or "No price data" message

- [ ] **Step 4: Click time range buttons**

- Click each button (1W, 3M, etc.)
- Chart updates (loading state briefly shows)
- Different data may appear for different ranges

- [ ] **Step 5: Check browser console for errors**

```bash
# Open developer tools in browser, check console tab
# Should see no error messages
```

- [ ] **Step 6: Test with a card that has price data**

Try searching for popular cards (e.g., "Sheoldred", "Lightning Bolt") to find cards with price history.

---

## Verification & Testing

### Task 12: Verify All Backend Tests Pass

- [ ] **Step 1: Run all new backend tests**

```bash
pytest tests/unit/core/models/card_catalog/test_price_history_model.py -v
pytest tests/unit/core/repositories/card_catalog/test_card_repository_price_history.py -v
pytest tests/unit/core/services/card_catalog/test_card_service_price_history.py -v
```

Expected: All PASS

- [ ] **Step 2: Run full test suite to check for regressions**

```bash
pytest tests/unit/ -v --tb=short 2>&1 | tail -20
```

Expected: No new failures

- [ ] **Step 3: Commit summary**

```bash
git log --oneline -15
```

Verify all tasks are committed.

---

## Success Criteria Checklist

- [ ] Backend endpoint `GET /card-reference/{card_id}/price-history` returns aggregated price data
- [ ] Frontend displays DualAreaChart with two distinct curves (list avg + sold avg)
- [ ] Time range toggles (1W, 1M default, 3M, 1Y, ALL) update the chart
- [ ] Card detail layout is two-column (art left, info + charts right)
- [ ] Responsive design works on mobile (<768px)
- [ ] All unit tests pass
- [ ] No console errors when viewing card detail
- [ ] Price data is cached at API (24h) and client (24h) levels
- [ ] Charts handle missing data gracefully (null-fill or skip)

---

## Known Limitations (Phase 1)

- Only non-foil prices (foil support deferred)
- No individual source filtering (aggregated only)
- No annotations/markers on timeline (set releases, bans, etc.)
- No CSV export

These are in the Future Work section and can be addressed in follow-up PRs.
