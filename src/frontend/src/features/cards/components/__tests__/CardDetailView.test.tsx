// src/frontend/src/features/cards/components/__tests__/CardDetailView.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CardDetailView } from '../CardDetailView'
import type { CardDetail } from '../../types'

vi.mock('../PriceCharts', () => ({
  PriceCharts: ({ finish }: { finish?: string }) => (
    <div data-testid="price-charts" data-finish={finish ?? ''} />
  ),
}))
vi.mock('../../../../components/design-system/CardArt', () => ({
  CardArt: () => <div />,
}))
vi.mock('../../../../components/design-system/AreaChart', () => ({
  AreaChart: () => <div />,
}))
vi.mock('../../../../components/design-system/Pip', () => ({
  Pip: () => <span />,
}))

const mockCard: CardDetail = {
  card_version_id: '11111111-1111-1111-1111-111111111111',
  card_name: 'Sheoldred',
  set_code: 'mom',
  set_name: 'March of the Machine',
  finish: 'non-foil',
  rarity_name: 'rare',
  price: 42.5,
  price_change_1d: 1.2,
  price_change_7d: -0.5,
  price_change_30d: 3.1,
  image_uri: null,
  spark: [],
  available_finishes: ['nonfoil', 'foil'],
}

describe('CardDetailView', () => {
  it('renders a chip for each available finish', () => {
    render(<CardDetailView card={mockCard} />)
    expect(screen.getByText('nonfoil')).toBeTruthy()
    expect(screen.getByText('foil')).toBeTruthy()
  })

  it('defaults selected finish to first available finish', () => {
    render(<CardDetailView card={mockCard} />)
    expect(screen.getByTestId('price-charts').dataset.finish).toBe('nonfoil')
  })

  it('updates selected finish and passes it to PriceCharts when chip clicked', () => {
    render(<CardDetailView card={mockCard} />)
    fireEvent.click(screen.getByText('foil'))
    expect(screen.getByTestId('price-charts').dataset.finish).toBe('foil')
  })

  it('falls back to nonfoil chip when available_finishes is empty', () => {
    render(<CardDetailView card={{ ...mockCard, available_finishes: [] }} />)
    expect(screen.getByText('nonfoil')).toBeTruthy()
  })

  it('falls back to nonfoil chip when available_finishes is undefined', () => {
    const { available_finishes: _, ...cardWithoutFinishes } = mockCard
    render(<CardDetailView card={cardWithoutFinishes as CardDetail} />)
    expect(screen.getByText('nonfoil')).toBeTruthy()
  })
})
