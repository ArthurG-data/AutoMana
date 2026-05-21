import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { CollectionGrid } from '../CollectionGrid'
import type { CollectionEntry } from '../../api'

const ENTRIES: CollectionEntry[] = [
  {
    item_id: 'e1',
    card_version_id: 'cv1',
    card_name: 'Ragavan, Nimble Pilferer',
    set_code: 'MH2',
    collector_number: '138',
    finish: 'NONFOIL',
    condition: 'NM',
    purchase_price: '28.00',
    purchase_date: '2024-01-01',
    currency_code: 'USD',
    image_normal: null,
    price: 54.20,
    price_change_1d: 1.5,
  },
  {
    item_id: 'e2',
    card_version_id: 'cv2',
    card_name: 'Force of Will',
    set_code: 'ALL',
    collector_number: '28',
    finish: 'FOIL',
    condition: 'LP',
    purchase_price: '120.00',
    purchase_date: '2024-01-02',
    currency_code: 'USD',
    image_normal: null,
    price: 110,
    price_change_1d: -0.5,
  },
]

describe('CollectionGrid', () => {
  it('renders a card for each entry', () => {
    render(<CollectionGrid entries={ENTRIES} onRemove={vi.fn()} />)
    expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeTruthy()
    expect(screen.getByText('Force of Will')).toBeTruthy()
  })

  it('shows set code and condition', () => {
    render(<CollectionGrid entries={[ENTRIES[0]]} onRemove={vi.fn()} />)
    expect(screen.getByText('MH2')).toBeTruthy()
    expect(screen.getByText('NM')).toBeTruthy()
  })

  it('shows market price', () => {
    render(<CollectionGrid entries={[ENTRIES[0]]} onRemove={vi.fn()} />)
    expect(screen.getByText('$54.20')).toBeTruthy()
  })

  it('shows P&L in green when profit', () => {
    render(<CollectionGrid entries={[ENTRIES[0]]} onRemove={vi.fn()} />)
    // profit: 54.20 - 28.00 = +$26.20
    expect(screen.getByText('+$26.20')).toBeTruthy()
  })

  it('shows P&L in red when loss', () => {
    render(<CollectionGrid entries={[ENTRIES[1]]} onRemove={vi.fn()} />)
    // loss: 110 - 120 = -$10.00
    expect(screen.getByText('-$10.00')).toBeTruthy()
  })

  it('calls onRemove with item_id when remove button clicked', () => {
    const onRemove = vi.fn()
    render(<CollectionGrid entries={[ENTRIES[0]]} onRemove={onRemove} />)
    fireEvent.click(screen.getByRole('button', { name: /remove ragavan/i }))
    expect(onRemove).toHaveBeenCalledWith('e1')
  })

  it('shows empty state when no entries', () => {
    render(<CollectionGrid entries={[]} onRemove={vi.fn()} />)
    expect(screen.getByText(/no cards yet/i)).toBeTruthy()
  })

  it('renders finish badge for FOIL entries', () => {
    render(<CollectionGrid entries={[ENTRIES[1]]} onRemove={vi.fn()} />)
    expect(screen.getByText('foil')).toBeTruthy()
  })

  it('does not render a finish badge for NONFOIL entries', () => {
    render(<CollectionGrid entries={[ENTRIES[0]]} onRemove={vi.fn()} />)
    expect(screen.queryByText('nonfoil')).toBeNull()
  })
})
