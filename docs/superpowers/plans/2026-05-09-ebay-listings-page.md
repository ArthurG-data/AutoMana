# eBay Listings Page — Live Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the Active tab of `/listings` to real eBay API data — fetched in parallel from all production apps — adding thumbnail, app badge, finish column, and inline card-name filter.

**Architecture:** Add `EbayLiveListing` type and `parseCardTitle` utility to `mockListings.ts`; add `fetchActiveListings` to `api.ts` with a raw-to-typed mapper; rewrite `ListingsTable` to consume `EbayLiveListing[]`; update `listings.tsx` to fetch apps then listings in parallel and pass live data to the table.

**Tech Stack:** React 18, TypeScript, Vitest, @testing-library/react, CSS Modules, TanStack Router

---

## File Map

| File | Change |
|------|--------|
| `src/frontend/src/features/ebay/mockListings.ts` | Add `EbayLiveListing` interface + `parseCardTitle` helper |
| `src/frontend/src/features/ebay/__tests__/mockListings.test.ts` | **Create** — tests for `parseCardTitle` |
| `src/frontend/src/features/ebay/api.ts` | Add `fetchActiveListings` + internal `mapToLiveListing` |
| `src/frontend/src/features/ebay/__tests__/api.test.ts` | Extend — tests for `fetchActiveListings` |
| `src/frontend/src/features/ebay/components/ListingsTable.tsx` | Rewrite — new props/columns/filter |
| `src/frontend/src/features/ebay/components/ListingsTable.module.css` | Add new CSS classes |
| `src/frontend/src/features/ebay/components/__tests__/ListingsTable.test.tsx` | Rewrite — tests for new component |
| `src/frontend/src/routes/listings.tsx` | Wire Active tab to live data |
| `src/frontend/src/routes/__tests__/listings.test.tsx` | **Create** — tests for route fetch/render |

---

## Task 1: `EbayLiveListing` interface and `parseCardTitle` helper

**Files:**
- Modify: `src/frontend/src/features/ebay/mockListings.ts`
- Create: `src/frontend/src/features/ebay/__tests__/mockListings.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/frontend/src/features/ebay/__tests__/mockListings.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { parseCardTitle } from '../mockListings'

describe('parseCardTitle', () => {
  it('strips set code, collector number, condition, MTG suffix', () => {
    const { cardName, setInfo } = parseCardTitle('Ragavan, Nimble Pilferer MH2 #138 NM MTG')
    expect(cardName).toBe('Ragavan, Nimble Pilferer')
    expect(setInfo).toBe('MH2 #138')
  })

  it('strips FOIL suffix', () => {
    const { cardName, setInfo } = parseCardTitle('Mox Diamond STH NM FOIL MTG')
    expect(cardName).toBe('Mox Diamond')
    expect(setInfo).toBe('STH')
  })

  it('strips 3-letter set code without collector number', () => {
    const { cardName, setInfo } = parseCardTitle('Force of Will ALL LP MTG')
    expect(cardName).toBe('Force of Will')
    expect(setInfo).toBe('ALL')
  })

  it('handles set code with digits (e.g. MH2)', () => {
    const { cardName, setInfo } = parseCardTitle('Sheoldred, the Apocalypse DMU NM MTG')
    expect(cardName).toBe('Sheoldred, the Apocalypse')
    expect(setInfo).toBe('DMU')
  })

  it('falls back to full title when no suffix tokens match', () => {
    const { cardName, setInfo } = parseCardTitle('Some weird title')
    expect(cardName).toBe('Some weird title')
    expect(setInfo).toBe('')
  })

  it('does not strip mixed-case words like card names', () => {
    const { cardName } = parseCardTitle('Wrenn and Six MH1 NM MTG')
    expect(cardName).toBe('Wrenn and Six')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd src/frontend && npx vitest run src/features/ebay/__tests__/mockListings.test.ts
```

Expected: FAIL with "parseCardTitle is not a function" or similar.

- [ ] **Step 3: Add `EbayLiveListing` interface and `parseCardTitle` to `mockListings.ts`**

Append to the end of `src/frontend/src/features/ebay/mockListings.ts`:

```typescript
// ── Live listing types ─────────────────────────────────────────────────────

export interface EbayLiveListing {
  itemId: string
  title: string
  cardName: string
  setInfo: string
  price: number
  currency: string
  conditionLabel: string
  finish: 'Foil' | 'Regular'
  watchCount: number
  viewItemUrl: string
  imageUrl: string | null
  appCode: string
  appName: string
}

// ── Title parsing ──────────────────────────────────────────────────────────

const NOISE_TOKEN_RE = /^(MTG|FOIL|NM\+?|LP|MP|HP|PLD|EX|VG|GD|PR)$/i
const SET_CODE_RE = /^[A-Z0-9]{2,5}$/

export function parseCardTitle(title: string): { cardName: string; setInfo: string } {
  const tokens = title.trim().split(/\s+/)
  let i = tokens.length - 1
  const setTokens: string[] = []

  while (i >= 0) {
    const tok = tokens[i]
    if (NOISE_TOKEN_RE.test(tok)) {
      i--
      continue
    }
    if (/^#\d+$/.test(tok)) {
      setTokens.unshift(tok)
      i--
      continue
    }
    if (SET_CODE_RE.test(tok)) {
      setTokens.unshift(tok)
      i--
      continue
    }
    break
  }

  const cardName = i >= 0 ? tokens.slice(0, i + 1).join(' ') : title
  return { cardName, setInfo: setTokens.join(' ') }
}
```

`SET_CODE_RE` matches only tokens that are entirely uppercase letters/digits (2–5 chars), which excludes mixed-case card name words like "Will" or "Six".

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd src/frontend && npx vitest run src/features/ebay/__tests__/mockListings.test.ts
```

Expected: PASS — 6 tests passing.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/ebay/mockListings.ts \
        src/frontend/src/features/ebay/__tests__/mockListings.test.ts
git commit -m "feat(ebay): add EbayLiveListing interface and parseCardTitle helper"
```

---

## Task 2: `fetchActiveListings` API function

**Files:**
- Modify: `src/frontend/src/features/ebay/api.ts`
- Modify: `src/frontend/src/features/ebay/__tests__/api.test.ts`

The backend `GET /listing/active?app_code=…` returns a `PaginatedResponse` with `data` = array of `ItemModel` objects. The `apiClient` unwraps `{ data, success }` shaped responses automatically, so the resolved value is the item array directly.

