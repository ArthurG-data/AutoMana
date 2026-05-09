# Create & Edit eBay Listing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a create-listing flow at `/listings/new` and an inline edit-panel on `/listings`, both sharing a single `ListingFormPanel` component.

**Architecture:** All work is frontend-only — the backend `POST /listing/` and `PUT /listing/{id}` endpoints are already implemented. A shared `ListingFormPanel` (mode: create | edit) drives both flows. The edit panel opens inline on the listings page (master-detail split); the create page uses a two-column layout with a card search picker on the left and the form on the right.

**Tech Stack:** React 18, TanStack Router, TanStack Query, Zustand, Vitest + React Testing Library, CSS Modules

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Modify | `src/frontend/src/features/ebay/api.ts` | Add `createListing` + `updateListing` |
| Modify | `src/frontend/src/store/listings.ts` | Add `updateListing` action |
| Create | `src/frontend/src/features/ebay/components/ListingDetailPanel.tsx` | Read-only detail panel |
| Create | `src/frontend/src/features/ebay/components/ListingDetailPanel.module.css` | Detail panel styles |
| Create | `src/frontend/src/features/ebay/components/ListingFormPanel.tsx` | Shared create/edit form |
| Create | `src/frontend/src/features/ebay/components/ListingFormPanel.module.css` | Form styles |
| Modify | `src/frontend/src/features/ebay/components/ListingsTable.tsx` | Row selection support |
| Modify | `src/frontend/src/features/ebay/components/ListingsTable.module.css` | Selected row style |
| Modify | `src/frontend/src/routes/listings.tsx` | Split-panel edit flow |
| Modify | `src/frontend/src/routes/Listings.module.css` | Panel grid variant |
| Modify | `src/frontend/src/features/cards/components/SearchResults.tsx` | `onSelect` prop |
| Modify | `src/frontend/src/features/cards/components/SearchResults.module.css` | Selected card style |
| Create | `src/frontend/src/features/ebay/components/CardPicker.tsx` | Card search for create flow |
| Create | `src/frontend/src/features/ebay/components/CardPicker.module.css` | CardPicker styles |
| Create | `src/frontend/src/routes/listings_.new.tsx` | Create listing page |
| Create | `src/frontend/src/routes/ListingsNew.module.css` | Create page layout |

All tests live in `__tests__/` inside each component's directory, or alongside the route file in `routes/__tests__/`.

---

### Task 1: Add `createListing` and `updateListing` to the frontend API

**Files:**
- Modify: `src/frontend/src/features/ebay/api.ts`
- Test: `src/frontend/src/features/ebay/__tests__/api.listing.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `src/frontend/src/features/ebay/__tests__/api.listing.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createListing, updateListing } from '../api'

vi.mock('../../../lib/apiClient', () => ({
  apiClient: vi.fn(),
}))

import { apiClient } from '../../../lib/apiClient'
const mockApiClient = vi.mocked(apiClient)

beforeEach(() => {
  mockApiClient.mockReset()
  // crypto.randomUUID is available in jsdom via vitest
})

describe('createListing', () => {
  it('POSTs to the correct URL with Idempotency-Key header', async () => {
    mockApiClient.mockResolvedValueOnce(undefined)

    await createListing('automana_au', {
      title: 'Ragavan NM MTG',
      startPrice: { currency: 'AUD', value: 12.5 },
      quantity: 1,
      conditionID: 3000,
    })

    expect(mockApiClient).toHaveBeenCalledOnce()
    const [url, opts] = mockApiClient.mock.calls[0] as [string, RequestInit & { headers: Record<string, string> }]
    expect(url).toBe('/integrations/ebay/listing/?app_code=automana_au')
    expect(opts.method).toBe('POST')
    expect(opts.headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/)
    const body = JSON.parse(opts.body as string)
    expect(body.title).toBe('Ragavan NM MTG')
    expect(body.startPrice).toEqual({ currency: 'AUD', value: 12.5 })
    expect(body.quantity).toBe(1)
    expect(body.conditionID).toBe(3000)
  })

  it('includes description when provided', async () => {
    mockApiClient.mockResolvedValueOnce(undefined)

    await createListing('automana_au', {
      title: 'Test',
      startPrice: { currency: 'AUD', value: 5 },
      quantity: 2,
      conditionID: 4000,
      description: 'Lightly played card',
    })

    const [, opts] = mockApiClient.mock.calls[0] as [string, RequestInit]
    const body = JSON.parse(opts.body as string)
    expect(body.description).toBe('Lightly played card')
  })
})

