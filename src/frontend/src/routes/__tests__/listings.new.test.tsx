// src/frontend/src/routes/__tests__/listings.new.test.tsx
import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { CardSummary } from '../../features/cards/types'
import type { ListingFormValues } from '../../features/ebay/components/ListingFormPanel'

const mockNavigate = vi.fn()

vi.mock('@tanstack/react-router', () => ({
  createFileRoute: () => () => ({ component: null }),
  useNavigate: () => mockNavigate,
}))

vi.mock('../../features/ebay/api', () => ({
  fetchUserApps: vi.fn(),
  createListing: vi.fn(),
}))

const mockCard: CardSummary = {
  card_version_id: 'cv1',
  card_name: 'Ragavan, Nimble Pilferer',
  set_code: 'mh2',
  set_name: 'Modern Horizons 2',
  finish: 'non-foil',
  rarity_name: 'mythic',
  price: 60,
  price_change_1d: 0,
  price_change_7d: 0,
  price_change_30d: 0,
  image_uri: null,
  image_normal: null,
  spark: [],
}

vi.mock('../../features/ebay/components/CardPicker', () => ({
  CardPicker: ({ onSelect }: { onSelect: (c: CardSummary) => void }) => (
    <button onClick={() => onSelect(mockCard)}>Pick card</button>
  ),
}))

vi.mock('../../components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('../../components/layout/TopBar', () => ({
  TopBar: ({ title }: { title: string }) => <div data-testid="topbar">{title}</div>,
}))

vi.mock('../../features/ebay/components/ListingFormPanel', () => ({
  ListingFormPanel: ({
    onSave,
    onCancel,
    initialValues,
    isSaving,
    error,
  }: {
    onSave: (v: ListingFormValues, appCode: string) => Promise<void>
    onCancel: () => void
    initialValues: Partial<ListingFormValues>
    isSaving: boolean
    error: string | null
  }) => (
    <div
      data-testid="listing-form"
      data-title={initialValues.title ?? ''}
      data-saving={String(isSaving)}
      data-error={error ?? ''}
    >
      <button
        onClick={() =>
          onSave(
            { title: 'Test', price: 10, quantity: 1, conditionId: 3000, description: '' },
            'automana_au',
          )
        }
      >
        Save
      </button>
      <button onClick={onCancel}>Cancel</button>
    </div>
  ),
}))

import { fetchUserApps, createListing } from '../../features/ebay/api'
import type { EbayAppSummary } from '../../features/ebay/api'
import { ListingsNewPage } from '../listings_.new'

const mockFetchUserApps = vi.mocked(fetchUserApps)
const mockCreateListing = vi.mocked(createListing)

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

describe('ListingsNewPage', () => {
  beforeEach(() => {
    mockNavigate.mockClear()
    mockFetchUserApps.mockReset()
    mockCreateListing.mockReset()
  })

  it('shows loading state while fetching apps', () => {
    mockFetchUserApps.mockReturnValue(new Promise(() => {}))
    render(<ListingsNewPage />)
    expect(screen.getByTestId('loading')).toBeInTheDocument()
  })

  it('renders CardPicker and ListingFormPanel after apps load', async () => {
    mockFetchUserApps.mockResolvedValue([makeApp()])
    render(<ListingsNewPage />)
    await waitFor(() => {
      expect(screen.getByText('Pick card')).toBeInTheDocument()
      expect(screen.getByTestId('listing-form')).toBeInTheDocument()
    })
  })

  it('pre-fills form title when a card is selected', async () => {
    const user = userEvent.setup()
    mockFetchUserApps.mockResolvedValue([makeApp()])
    render(<ListingsNewPage />)
    await waitFor(() => expect(screen.getByText('Pick card')).toBeInTheDocument())
    await user.click(screen.getByText('Pick card'))
    const form = screen.getByTestId('listing-form')
    expect(form.getAttribute('data-title')).toBe('Ragavan, Nimble Pilferer MH2 NM MTG')
  })

  it('calls createListing and navigates to /listings on save', async () => {
    const user = userEvent.setup()
    mockFetchUserApps.mockResolvedValue([makeApp()])
    mockCreateListing.mockResolvedValue(undefined)
    render(<ListingsNewPage />)
    await waitFor(() => expect(screen.getByTestId('listing-form')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => {
      expect(mockCreateListing).toHaveBeenCalledWith('automana_au', {
        title: 'Test',
        startPrice: { currency: 'AUD', value: 10 },
        quantity: 1,
        conditionID: 3000,
      })
      expect(mockNavigate).toHaveBeenCalledWith({ to: '/listings' })
    })
  })

  it('navigates to /listings on cancel', async () => {
    const user = userEvent.setup()
    mockFetchUserApps.mockResolvedValue([makeApp()])
    render(<ListingsNewPage />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(mockNavigate).toHaveBeenCalledWith({ to: '/listings' })
  })

  it('shows save error in form', async () => {
    const user = userEvent.setup()
    mockFetchUserApps.mockResolvedValue([makeApp()])
    mockCreateListing.mockRejectedValue(new Error('eBay API error'))
    render(<ListingsNewPage />)
    await waitFor(() => expect(screen.getByTestId('listing-form')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => {
      const form = screen.getByTestId('listing-form')
      expect(form.getAttribute('data-error')).toBe('eBay API error')
    })
  })

  it('only passes PRODUCTION apps to form', async () => {
    const user = userEvent.setup()
    mockFetchUserApps.mockResolvedValue([
      makeApp({ environment: 'SANDBOX', app_code: 'sandbox_app', app_name: 'Sandbox App' }),
      makeApp({ environment: 'PRODUCTION', app_code: 'automana_au', app_name: 'AutoMana AU' }),
    ])
    mockCreateListing.mockResolvedValue(undefined)
    render(<ListingsNewPage />)
    await waitFor(() => expect(screen.getByTestId('listing-form')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => {
      expect(mockCreateListing).toHaveBeenCalled()
    })
  })
})
