// src/frontend/src/features/cards/components/__tests__/GameInfoCard.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { GameInfoCard } from '../GameInfoCard'

vi.mock('../../../../components/design-system/Pip', () => ({
  Pip: () => <span data-testid="pip" />,
}))
vi.mock('../LegalityGrid', () => ({
  LegalityGrid: ({ legalities }: { legalities: Record<string, string> }) => (
    <div data-testid="legality-grid" data-count={Object.keys(legalities).length} />
  ),
}))

const BASE = {
  cardName: 'Lightning Helix',
  setCode: 'rvr',
  setName: 'Ravnica Remastered',
  rarityName: 'uncommon',
}

describe('GameInfoCard', () => {
  it('renders the card name', () => {
    render(<GameInfoCard {...BASE} />)
    expect(screen.getByText('Lightning Helix')).toBeTruthy()
  })

  it('renders set name and uppercased set code', () => {
    render(<GameInfoCard {...BASE} />)
    expect(screen.getByText('Ravnica Remastered')).toBeTruthy()
    expect(screen.getByText('(RVR)')).toBeTruthy()
  })

  it('renders Keyrune icon with lowercased set_code and rarity classes', () => {
    const { container } = render(<GameInfoCard {...BASE} setCode="RVR" rarityName="MYTHIC" />)
    const icon = container.querySelector('i')
    expect(icon?.className).toContain('ss-rvr')
    expect(icon?.className).toContain('ss-mythic')
  })

  it('renders capitalized rarity label', () => {
    render(<GameInfoCard {...BASE} />)
    expect(screen.getByText('Uncommon')).toBeTruthy()
  })

  it('renders collector number with # prefix when provided', () => {
    render(<GameInfoCard {...BASE} collectorNumber="372" />)
    expect(screen.getByText('#372')).toBeTruthy()
  })

  it('omits collector number section when not provided', () => {
    render(<GameInfoCard {...BASE} />)
    expect(screen.queryByText(/^#/)).toBeNull()
  })

  it('renders one badge per promo type', () => {
    render(<GameInfoCard {...BASE} promoTypes={['boosterfun', 'showcase']} />)
    expect(screen.getByText(/boosterfun/)).toBeTruthy()
    expect(screen.getByText(/showcase/)).toBeTruthy()
  })

  it('renders mana cost text when provided', () => {
    render(<GameInfoCard {...BASE} manaCost="{R}{W}" />)
    expect(screen.getByText('{R}{W}')).toBeTruthy()
  })

  it('renders one pip per colored symbol in mana cost', () => {
    render(<GameInfoCard {...BASE} manaCost="{R}{W}" />)
    expect(screen.getAllByTestId('pip').length).toBe(2)
  })

  it('renders type line when provided', () => {
    render(<GameInfoCard {...BASE} typeLine="Instant" />)
    expect(screen.getByText('Instant')).toBeTruthy()
  })

  it('renders oracle text as separate paragraphs split on newlines', () => {
    const { container } = render(
      <GameInfoCard {...BASE} oracleText={'First line.\nSecond line.'} />
    )
    expect(container.querySelectorAll('p').length).toBe(2)
  })

  it('renders artist in footer when provided', () => {
    render(<GameInfoCard {...BASE} artist="Kev Walker" />)
    expect(screen.getByText(/Illus. Kev Walker/)).toBeTruthy()
  })

  it('omits footer when artist missing', () => {
    const { container } = render(<GameInfoCard {...BASE} />)
    expect(container.querySelectorAll('footer').length).toBe(0)
  })

  it('renders the legality grid when legalities has entries', () => {
    render(<GameInfoCard {...BASE} legalities={{ modern: 'legal', standard: 'not_legal' }} />)
    const grid = screen.getByTestId('legality-grid')
    expect(grid).toBeTruthy()
    expect(grid.dataset.count).toBe('2')
    expect(screen.getByText('Legalities')).toBeTruthy()
  })

  it('does not render the legality grid when legalities is empty', () => {
    render(<GameInfoCard {...BASE} legalities={{}} />)
    expect(screen.queryByTestId('legality-grid')).toBeNull()
    expect(screen.queryByText('Legalities')).toBeNull()
  })

  it('does not render the legality grid when legalities is undefined', () => {
    render(<GameInfoCard {...BASE} />)
    expect(screen.queryByTestId('legality-grid')).toBeNull()
  })

  it('applies rarity-specific class on the outer card', () => {
    const { container, rerender } = render(<GameInfoCard {...BASE} rarityName="mythic" />)
    expect(container.firstChild?.className).toMatch(/rarityMythic/)

    rerender(<GameInfoCard {...BASE} rarityName="rare" />)
    expect(container.firstChild?.className).toMatch(/rarityRare/)

    rerender(<GameInfoCard {...BASE} rarityName="common" />)
    expect(container.firstChild?.className).toMatch(/rarityCommon/)
  })
})
