// src/frontend/src/features/cards/components/__tests__/GameInfoCard.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { GameInfoCard } from '../GameInfoCard'

const navigateSpy = vi.fn()
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateSpy,
}))
vi.mock('../../../../components/design-system/ManaSymbol', () => ({
  ManaSymbol: ({ symbol }: { symbol: string }) => (
    <span data-testid="mana-symbol" data-symbol={symbol} />
  ),
  renderSymbolsInText: (text: string) => [
    <span key="rendered" data-testid="oracle-line">{text}</span>,
  ],
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

  it('renders one badge per promo type with formatted labels', () => {
    render(<GameInfoCard {...BASE} promoTypes={['boosterfun', 'showcase']} />)
    expect(screen.getByText(/Booster Fun/)).toBeTruthy()
    expect(screen.getByText(/Showcase/)).toBeTruthy()
  })

  it('falls back to capitalized raw value for unknown promo types', () => {
    render(<GameInfoCard {...BASE} promoTypes={['weirdthing']} />)
    expect(screen.getByText(/Weirdthing/)).toBeTruthy()
  })

  it('renders one ManaSymbol per token in the mana cost', () => {
    render(<GameInfoCard {...BASE} manaCost="{2}{R}{W}" />)
    const symbols = screen.getAllByTestId('mana-symbol')
    expect(symbols.length).toBe(3)
    expect(symbols.map((s) => s.dataset.symbol)).toEqual(['2', 'R', 'W'])
  })

  it('renders hybrid mana tokens correctly (W/U)', () => {
    render(<GameInfoCard {...BASE} manaCost="{W/U}{B/G}" />)
    const symbols = screen.getAllByTestId('mana-symbol')
    expect(symbols.map((s) => s.dataset.symbol)).toEqual(['W/U', 'B/G'])
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
    expect(screen.getByText('Kev Walker')).toBeTruthy()
  })

  it('clicking the artist name navigates to /search filtered by artist', () => {
    navigateSpy.mockClear()
    render(<GameInfoCard {...BASE} artist="Kev Walker" />)
    fireEvent.click(screen.getByText('Kev Walker'))
    expect(navigateSpy).toHaveBeenCalledWith({ to: '/search', search: { artist: 'Kev Walker' } })
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

  it('clicking the set name navigates to /search filtered by that set', () => {
    navigateSpy.mockClear()
    render(<GameInfoCard {...BASE} />)
    fireEvent.click(screen.getByText('Ravnica Remastered'))
    expect(navigateSpy).toHaveBeenCalledWith({ to: '/search', search: { set: 'rvr' } })
  })

  it('clicking the set icon button navigates to /search filtered by that set', () => {
    navigateSpy.mockClear()
    const { container } = render(<GameInfoCard {...BASE} />)
    const iconBtn = container.querySelector('button[aria-label*="Search"]') as HTMLButtonElement
    fireEvent.click(iconBtn)
    expect(navigateSpy).toHaveBeenCalledWith({ to: '/search', search: { set: 'rvr' } })
  })

  it('does not navigate when setCode is undefined', () => {
    navigateSpy.mockClear()
    render(<GameInfoCard cardName="Mystery" />)
    const allButtons = document.querySelectorAll('button')
    allButtons.forEach((b) => fireEvent.click(b))
    expect(navigateSpy).not.toHaveBeenCalled()
  })
})