Backend Pydantic serialises with Python field names (not aliases), so items arrive as:
- `ItemID`, `Title`, `WatchCount`, `ConditionDisplayName`, `ConditionDescription`, `SKU`
- `StartPrice: { currencyID: string, text: number }`  (`BaseCostType` fields)
- `ListingDetails: { ViewItemURL: string | null }`
- `PictureDetails: { GalleryURL: string | string[] } | null`  (raw dict)
- `ItemSpecifics: { NameValueList: ... } | null`  (raw dict)

- [ ] **Step 1: Write the failing tests**

Append a new `describe` block to `src/frontend/src/features/ebay/__tests__/api.test.ts`:

```typescript
import { fetchActiveListings } from '../api'

// (add these imports at the top alongside the existing ones)
// import { fetchActiveListings } from '../api'
// import type { EbayLiveListing } from '../mockListings'

describe('fetchActiveListings', () => {
  beforeEach(() => {
    mockApiClient.mockReset()
  })

  it('calls GET /listing/active with correct query params', async () => {
    mockApiClient.mockResolvedValue([])
    await fetchActiveListings('my_app', 50, 0)
    expect(mockApiClient).toHaveBeenCalledWith(
      '/listing/active?app_code=my_app&limit=50&offset=0'
    )
  })

  it('uses default limit=50 and offset=0', async () => {
    mockApiClient.mockResolvedValue([])
    await fetchActiveListings('my_app')
    expect(mockApiClient).toHaveBeenCalledWith(
      '/listing/active?app_code=my_app&limit=50&offset=0'
    )
  })

  it('maps StartPrice to price and currency', async () => {
    mockApiClient.mockResolvedValue([
      {
        ItemID: '123',
        Title: 'Ragavan, Nimble Pilferer MH2 NM MTG',
        StartPrice: { currencyID: 'AUD', text: 62.0 },
        WatchCount: 5,
        ConditionDisplayName: 'Near Mint or Better',
        ConditionDescription: null,
        ItemSpecifics: null,
        ListingDetails: { ViewItemURL: 'https://www.ebay.com.au/itm/123' },
        PictureDetails: { GalleryURL: 'https://img.ebay.com/1.jpg' },
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].price).toBe(62)
    expect(result[0].currency).toBe('AUD')
    expect(result[0].itemId).toBe('123')
    expect(result[0].conditionLabel).toBe('Near Mint or Better')
  })

  it('falls back to ConditionDescription when ConditionDisplayName is absent', async () => {
    mockApiClient.mockResolvedValue([
      {
        ItemID: '124',
        Title: 'Force of Will ALL LP MTG',
        StartPrice: { currencyID: 'AUD', text: 100 },
        WatchCount: 0,
        ConditionDescription: 'Light Play',
        ConditionDisplayName: null,
        ItemSpecifics: null,
        ListingDetails: { ViewItemURL: 'https://www.ebay.com.au/itm/124' },
        PictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].conditionLabel).toBe('Light Play')
  })

  it('uses fallback eBay URL when ViewItemURL is null', async () => {
    mockApiClient.mockResolvedValue([
      {
        ItemID: '456',
        Title: 'Force of Will ALL MTG',
        StartPrice: { currencyID: 'AUD', text: 10 },
        WatchCount: 0,
        ConditionDisplayName: null,
        ConditionDescription: null,
        ItemSpecifics: null,
        ListingDetails: null,
        PictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].viewItemUrl).toBe('https://www.ebay.com.au/itm/456')
  })

  it('extracts Finish from ItemSpecifics NameValueList (array)', async () => {
    mockApiClient.mockResolvedValue([
      {
        ItemID: '789',
        Title: 'Ragavan, Nimble Pilferer MH2 NM FOIL MTG',
        StartPrice: { currencyID: 'AUD', text: 100 },
        WatchCount: 3,
        ConditionDisplayName: 'Near Mint',
        ConditionDescription: null,
        ItemSpecifics: {
          NameValueList: [{ Name: 'Finish', Value: 'Foil' }],
        },
        ListingDetails: { ViewItemURL: 'https://www.ebay.com.au/itm/789' },
        PictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].finish).toBe('Foil')
  })

  it('extracts Finish from ItemSpecifics NameValueList (single object, not array)', async () => {
    mockApiClient.mockResolvedValue([
      {
        ItemID: '790',
        Title: 'Ragavan MH2 NM FOIL MTG',
        StartPrice: { currencyID: 'AUD', text: 80 },
        WatchCount: 0,
        ConditionDisplayName: 'NM',
        ConditionDescription: null,
        ItemSpecifics: {
          NameValueList: { Name: 'Finish', Value: 'Foil' },
        },
        ListingDetails: { ViewItemURL: 'https://www.ebay.com.au/itm/790' },
        PictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].finish).toBe('Foil')
  })

  it('defaults finish to Regular when ItemSpecifics is null', async () => {
    mockApiClient.mockResolvedValue([
      {
        ItemID: '999',
        Title: 'Ancient Tomb TMP NM MTG',
        StartPrice: { currencyID: 'AUD', text: 58 },
        WatchCount: 0,
        ConditionDisplayName: 'NM',
        ConditionDescription: null,
        ItemSpecifics: null,
        ListingDetails: { ViewItemURL: 'https://www.ebay.com.au/itm/999' },
        PictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].finish).toBe('Regular')
  })

  it('extracts GalleryURL when PictureDetails is present', async () => {
    mockApiClient.mockResolvedValue([
      {
        ItemID: '111',
        Title: 'Dark Confidant RAV NM MTG',
        StartPrice: { currencyID: 'AUD', text: 30 },
        WatchCount: 1,
        ConditionDisplayName: 'NM',
        ConditionDescription: null,
        ItemSpecifics: null,
        ListingDetails: { ViewItemURL: 'https://www.ebay.com.au/itm/111' },
        PictureDetails: { GalleryURL: 'https://img.ebay.com/card.jpg' },
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].imageUrl).toBe('https://img.ebay.com/card.jpg')
  })

  it('sets imageUrl to null when PictureDetails is null', async () => {
    mockApiClient.mockResolvedValue([
      {
        ItemID: '222',
        Title: 'Snapcaster Mage ISD LP MTG',
        StartPrice: { currencyID: 'AUD', text: 20 },
        WatchCount: 0,
        ConditionDisplayName: 'LP',
        ConditionDescription: null,
        ItemSpecifics: null,
        ListingDetails: { ViewItemURL: 'https://www.ebay.com.au/itm/222' },
        PictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].imageUrl).toBeNull()
  })

  it('parses cardName from title', async () => {
    mockApiClient.mockResolvedValue([
      {
        ItemID: '333',
        Title: 'Sheoldred, the Apocalypse DMU #107 NM MTG',
        StartPrice: { currencyID: 'AUD', text: 44 },
        WatchCount: 0,
        ConditionDisplayName: 'NM',
        ConditionDescription: null,
        ItemSpecifics: null,
        ListingDetails: { ViewItemURL: 'https://www.ebay.com.au/itm/333' },
        PictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].cardName).toBe('Sheoldred, the Apocalypse')
    expect(result[0].setInfo).toBe('DMU #107')
  })

  it('propagates errors from apiClient', async () => {
    mockApiClient.mockRejectedValue(new Error('API 401: unauthorized'))
    await expect(fetchActiveListings('my_app')).rejects.toThrow('API 401: unauthorized')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd src/frontend && npx vitest run src/features/ebay/__tests__/api.test.ts
```

