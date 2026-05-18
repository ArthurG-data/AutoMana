// src/frontend/src/features/collection/components/__tests__/CollectionTable.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { CollectionTable } from '../CollectionTable'
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

describe('CollectionTable', () => {
  it('renders table headers', () => {
    render(<CollectionTable entries={[]} />)
    expect(screen.getByText('Card name')).toBeTruthy()
    expect(screen.getByText('Set')).toBeTruthy()
    expect(screen.getByText('Market')).toBeTruthy()
    expect(screen.getByText('P/L')).toBeTruthy()
    expect(screen.getByText('Finish')).toBeTruthy()
  })

  it('shows empty state when no entries', () => {
    render(<CollectionTable entries={[]} />)
    expect(screen.getByText(/no cards match/i)).toBeTruthy()
  })

  it('renders card rows', () => {
    render(<CollectionTable entries={ENTRIES} />)
    expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeTruthy()
    expect(screen.getByText('Force of Will')).toBeTruthy()
  })

  it('shows set code, condition, and finish', () => {
    render(<CollectionTable entries={[ENTRIES[0]]} />)
    expect(screen.getByText('MH2')).toBeTruthy()
    expect(screen.getByText('NM')).toBeTruthy()
    expect(screen.getByText('nonfoil')).toBeTruthy()
  })

  it('shows positive P/L', () => {
    render(<CollectionTable entries={[ENTRIES[0]]} />)
    // profit: 54.20 - 28.00 = +$26.20
    expect(screen.getByText('+$26.20')).toBeTruthy()
  })

  it('calls onRemove with item_id when remove is clicked', () => {
    const onRemove = vi.fn()
    render(<CollectionTable entries={[ENTRIES[0]]} onRemove={onRemove} />)
    fireEvent.click(screen.getByRole('button', { name: /remove ragavan/i }))
    expect(onRemove).toHaveBeenCalledWith('e1')
  })
})
