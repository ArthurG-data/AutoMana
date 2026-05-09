import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { ListingsTable } from '../ListingsTable'
import type { EbayLiveListing } from '../../mockListings'

// Link needs a router context — stub it to a plain anchor so tests stay unit-level.
vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    Link: ({ children, to, params, ...props }: Record<string, unknown> & { children: React.ReactNode; to?: string; params?: unknown }) => (
      <a href={typeof to === 'string' ? to : '#'} {...props}>{children}</a>
    ),
  }
})

function makeListing(overrides: Partial<EbayLiveListing> = {}): EbayLiveListing {
  return {
    itemId: 'l1',
    title: 'Ragavan, Nimble Pilferer MH2 NM MTG',
    cardName: 'Ragavan, Nimble Pilferer',
    setCode: 'MH2',
    setInfo: 'MH2',
    style: '',
    daysListed: 14,
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
    expect(screen.getByText('WATCH')).toBeTruthy()
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

  it('renders card name as an internal detail-page link', () => {
    render(<ListingsTable listings={[makeListing()]} />)
    const link = screen.getByRole('link', { name: /ragavan, nimble pilferer/i })
    expect(link.getAttribute('href')).toBe('/listings_/$id')
  })

  it('renders a separate eBay external link next to the card name', () => {
    render(<ListingsTable listings={[makeListing()]} />)
    const ebayLink = screen.getByTitle('View on eBay')
    expect(ebayLink.getAttribute('href')).toBe('https://www.ebay.com.au/itm/123')
    expect(ebayLink.getAttribute('target')).toBe('_blank')
    expect(ebayLink.getAttribute('rel')).toBe('noopener noreferrer')
  })

  it('renders condition label in its own column', () => {
    render(<ListingsTable listings={[makeListing({ conditionLabel: 'NM' })]} />)
    expect(screen.getByText('NM')).toBeTruthy()
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

  it('sorts by price ascending when price header is clicked', () => {
    const listings = [
      makeListing({ itemId: 'l1', cardName: 'Alpha', price: 100 }),
      makeListing({ itemId: 'l2', cardName: 'Beta', price: 10 }),
    ]
    render(<ListingsTable listings={listings} />)
    fireEvent.click(screen.getByText(/^PRICE/))
    const cells = screen.getAllByText(/^\$\d+\.00$/)
    expect(cells[0].textContent).toBe('$10.00')
    expect(cells[1].textContent).toBe('$100.00')
  })

  it('sorts by price descending on second click', () => {
    const listings = [
      makeListing({ itemId: 'l1', cardName: 'Alpha', price: 100 }),
      makeListing({ itemId: 'l2', cardName: 'Beta', price: 10 }),
    ]
    render(<ListingsTable listings={listings} />)
    fireEvent.click(screen.getByText(/^PRICE/))
    fireEvent.click(screen.getByText(/^PRICE/))
    const cells = screen.getAllByText(/^\$\d+\.00$/)
    expect(cells[0].textContent).toBe('$100.00')
    expect(cells[1].textContent).toBe('$10.00')
  })
})

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
    expect(screen.queryByRole('link', { name: /ragavan/i })).toBeNull()
    expect(screen.getByText('Ragavan')).toBeInTheDocument()
  })

  it('clicking the eBay link does not fire onRowClick', async () => {
    const onRowClick = vi.fn()
    const listing = makeListing({ itemId: 'abc', viewItemUrl: 'https://www.ebay.com.au/itm/123' })
    render(<ListingsTable listings={[listing]} onRowClick={onRowClick} />)
    await userEvent.click(screen.getByTitle('View on eBay'))
    expect(onRowClick).not.toHaveBeenCalled()
  })
})
