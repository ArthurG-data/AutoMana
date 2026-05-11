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
vi.mock('../GameInfoCard', () => ({
  GameInfoCard: ({ cardName }: { cardName: string }) => (
    <div data-testid="game-info-card" data-name={cardName} />
  ),
}))
vi.mock('../MarketCard', () => ({
  MarketCard: ({
    selectedFinish,
    finishes,
    onFinishChange,
  }: {
    selectedFinish: string
    finishes: string[]
    onFinishChange: (f: string) => void
  }) => (
    <div data-testid="market-card" data-selected={selectedFinish}>
      {finishes.map((f) => (
        <button key={f} onClick={() => onFinishChange(f)}>{f}</button>
      ))}
    </div>
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
  it('renders GameInfoCard with the card name', () => {
    render(<CardDetailView card={mockCard} />)
    const gameInfo = screen.getByTestId('game-info-card')
    expect(gameInfo).toBeTruthy()
    expect(gameInfo.dataset.name).toBe('Sheoldred')
  })

  it('renders MarketCard with the available finishes', () => {
    render(<CardDetailView card={mockCard} />)
    const market = screen.getByTestId('market-card')
    expect(market).toBeTruthy()
    expect(screen.getByText('nonfoil')).toBeTruthy()
    expect(screen.getByText('foil')).toBeTruthy()
  })

  it('defaults selected finish to the first available finish', () => {
    render(<CardDetailView card={mockCard} />)
    expect(screen.getByTestId('market-card').dataset.selected).toBe('nonfoil')
    expect(screen.getByTestId('price-charts').dataset.finish).toBe('nonfoil')
  })

  it('updates the selected finish when MarketCard reports a change', () => {
    render(<CardDetailView card={mockCard} />)
    fireEvent.click(screen.getByText('foil'))
    expect(screen.getByTestId('market-card').dataset.selected).toBe('foil')
    expect(screen.getByTestId('price-charts').dataset.finish).toBe('foil')
  })

  it('falls back to nonfoil when available_finishes is empty', () => {
    render(<CardDetailView card={{ ...mockCard, available_finishes: [] }} />)
    expect(screen.getByTestId('market-card').dataset.selected).toBe('nonfoil')
  })

  it('falls back to nonfoil when available_finishes is undefined', () => {
    const { available_finishes: _, ...rest } = mockCard
    render(<CardDetailView card={rest as CardDetail} />)
    expect(screen.getByTestId('market-card').dataset.selected).toBe('nonfoil')
  })

  it('passes image_large as frontUrl to FlippableCardArt', () => {
    render(<CardDetailView card={mockCard} />)
    expect(screen.getByTestId('flippable-card-art').dataset.front).toBe('https://example.com/front.jpg')
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
    expect(screen.getByTestId('flippable-card-art').dataset.back).toBe('https://example.com/back.jpg')
  })

  it('constructs a Scryfall back URL for regular cards with card_back_id', () => {
    render(
      <CardDetailView
        card={{
          ...mockCard,
          is_multifaced: false,
          card_back_id: '0aeebaf5-8c7d-4636-9e82-8c27447861f7',
        }}
      />
    )
    const back = screen.getByTestId('flippable-card-art').dataset.back ?? ''
    expect(back).toContain('scryfall-card-backs')
    expect(back).toContain('0aeebaf5-8c7d-4636-9e82-8c27447861f7')
  })

  it('passes an empty backUrl when card has no card_back_id and is not multifaced', () => {
    render(
      <CardDetailView
        card={{ ...mockCard, is_multifaced: false, card_back_id: null }}
      />
    )
    expect(screen.getByTestId('flippable-card-art').dataset.back).toBe('')
  })

})