Expected: FAIL with "fetchActiveListings is not a function".

- [ ] **Step 3: Implement `fetchActiveListings` and helpers in `api.ts`**

Add these imports and implementations to `src/frontend/src/features/ebay/api.ts`:

At the top of the file, add the import:
```typescript
import { parseCardTitle, type EbayLiveListing } from './mockListings'
```

Then add the following at the end of the file:

```typescript
// ── Active listings ────────────────────────────────────────────────────────

interface RawEbayItem {
  ItemID?: string | null
  Title?: string | null
  StartPrice?: { currencyID?: string | null; text?: string | number | null } | null
  WatchCount?: number | null
  ConditionDescription?: string | null
  ConditionDisplayName?: string | null
  PictureDetails?: { GalleryURL?: string | string[] } | null
  ListingDetails?: { ViewItemURL?: string | null } | null
  ItemSpecifics?: {
    NameValueList?:
      | Array<{ Name: string; Value: string | string[] }>
      | { Name: string; Value: string | string[] }
  } | null
}

function getFinish(itemSpecifics: RawEbayItem['ItemSpecifics']): 'Foil' | 'Regular' {
  if (!itemSpecifics?.NameValueList) return 'Regular'
  const list = Array.isArray(itemSpecifics.NameValueList)
    ? itemSpecifics.NameValueList
    : [itemSpecifics.NameValueList]
  const finishSpec = list.find((nv) => nv.Name === 'Finish')
  if (!finishSpec) return 'Regular'
  const val = Array.isArray(finishSpec.Value) ? finishSpec.Value[0] : finishSpec.Value
  return val === 'Foil' ? 'Foil' : 'Regular'
}

function getImageUrl(pictureDetails: RawEbayItem['PictureDetails']): string | null {
  if (!pictureDetails?.GalleryURL) return null
  return Array.isArray(pictureDetails.GalleryURL)
    ? (pictureDetails.GalleryURL[0] ?? null)
    : pictureDetails.GalleryURL
}

function mapToLiveListing(raw: RawEbayItem): Omit<EbayLiveListing, 'appCode' | 'appName'> {
  const itemId = raw.ItemID ?? ''
  const { cardName, setInfo } = parseCardTitle(raw.Title ?? '')
  return {
    itemId,
    title: raw.Title ?? '',
    cardName,
    setInfo,
    price: Number(raw.StartPrice?.text ?? 0),
    currency: raw.StartPrice?.currencyID ?? 'AUD',
    conditionLabel: raw.ConditionDisplayName ?? raw.ConditionDescription ?? '',
    finish: getFinish(raw.ItemSpecifics),
    watchCount: raw.WatchCount ?? 0,
    viewItemUrl:
      raw.ListingDetails?.ViewItemURL ?? `https://www.ebay.com.au/itm/${itemId}`,
    imageUrl: getImageUrl(raw.PictureDetails),
  }
}

export async function fetchActiveListings(
  appCode: string,
  limit = 50,
  offset = 0,
): Promise<EbayLiveListing[]> {
  const items = await apiClient<RawEbayItem[]>(
    `/listing/active?app_code=${encodeURIComponent(appCode)}&limit=${limit}&offset=${offset}`
  )
  return (items ?? []).map((raw) => ({ ...mapToLiveListing(raw), appCode, appName: '' }))
}
```

Note: `appName` is set to `''` here; the caller (`listings.tsx`) overwrites it after the fact via `.map(item => ({ ...item, appName: app.app_name }))`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd src/frontend && npx vitest run src/features/ebay/__tests__/api.test.ts
```

Expected: all tests in both describe blocks pass (existing `registerEbayApp` tests + new `fetchActiveListings` tests).

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/ebay/api.ts \
        src/frontend/src/features/ebay/__tests__/api.test.ts
git commit -m "feat(ebay): add fetchActiveListings API function with raw item mapper"
```

---

## Task 3: Rewrite `ListingsTable` component

**Files:**
- Modify: `src/frontend/src/features/ebay/components/ListingsTable.tsx`
- Modify: `src/frontend/src/features/ebay/components/ListingsTable.module.css`
- Modify: `src/frontend/src/features/ebay/components/__tests__/ListingsTable.test.tsx`

The component changes from `ActiveListing[]` to `EbayLiveListing[]`. The Actions, Market price, and Set columns are removed. New columns: Thumbnail, App badge, Finish. Card name becomes an external `<a>` to eBay. The CARD NAME header contains an inline underline `<input>` for client-side filtering.

- [ ] **Step 1: Replace the test file with new tests**

Replace the entire contents of `src/frontend/src/features/ebay/components/__tests__/ListingsTable.test.tsx`:

```typescript
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ListingsTable } from '../ListingsTable'
import type { EbayLiveListing } from '../../mockListings'

function makeListing(overrides: Partial<EbayLiveListing> = {}): EbayLiveListing {
  return {
    itemId: 'l1',
    title: 'Ragavan, Nimble Pilferer MH2 NM MTG',
    cardName: 'Ragavan, Nimble Pilferer',
    setInfo: 'MH2',
    price: 62,
    currency: 'AUD',
    conditionLabel: 'NM',
    finish: 'Regular',
    watchCount: 12,
    viewItemUrl: 'https://www.ebay.com.au/itm/123',
    imageUrl: null,
    appCode: 'automana_au',
    appName: 'AutoMana AU',
    ...overrides,
  }
}

