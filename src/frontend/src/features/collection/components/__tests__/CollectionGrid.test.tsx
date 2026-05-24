import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CollectionGrid } from '../CollectionGrid'
import type { CollectionEntry } from '../../api'

const makeEntry = (overrides: Partial<CollectionEntry> = {}): CollectionEntry => ({
  item_id: 'item-1',
  card_version_id: 'card-a',
  card_name: 'Sol Ring',
  set_code: 'lea',
  collector_number: '265',
  finish: 'NONFOIL',
  condition: 'NM',
  purchase_price: '5.00',
  purchase_date: '2024-01-01',
  currency_code: 'USD',
  price: 10.00,
  price_change_1d: 0,
  status: 'purchased',
  image_normal: null,
  ...overrides,
})

describe('CollectionGrid', () => {
  it('shows empty state when no entries', () => {
    render(<CollectionGrid entries={[]} onRemove={vi.fn()} />)
    expect(screen.getByText(/No cards yet/)).toBeInTheDocument()
  })

  it('renders one tile for a single entry', () => {
    render(<CollectionGrid entries={[makeEntry()]} onRemove={vi.fn()} />)
    expect(screen.getAllByText('Sol Ring')).toHaveLength(1)
  })

  it('renders one tile for multiple copies of the same card', () => {
    const entries = [
      makeEntry({ item_id: 'item-1' }),
      makeEntry({ item_id: 'item-2' }),
      makeEntry({ item_id: 'item-3' }),
    ]
    render(<CollectionGrid entries={entries} onRemove={vi.fn()} />)
    expect(screen.getAllByText('Sol Ring')).toHaveLength(1)
  })

  it('shows ×N badge when there are multiple copies', () => {
    const entries = [
      makeEntry({ item_id: 'item-1' }),
      makeEntry({ item_id: 'item-2' }),
      makeEntry({ item_id: 'item-3' }),
    ]
    render(<CollectionGrid entries={entries} onRemove={vi.fn()} />)
    expect(screen.getByText('×3')).toBeInTheDocument()
  })

  it('shows ×1 badge for a single copy', () => {
    render(<CollectionGrid entries={[makeEntry()]} onRemove={vi.fn()} />)
    expect(screen.getByText('×1')).toBeInTheDocument()
  })

  it('always shows copy rows without needing to expand', () => {
    const entries = [makeEntry({ item_id: 'item-1' }), makeEntry({ item_id: 'item-2' })]
    render(<CollectionGrid entries={entries} onRemove={vi.fn()} />)
    expect(screen.getByRole('list')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('shows remove button for each copy without interaction', () => {
    const entries = [makeEntry({ item_id: 'item-1' }), makeEntry({ item_id: 'item-2' })]
    render(<CollectionGrid entries={entries} onRemove={vi.fn()} />)
    expect(screen.getAllByRole('button', { name: /Remove copy/i })).toHaveLength(2)
  })

  it('calls onRemove with the correct item_id', () => {
    const onRemove = vi.fn()
    const entries = [makeEntry({ item_id: 'item-1' }), makeEntry({ item_id: 'item-2' })]
    render(<CollectionGrid entries={entries} onRemove={onRemove} />)
    const removeBtns = screen.getAllByRole('button', { name: /Remove copy/i })
    fireEvent.click(removeBtns[1])
    expect(onRemove).toHaveBeenCalledWith('item-2')
  })

  it('renders two separate tiles for different card versions', () => {
    const entries = [
      makeEntry({ item_id: 'item-1', card_version_id: 'card-a', card_name: 'Sol Ring' }),
      makeEntry({ item_id: 'item-2', card_version_id: 'card-b', card_name: 'Black Lotus' }),
    ]
    render(<CollectionGrid entries={entries} onRemove={vi.fn()} />)
    expect(screen.getByText('Sol Ring')).toBeInTheDocument()
    expect(screen.getByText('Black Lotus')).toBeInTheDocument()
  })

  it('hides price and P/L when showFinancials is false', () => {
    const entry = makeEntry({ price: 10.00, purchase_price: '5.00' })
    render(<CollectionGrid entries={[entry]} onRemove={vi.fn()} showFinancials={false} />)
    // $10.00 is the market price — should be hidden
    expect(screen.queryByText('$10.00')).toBeNull()
  })

  it('shows price by default (showFinancials defaults to true)', () => {
    const entry = makeEntry({ price: 10.00, purchase_price: '5.00' })
    render(<CollectionGrid entries={[entry]} onRemove={vi.fn()} />)
    expect(screen.getByText('$10.00')).toBeInTheDocument()
  })
})
