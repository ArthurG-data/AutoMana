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

  it('does not show ×N badge for a single copy', () => {
    render(<CollectionGrid entries={[makeEntry()]} onRemove={vi.fn()} />)
    expect(screen.queryByText(/×\d/)).not.toBeInTheDocument()
  })

  it('does not show copy list when collapsed', () => {
    const entries = [makeEntry({ item_id: 'item-1' }), makeEntry({ item_id: 'item-2' })]
    render(<CollectionGrid entries={entries} onRemove={vi.fn()} />)
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('shows mini-rows when the tile is expanded', () => {
    const entries = [makeEntry({ item_id: 'item-1' }), makeEntry({ item_id: 'item-2' })]
    render(<CollectionGrid entries={entries} onRemove={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Expand Sol Ring/i }))
    expect(screen.getByRole('list')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('collapses when the expand button is clicked again', () => {
    const entries = [makeEntry({ item_id: 'item-1' }), makeEntry({ item_id: 'item-2' })]
    render(<CollectionGrid entries={entries} onRemove={vi.fn()} />)
    const btn = screen.getByRole('button', { name: /Expand Sol Ring/i })
    fireEvent.click(btn)
    fireEvent.click(btn)
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('calls onRemove with the correct item_id from the copy list', () => {
    const onRemove = vi.fn()
    const entries = [makeEntry({ item_id: 'item-1' }), makeEntry({ item_id: 'item-2' })]
    render(<CollectionGrid entries={entries} onRemove={onRemove} />)
    fireEvent.click(screen.getByRole('button', { name: /Expand Sol Ring/i }))
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
})
