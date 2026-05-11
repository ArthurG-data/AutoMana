// src/frontend/src/features/cards/components/__tests__/SetInfoBox.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SetInfoBox } from '../SetInfoBox'

describe('SetInfoBox', () => {
  it('renders set name', () => {
    render(
      <SetInfoBox setCode="mom" setName="March of the Machine" rarityName="rare" />
    )
    expect(screen.getByText('March of the Machine')).toBeTruthy()
  })

  it('renders set code in parentheses, uppercased', () => {
    render(
      <SetInfoBox setCode="mom" setName="March of the Machine" rarityName="rare" />
    )
    expect(screen.getByText('(MOM)')).toBeTruthy()
  })

  it('renders Keyrune icon with lowercase set_code and rarity classes', () => {
    const { container } = render(
      <SetInfoBox setCode="MOM" setName="March of the Machine" rarityName="mythic" />
    )
    const icon = container.querySelector('i')
    expect(icon?.className).toContain('ss-mom')
    expect(icon?.className).toContain('ss-mythic')
  })

  it('renders capitalized rarity label', () => {
    render(
      <SetInfoBox setCode="mom" setName="March of the Machine" rarityName="uncommon" />
    )
    expect(screen.getByText('Uncommon')).toBeTruthy()
  })

  it('renders collector number with # prefix when provided', () => {
    render(
      <SetInfoBox setCode="mom" setName="March of the Machine" rarityName="rare" collectorNumber="245" />
    )
    expect(screen.getByText('#245')).toBeTruthy()
  })

  it('omits collector number section when not provided', () => {
    const { queryByText } = render(
      <SetInfoBox setCode="mom" setName="March of the Machine" rarityName="rare" />
    )
    expect(queryByText(/^#/)).toBeNull()
  })

  it('renders one badge per promo type', () => {
    render(
      <SetInfoBox
        setCode="mom"
        setName="March of the Machine"
        rarityName="rare"
        promoTypes={['Showcase', 'Etched Foil']}
      />
    )
    expect(screen.getByText(/Showcase/)).toBeTruthy()
    expect(screen.getByText(/Etched Foil/)).toBeTruthy()
  })

  it('renders no badges when promoTypes is empty', () => {
    const { container } = render(
      <SetInfoBox setCode="mom" setName="March of the Machine" rarityName="rare" promoTypes={[]} />
    )
    expect(container.querySelectorAll('[class*="badge"]').length).toBe(0)
  })
})
