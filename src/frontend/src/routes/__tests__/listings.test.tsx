import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('../../features/ebay/api', () => ({
  fetchUserApps: vi.fn(),
  fetchActiveListings: vi.fn(),
  fetchActiveListingsPaginated: vi.fn(),
  updateListing: vi.fn(),
}))

vi.mock('../../features/ebay/lib/catalogEnrich', () => ({
  enrichWithCatalog: vi.fn((listings: unknown[]) => Promise.resolve(listings)),
}))

vi.mock('../../components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('../../components/layout/TopBar', () => ({
  TopBar: ({ title }: { title: string }) => <div>{title}</div>,
}))

vi.mock('../../features/ebay/components/ListingsTable', () => ({
  ListingsTable: ({
    listings,
    isLoading,
    onRowClick,
  }: {
    listings: { appName: string; itemId: string }[]
    isLoading?: boolean
    onRowClick?: (id: string) => void
  }) => (
    <div
      data-testid="listings-table"
      data-loading={String(isLoading)}
      data-count={listings.length}
      data-app-names={listings.map((l) => l.appName).join(',')}
      onClick={() => listings[0] && onRowClick?.(listings[0].itemId)}
    />
  ),
}))

vi.mock('../../features/ebay/components/ListingDetailPanel', () => ({
  ListingDetailPanel: ({
    listing,
    onEdit,
    onClose,
  }: {
    listing: { cardName: string }
    onEdit: () => void
    onClose: () => void
  }) => (
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

import { fetchUserApps, fetchActiveListingsPaginated } from '../../features/ebay/api'
import type { EbayAppSummary } from '../../features/ebay/api'
import type { EbayLiveListing } from '../../features/ebay/mockListings'
import { ListingsPage } from '../listings'

const mockFetchUserApps = vi.mocked(fetchUserApps)
const mockFetchActiveListingsPaginated = vi.mocked(fetchActiveListingsPaginated)

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
    setCode: 'MH2',
    setInfo: 'MH2',
    style: '',
    daysListed: 0,
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

function pagedResult(listings: EbayLiveListing[], hasMore = false) {
  return { items: listings, hasMore }
}

function renderListingsPage() {
  return render(<ListingsPage />)
}

describe('ListingsPage Active tab', () => {
  beforeEach(() => {
    mockFetchUserApps.mockReset()
    mockFetchActiveListingsPaginated.mockReset()
  })

  it('shows loading skeleton while fetching', async () => {
    mockFetchUserApps.mockReturnValue(new Promise(() => {}))
    renderListingsPage()
    const table = screen.getByTestId('listings-table')
    expect(table.getAttribute('data-loading')).toBe('true')
  })

  it('passes merged live listings to ListingsTable after fetch', async () => {
    const listing = makeListing()
    mockFetchUserApps.mockResolvedValue([makeApp()])
    mockFetchActiveListingsPaginated.mockResolvedValue(pagedResult([listing]))
    renderListingsPage()
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
    mockFetchActiveListingsPaginated.mockResolvedValue(pagedResult([]))
    renderListingsPage()
    await waitFor(() => {
      expect(mockFetchActiveListingsPaginated).toHaveBeenCalledTimes(1)
      expect(mockFetchActiveListingsPaginated).toHaveBeenCalledWith('prod_app', 25, 0)
    })
  })

  it('merges listings from multiple apps', async () => {
    mockFetchUserApps.mockResolvedValue([
      makeApp({ app_code: 'app_1', app_name: 'App 1' }),
      makeApp({ app_code: 'app_2', app_name: 'App 2', app_id: 'app-2' }),
    ])
    mockFetchActiveListingsPaginated
      .mockResolvedValueOnce(pagedResult([makeListing({ itemId: 'l1', appCode: 'app_1' })]))
      .mockResolvedValueOnce(pagedResult([makeListing({ itemId: 'l2', appCode: 'app_2' })]))
    renderListingsPage()
    await waitFor(() => {
      const table = screen.getByTestId('listings-table')
      expect(table.getAttribute('data-count')).toBe('2')
    })
  })

  it('injects appName onto each listing', async () => {
    mockFetchUserApps.mockResolvedValue([makeApp({ app_code: 'automana_au', app_name: 'AutoMana AU' })])
    mockFetchActiveListingsPaginated.mockResolvedValue(
      pagedResult([makeListing({ appCode: 'automana_au', appName: '' })])
    )
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
    mockFetchActiveListingsPaginated
      .mockResolvedValueOnce(pagedResult([makeListing()]))
      .mockRejectedValueOnce(new Error('Network error'))
    renderListingsPage()
    await waitFor(() => {
      expect(screen.getByText(/could not load listings for bad app/i)).toBeTruthy()
    })
  })

  it('renders listings from successful apps even when one fails', async () => {
    mockFetchUserApps.mockResolvedValue([
      makeApp({ app_code: 'app_ok', app_name: 'Good App' }),
      makeApp({ app_code: 'app_fail', app_name: 'Bad App', app_id: 'app-2' }),
    ])
    mockFetchActiveListingsPaginated
      .mockResolvedValueOnce(pagedResult([makeListing({ itemId: 'l1' })]))
      .mockRejectedValueOnce(new Error('fail'))
    renderListingsPage()
    await waitFor(() => {
      const table = screen.getByTestId('listings-table')
      expect(table.getAttribute('data-count')).toBe('1')
    })
  })

  it('dismisses error banner on close click', async () => {
    const user = userEvent.setup()
    mockFetchUserApps.mockResolvedValue([makeApp({ app_code: 'app_fail', app_name: 'Bad App' })])
    mockFetchActiveListingsPaginated.mockRejectedValue(new Error('fail'))
    renderListingsPage()
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
    renderListingsPage()
    await waitFor(() => {
      expect(mockFetchActiveListingsPaginated).not.toHaveBeenCalled()
    })
  })
})

describe('ListingsPage — split-panel edit', () => {
  beforeEach(() => {
    mockFetchUserApps.mockResolvedValue([makeApp()])
    mockFetchActiveListingsPaginated.mockResolvedValue(
      pagedResult([makeListing({ itemId: 'l1', cardName: 'Ragavan' })])
    )
  })

  it('shows detail panel after clicking a row', async () => {
    render(<ListingsPage />)
    await waitFor(() => expect(screen.getByTestId('listings-table')).toBeInTheDocument())

    const { useListingsStore } = await import('../../store/listings')
    useListingsStore.getState().setListings([makeListing({ itemId: 'l1', cardName: 'Ragavan' })])

    await userEvent.click(screen.getByTestId('listings-table'))
    await waitFor(() => expect(screen.getByTestId('detail-panel')).toBeInTheDocument())
  })

  it('switches to form panel when Edit listing is clicked', async () => {
    render(<ListingsPage />)
    await waitFor(() => expect(screen.getByTestId('listings-table')).toBeInTheDocument())

    const { useListingsStore } = await import('../../store/listings')
    useListingsStore.getState().setListings([makeListing({ itemId: 'l1', cardName: 'Ragavan' })])

    await userEvent.click(screen.getByTestId('listings-table'))
    await waitFor(() => screen.getByTestId('detail-panel'))
    await userEvent.click(screen.getByRole('button', { name: /edit listing/i }))
    expect(screen.getByTestId('form-panel')).toBeInTheDocument()
  })

  it('returns to detail panel when Cancel is clicked in form', async () => {
    render(<ListingsPage />)
    await waitFor(() => expect(screen.getByTestId('listings-table')).toBeInTheDocument())

    const { useListingsStore } = await import('../../store/listings')
    useListingsStore.getState().setListings([makeListing({ itemId: 'l1', cardName: 'Ragavan' })])

    await userEvent.click(screen.getByTestId('listings-table'))
    await waitFor(() => screen.getByTestId('detail-panel'))
    await userEvent.click(screen.getByRole('button', { name: /edit listing/i }))
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(screen.getByTestId('detail-panel')).toBeInTheDocument()
  })
})
