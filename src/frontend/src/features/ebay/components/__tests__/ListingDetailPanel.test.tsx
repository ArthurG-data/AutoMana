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
