import { describe, it, expect } from 'vitest'
import { formatPrice, formatPriceParts, formatUSD } from '../format'

describe('formatPrice', () => {
  it('formats USD with two decimals and $ symbol', () => {
    expect(formatPrice(12.5, 'USD')).toBe('$12.50')
  })

  it('formats EUR with two decimals and € symbol', () => {
    expect(formatPrice(12.5, 'EUR')).toBe('€12.50')
  })

  it('formats JPY with no decimals and thousands grouping', () => {
    // Yen-glyph codepoint varies across ICU builds, so assert behavior not the exact symbol.
    const out = formatPrice(1234, 'JPY')
    expect(out).toContain('1,234')
    expect(out).not.toContain('.')
  })

  it('returns N/A for null/undefined', () => {
    expect(formatPrice(null)).toBe('N/A')
    expect(formatPrice(undefined)).toBe('N/A')
  })

  it('defaults to USD', () => {
    expect(formatPrice(5)).toBe('$5.00')
  })
})

describe('formatPriceParts', () => {
  it('splits USD into symbol/whole/cents', () => {
    expect(formatPriceParts(12.5, 'USD')).toEqual({ symbol: '$', whole: '12', cents: '50' })
  })

  it('splits EUR into symbol/whole/cents', () => {
    expect(formatPriceParts(8.99, 'EUR')).toEqual({ symbol: '€', whole: '8', cents: '99' })
  })

  it('yields empty cents for JPY (0 decimals) and groups thousands', () => {
    const parts = formatPriceParts(1234, 'JPY')
    expect(parts?.whole).toBe('1,234')
    expect(parts?.cents).toBe('')
    expect(parts?.symbol).toBeTruthy()
  })

  it('returns null for null/undefined', () => {
    expect(formatPriceParts(null)).toBeNull()
    expect(formatPriceParts(undefined)).toBeNull()
  })
})

describe('formatUSD (legacy)', () => {
  it('formats with $ and two decimals', () => {
    expect(formatUSD(3)).toBe('$3.00')
  })

  it('returns N/A for nullish', () => {
    expect(formatUSD(null)).toBe('N/A')
  })
})
