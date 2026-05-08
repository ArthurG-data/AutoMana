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
    expect(screen.getByText('APP')).toBeTruthy()
    expect(screen.getByText('COND')).toBeTruthy()
    expect(screen.getByText('PRICE')).toBeTruthy()
    expect(screen.getByText('WATCHERS')).toBeTruthy()
    expect(screen.getByText('STATUS')).toBeTruthy()
  })

  it('shows empty state when no listings and not loading', () => {
    render(<ListingsTable listings={[]} />)
    expect(screen.getByText(/no listings found/i)).toBeTruthy()
  })

  it('renders filter input above the table', () => {
    render(<ListingsTable listings={[]} />)
    expect(screen.getByPlaceholderText('Filter by card name…')).toBeTruthy()
  })

  it('renders card name as an external link to eBay', () => {
    render(<ListingsTable listings={[makeListing()]} />)
    const link = screen.getByRole('link', { name: /ragavan/i })
    expect(link.getAttribute('href')).toBe('https://www.ebay.com.au/itm/123')
    expect(link.getAttribute('target')).toBe('_blank')
    expect(link.getAttribute('rel')).toBe('noopener noreferrer')
  })

  it('renders COND · SET badge next to card name', () => {
    render(<ListingsTable listings={[makeListing({ conditionLabel: 'NM', setInfo: 'MH2' })]} />)
    expect(screen.getByText('NM · MH2')).toBeTruthy()
  })

  it('renders badge with only setInfo when conditionLabel is empty', () => {
    render(<ListingsTable listings={[makeListing({ conditionLabel: '', setInfo: 'MH2' })]} />)
    expect(screen.getByText('MH2')).toBeTruthy()
  })

  it('renders app badge with app name', () => {
    render(<ListingsTable listings={[makeListing()]} />)
    expect(screen.getByText('AutoMana AU')).toBeTruthy()
  })

  it('filters rows by card name input', () => {
    const listings = [
      makeListing({ itemId: 'l1', cardName: 'Ragavan, Nimble Pilferer' }),
      makeListing({ itemId: 'l2', cardName: 'Force of Will', viewItemUrl: 'https://www.ebay.com.au/itm/2' }),
    ]
    render(<ListingsTable listings={listings} />)
    const input = screen.getByPlaceholderText('Filter by card name…')
    fireEvent.change(input, { target: { value: 'Force' } })
    expect(screen.queryByText('Ragavan, Nimble Pilferer')).toBeNull()
    expect(screen.getByText('Force of Will')).toBeTruthy()
  })

  it('filter is case-insensitive', () => {
    render(<ListingsTable listings={[makeListing({ cardName: 'Ragavan, Nimble Pilferer' })]} />)
    const input = screen.getByPlaceholderText('Filter by card name…')
    fireEvent.change(input, { target: { value: 'ragavan' } })
    expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeTruthy()
  })

  it('shows skeleton rows when isLoading is true', () => {
    render(<ListingsTable listings={[]} isLoading />)
    expect(screen.queryByText(/no listings found/i)).toBeNull()
    const skeletonRows = document.querySelectorAll('[data-testid="skeleton-row"]')
    expect(skeletonRows.length).toBe(3)
  })

  it('renders price as $XX.XX', () => {
    render(<ListingsTable listings={[makeListing({ price: 62 })]} />)
    expect(screen.getByText('$62.00')).toBeTruthy()
  })

  it('renders watch count', () => {
    render(<ListingsTable listings={[makeListing({ watchCount: 7 })]} />)
    expect(screen.getByText('7')).toBeTruthy()
  })

  it('shows listing count and app count in filter bar', () => {
    const listings = [
      makeListing({ itemId: 'l1', appCode: 'app_1' }),
      makeListing({ itemId: 'l2', appCode: 'app_2' }),
    ]
    render(<ListingsTable listings={listings} />)
    expect(screen.getByText(/2 listings · 2 apps/i)).toBeTruthy()
  })
})
