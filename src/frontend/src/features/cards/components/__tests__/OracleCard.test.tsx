// src/frontend/src/features/cards/components/__tests__/OracleCard.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { OracleCard } from '../OracleCard'

vi.mock('../../../../components/design-system/Pip', () => ({
  Pip: () => <span data-testid="pip" />,
}))

describe('OracleCard', () => {
  it('renders the card name', () => {
    render(<OracleCard cardName="Lightning Helix" />)
    expect(screen.getByText('Lightning Helix')).toBeTruthy()
  })

  it('renders type line when provided', () => {
    render(<OracleCard cardName="Lightning Helix" typeLine="Instant" />)
    expect(screen.getByText('Instant')).toBeTruthy()
  })

  it('omits type line when not provided', () => {
    render(<OracleCard cardName="Lightning Helix" />)
    expect(screen.queryByText('Instant')).toBeNull()
  })

  it('renders mana cost text', () => {
    render(<OracleCard cardName="Lightning Helix" manaCost="{R}{W}" />)
    expect(screen.getByText('{R}{W}')).toBeTruthy()
  })

  it('renders one pip per W/U/B/R/G symbol in mana cost', () => {
    render(<OracleCard cardName="Lightning Helix" manaCost="{R}{W}" />)
    expect(screen.getAllByTestId('pip').length).toBe(2)
  })

  it('renders oracle text', () => {
    render(
      <OracleCard
        cardName="Lightning Helix"
        oracleText="Lightning Helix deals 3 damage to any target and you gain 3 life."
      />
    )
    expect(screen.getByText(/deals 3 damage/)).toBeTruthy()
  })

  it('renders multi-paragraph oracle text split by newlines', () => {
    const { container } = render(
      <OracleCard cardName="Ragavan" oracleText={'First ability.\nDash {R}'} />
    )
    expect(container.querySelectorAll('p').length).toBe(2)
  })

  it('renders artist and collector number together with separator', () => {
    render(
      <OracleCard cardName="Lightning Helix" artist="Kev Walker" collectorNumber="372" />
    )
    expect(screen.getByText(/Illus. Kev Walker/)).toBeTruthy()
    expect(screen.getByText(/#372/)).toBeTruthy()
  })

  it('renders only artist when collector number is missing', () => {
    render(<OracleCard cardName="Lightning Helix" artist="Kev Walker" />)
    expect(screen.getByText(/Illus. Kev Walker/)).toBeTruthy()
    expect(screen.queryByText(/^#/)).toBeNull()
  })

  it('renders only collector number when artist is missing', () => {
    render(<OracleCard cardName="Lightning Helix" collectorNumber="372" />)
    expect(screen.getByText('#372')).toBeTruthy()
    expect(screen.queryByText(/Illus\./)).toBeNull()
  })

  it('omits footer when both artist and collector number are missing', () => {
    const { container } = render(<OracleCard cardName="Lightning Helix" />)
    expect(container.querySelectorAll('[class*="footer"]').length).toBe(0)
  })

  it('applies a rarity-specific class based on rarityName', () => {
    const { container, rerender } = render(
      <OracleCard cardName="X" rarityName="mythic" />
    )
    expect(container.firstChild?.className).toMatch(/rarityMythic/)

    rerender(<OracleCard cardName="X" rarityName="rare" />)
    expect(container.firstChild?.className).toMatch(/rarityRare/)

    rerender(<OracleCard cardName="X" rarityName="uncommon" />)
    expect(container.firstChild?.className).toMatch(/rarityUncommon/)

    rerender(<OracleCard cardName="X" rarityName="common" />)
    expect(container.firstChild?.className).toMatch(/rarityCommon/)
  })

  it('falls back to common rarity when rarityName is missing', () => {
    const { container } = render(<OracleCard cardName="X" />)
    expect(container.firstChild?.className).toMatch(/rarityCommon/)
  })
})