describe('ListingsTable', () => {
  it('renders column headers', () => {
    render(<ListingsTable listings={[]} />)
    expect(screen.getByText(/app/i)).toBeTruthy()
    expect(screen.getByText(/cond/i)).toBeTruthy()
    expect(screen.getByText(/finish/i)).toBeTruthy()
    expect(screen.getByText(/price/i)).toBeTruthy()
    expect(screen.getByText(/watch/i)).toBeTruthy()
  })

  it('shows empty state when no listings and not loading', () => {
    render(<ListingsTable listings={[]} />)
    expect(screen.getByText(/no listings found/i)).toBeTruthy()
  })

  it('renders card name as an external link to eBay', () => {
    const listing = makeListing()
    render(<ListingsTable listings={[listing]} />)
    const link = screen.getByRole('link', { name: /ragavan/i })
    expect(link.getAttribute('href')).toBe('https://www.ebay.com.au/itm/123')
    expect(link.getAttribute('target')).toBe('_blank')
    expect(link.getAttribute('rel')).toBe('noopener noreferrer')
  })

  it('renders set info badge next to card name', () => {
    render(<ListingsTable listings={[makeListing({ setInfo: 'MH2 #138' })]} />)
    expect(screen.getByText('MH2 #138')).toBeTruthy()
  })

  it('renders app badge with app name', () => {
    render(<ListingsTable listings={[makeListing()]} />)
    expect(screen.getByText('AutoMana AU')).toBeTruthy()
  })

  it('shows Regular finish as plain text', () => {
    render(<ListingsTable listings={[makeListing({ finish: 'Regular' })]} />)
    expect(screen.getByText('Regular')).toBeTruthy()
  })

  it('shows Foil finish with badge styling', () => {
    render(<ListingsTable listings={[makeListing({ finish: 'Foil' })]} />)
    expect(screen.getByText('Foil')).toBeTruthy()
  })

  it('renders thumbnail img when imageUrl is provided', () => {
    const listing = makeListing({ imageUrl: 'https://img.ebay.com/card.jpg' })
    render(<ListingsTable listings={[listing]} />)
    const img = screen.getByRole('img', { name: /ragavan/i })
    expect(img.getAttribute('src')).toBe('https://img.ebay.com/card.jpg')
  })

  it('renders fallback placeholder when imageUrl is null', () => {
    render(<ListingsTable listings={[makeListing({ imageUrl: null })]} />)
    expect(screen.getByText('MTG')).toBeTruthy()
  })

  it('filters rows by card name input', () => {
    const listings = [
      makeListing({ itemId: 'l1', cardName: 'Ragavan, Nimble Pilferer' }),
      makeListing({ itemId: 'l2', cardName: 'Force of Will', viewItemUrl: 'https://www.ebay.com.au/itm/2' }),
    ]
    render(<ListingsTable listings={listings} />)
    const input = screen.getByPlaceholderText('card name')
    fireEvent.change(input, { target: { value: 'Force' } })
    expect(screen.queryByText('Ragavan, Nimble Pilferer')).toBeNull()
    expect(screen.getByText('Force of Will')).toBeTruthy()
  })

  it('filter is case-insensitive', () => {
    const listings = [makeListing({ cardName: 'Ragavan, Nimble Pilferer' })]
    render(<ListingsTable listings={listings} />)
    const input = screen.getByPlaceholderText('card name')
    fireEvent.change(input, { target: { value: 'ragavan' } })
    expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeTruthy()
  })

  it('shows skeleton rows when isLoading is true', () => {
    render(<ListingsTable listings={[]} isLoading />)
    expect(screen.queryByText(/no listings found/i)).toBeNull()
    const skeletonRows = document.querySelectorAll('[data-testid="skeleton-row"]')
    expect(skeletonRows.length).toBe(3)
  })

  it('renders price with currency', () => {
    render(<ListingsTable listings={[makeListing({ price: 62, currency: 'AUD' })]} />)
    expect(screen.getByText(/62/)).toBeTruthy()
  })

  it('renders watch count', () => {
    render(<ListingsTable listings={[makeListing({ watchCount: 7 })]} />)
    expect(screen.getByText('7')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd src/frontend && npx vitest run src/features/ebay/components/__tests__/ListingsTable.test.tsx
```

Expected: many failures — old component has wrong props, missing elements.

- [ ] **Step 3: Rewrite `ListingsTable.tsx`**

Replace the entire content of `src/frontend/src/features/ebay/components/ListingsTable.tsx`:

```typescript
import React, { useState, useMemo } from 'react'
import { AIBadge } from '../../../components/design-system/AIBadge'
import { Icon } from '../../../components/design-system/Icon'
import type { EbayLiveListing } from '../mockListings'
import styles from './ListingsTable.module.css'

interface ListingsTableProps {
  listings: EbayLiveListing[]
  isLoading?: boolean
}

const APP_PALETTE = ['var(--hd-blue)', '#a78bfa', '#34d399', '#f59e0b']

export function ListingsTable({ listings, isLoading = false }: ListingsTableProps) {
  const [filter, setFilter] = useState('')

  const appColors = useMemo<Record<string, string>>(() => {
    const codes = [...new Set(listings.map((l) => l.appCode))]
    return Object.fromEntries(codes.map((code, i) => [code, APP_PALETTE[i % APP_PALETTE.length]]))
  }, [listings])

  const visible = useMemo(
    () =>
      filter.trim()
        ? listings.filter((l) =>
            l.cardName.toLowerCase().includes(filter.toLowerCase())
          )
        : listings,
    [listings, filter]
  )

  return (
    <div className={styles.wrapper} role="region" aria-label="Listings table">
      <table className={styles.table}>
        <thead className={styles.thead}>
          <tr>
            <th scope="col" style={{ width: 36 }} aria-label="Thumbnail" />
            <th scope="col">
              <div className={styles.filterInputWrapper}>
                <input
                  className={styles.filterInput}
                  type="text"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="card name"
                  aria-label="Filter by card name"
                />
              </div>
            </th>
            <th scope="col">App</th>
            <th scope="col">Cond</th>
            <th scope="col">Finish</th>
            <th scope="col" className={styles.right}>Price</th>
            <th scope="col" className={styles.center}>Watchers</th>
            <th scope="col" className={styles.center}>Status</th>
          </tr>
        </thead>
        <tbody>
          {isLoading && (
            <>
              {[0, 1, 2].map((i) => (
                <tr key={i} data-testid="skeleton-row" className={styles.skeletonRow}>
                  <td><div className={styles.skeletonThumb} /></td>
                  <td><div className={styles.skeletonText} style={{ width: '60%' }} /></td>
                  <td><div className={styles.skeletonText} style={{ width: '70%' }} /></td>
                  <td><div className={styles.skeletonText} style={{ width: '40%' }} /></td>
                  <td><div className={styles.skeletonText} style={{ width: '50%' }} /></td>
                  <td><div className={styles.skeletonText} style={{ width: '50%', marginLeft: 'auto' }} /></td>
                  <td><div className={styles.skeletonText} style={{ width: '30%', margin: '0 auto' }} /></td>
                  <td><div className={styles.skeletonText} style={{ width: '50%', margin: '0 auto' }} /></td>
                </tr>
              ))}
            </>
          )}
          {!isLoading && visible.length === 0 && (
            <tr>
              <td colSpan={8} className={styles.empty}>No listings found</td>
            </tr>
          )}
          {!isLoading && visible.map((listing) => {
            const isFoil = listing.finish === 'Foil'
            const appColor = appColors[listing.appCode] ?? APP_PALETTE[0]
            return (
              <tr
                key={listing.itemId}
                className={[styles.row, isFoil ? styles.rowFoil : ''].filter(Boolean).join(' ')}
              >
                {/* Thumbnail */}
                <td className={styles.thumbCell}>
                  {listing.imageUrl ? (
                    <img
                      src={listing.imageUrl}
                      alt={listing.cardName}
                      className={[styles.thumb, isFoil ? styles.thumbFoil : ''].filter(Boolean).join(' ')}
                    />
                  ) : (
                    <div className={styles.thumbPlaceholder}>MTG</div>
                  )}
                </td>

                {/* Card name + set info */}
                <td>
                  <div className={styles.nameCell}>
                    <a
                      href={listing.viewItemUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={styles.cardName}
                    >
                      {listing.cardName}
                    </a>
                    {listing.setInfo && (
                      <span className={styles.setInfo}>{listing.setInfo}</span>
                    )}
                  </div>
                </td>

                {/* App badge */}
                <td>
                  <span
                    className={styles.appBadge}
                    style={{
                      color: appColor,
                      background: `${appColor}1a`,
                      border: `1px solid ${appColor}44`,
                    }}
                  >
                    {listing.appName.length > 10
                      ? listing.appName.slice(0, 10)
                      : listing.appName}
                  </span>
                </td>

                {/* Condition */}
                <td>
                  <span className={styles.condition}>{listing.conditionLabel}</span>
                </td>

                {/* Finish */}
                <td>
                  {isFoil ? (
                    <span className={styles.foilBadge}>Foil</span>
                  ) : (
                    <span className={styles.regularFinish}>Regular</span>
                  )}
                </td>

                {/* Price */}
                <td className={styles.right}>
                  <span className={styles.price}>
                    {listing.currency}&nbsp;{listing.price.toFixed(2)}
                  </span>
                </td>

                {/* Watchers */}
                <td className={styles.center}>
                  <span className={styles.watchers}>
                    <Icon kind="eye" size={11} color="var(--hd-muted)" />
                    {listing.watchCount}
                  </span>
                </td>

                {/* AI status (static badge, real signal TBD) */}
                <td className={styles.center}>
                  <AIBadge status="ok" showLabel size="sm" />
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

- [ ] **Step 4: Add new CSS classes to `ListingsTable.module.css`**

Append to the end of `src/frontend/src/features/ebay/components/ListingsTable.module.css`:

```css
/* Filter input in header */
.filterInputWrapper {
  display: flex;
  align-items: center;
}

.filterInput {
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--hd-border);
  color: var(--hd-sub);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 1.2px;
  text-transform: uppercase;
  padding: 2px 0;
  width: 140px;
  outline: none;
  transition: border-color 0.15s;
}

.filterInput::placeholder {
  color: var(--hd-sub);
  text-transform: uppercase;
  letter-spacing: 1.2px;
}

.filterInput:focus {
  border-bottom-color: var(--hd-accent);
}

/* Thumbnail column */
.thumbCell {
  padding: 6px 10px;
  width: 36px;
}

.thumb {
  width: 28px;
  height: 39px;
  border-radius: 3px;
  object-fit: cover;
  display: block;
}

.thumbFoil {
  border: 1px solid #a78bfa44;
  box-shadow: 0 0 6px #a78bfa33;
}

.thumbPlaceholder {
  width: 28px;
  height: 39px;
  border-radius: 3px;
  background: var(--hd-surface-alt);
  border: 1px solid var(--hd-border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-size: 8px;
  color: var(--hd-sub);
  letter-spacing: 0.5px;
}

/* App badge */
.appBadge {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 90px;
}

/* Finish badges */
.foilBadge {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  background: linear-gradient(90deg, #a78bfa22, #60a5fa22);
  border: 1px solid #a78bfa44;
  color: #a78bfa;
}

.regularFinish {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--hd-sub);
}

/* Foil row tint */
.rowFoil {
  background: #a78bfa05;
}

.rowFoil:hover {
  background: #a78bfa0d;
}

/* Price */
.price {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--hd-text);
}

/* Skeleton loading */
.skeletonRow td {
  padding: 10px 14px;
}

.skeletonThumb {
  width: 28px;
  height: 39px;
  border-radius: 3px;
  background: var(--hd-surface-alt);
  animation: shimmer 1.4s infinite linear;
}

.skeletonText {
  height: 10px;
  border-radius: 3px;
  background: var(--hd-surface-alt);
  animation: shimmer 1.4s infinite linear;
}

@keyframes shimmer {
  0%   { opacity: 0.6; }
  50%  { opacity: 0.3; }
  100% { opacity: 0.6; }
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd src/frontend && npx vitest run src/features/ebay/components/__tests__/ListingsTable.test.tsx
```

Expected: all 14 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/ebay/components/ListingsTable.tsx \
        src/frontend/src/features/ebay/components/ListingsTable.module.css \
        src/frontend/src/features/ebay/components/__tests__/ListingsTable.test.tsx
git commit -m "feat(ebay): rewrite ListingsTable with live data columns, thumbnail, app badge, filter"
```

---

## Task 4: Wire `listings.tsx` route to live data

**Files:**
- Modify: `src/frontend/src/routes/listings.tsx`
- Create: `src/frontend/src/routes/__tests__/listings.test.tsx`

The route currently imports `MOCK_ACTIVE_LISTINGS` and passes it to `<ListingsTable>`. After this task it will fetch production apps, fetch their active listings in parallel, and pass the merged result to the table with `isLoading` and per-app error banners.

- [ ] **Step 1: Write the failing tests**

Create `src/frontend/src/routes/__tests__/listings.test.tsx`:

```typescript
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'

vi.mock('../../features/ebay/api', () => ({
  fetchUserApps: vi.fn(),
  fetchActiveListings: vi.fn(),
}))

vi.mock('../../components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('../../components/layout/TopBar', () => ({
  TopBar: ({ title }: { title: string }) => <div>{title}</div>,
}))

vi.mock('../../features/ebay/components/ListingsTable', () => ({
  ListingsTable: ({ listings, isLoading }: { listings: { appName: string }[]; isLoading?: boolean }) => (
    <div
      data-testid="listings-table"
      data-loading={String(isLoading)}
      data-count={listings.length}
      data-app-names={listings.map((l) => l.appName).join(',')}
    />
  ),
}))

import { fetchUserApps, fetchActiveListings } from '../../features/ebay/api'
import type { EbayAppSummary } from '../../features/ebay/api'
import type { EbayLiveListing } from '../../features/ebay/mockListings'
import { ListingsPage } from '../listings'

const mockFetchUserApps = vi.mocked(fetchUserApps)
const mockFetchActiveListings = vi.mocked(fetchActiveListings)

function makeApp(overrides: Partial<EbayAppSummary> = {}): EbayAppSummary {
  return {
    app_id: 'app-1',
    app_name: 'AutoMana AU',
    app_code: 'automana_au',
    environment: 'PRODUCTION',
    description: null,
    is_active: true,
    is_connected: true,
    token_expires_at: null,
    other_user_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function makeListing(overrides: Partial<EbayLiveListing> = {}): EbayLiveListing {
  return {
    itemId: 'l1',
    title: 'Ragavan MH2 NM MTG',
    cardName: 'Ragavan',
    setInfo: 'MH2',
    price: 62,
    currency: 'AUD',
    conditionLabel: 'NM',
    finish: 'Regular',
    watchCount: 5,
    viewItemUrl: 'https://www.ebay.com.au/itm/123',
    imageUrl: null,
    appCode: 'automana_au',
    appName: 'AutoMana AU',
    ...overrides,
  }
}

function renderListingsPage() {
  return render(<ListingsPage />)
}

describe('ListingsPage Active tab', () => {
  beforeEach(() => {
    mockFetchUserApps.mockReset()
    mockFetchActiveListings.mockReset()
  })

  it('shows loading skeleton while fetching', async () => {
    mockFetchUserApps.mockReturnValue(new Promise(() => {}))
    await renderListingsPage()
    const table = screen.getByTestId('listings-table')
    expect(table.getAttribute('data-loading')).toBe('true')
  })

  it('passes merged live listings to ListingsTable after fetch', async () => {
    const listing = makeListing()
    mockFetchUserApps.mockResolvedValue([makeApp()])
    mockFetchActiveListings.mockResolvedValue([listing])
    await renderListingsPage()
    await waitFor(() => {
      const table = screen.getByTestId('listings-table')
      expect(table.getAttribute('data-count')).toBe('1')
      expect(table.getAttribute('data-loading')).toBe('false')
    })
  })

  it('only fetches PRODUCTION apps, ignores SANDBOX', async () => {
    mockFetchUserApps.mockResolvedValue([
      makeApp({ environment: 'PRODUCTION', app_code: 'prod_app' }),
      makeApp({ environment: 'SANDBOX', app_code: 'sandbox_app' }),
    ])
    mockFetchActiveListings.mockResolvedValue([])
    await renderListingsPage()
    await waitFor(() => {
      expect(mockFetchActiveListings).toHaveBeenCalledTimes(1)
      expect(mockFetchActiveListings).toHaveBeenCalledWith('prod_app', 50, 0)
    })
  })

  it('merges listings from multiple apps', async () => {
    mockFetchUserApps.mockResolvedValue([
      makeApp({ app_code: 'app_1', app_name: 'App 1' }),
      makeApp({ app_code: 'app_2', app_name: 'App 2', app_id: 'app-2' }),
    ])
    mockFetchActiveListings
      .mockResolvedValueOnce([makeListing({ itemId: 'l1', appCode: 'app_1' })])
      .mockResolvedValueOnce([makeListing({ itemId: 'l2', appCode: 'app_2' })])
    await renderListingsPage()
    await waitFor(() => {
      const table = screen.getByTestId('listings-table')
      expect(table.getAttribute('data-count')).toBe('2')
    })
  })

  it('injects appName onto each listing', async () => {
    mockFetchUserApps.mockResolvedValue([makeApp({ app_code: 'automana_au', app_name: 'AutoMana AU' })])
    mockFetchActiveListings.mockResolvedValue([makeListing({ appCode: 'automana_au', appName: '' })])
    renderListingsPage()
    await waitFor(() => {
      const table = screen.getByTestId('listings-table')
      expect(table.getAttribute('data-app-names')).toBe('AutoMana AU')
    })
  })

  it('shows error banner when one app fetch fails', async () => {
    mockFetchUserApps.mockResolvedValue([
      makeApp({ app_code: 'app_ok', app_name: 'Good App' }),
      makeApp({ app_code: 'app_fail', app_name: 'Bad App', app_id: 'app-2' }),
    ])
    mockFetchActiveListings
      .mockResolvedValueOnce([makeListing()])
      .mockRejectedValueOnce(new Error('Network error'))
    await renderListingsPage()
    await waitFor(() => {
      expect(screen.getByText(/could not load listings for bad app/i)).toBeTruthy()
    })
  })

  it('renders listings from successful apps even when one fails', async () => {
    mockFetchUserApps.mockResolvedValue([
      makeApp({ app_code: 'app_ok', app_name: 'Good App' }),
      makeApp({ app_code: 'app_fail', app_name: 'Bad App', app_id: 'app-2' }),
    ])
    mockFetchActiveListings
      .mockResolvedValueOnce([makeListing({ itemId: 'l1' })])
      .mockRejectedValueOnce(new Error('fail'))
    await renderListingsPage()
    await waitFor(() => {
      const table = screen.getByTestId('listings-table')
      expect(table.getAttribute('data-count')).toBe('1')
    })
  })

  it('dismisses error banner on close click', async () => {
    const user = userEvent.setup()
    mockFetchUserApps.mockResolvedValue([makeApp({ app_code: 'app_fail', app_name: 'Bad App' })])
    mockFetchActiveListings.mockRejectedValue(new Error('fail'))
    await renderListingsPage()
    await waitFor(() => {
      expect(screen.getByText(/could not load listings for bad app/i)).toBeTruthy()
    })
    const closeBtn = screen.getByRole('button', { name: /dismiss/i })
    await user.click(closeBtn)
    expect(screen.queryByText(/could not load listings for bad app/i)).toBeNull()
  })

  it('does not fetch listings when there are no production apps', async () => {
    mockFetchUserApps.mockResolvedValue([
      makeApp({ environment: 'SANDBOX' }),
    ])
    await renderListingsPage()
    await waitFor(() => {
      expect(mockFetchActiveListings).not.toHaveBeenCalled()
    })
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd src/frontend && npx vitest run src/routes/__tests__/listings.test.tsx
```

Expected: FAIL — component does not import `fetchUserApps` or `fetchActiveListings` yet.

- [ ] **Step 3: Rewrite `listings.tsx`**

Replace the entire content of `src/frontend/src/routes/listings.tsx`:

```typescript
import React, { useState, useMemo, useEffect } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { Button } from '../components/ui/Button'
import { Icon } from '../components/design-system/Icon'
import { ListingsTable } from '../features/ebay/components/ListingsTable'
import { fetchUserApps, fetchActiveListings } from '../features/ebay/api'
import {
  MOCK_SOLD_LISTINGS,
  MOCK_ATTENTION_ALERTS,
  MOCK_STRATEGY_MIX,
  formatUSD,
  priceDeltaPct,
  type EbayLiveListing,
} from '../features/ebay/mockListings'
import styles from './Listings.module.css'

export const Route = createFileRoute('/listings')({
  component: ListingsPage,
})

type Tab = 'active' | 'sold' | 'saved'

const ALERT_COLORS: Record<string, string> = {
  overpriced:  'var(--hd-red)',
  stale:       'var(--hd-amber)',
  underpriced: 'var(--hd-blue)',
}

const ALERT_ICONS: Record<string, 'arrowDown' | 'flag' | 'arrowUp'> = {
  overpriced:  'arrowDown',
  stale:       'flag',
  underpriced: 'arrowUp',
}

export function ListingsPage() {
  const [tab, setTab] = useState<Tab>('active')
  const [listings, setListings] = useState<EbayLiveListing[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [failedApps, setFailedApps] = useState<string[]>([])
  const [dismissedApps, setDismissedApps] = useState<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false
    async function load() {
      setIsLoading(true)
      try {
        const apps = await fetchUserApps()
        const productionApps = apps.filter((a) => a.environment === 'PRODUCTION')

        const results = await Promise.allSettled(
          productionApps.map((app) =>
            fetchActiveListings(app.app_code, 50, 0).then((items) =>
              items.map((item) => ({ ...item, appName: app.app_name }))
            )
          )
        )

        if (cancelled) return

        const merged: EbayLiveListing[] = []
        const failed: string[] = []
        results.forEach((result, i) => {
          if (result.status === 'fulfilled') {
            merged.push(...result.value)
          } else {
            failed.push(productionApps[i].app_name)
          }
        })

        setListings(merged)
        setFailedApps(failed)
      } catch {
        // fetchUserApps itself failed — leave listings empty, no per-app banners
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  const strategyTotal = useMemo(
    () => MOCK_STRATEGY_MIX.reduce((a, b) => a + b.count, 0) || 1,
    []
  )

  const visibleBanners = failedApps.filter((name) => !dismissedApps.has(name))

  return (
    <AppShell active="listings">
      <TopBar
        title="Your listings"
        actions={
          <div style={{ display: 'flex', gap: 8 }}>
            <Button variant="ghost" size="sm">Import</Button>
            <Button
              variant="accent"
              size="sm"
              icon={<Icon kind="plus" size={12} color="currentColor" />}
            >
              New listing
            </Button>
          </div>
        }
      />

      <div className={styles.page}>
        {/* ── Error banners ────────────────────────────────────── */}
        {visibleBanners.map((appName) => (
          <div key={appName} className={styles.errorBanner} role="alert">
            <span>Could not load listings for {appName}.</span>
            <button
              className={styles.errorBannerDismiss}
              aria-label="Dismiss"
              onClick={() => setDismissedApps((prev) => new Set([...prev, appName]))}
            >
              <Icon kind="close" size={12} color="currentColor" />
            </button>
          </div>
        ))}

        {/* ── Tabs ─────────────────────────────────────────────── */}
        <div className={styles.tabRow} role="tablist" aria-label="Listing tabs">
          {(['active', 'sold', 'saved'] as Tab[]).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              className={[styles.tab, tab === t ? styles.tabActive : ''].filter(Boolean).join(' ')}
              onClick={() => setTab(t)}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
              {t === 'active' && (
                <span className={styles.tabCount}>{listings.length}</span>
              )}
            </button>
          ))}
        </div>

        {/* ── Main grid ─────────────────────────────────────────── */}
        <div className={styles.contentGrid}>
          <div>
            {tab === 'active' && (
              <ListingsTable listings={listings} isLoading={isLoading} />
            )}
            {tab === 'sold' && (
              <div className={styles.soldTable} role="region" aria-label="Sold listings">
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Card name</th>
                      <th>Set</th>
                      <th>Condition</th>
                      <th className={styles.right}>Sale price</th>
                      <th className={styles.right}>Market at sale</th>
                      <th className={styles.right}>Days listed</th>
                      <th>Sold date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {MOCK_SOLD_LISTINGS.map((s) => {
                      const delta = priceDeltaPct(s.salePrice, s.marketPriceAtSale)
                      return (
                        <tr key={s.id} className={styles.soldRow}>
                          <td>
                            <span className={styles.soldCardName}>{s.cardName}</span>
                            {s.foil && <span className={styles.foilBadge}>foil</span>}
                          </td>
                          <td><span className={styles.setCode}>{s.setCode}</span></td>
                          <td className={styles.condition}>{s.condition}</td>
                          <td className={[styles.right, styles.mono].join(' ')}>
                            <span className={delta >= 0 ? styles.positive : styles.negative}>
                              {formatUSD(s.salePrice)}
                            </span>
                          </td>
                          <td className={[styles.right, styles.mono, styles.muted].join(' ')}>
                            {formatUSD(s.marketPriceAtSale)}
                          </td>
                          <td className={[styles.right, styles.mono, styles.muted].join(' ')}>
                            {s.daysListed}d
                          </td>
                          <td className={[styles.mono, styles.muted].join(' ')}>{s.soldDate}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {tab === 'saved' && (
              <div className={styles.emptyState}>
                <Icon kind="tag" size={32} color="var(--hd-sub)" />
                <p>No saved drafts</p>
              </div>
            )}
          </div>

          {/* Right: sidebar panels */}
          <aside className={styles.sidebar} aria-label="Listings sidebar">
            <div className={styles.sidePanel}>
              <div className={styles.sidePanelTitle}>Needs your attention</div>
              <div className={styles.alertList}>
                {MOCK_ATTENTION_ALERTS.map((alert) => {
                  const color = ALERT_COLORS[alert.type]
                  const iconKind = ALERT_ICONS[alert.type]
                  return (
                    <div key={alert.id} className={styles.alertRow}>
                      <div className={styles.alertDot} style={{ background: color }} aria-hidden="true" />
                      <div className={styles.alertContent}>
                        <div className={styles.alertIcon} style={{ color }}>
                          <Icon kind={iconKind} size={11} color={color} />
                        </div>
                        <div>
                          <div className={styles.alertCard}>{alert.cardName}</div>
                          <div className={styles.alertMessage}>{alert.message}</div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            <div className={styles.sidePanel}>
              <div className={styles.sidePanelTitle}>Recent sales</div>
              {MOCK_SOLD_LISTINGS.slice(0, 3).map((sale) => {
                const delta = priceDeltaPct(sale.salePrice, sale.marketPriceAtSale)
                return (
                  <div key={sale.id} className={styles.recentSaleRow}>
                    <div className={styles.recentSaleName}>{sale.cardName}</div>
                    <div className={styles.recentSaleRight}>
                      <span className={styles.recentSalePrice}>{formatUSD(sale.salePrice)}</span>
                      <span className={[styles.recentSaleDelta, delta >= 0 ? styles.positive : styles.negative].join(' ')}>
                        {delta > 0 ? '+' : ''}{delta}%
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>

            <div className={styles.sidePanel}>
              <div className={styles.sidePanelTitle}>Strategy mix</div>
              <div className={styles.strategyBarWrapper}>
                <div className={styles.strategyBar} role="img" aria-label="Strategy distribution bar">
                  {MOCK_STRATEGY_MIX.map((item) => (
                    <div
                      key={item.label}
                      className={styles.strategyBarSegment}
                      style={{ flex: item.count, background: item.color }}
                      title={`${item.label}: ${item.count}`}
                    />
                  ))}
                </div>
              </div>
              <div className={styles.strategyLegend}>
                {MOCK_STRATEGY_MIX.map((item) => (
                  <div key={item.label} className={styles.strategyLegendRow}>
                    <div className={styles.strategyLegendDot} style={{ background: item.color }} aria-hidden="true" />
                    <span className={styles.strategyLegendLabel}>{item.label}</span>
                    <span className={styles.strategyLegendCount}>
                      {item.count} ({Math.round((item.count / strategyTotal) * 100)}%)
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </aside>
        </div>
      </div>
    </AppShell>
  )
}
```

Note: `ListingsPage` is exported as a named export so the test can import it directly without a router context.

- [ ] **Step 4: Add error banner CSS to `Listings.module.css`**

Check if `src/frontend/src/routes/Listings.module.css` exists:

```bash
ls src/frontend/src/routes/Listings.module.css
```

Append to the end of that file:

```css
/* Error banner */
.errorBanner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 0 0 8px 0;
  padding: 8px 12px;
  background: rgba(227, 94, 108, 0.08);
  border: 1px solid rgba(227, 94, 108, 0.25);
  border-radius: 6px;
  font-size: 12px;
  color: var(--hd-red);
}

.errorBannerDismiss {
  background: transparent;
  border: none;
  color: var(--hd-muted);
  cursor: pointer;
  padding: 2px;
  display: flex;
  align-items: center;
  border-radius: 3px;
  transition: color 0.1s;
}

.errorBannerDismiss:hover {
  color: var(--hd-text);
}
```

- [ ] **Step 5: Run all tests**

```bash
cd src/frontend && npx vitest run
```

Expected: all tests in the suite pass.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/routes/listings.tsx \
        src/frontend/src/routes/__tests__/listings.test.tsx
git commit -m "feat(ebay): wire listings Active tab to live API data with parallel fetch and error banners"
```

---

## Self-Review Checklist

Run this mentally after all tasks complete:

1. **Spec coverage:**
   - ✓ Thumbnail column (Task 3) — 28×39px, `object-fit: cover`, placeholder div
   - ✓ Card name as external link (Task 3) — `target="_blank" rel="noopener noreferrer"`
   - ✓ App badge with colour cycling (Task 3)
   - ✓ Finish badge — Foil gradient, Regular muted (Task 3 + CSS)
   - ✓ Foil row tint (Task 3 + CSS)
   - ✓ Inline filter in card name header (Task 3) — 140px underline input, placeholder "card name"
   - ✓ Data flow — production apps only, parallel fetch, flatten, error skip (Task 4)
   - ✓ Skeleton rows while loading (Task 3, Task 4)
   - ✓ Error banner dismissible (Task 4)
   - ✓ AI status badge kept static (Task 3)
   - ✓ Sold + Saved tabs remain mock (Task 4)

2. **Type consistency:**
   - `EbayLiveListing` defined in Task 1, imported in Tasks 2, 3, 4 — check spellings match exactly.
   - `fetchActiveListings` signature: `(appCode: string, limit?: number, offset?: number): Promise<EbayLiveListing[]>` — used in Task 4 as `fetchActiveListings(app.app_code, 50, 0)`.

3. **No placeholders:** All code blocks are complete and runnable.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-09-ebay-listings-page.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
