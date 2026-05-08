import { render, screen, waitFor } from '@testing-library/react'
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
    renderListingsPage()
    const table = screen.getByTestId('listings-table')
    expect(table.getAttribute('data-loading')).toBe('true')
  })

  it('passes merged live listings to ListingsTable after fetch', async () => {
    const listing = makeListing()
    mockFetchUserApps.mockResolvedValue([makeApp()])
    mockFetchActiveListings.mockResolvedValue([listing])
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
    mockFetchActiveListings.mockResolvedValue([])
    renderListingsPage()
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
    renderListingsPage()
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
    mockFetchActiveListings
      .mockResolvedValueOnce([makeListing({ itemId: 'l1' })])
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
    mockFetchActiveListings.mockRejectedValue(new Error('fail'))
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
      expect(mockFetchActiveListings).not.toHaveBeenCalled()
    })
  })
})
