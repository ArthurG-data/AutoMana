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
vi.mock('../SetInfoBox', () => ({
  SetInfoBox: () => <div data-testid="set-info-box" />,
}))
vi.mock('../LegalityGrid', () => ({
  LegalityGrid: ({ legalities }: { legalities: Record<string, string> }) => (
    <div data-testid="legality-grid" data-has-entries={Object.keys(legalities).length > 0 ? 'true' : 'false'} />
  ),
}))
vi.mock('../../../../components/design-system/FlippableCardArt', () => ({
  FlippableCardArt: ({
    frontUrl,
    backUrl,
  }: {
    name?: string
    frontUrl?: string | null
    backUrl?: string | null
    w?: number | string
    h?: number | string
    style?: React.CSSProperties
  }) => (
    <div
      data-testid="flippable-card-art"
      data-front={frontUrl ?? ''}
      data-back={backUrl ?? ''}
    />
  ),
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
  image_large: 'https://example.com/front.jpg',
  collector_number: '245',
  promo_types: [],
  legalities: { modern: 'legal', standard: 'not_legal' },
}

describe('CardDetailView', () => {
  it('renders a button for each available finish', () => {
    render(<CardDetailView card={mockCard} />)
    expect(screen.getByText('nonfoil')).toBeTruthy()
    expect(screen.getByText('foil')).toBeTruthy()
  })

  it('defaults selected finish to first available finish', () => {
    render(<CardDetailView card={mockCard} />)
    expect(screen.getByTestId('price-charts').dataset.finish).toBe('nonfoil')
  })

  it('updates selected finish and passes it to PriceCharts when button clicked', () => {
    render(<CardDetailView card={mockCard} />)
    fireEvent.click(screen.getByText('foil'))
    expect(screen.getByTestId('price-charts').dataset.finish).toBe('foil')
  })

  it('falls back to nonfoil when available_finishes is empty', () => {
    render(<CardDetailView card={{ ...mockCard, available_finishes: [] }} />)
    expect(screen.getByText('nonfoil')).toBeTruthy()
  })

  it('falls back to nonfoil when available_finishes is undefined', () => {
    const { available_finishes: _, ...cardWithoutFinishes } = mockCard
    render(<CardDetailView card={cardWithoutFinishes as CardDetail} />)
    expect(screen.getByText('nonfoil')).toBeTruthy()
  })

  it('passes image_large as frontUrl to FlippableCardArt', () => {
    render(<CardDetailView card={mockCard} />)
    const art = screen.getByTestId('flippable-card-art')
    expect(art.dataset.front).toBe('https://example.com/front.jpg')
  })

  it('passes back_face_image_uri as backUrl for DFC cards', () => {
    render(
      <CardDetailView
        card={{
          ...mockCard,
          is_multifaced: true,
          back_face_image_uri: 'https://example.com/back.jpg',
        }}
      />
    )
    const art = screen.getByTestId('flippable-card-art')
    expect(art.dataset.back).toBe('https://example.com/back.jpg')
  })

  it('constructs Scryfall back URL for regular cards with card_back_id', () => {
    render(
      <CardDetailView
        card={{
          ...mockCard,
          is_multifaced: false,
          card_back_id: '0aeebaf5-8c7d-4636-9e82-8c27447861f7',
        }}
      />
    )
    const art = screen.getByTestId('flippable-card-art')
    expect(art.dataset.back).toContain('scryfall-card-backs')
    expect(art.dataset.back).toContain('0aeebaf5-8c7d-4636-9e82-8c27447861f7')
  })

  it('passes null backUrl when card has no card_back_id and is not multifaced', () => {
    render(
      <CardDetailView
        card={{ ...mockCard, is_multifaced: false, card_back_id: null }}
      />
    )
    const art = screen.getByTestId('flippable-card-art')
    expect(art.dataset.back).toBe('')
  })

  it('renders SetInfoBox', () => {
    render(<CardDetailView card={mockCard} />)
    expect(screen.getByTestId('set-info-box')).toBeTruthy()
  })

  it('renders LegalityGrid when legalities has entries', () => {
    render(<CardDetailView card={mockCard} />)
    const grid = screen.getByTestId('legality-grid')
    expect(grid).toBeTruthy()
    expect(grid.dataset.hasEntries).toBe('true')
  })

  it('does not render LegalityGrid when legalities is empty', () => {
    render(<CardDetailView card={{ ...mockCard, legalities: {} }} />)
    expect(screen.queryByTestId('legality-grid')).toBeNull()
  })

  it('does not render LegalityGrid when legalities is undefined', () => {
    const { legalities: _, ...cardNoLegalities } = mockCard
    render(<CardDetailView card={cardNoLegalities as CardDetail} />)
    expect(screen.queryByTestId('legality-grid')).toBeNull()
  })
})