describe('updateListing', () => {
  it('PUTs to the correct URL with itemID in the body', async () => {
    mockApiClient.mockResolvedValueOnce(undefined)

    await updateListing('automana_au', '123456789', {
      title: 'Sheoldred NM MTG',
      startPrice: { currency: 'AUD', value: 55 },
      quantity: 1,
      conditionID: 3000,
    })

    expect(mockApiClient).toHaveBeenCalledOnce()
    const [url, opts] = mockApiClient.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/integrations/ebay/listing/123456789?app_code=automana_au')
    expect(opts.method).toBe('PUT')
    const body = JSON.parse(opts.body as string)
    expect(body.itemID).toBe('123456789')
    expect(body.title).toBe('Sheoldred NM MTG')
    expect(body.startPrice).toEqual({ currency: 'AUD', value: 55 })
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd src/frontend && npm test -- api.listing
```

Expected: FAIL — `createListing` and `updateListing` are not yet exported from `api.ts`.

- [ ] **Step 3: Add `createListing` and `updateListing` to `api.ts`**

Append to `src/frontend/src/features/ebay/api.ts`:

```ts
// ── Listing writes ─────────────────────────────────────────────────────────

export interface ListingItemPayload {
  title: string
  startPrice: { currency: string; value: number }
  quantity: number
  conditionID: number
  description?: string
}

export async function createListing(
  appCode: string,
  item: ListingItemPayload,
): Promise<void> {
  await apiClient<unknown>(
    `/integrations/ebay/listing/?app_code=${encodeURIComponent(appCode)}`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify(item),
    },
  )
}

export async function updateListing(
  appCode: string,
  itemId: string,
  item: ListingItemPayload,
): Promise<void> {
  await apiClient<unknown>(
    `/integrations/ebay/listing/${encodeURIComponent(itemId)}?app_code=${encodeURIComponent(appCode)}`,
    {
      method: 'PUT',
      body: JSON.stringify({ itemID: itemId, ...item }),
    },
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd src/frontend && npm test -- api.listing
```

Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/ebay/api.ts \
        src/frontend/src/features/ebay/__tests__/api.listing.test.ts
git commit -m "feat(ebay): add createListing and updateListing to frontend API"
```

---

### Task 2: Add `updateListing` action to Zustand listings store

**Files:**
- Modify: `src/frontend/src/store/listings.ts`
- Test: `src/frontend/src/store/__tests__/listings.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/frontend/src/store/__tests__/listings.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { useListingsStore } from '../listings'
import type { EbayLiveListing } from '../../features/ebay/mockListings'

function makeListing(overrides: Partial<EbayLiveListing> = {}): EbayLiveListing {
  return {
    itemId: 'l1',
    title: 'Ragavan MH2 NM',
    cardName: 'Ragavan',
    setCode: 'MH2',
    setInfo: 'MH2',
    price: 60,
    currency: 'AUD',
    conditionLabel: 'NM',
    finish: 'Regular',
    style: '',
    daysListed: 5,
    watchCount: 3,
    viewItemUrl: 'https://ebay.com.au/itm/l1',
    imageUrl: null,
    appCode: 'app1',
    appName: 'App 1',
    ...overrides,
  }
}

beforeEach(() => {
  useListingsStore.setState({ listings: [] })
})

describe('listings store', () => {
  it('setListings replaces all listings', () => {
    const l = makeListing()
    useListingsStore.getState().setListings([l])
    expect(useListingsStore.getState().listings).toHaveLength(1)
  })

  it('getById returns the matching listing', () => {
    useListingsStore.getState().setListings([makeListing({ itemId: 'abc' })])
    expect(useListingsStore.getState().getById('abc')?.itemId).toBe('abc')
  })

  it('getById returns undefined for unknown id', () => {
    useListingsStore.getState().setListings([makeListing()])
    expect(useListingsStore.getState().getById('nope')).toBeUndefined()
  })

  it('updateListing patches only the matching entry', () => {
    const l1 = makeListing({ itemId: 'l1', price: 60 })
    const l2 = makeListing({ itemId: 'l2', price: 10 })
    useListingsStore.getState().setListings([l1, l2])

    useListingsStore.getState().updateListing('l1', { price: 75, conditionLabel: 'LP' })

    const updated = useListingsStore.getState().listings
    expect(updated[0].price).toBe(75)
    expect(updated[0].conditionLabel).toBe('LP')
    expect(updated[1].price).toBe(10)
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd src/frontend && npm test -- listings.test
```

Expected: FAIL — `updateListing` is not defined on the store.

- [ ] **Step 3: Add `updateListing` to the store**

Replace `src/frontend/src/store/listings.ts` with:

```ts
import { create } from 'zustand'
import type { EbayLiveListing } from '../features/ebay/mockListings'

interface ListingsState {
  listings: EbayLiveListing[]
  setListings: (listings: EbayLiveListing[]) => void
  getById: (itemId: string) => EbayLiveListing | undefined
  updateListing: (itemId: string, patch: Partial<EbayLiveListing>) => void
}

export const useListingsStore = create<ListingsState>()((set, get) => ({
  listings: [],
  setListings: (listings) => set({ listings }),
  getById: (itemId) => get().listings.find((l) => l.itemId === itemId),
  updateListing: (itemId, patch) =>
    set((state) => ({
      listings: state.listings.map((l) =>
        l.itemId === itemId ? { ...l, ...patch } : l
      ),
    })),
}))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd src/frontend && npm test -- listings.test
```

Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/store/listings.ts \
        src/frontend/src/store/__tests__/listings.test.ts
git commit -m "feat(ebay): add updateListing action to listings store"
```

---

### Task 3: Build `ListingDetailPanel` (read-only panel)

**Files:**
- Create: `src/frontend/src/features/ebay/components/ListingDetailPanel.tsx`
- Create: `src/frontend/src/features/ebay/components/ListingDetailPanel.module.css`
- Test: `src/frontend/src/features/ebay/components/__tests__/ListingDetailPanel.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `src/frontend/src/features/ebay/components/__tests__/ListingDetailPanel.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { ListingDetailPanel } from '../ListingDetailPanel'
import type { EbayLiveListing } from '../../mockListings'

function makeListing(overrides: Partial<EbayLiveListing> = {}): EbayLiveListing {
  return {
    itemId: 'l1',
    title: 'Sheoldred MOM NM MTG',
    cardName: 'Sheoldred, the Apocalypse',
    setCode: 'MOM',
    setInfo: 'MOM',
    price: 55,
    currency: 'AUD',
    conditionLabel: 'Near Mint (NM)',
    finish: 'Regular',
    style: '',
    daysListed: 3,
    watchCount: 7,
    viewItemUrl: 'https://www.ebay.com.au/itm/l1',
    imageUrl: null,
    appCode: 'app1',
    appName: 'AutoMana AU',
    ...overrides,
  }
}

describe('ListingDetailPanel', () => {
  it('renders card name, price, condition, and watchers', () => {
    render(
      <ListingDetailPanel
        listing={makeListing()}
        onEdit={vi.fn()}
        onClose={vi.fn()}
      />
    )
    expect(screen.getByText('Sheoldred, the Apocalypse')).toBeInTheDocument()
    expect(screen.getByText(/55\.00/)).toBeInTheDocument()
    expect(screen.getByText('Near Mint (NM)')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
  })

  it('calls onEdit when Edit listing button is clicked', async () => {
    const onEdit = vi.fn()
    render(<ListingDetailPanel listing={makeListing()} onEdit={onEdit} onClose={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /edit listing/i }))
    expect(onEdit).toHaveBeenCalledOnce()
  })

  it('calls onClose when close button is clicked', async () => {
    const onClose = vi.fn()
    render(<ListingDetailPanel listing={makeListing()} onEdit={vi.fn()} onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('shows thumbnail when imageUrl is present', () => {
    render(
      <ListingDetailPanel
        listing={makeListing({ imageUrl: 'https://example.com/img.jpg' })}
        onEdit={vi.fn()}
        onClose={vi.fn()}
      />
    )
    expect(screen.getByRole('img')).toHaveAttribute('src', 'https://example.com/img.jpg')
  })

  it('shows eBay link', () => {
    render(<ListingDetailPanel listing={makeListing()} onEdit={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByRole('link', { name: /view/i })).toHaveAttribute('href', 'https://www.ebay.com.au/itm/l1')
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd src/frontend && npm test -- ListingDetailPanel.test
```

Expected: FAIL — module not found.

- [ ] **Step 3: Create `ListingDetailPanel.tsx`**

```tsx
// src/frontend/src/features/ebay/components/ListingDetailPanel.tsx
import { Icon } from '../../../components/design-system/Icon'
import type { EbayLiveListing } from '../mockListings'
import styles from './ListingDetailPanel.module.css'

interface ListingDetailPanelProps {
  listing: EbayLiveListing
  onEdit: () => void
  onClose: () => void
}

export function ListingDetailPanel({ listing, onEdit, onClose }: ListingDetailPanelProps) {
  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <span className={styles.title}>{listing.cardName}</span>
        <button onClick={onClose} className={styles.closeBtn} aria-label="Close panel">
          <Icon kind="close" size={14} color="currentColor" />
        </button>
      </div>

      {listing.imageUrl ? (
        <img src={listing.imageUrl} alt={listing.cardName} className={styles.image} />
      ) : (
        <div className={styles.imagePlaceholder}>
          <span className={styles.placeholderName}>{listing.cardName}</span>
          <span className={styles.placeholderSet}>{listing.setCode}</span>
        </div>
      )}

      <div className={styles.fields}>
        {[
          { label: 'Set', value: listing.setCode || '—' },
          { label: 'Condition', value: listing.conditionLabel || '—' },
          { label: 'Days listed', value: listing.daysListed > 0 ? `${listing.daysListed}d` : '—' },
          { label: 'App', value: listing.appName || listing.appCode },
        ].map(({ label, value }) => (
          <div key={label} className={styles.row}>
            <span className={styles.label}>{label}</span>
            <span className={styles.value}>{value}</span>
          </div>
        ))}
        <div className={styles.row}>
          <span className={styles.label}>Price</span>
          <span className={styles.valueAccent}>
            {listing.currency} {listing.price.toFixed(2)}
          </span>
        </div>
        <div className={styles.row}>
          <span className={styles.label}>Watchers</span>
          <span className={styles.value}>{listing.watchCount}</span>
        </div>
        <div className={styles.row}>
          <span className={styles.label}>eBay</span>
          <a
            href={listing.viewItemUrl}
            target="_blank"
            rel="noopener noreferrer"
            className={styles.link}
          >
            View ↗
          </a>
        </div>
      </div>

      <button onClick={onEdit} className={styles.editBtn}>
        Edit listing
      </button>
    </div>
  )
}
```

- [ ] **Step 4: Create `ListingDetailPanel.module.css`**

```css
/* src/frontend/src/features/ebay/components/ListingDetailPanel.module.css */
.panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: var(--hd-surface);
  border: 1px solid var(--hd-border);
  border-radius: 12px;
  padding: 20px;
  position: sticky;
  top: 24px;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.title {
  font-size: 14px;
  font-weight: 600;
  color: var(--hd-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.closeBtn {
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--hd-muted);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  flex-shrink: 0;
  transition: color 0.1s;
}
.closeBtn:hover { color: var(--hd-text); }

.image {
  width: 100%;
  border-radius: 8px;
  object-fit: contain;
  max-height: 180px;
}

.imagePlaceholder {
  width: 100%;
  aspect-ratio: 5 / 7;
  max-height: 180px;
  background: var(--hd-surface-alt);
  border: 1px solid var(--hd-border);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.placeholderName {
  font-size: 12px;
  font-weight: 600;
  color: var(--hd-text);
  text-align: center;
  padding: 0 8px;
}

.placeholderSet {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--hd-sub);
}

.fields {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.label {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--hd-sub);
  text-transform: uppercase;
  letter-spacing: 0.8px;
  white-space: nowrap;
}

.value {
  font-size: 12px;
  color: var(--hd-text);
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.valueAccent {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 600;
  color: var(--hd-accent);
  text-align: right;
}

.link {
  font-size: 12px;
  color: var(--hd-accent);
  text-decoration: none;
}
.link:hover { text-decoration: underline; }

.editBtn {
  width: 100%;
  padding: 10px 16px;
  background: var(--hd-accent);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.12s;
}
.editBtn:hover { opacity: 0.88; }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd src/frontend && npm test -- ListingDetailPanel.test
```

Expected: PASS — 5 tests.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/ebay/components/ListingDetailPanel.tsx \
        src/frontend/src/features/ebay/components/ListingDetailPanel.module.css \
        src/frontend/src/features/ebay/components/__tests__/ListingDetailPanel.test.tsx
git commit -m "feat(ebay): add ListingDetailPanel read-only component"
```

---

### Task 4: Build `ListingFormPanel` (shared create/edit form)

**Files:**
- Create: `src/frontend/src/features/ebay/components/ListingFormPanel.tsx`
- Create: `src/frontend/src/features/ebay/components/ListingFormPanel.module.css`
- Test: `src/frontend/src/features/ebay/components/__tests__/ListingFormPanel.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `src/frontend/src/features/ebay/components/__tests__/ListingFormPanel.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { ListingFormPanel } from '../ListingFormPanel'
import type { EbayAppSummary } from '../../api'

function makeApp(overrides: Partial<EbayAppSummary> = {}): EbayAppSummary {
  return {
    app_id: 'a1',
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

describe('ListingFormPanel', () => {
  it('pre-fills fields from initialValues', () => {
    render(
      <ListingFormPanel
        mode="edit"
        initialValues={{ title: 'Sheoldred MOM NM', price: 55, quantity: 1, conditionId: 3000, description: '' }}
        availableApps={[makeApp()]}
        appCode="automana_au"
        onSave={vi.fn()}
        onCancel={vi.fn()}
        isSaving={false}
        error={null}
      />
    )
    expect(screen.getByDisplayValue('Sheoldred MOM NM')).toBeInTheDocument()
    expect(screen.getByDisplayValue('55')).toBeInTheDocument()
    expect(screen.getByDisplayValue('1')).toBeInTheDocument()
  })

  it('calls onCancel when Cancel is clicked', async () => {
    const onCancel = vi.fn()
    render(
      <ListingFormPanel
        mode="edit"
        initialValues={{ title: 'Test', price: 10, quantity: 1, conditionId: 3000, description: '' }}
        availableApps={[makeApp()]}
        appCode="automana_au"
        onSave={vi.fn()}
        onCancel={onCancel}
        isSaving={false}
        error={null}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('calls onSave with current values when Save is clicked', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(
      <ListingFormPanel
        mode="edit"
        initialValues={{ title: 'Ragavan MH2 NM', price: 62, quantity: 1, conditionId: 3000, description: '' }}
        availableApps={[makeApp()]}
        appCode="automana_au"
        onSave={onSave}
        onCancel={vi.fn()}
        isSaving={false}
        error={null}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: /save/i }))
    expect(onSave).toHaveBeenCalledWith(
      { title: 'Ragavan MH2 NM', price: 62, quantity: 1, conditionId: 3000, description: '' },
      'automana_au',
    )
  })

  it('shows error message when error prop is set', () => {
    render(
      <ListingFormPanel
        mode="edit"
        initialValues={{ title: 'Test', price: 10, quantity: 1, conditionId: 3000, description: '' }}
        availableApps={[makeApp()]}
        appCode="automana_au"
        onSave={vi.fn()}
        onCancel={vi.fn()}
        isSaving={false}
        error="eBay API error: token expired"
      />
    )
    expect(screen.getByText('eBay API error: token expired')).toBeInTheDocument()
  })

  it('disables Save button while isSaving', () => {
    render(
      <ListingFormPanel
        mode="edit"
        initialValues={{ title: 'Test', price: 10, quantity: 1, conditionId: 3000, description: '' }}
        availableApps={[makeApp()]}
        appCode="automana_au"
        onSave={vi.fn()}
        onCancel={vi.fn()}
        isSaving={true}
        error={null}
      />
    )
    expect(screen.getByRole('button', { name: /saving/i })).toBeDisabled()
  })

  it('shows app dropdown in create mode', () => {
    render(
      <ListingFormPanel
        mode="create"
        initialValues={{}}
        availableApps={[makeApp(), makeApp({ app_code: 'app2', app_name: 'App 2' })]}
        onSave={vi.fn()}
        onCancel={vi.fn()}
        isSaving={false}
        error={null}
      />
    )
    expect(screen.getByRole('combobox', { name: /app/i })).toBeInTheDocument()
  })

  it('validates price must be > 0 before calling onSave', async () => {
    const onSave = vi.fn()
    render(
      <ListingFormPanel
        mode="create"
        initialValues={{ title: 'Test', price: 0, quantity: 1, conditionId: 3000, description: '' }}
        availableApps={[makeApp()]}
        onSave={onSave}
        onCancel={vi.fn()}
        isSaving={false}
        error={null}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: /create/i }))
    expect(onSave).not.toHaveBeenCalled()
    expect(screen.getByText(/price must be greater than 0/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd src/frontend && npm test -- ListingFormPanel.test
```

Expected: FAIL — module not found.

- [ ] **Step 3: Create `ListingFormPanel.tsx`**

```tsx
// src/frontend/src/features/ebay/components/ListingFormPanel.tsx
import { useState } from 'react'
import type { EbayAppSummary } from '../api'
import styles from './ListingFormPanel.module.css'

export interface ListingFormValues {
  title: string
  price: number
  quantity: number
  conditionId: number
  description: string
}

const CONDITION_OPTIONS = [
  { label: 'Near Mint (NM)', value: 3000 },
  { label: 'Lightly Played (LP)', value: 4000 },
  { label: 'Moderately Played (MP)', value: 5000 },
  { label: 'Heavily Played (HP)', value: 6000 },
  { label: 'Damaged (DMG)', value: 7000 },
]

interface ListingFormPanelProps {
  mode: 'create' | 'edit'
  initialValues: Partial<ListingFormValues>
  availableApps: EbayAppSummary[]
  appCode?: string
  onSave: (values: ListingFormValues, appCode: string) => Promise<void>
  onCancel: () => void
  isSaving: boolean
  error: string | null
}

export function ListingFormPanel({
  mode,
  initialValues,
  availableApps,
  appCode: fixedAppCode,
  onSave,
  onCancel,
  isSaving,
  error,
}: ListingFormPanelProps) {
  const [title, setTitle] = useState(initialValues.title ?? '')
  const [price, setPrice] = useState(initialValues.price ?? 0)
  const [quantity, setQuantity] = useState(initialValues.quantity ?? 1)
  const [conditionId, setConditionId] = useState(initialValues.conditionId ?? 3000)
  const [description, setDescription] = useState(initialValues.description ?? '')
  const [selectedAppCode, setSelectedAppCode] = useState(
    fixedAppCode ?? availableApps[0]?.app_code ?? '',
  )
  const [validationError, setValidationError] = useState<string | null>(null)

  function validate(): boolean {
    if (price <= 0) {
      setValidationError('Price must be greater than 0')
      return false
    }
    if (quantity < 1) {
      setValidationError('Quantity must be at least 1')
      return false
    }
    if (!title.trim()) {
      setValidationError('Title is required')
      return false
    }
    setValidationError(null)
    return true
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return
    await onSave(
      { title: title.trim(), price, quantity, conditionId, description },
      selectedAppCode,
    )
  }

  const saveLabel = mode === 'create' ? 'Create listing' : 'Save changes'
  const displayError = validationError ?? error

  return (
    <form onSubmit={handleSubmit} className={styles.form} noValidate>
      <div className={styles.header}>
        <span className={styles.title}>
          {mode === 'create' ? 'New listing' : 'Edit listing'}
        </span>
      </div>

      <div className={styles.fields}>
        <label className={styles.field}>
          <span className={styles.label}>Title</span>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={80}
            className={styles.input}
            placeholder="Card name + set + condition"
          />
        </label>

        <div className={styles.row}>
          <label className={styles.field}>
            <span className={styles.label}>Price (AUD)</span>
            <input
              type="number"
              value={price}
              onChange={(e) => setPrice(Number(e.target.value))}
              step="0.01"
              min="0.01"
              className={styles.input}
            />
          </label>

          <label className={styles.field}>
            <span className={styles.label}>Qty</span>
            <input
              type="number"
              value={quantity}
              onChange={(e) => setQuantity(Number(e.target.value))}
              step="1"
              min="1"
              className={styles.inputSmall}
            />
          </label>
        </div>

        <label className={styles.field}>
          <span className={styles.label}>Condition</span>
          <select
            value={conditionId}
            onChange={(e) => setConditionId(Number(e.target.value))}
            className={styles.select}
          >
            {CONDITION_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>

        <label className={styles.field}>
          <span className={styles.label}>Description (optional)</span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={500}
            rows={3}
            className={styles.textarea}
            placeholder="Any extra notes for the buyer"
          />
        </label>

        {mode === 'create' && (
          <label className={styles.field} aria-label="App">
            <span className={styles.label}>App</span>
            <select
              value={selectedAppCode}
              onChange={(e) => setSelectedAppCode(e.target.value)}
              className={styles.select}
            >
              {availableApps.map((app) => (
                <option key={app.app_code} value={app.app_code}>
                  {app.app_name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {displayError && (
        <div className={styles.error} role="alert">
          {displayError}
        </div>
      )}

      <div className={styles.actions}>
        <button type="button" onClick={onCancel} className={styles.cancelBtn}>
          Cancel
        </button>
        <button type="submit" disabled={isSaving} className={styles.saveBtn}>
          {isSaving ? 'Saving…' : saveLabel}
        </button>
      </div>
    </form>
  )
}
```

- [ ] **Step 4: Create `ListingFormPanel.module.css`**

```css
/* src/frontend/src/features/ebay/components/ListingFormPanel.module.css */
.form {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: var(--hd-surface);
  border: 1px solid var(--hd-border);
  border-radius: 12px;
  padding: 20px;
}

.header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.title {
  font-size: 14px;
  font-weight: 600;
  color: var(--hd-text);
}

.fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.row {
  display: grid;
  grid-template-columns: 1fr 80px;
  gap: 10px;
}

.label {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--hd-sub);
  text-transform: uppercase;
  letter-spacing: 0.8px;
}

.input,
.select,
.textarea {
  background: var(--hd-bg);
  border: 1px solid var(--hd-border);
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 13px;
  color: var(--hd-text);
  font-family: var(--font-sans);
  width: 100%;
  box-sizing: border-box;
  transition: border-color 0.12s;
}

.input:focus,
.select:focus,
.textarea:focus {
  outline: none;
  border-color: var(--hd-accent);
}

.inputSmall {
  composes: input;
  text-align: center;
}

.textarea {
  resize: vertical;
  min-height: 72px;
}

.error {
  padding: 8px 12px;
  background: rgba(227, 94, 108, 0.08);
  border: 1px solid rgba(227, 94, 108, 0.25);
  border-radius: 6px;
  font-size: 12px;
  color: var(--hd-red);
}

.actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.cancelBtn {
  padding: 8px 16px;
  background: transparent;
  border: 1px solid var(--hd-border);
  border-radius: 6px;
  font-size: 13px;
  color: var(--hd-muted);
  cursor: pointer;
  transition: color 0.1s, border-color 0.1s;
}
.cancelBtn:hover {
  color: var(--hd-text);
  border-color: var(--hd-text);
}

.saveBtn {
  padding: 8px 18px;
  background: var(--hd-accent);
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #fff;
  cursor: pointer;
  transition: opacity 0.12s;
}
.saveBtn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.saveBtn:not(:disabled):hover {
  opacity: 0.88;
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd src/frontend && npm test -- ListingFormPanel.test
```

Expected: PASS — 7 tests.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/ebay/components/ListingFormPanel.tsx \
        src/frontend/src/features/ebay/components/ListingFormPanel.module.css \
        src/frontend/src/features/ebay/components/__tests__/ListingFormPanel.test.tsx
git commit -m "feat(ebay): add shared ListingFormPanel create/edit form"
```

---

### Task 5: Add row selection to `ListingsTable`

**Files:**
- Modify: `src/frontend/src/features/ebay/components/ListingsTable.tsx`
- Modify: `src/frontend/src/features/ebay/components/ListingsTable.module.css`
- Test: `src/frontend/src/features/ebay/components/__tests__/ListingsTable.test.tsx` (extend existing)

- [ ] **Step 1: Write the new failing tests**

Append to the existing `ListingsTable.test.tsx`:

```tsx
describe('ListingsTable — row selection', () => {
  it('calls onRowClick with the listing itemId when a row is clicked', async () => {
    const onRowClick = vi.fn()
    const listing = makeListing({ itemId: 'abc123' })
    render(
      <ListingsTable
        listings={[listing]}
        isLoading={false}
        onRowClick={onRowClick}
      />
    )
    // Click the row (the <tr> itself)
    const rows = document.querySelectorAll('tbody tr')
    await userEvent.click(rows[0])
    expect(onRowClick).toHaveBeenCalledWith('abc123')
  })

  it('adds a selected style class to the row matching selectedId', () => {
    const listing = makeListing({ itemId: 'sel1' })
    render(
      <ListingsTable
        listings={[listing]}
        isLoading={false}
        selectedId="sel1"
        onRowClick={vi.fn()}
      />
    )
    const rows = document.querySelectorAll('tbody tr')
    expect(rows[0].className).toMatch(/rowSelected/)
  })

  it('renders card name as plain text (not a link) when onRowClick is provided', () => {
    const listing = makeListing({ itemId: 'l1', cardName: 'Ragavan' })
    render(
      <ListingsTable
        listings={[listing]}
        isLoading={false}
        onRowClick={vi.fn()}
      />
    )
    // The card name should be text, not a router Link
    expect(screen.queryByRole('link', { name: /ragavan/i })).toBeNull()
    expect(screen.getByText('Ragavan')).toBeInTheDocument()
  })
})
```

You'll need to add `import userEvent from '@testing-library/user-event'` at the top of the test file if it's not already there.

- [ ] **Step 2: Run to verify failure**

```bash
cd src/frontend && npm test -- ListingsTable.test
```

Expected: new tests FAIL — `onRowClick` and `selectedId` props not yet supported.

- [ ] **Step 3: Update `ListingsTable.tsx`**

In `ListingsTable.tsx`, update the `ListingsTableProps` interface:

```tsx
interface ListingsTableProps {
  listings: EbayLiveListing[]
  isLoading?: boolean
  selectedId?: string
  onRowClick?: (id: string) => void
}
```

Update the function signature:

```tsx
export function ListingsTable({ listings, isLoading = false, selectedId, onRowClick }: ListingsTableProps) {
```

In the `{!isLoading && visible.map((listing) => {` section, replace the `<tr>` opening tag:

```tsx
<tr
  key={listing.itemId}
  className={[
    styles.row,
    listing.itemId === selectedId ? styles.rowSelected : '',
  ].filter(Boolean).join(' ')}
  onClick={() => onRowClick?.(listing.itemId)}
  style={{ cursor: onRowClick ? 'pointer' : 'default' }}
>
```

Replace the card name `<Link>` inside that row with conditional rendering:

```tsx
<div className={styles.nameText}>
  {onRowClick ? (
    <span className={styles.cardName}>{listing.cardName}</span>
  ) : (
    <Link
      to="/listings_/$id"
      params={{ id: listing.itemId }}
      className={styles.cardName}
    >
      {listing.cardName}
    </Link>
  )}
  <a
    href={listing.viewItemUrl}
    target="_blank"
    rel="noopener noreferrer"
    className={styles.ebayLink}
    title="View on eBay"
    onClick={(e) => e.stopPropagation()}
  >
    eBay ↗
  </a>
</div>
```

- [ ] **Step 4: Add `.rowSelected` to `ListingsTable.module.css`**

Append to `ListingsTable.module.css`:

```css
.rowSelected {
  background: rgba(var(--hd-accent-rgb), 0.07);
}
.rowSelected:hover {
  background: rgba(var(--hd-accent-rgb), 0.11);
}
```

- [ ] **Step 5: Run all ListingsTable tests to verify they pass**

```bash
cd src/frontend && npm test -- ListingsTable.test
```

Expected: PASS — all tests including the 3 new ones.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/ebay/components/ListingsTable.tsx \
        src/frontend/src/features/ebay/components/ListingsTable.module.css \
        src/frontend/src/features/ebay/components/__tests__/ListingsTable.test.tsx
git commit -m "feat(ebay): add row selection support to ListingsTable"
```

---

### Task 6: Wire the split-panel edit flow into `listings.tsx`

**Files:**
- Modify: `src/frontend/src/routes/listings.tsx`
- Modify: `src/frontend/src/routes/Listings.module.css`
- Test: `src/frontend/src/routes/__tests__/listings.test.tsx` (extend)

- [ ] **Step 1: Write the new failing tests**

Append to the existing `src/frontend/src/routes/__tests__/listings.test.tsx`:

```tsx
// Add these extra mocks at the top alongside the existing vi.mock calls:
vi.mock('../../features/ebay/components/ListingDetailPanel', () => ({
  ListingDetailPanel: ({ listing, onEdit, onClose }: { listing: { cardName: string }; onEdit: () => void; onClose: () => void }) => (
    <div data-testid="detail-panel">
      <span>{listing.cardName}</span>
      <button onClick={onEdit}>Edit listing</button>
      <button onClick={onClose}>Close panel</button>
    </div>
  ),
}))

vi.mock('../../features/ebay/components/ListingFormPanel', () => ({
  ListingFormPanel: ({ onCancel }: { onCancel: () => void }) => (
    <div data-testid="form-panel">
      <button onClick={onCancel}>Cancel</button>
    </div>
  ),
}))

vi.mock('../../features/ebay/api', () => ({
  fetchUserApps: vi.fn(),
  fetchActiveListings: vi.fn(),
  fetchActiveListingsPaginated: vi.fn(),
  updateListing: vi.fn(),
}))

// New test group:
describe('ListingsPage — split-panel edit', () => {
  beforeEach(() => {
    mockFetchUserApps.mockResolvedValue([makeApp()])
    mockFetchActiveListingsPaginated.mockResolvedValue({
      items: [makeListing({ itemId: 'l1', cardName: 'Ragavan' })],
      hasMore: false,
    })
  })

  it('shows detail panel when a row is clicked', async () => {
    render(<ListingsPage />)
    await waitFor(() => expect(screen.queryByText('Loading')).not.toBeInTheDocument(), { timeout: 3000 })

    // Simulate row click via ListingsTable mock's onRowClick
    const table = screen.getByTestId('listings-table')
    // The mock passes onRowClick — we need to update the ListingsTable mock to expose it
    // For this test, trigger via data attribute or check panel existence via store
    // The test verifies the panel appears after interaction
  })
})
```

> **Note:** The existing `ListingsTable` mock renders a `<div data-testid="listings-table">`. Update the mock in this test file to also call `onRowClick('l1')` when the div is clicked:
>
> ```tsx
> vi.mock('../../features/ebay/components/ListingsTable', () => ({
>   ListingsTable: ({
>     listings,
>     isLoading,
>     onRowClick,
>   }: {
>     listings: { appName: string; itemId: string }[]
>     isLoading?: boolean
>     onRowClick?: (id: string) => void
>   }) => (
>     <div
>       data-testid="listings-table"
>       data-loading={String(isLoading)}
>       data-count={listings.length}
>       onClick={() => listings[0] && onRowClick?.(listings[0].itemId)}
>     />
>   ),
> }))
> ```
>
> Then write:

```tsx
describe('ListingsPage — split-panel edit', () => {
  beforeEach(() => {
    mockFetchUserApps.mockResolvedValue([makeApp()])
    mockFetchActiveListingsPaginated.mockResolvedValue({
      items: [makeListing({ itemId: 'l1', cardName: 'Ragavan' })],
      hasMore: false,
    })
  })

  it('shows detail panel after clicking a row', async () => {
    render(<ListingsPage />)
    await waitFor(() => expect(screen.getByTestId('listings-table')).toBeInTheDocument())

    // Set listing in store so the panel can read it
    const { useListingsStore } = await import('../../store/listings')
    useListingsStore.getState().setListings([
      makeListing({ itemId: 'l1', cardName: 'Ragavan' }),
    ])

    await userEvent.click(screen.getByTestId('listings-table'))
    await waitFor(() => expect(screen.getByTestId('detail-panel')).toBeInTheDocument())
  })

  it('switches to form panel when Edit listing is clicked', async () => {
    render(<ListingsPage />)
    await waitFor(() => expect(screen.getByTestId('listings-table')).toBeInTheDocument())

    const { useListingsStore } = await import('../../store/listings')
    useListingsStore.getState().setListings([
      makeListing({ itemId: 'l1', cardName: 'Ragavan' }),
    ])

    await userEvent.click(screen.getByTestId('listings-table'))
    await waitFor(() => screen.getByTestId('detail-panel'))
    await userEvent.click(screen.getByRole('button', { name: /edit listing/i }))
    expect(screen.getByTestId('form-panel')).toBeInTheDocument()
  })

  it('returns to detail panel when Cancel is clicked in form', async () => {
    render(<ListingsPage />)
    await waitFor(() => expect(screen.getByTestId('listings-table')).toBeInTheDocument())

    const { useListingsStore } = await import('../../store/listings')
    useListingsStore.getState().setListings([
      makeListing({ itemId: 'l1', cardName: 'Ragavan' }),
    ])

    await userEvent.click(screen.getByTestId('listings-table'))
    await waitFor(() => screen.getByTestId('detail-panel'))
    await userEvent.click(screen.getByRole('button', { name: /edit listing/i }))
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(screen.getByTestId('detail-panel')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd src/frontend && npm test -- routes/__tests__/listings
```

Expected: new tests FAIL.

- [ ] **Step 3: Update `listings.tsx`**

Add the new imports at the top of `src/frontend/src/routes/listings.tsx`:

```tsx
import { ListingDetailPanel } from '../features/ebay/components/ListingDetailPanel'
import { ListingFormPanel, type ListingFormValues } from '../features/ebay/components/ListingFormPanel'
import { updateListing } from '../features/ebay/api'
```

Add the new state variables inside `ListingsPage` (after the existing state):

```tsx
const [selectedId, setSelectedId] = useState<string | null>(null)
const [panelMode, setPanelMode] = useState<'detail' | 'edit'>('detail')
const [isSaving, setIsSaving] = useState(false)
const [saveError, setSaveError] = useState<string | null>(null)
const [productionApps, setProductionApps] = useState<EbayAppSummary[]>([])
const selectedListing = useListingsStore((s) => s.getById(selectedId ?? ''))
const storeUpdateListing = useListingsStore((s) => s.updateListing)
```

In the `load()` effect, after `appsRef.current = productionApps`, also call:

```tsx
setProductionApps(productionApps)
```

Add the save handler after the `loadMore` function:

```tsx
async function handleUpdateListing(values: ListingFormValues, appCode: string) {
  if (!selectedId || !selectedListing) return
  setIsSaving(true)
  setSaveError(null)
  try {
    await updateListing(appCode, selectedId, {
      title: values.title,
      startPrice: { currency: 'AUD', value: values.price },
      quantity: values.quantity,
      conditionID: values.conditionId,
      ...(values.description ? { description: values.description } : {}),
    })
    storeUpdateListing(selectedId, { price: values.price, title: values.title })
    setPanelMode('detail')
  } catch (err) {
    setSaveError(err instanceof Error ? err.message : 'Failed to update listing')
  } finally {
    setIsSaving(false)
  }
}
```

Replace the `{tab === 'active' && (...)}` block with:

```tsx
{tab === 'active' && (
  <div className={selectedId ? styles.withPanel : undefined}>
    <div>
      <ListingsTable
        listings={listings}
        isLoading={isLoading}
        selectedId={selectedId ?? undefined}
        onRowClick={(id) => {
          setSelectedId(id)
          setPanelMode('detail')
          setSaveError(null)
        }}
      />
      {!isLoading && (
        <>
          <div ref={sentinelRef} style={{ height: 1 }} aria-hidden />
          {isLoadingMore && (
            <div className={styles.loadingMore}>Loading more listings…</div>
          )}
          {!hasMore && listings.length > 0 && !isLoadingMore && (
            <div className={styles.endOfList}>
              {listings.length} listing{listings.length !== 1 ? 's' : ''} total
            </div>
          )}
        </>
      )}
    </div>

    {selectedId && selectedListing && (
      <div>
        {panelMode === 'detail' ? (
          <ListingDetailPanel
            listing={selectedListing}
            onEdit={() => setPanelMode('edit')}
            onClose={() => { setSelectedId(null); setPanelMode('detail') }}
          />
        ) : (
          <ListingFormPanel
            mode="edit"
            initialValues={{
              title: selectedListing.title,
              price: selectedListing.price,
              quantity: 1,
              conditionId: 3000,
              description: '',
            }}
            availableApps={productionApps}
            appCode={selectedListing.appCode}
            onSave={handleUpdateListing}
            onCancel={() => setPanelMode('detail')}
            isSaving={isSaving}
            error={saveError}
          />
        )}
      </div>
    )}
  </div>
)}
```

- [ ] **Step 4: Add `.withPanel` to `Listings.module.css`**

Append to `Listings.module.css`:

```css
/* ── Split-panel layout (active when a listing is selected) ─── */
.withPanel {
  display: grid;
  grid-template-columns: 1fr 400px;
  gap: 20px;
  align-items: start;
}

@media (max-width: 1100px) {
  .withPanel {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd src/frontend && npm test -- routes/__tests__/listings
```

Expected: PASS — all tests including the 3 new ones.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/routes/listings.tsx \
        src/frontend/src/routes/Listings.module.css \
        src/frontend/src/routes/__tests__/listings.test.tsx
git commit -m "feat(ebay): wire split-panel edit flow into listings page"
```

---

### Task 7: Add `onSelect` mode to `SearchResults`

**Files:**
- Modify: `src/frontend/src/features/cards/components/SearchResults.tsx`
- Modify: `src/frontend/src/features/cards/components/SearchResults.module.css`

- [ ] **Step 1: Update `SearchResultsProps` in `SearchResults.tsx`**

Add two optional props to the interface:

```tsx
interface SearchResultsProps {
  cards: CardSummary[]
  total: number
  fetchNextPage: () => void
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  onSelect?: (card: CardSummary) => void
  selectedId?: string
}
```

Update the function signature:

```tsx
export function SearchResults({
  cards,
  total,
  fetchNextPage,
  hasNextPage,
  isFetchingNextPage,
  onSelect,
  selectedId,
}: SearchResultsProps) {
```

Replace the `onClick` on the card button:

```tsx
onClick={() =>
  onSelect
    ? onSelect(card)
    : navigate({ to: '/cards/$id', params: { id: card.card_version_id } })
}
```

Add the selected style to the card button's `className`:

```tsx
className={[
  styles.card,
  card.card_version_id === selectedId ? styles.cardSelected : '',
].filter(Boolean).join(' ')}
```

- [ ] **Step 2: Add `.cardSelected` to `SearchResults.module.css`**

Append:

```css
.cardSelected {
  outline: 2px solid var(--hd-accent);
  outline-offset: -2px;
}
```

- [ ] **Step 3: Run the full test suite to verify no regressions**

```bash
cd src/frontend && npm test
```

Expected: PASS — all existing tests still pass (new props are optional, default behaviour is unchanged).

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/features/cards/components/SearchResults.tsx \
        src/frontend/src/features/cards/components/SearchResults.module.css
git commit -m "feat(cards): add optional onSelect mode to SearchResults"
```

---

### Task 8: Build `CardPicker` (left panel for the create flow)

**Files:**
- Create: `src/frontend/src/features/ebay/components/CardPicker.tsx`
- Create: `src/frontend/src/features/ebay/components/CardPicker.module.css`
- Test: `src/frontend/src/features/ebay/components/__tests__/CardPicker.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `src/frontend/src/features/ebay/components/__tests__/CardPicker.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CardPicker } from '../CardPicker'
import type { CardSummary } from '../../../features/cards/types'

vi.mock('../../../features/cards/api', () => ({
  cardInfiniteSearchQueryOptions: (params: { q?: string }) => ({
    queryKey: ['cards', 'search', params],
    queryFn: async () => ({
      cards: [
        {
          card_version_id: 'cv1',
          card_name: 'Ragavan, Nimble Pilferer',
          set_code: 'mh2',
          set_name: 'MH2',
          finish: 'non-foil',
          rarity_name: 'mythic',
          price: 60,
          price_change_1d: 0,
          price_change_7d: 0,
          price_change_30d: 0,
          image_uri: null,
          image_normal: null,
          spark: [],
        } satisfies CardSummary,
      ],
      pagination: { has_next: false, offset: 0, limit: 20 },
    }),
    initialPageParam: 0,
    getNextPageParam: () => undefined,
  }),
}))

vi.mock('../../../features/cards/components/SearchResults', () => ({
  SearchResults: ({
    cards,
    onSelect,
  }: {
    cards: CardSummary[]
    onSelect?: (c: CardSummary) => void
  }) => (
    <div data-testid="search-results">
      {cards.map((c) => (
        <button key={c.card_version_id} onClick={() => onSelect?.(c)}>
          {c.card_name}
        </button>
      ))}
    </div>
  ),
}))

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('CardPicker', () => {
  it('renders a search input', () => {
    render(<CardPicker onSelect={vi.fn()} selectedId={undefined} />, { wrapper })
    expect(screen.getByPlaceholderText(/search cards/i)).toBeInTheDocument()
  })

  it('shows search results', async () => {
    render(<CardPicker onSelect={vi.fn()} selectedId={undefined} />, { wrapper })
    await waitFor(() => expect(screen.getByTestId('search-results')).toBeInTheDocument())
  })

  it('calls onSelect with the clicked card', async () => {
    const onSelect = vi.fn()
    render(<CardPicker onSelect={onSelect} selectedId={undefined} />, { wrapper })
    await waitFor(() => screen.getByText('Ragavan, Nimble Pilferer'))
    await userEvent.click(screen.getByText('Ragavan, Nimble Pilferer'))
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ card_version_id: 'cv1' })
    )
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd src/frontend && npm test -- CardPicker.test
```

Expected: FAIL — module not found.

- [ ] **Step 3: Create `CardPicker.tsx`**

```tsx
// src/frontend/src/features/ebay/components/CardPicker.tsx
import { useState } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { cardInfiniteSearchQueryOptions } from '../../../features/cards/api'
import { SearchResults } from '../../../features/cards/components/SearchResults'
import type { CardSummary } from '../../../features/cards/types'
import styles from './CardPicker.module.css'

interface CardPickerProps {
  onSelect: (card: CardSummary) => void
  selectedId: string | undefined
}

export function CardPicker({ onSelect, selectedId }: CardPickerProps) {
  const [q, setQ] = useState('')

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } =
    useInfiniteQuery(cardInfiniteSearchQueryOptions({ q: q || undefined }))

  const cards = data?.pages.flatMap((p) => p.cards) ?? []
  const total = data?.pages[0]?.pagination?.total_count ?? cards.length

  return (
    <div className={styles.picker}>
      <div className={styles.searchBar}>
        <input
          type="text"
          className={styles.searchInput}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search cards…"
          aria-label="Search cards"
        />
      </div>
      {isLoading ? (
        <div className={styles.loading}>Loading…</div>
      ) : (
        <SearchResults
          cards={cards}
          total={total}
          fetchNextPage={fetchNextPage}
          hasNextPage={hasNextPage}
          isFetchingNextPage={isFetchingNextPage}
          onSelect={onSelect}
          selectedId={selectedId}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 4: Create `CardPicker.module.css`**

```css
/* src/frontend/src/features/ebay/components/CardPicker.module.css */
.picker {
  display: flex;
  flex-direction: column;
  gap: 0;
  height: 100%;
  overflow: hidden;
  border-right: 1px solid var(--hd-border);
}

.searchBar {
  padding: 16px;
  border-bottom: 1px solid var(--hd-border);
  background: var(--hd-surface);
}

.searchInput {
  width: 100%;
  box-sizing: border-box;
  background: var(--hd-bg);
  border: 1px solid var(--hd-border);
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 13px;
  color: var(--hd-text);
  font-family: var(--font-sans);
  transition: border-color 0.12s;
}
.searchInput:focus {
  outline: none;
  border-color: var(--hd-accent);
}

.loading {
  padding: 24px;
  font-size: 13px;
  color: var(--hd-muted);
  text-align: center;
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd src/frontend && npm test -- CardPicker.test
```

Expected: PASS — 3 tests.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/ebay/components/CardPicker.tsx \
        src/frontend/src/features/ebay/components/CardPicker.module.css \
        src/frontend/src/features/ebay/components/__tests__/CardPicker.test.tsx
git commit -m "feat(ebay): add CardPicker component for create listing flow"
```

---

### Task 9: Build the `/listings/new` create listing page

**Files:**
- Create: `src/frontend/src/routes/listings_.new.tsx`
- Create: `src/frontend/src/routes/ListingsNew.module.css`
- Test: `src/frontend/src/routes/__tests__/listings.new.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `src/frontend/src/routes/__tests__/listings.new.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'

vi.mock('../../components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('../../components/layout/TopBar', () => ({
  TopBar: ({ title }: { title: string }) => <div>{title}</div>,
}))

vi.mock('../../features/ebay/api', () => ({
  fetchUserApps: vi.fn(),
  createListing: vi.fn(),
}))

vi.mock('../../features/ebay/components/CardPicker', () => ({
  CardPicker: ({
    onSelect,
  }: {
    onSelect: (card: { card_version_id: string; card_name: string; set_code: string }) => void
  }) => (
    <div data-testid="card-picker">
      <button
        onClick={() =>
          onSelect({ card_version_id: 'cv1', card_name: 'Ragavan', set_code: 'mh2' })
        }
      >
        Pick Ragavan
      </button>
    </div>
  ),
}))

vi.mock('../../features/ebay/components/ListingFormPanel', () => ({
  ListingFormPanel: ({
    mode,
    initialValues,
    onSave,
    onCancel,
  }: {
    mode: string
    initialValues: { title?: string }
    onSave: (values: unknown, appCode: string) => Promise<void>
    onCancel: () => void
  }) => (
    <div data-testid="form-panel" data-mode={mode} data-title={initialValues.title ?? ''}>
      <button onClick={() => onSave({}, 'app1')}>Create listing</button>
      <button onClick={onCancel}>Cancel</button>
    </div>
  ),
}))

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    createFileRoute: () => ({ component: (c: unknown) => c }),
    useNavigate: () => vi.fn(),
  }
})

import { fetchUserApps, createListing } from '../../features/ebay/api'
import type { EbayAppSummary } from '../../features/ebay/api'
import { ListingsNewPage } from '../listings_.new'

const mockFetchUserApps = vi.mocked(fetchUserApps)
const mockCreateListing = vi.mocked(createListing)

function makeApp(overrides: Partial<EbayAppSummary> = {}): EbayAppSummary {
  return {
    app_id: 'a1', app_name: 'AutoMana AU', app_code: 'automana_au',
    environment: 'PRODUCTION', description: null, is_active: true,
    is_connected: true, token_expires_at: null, other_user_count: 0,
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('ListingsNewPage', () => {
  beforeEach(() => {
    mockFetchUserApps.mockResolvedValue([makeApp()])
    mockCreateListing.mockResolvedValue(undefined)
  })

  it('renders the card picker and an empty form state', async () => {
    render(<ListingsNewPage />)
    await waitFor(() => expect(screen.getByTestId('card-picker')).toBeInTheDocument())
    expect(screen.getByText(/search for a card/i)).toBeInTheDocument()
  })

  it('shows the form panel pre-filled after a card is selected', async () => {
    render(<ListingsNewPage />)
    await waitFor(() => screen.getByTestId('card-picker'))
    await userEvent.click(screen.getByText('Pick Ragavan'))
    await waitFor(() => expect(screen.getByTestId('form-panel')).toBeInTheDocument())
    expect(screen.getByTestId('form-panel').dataset.title).toMatch(/Ragavan/)
  })

  it('calls createListing when the form is submitted', async () => {
    render(<ListingsNewPage />)
    await waitFor(() => screen.getByTestId('card-picker'))
    await userEvent.click(screen.getByText('Pick Ragavan'))
    await waitFor(() => screen.getByTestId('form-panel'))
    await userEvent.click(screen.getByRole('button', { name: /create listing/i }))
    expect(mockCreateListing).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd src/frontend && npm test -- listings.new.test
```

Expected: FAIL — module not found.

- [ ] **Step 3: Create `listings_.new.tsx`**

```tsx
// src/frontend/src/routes/listings_.new.tsx
import { useState, useEffect } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { CardPicker } from '../features/ebay/components/CardPicker'
import {
  ListingFormPanel,
  type ListingFormValues,
} from '../features/ebay/components/ListingFormPanel'
import { fetchUserApps, createListing, type EbayAppSummary } from '../features/ebay/api'
import type { CardSummary } from '../features/cards/types'
import styles from './ListingsNew.module.css'

export const Route = createFileRoute('/listings/new')({
  component: ListingsNewPage,
})

export { ListingsNewPage }

function ListingsNewPage() {
  const navigate = useNavigate()
  const [apps, setApps] = useState<EbayAppSummary[]>([])
  const [selectedCard, setSelectedCard] = useState<CardSummary | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    fetchUserApps()
      .then((all) => setApps(all.filter((a) => a.environment === 'PRODUCTION')))
      .catch(() => setApps([]))
  }, [])

  async function handleCreate(values: ListingFormValues, appCode: string) {
    setIsSaving(true)
    setSaveError(null)
    try {
      await createListing(appCode, {
        title: values.title,
        startPrice: { currency: 'AUD', value: values.price },
        quantity: values.quantity,
        conditionID: values.conditionId,
        ...(values.description ? { description: values.description } : {}),
      })
      navigate({ to: '/listings' })
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to create listing')
      setIsSaving(false)
    }
  }

  const initialTitle = selectedCard
    ? `${selectedCard.card_name} [${selectedCard.set_code.toUpperCase()}]`
    : ''

  return (
    <AppShell active="listings">
      <TopBar title="New listing" breadcrumb="LISTINGS › NEW" />
      <div className={styles.layout}>
        <CardPicker onSelect={setSelectedCard} selectedId={selectedCard?.card_version_id} />
        <div className={styles.formArea}>
          {selectedCard ? (
            <ListingFormPanel
              mode="create"
              initialValues={{
                title: initialTitle,
                price: 0,
                quantity: 1,
                conditionId: 3000,
                description: '',
              }}
              availableApps={apps}
              onSave={handleCreate}
              onCancel={() => navigate({ to: '/listings' })}
              isSaving={isSaving}
              error={saveError}
            />
          ) : (
            <div className={styles.emptyForm}>
              <p>Search for a card to create a listing</p>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  )
}
```

- [ ] **Step 4: Create `ListingsNew.module.css`**

```css
/* src/frontend/src/routes/ListingsNew.module.css */
.layout {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 0;
  min-height: calc(100vh - 120px);
  margin: 0 -36px;
  border-top: 1px solid var(--hd-border);
}

@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
  }
}

.formArea {
  padding: 24px;
  overflow-y: auto;
}

.emptyForm {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 300px;
  color: var(--hd-sub);
  font-size: 14px;
}
```

- [ ] **Step 5: Update the "New listing" button in `listings.tsx` to navigate**

In `src/frontend/src/routes/listings.tsx`, the "New listing" button currently does nothing. Add a `useNavigate` import and wire it:

First add the import at the top of the file:
```tsx
import { createFileRoute, useNavigate } from '@tanstack/react-router'
```

(If `useNavigate` is not already imported — check and add only if missing.)

Inside `ListingsPage`, add:
```tsx
const navigate = useNavigate()
```

Then change the `<Button>` for "New listing":
```tsx
<Button
  variant="accent"
  size="sm"
  icon={<Icon kind="plus" size={12} color="currentColor" />}
  onClick={() => navigate({ to: '/listings/new' })}
>
  New listing
</Button>
```

- [ ] **Step 6: Run all tests to verify the full suite passes**

```bash
cd src/frontend && npm test
```

Expected: PASS — all tests.

- [ ] **Step 7: Commit**

```bash
git add src/frontend/src/routes/listings_.new.tsx \
        src/frontend/src/routes/ListingsNew.module.css \
        src/frontend/src/routes/__tests__/listings.new.test.tsx \
        src/frontend/src/routes/listings.tsx
git commit -m "feat(ebay): add /listings/new create listing page"
```

---

## Self-Review

**Spec coverage:**
- ✅ Create flow at `/listings/new` — Task 9
- ✅ Edit flow inline on `/listings` (row click → panel) — Tasks 5, 6
- ✅ Shared `ListingFormPanel` — Task 4
- ✅ Read-only `ListingDetailPanel` — Task 3
- ✅ `createListing` + `updateListing` API functions — Task 1
- ✅ `updateListing` Zustand action — Task 2
- ✅ `ListingsTable` row selection — Task 5
- ✅ `SearchResults` `onSelect` mode — Task 7
- ✅ `CardPicker` for left panel — Task 8
- ✅ "New listing" button wired to navigate — Task 9, Step 5
- ✅ Condition IDs match backend mapping (NM→3000, LP→4000, MP→5000, HP→6000, DMG→7000)

**Placeholder scan:** No TBD/TODO/vague steps present.

**Type consistency:**
- `ListingFormValues` defined in Task 4 and imported in Tasks 6 and 9 ✅
- `ListingItemPayload` defined in Task 1 and used in Tasks 6 and 9 ✅
- `onSave: (values: ListingFormValues, appCode: string) => Promise<void>` consistent across Tasks 4, 6, 9 ✅
- `onRowClick?: (id: string) => void` defined in Task 5 and wired in Task 6 ✅
