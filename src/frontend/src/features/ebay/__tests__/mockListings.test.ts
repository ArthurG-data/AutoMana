import { describe, it, expect } from 'vitest'
import { parseCardTitle } from '../mockListings'

describe('parseCardTitle', () => {
  it('strips set code, collector number, condition, MTG suffix', () => {
    const { cardName, setInfo } = parseCardTitle('Ragavan, Nimble Pilferer MH2 #138 NM MTG')
    expect(cardName).toBe('Ragavan, Nimble Pilferer')
    expect(setInfo).toBe('MH2 #138')
  })

  it('strips FOIL suffix', () => {
    const { cardName, setInfo } = parseCardTitle('Mox Diamond STH NM FOIL MTG')
    expect(cardName).toBe('Mox Diamond')
    expect(setInfo).toBe('STH')
  })

  it('strips 3-letter set code without collector number', () => {
    const { cardName, setInfo } = parseCardTitle('Force of Will ALL LP MTG')
    expect(cardName).toBe('Force of Will')
    expect(setInfo).toBe('ALL')
  })

  it('handles set code with digits (e.g. MH2)', () => {
    const { cardName, setInfo } = parseCardTitle('Sheoldred, the Apocalypse MH2 NM MTG')
    expect(cardName).toBe('Sheoldred, the Apocalypse')
    expect(setInfo).toBe('MH2')
  })

  it('falls back to full title when no suffix tokens match', () => {
    const { cardName, setInfo } = parseCardTitle('Some weird title')
    expect(cardName).toBe('Some weird title')
    expect(setInfo).toBe('')
  })

  it('does not strip mixed-case words like card names', () => {
    const { cardName } = parseCardTitle('Wrenn and Six MH1 NM MTG')
    expect(cardName).toBe('Wrenn and Six')
  })
})
