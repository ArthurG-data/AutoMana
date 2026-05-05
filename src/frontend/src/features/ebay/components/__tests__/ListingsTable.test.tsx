// src/frontend/src/features/ebay/components/__tests__/ListingsTable.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { ListingsTable } from '../ListingsTable'
import { MOCK_ACTIVE_LISTINGS } from '../../mockListings'

// TanStack Router's <Link> needs a router context; use MemoryRouter from react-router-dom
// OR mock it — we prefer mocking to avoid installing the test harness for TanStack Router
vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    Link: ({ children, to, className, onClick, 'aria-label': ariaLabel }: {
      children: React.ReactNode
      to: string
      params?: Record<string, string>
      className?: string
      onClick?: () => void
      'aria-label'?: string
    }) => (
      <a href={to} className={className} onClick={onClick} aria-label={ariaLabel}>
        {children}
      </a>
    ),
  }
})

describe('ListingsTable', () => {
  it('renders table headers', () => {
    render(<ListingsTable listings={[]} />)
    expect(screen.getByText('Card name')).toBeTruthy()
    expect(screen.getByText('Set')).toBeTruthy()
    expect(screen.getByText('Condition')).toBeTruthy()
    expect(screen.getByText('Listed price')).toBeTruthy()
    expect(screen.getByText('Market price')).toBeTruthy()
    expect(screen.getByText('AI status')).toBeTruthy()
  })

  it('shows empty state when no listings', () => {
    render(<ListingsTable listings={[]} />)
    expect(screen.getByText(/no listings found/i)).toBeTruthy()
  })

  it('renders all mock listing rows', () => {
    render(<ListingsTable listings={MOCK_ACTIVE_LISTINGS} />)
    expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeTruthy()
    expect(screen.getByText('Force of Will')).toBeTruthy()
    expect(screen.getByText('Mox Diamond (Foil)')).toBeTruthy()
  })

  it('shows set codes for each listing', () => {
    render(<ListingsTable listings={MOCK_ACTIVE_LISTINGS} />)
    expect(screen.getByText('MH2')).toBeTruthy()
    expect(screen.getByText('ALL')).toBeTruthy()
  })

  it('calls onMore when more button is clicked', () => {
    const onMore = vi.fn()
    const listing = MOCK_ACTIVE_LISTINGS[0]
    render(<ListingsTable listings={[listing]} onMore={onMore} />)
    const btn = screen.getByRole('button', {
      name: new RegExp(`more options for ${listing.cardName}`, 'i'),
    })
    fireEvent.click(btn)
    expect(onMore).toHaveBeenCalledWith(listing)
  })

  it('shows foil badge for foil listings', () => {
    const foilListing = MOCK_ACTIVE_LISTINGS.find((l) => l.foil)!
    render(<ListingsTable listings={[foilListing]} />)
    expect(screen.getByText('foil')).toBeTruthy()
  })

  it('shows price delta badge for overpriced listings', () => {
    // Ragavan is listed at 62 vs market 54.20 → over
    const overlisted = MOCK_ACTIVE_LISTINGS.find((l) => l.aiStatus === 'over')!
    render(<ListingsTable listings={[overlisted]} />)
    // delta should be positive
    const deltaEl = screen.getByText(/\+\d+%/)
    expect(deltaEl).toBeTruthy()
  })

  it('renders strategy link for each listing', () => {
    const listing = MOCK_ACTIVE_LISTINGS[0]
    render(<ListingsTable listings={[listing]} />)
    const stratBtn = screen.getByRole('link', {
      name: new RegExp(`view ${listing.cardName} strategy`, 'i'),
    })
    expect(stratBtn).toBeTruthy()
  })
})
