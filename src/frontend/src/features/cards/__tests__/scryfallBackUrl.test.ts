import { describe, it, expect } from 'vitest'
import { buildScryfallBackUrl } from '../utils/scryfallBackUrl'

const STANDARD_BACK_ID = '0aeebaf5-8c7d-4636-9e82-8c27447861f7'

describe('buildScryfallBackUrl', () => {
  it('builds the correct CDN URL from the standard card back ID', () => {
    const url = buildScryfallBackUrl(STANDARD_BACK_ID)
    expect(url).toBe(
      'https://c2.scryfall.com/file/scryfall-card-backs/large/0a/ee/0aeebaf5-8c7d-4636-9e82-8c27447861f7.jpg'
    )
  })

  it('uses the first two chars as the first path segment', () => {
    const url = buildScryfallBackUrl('abcdef00-0000-0000-0000-000000000000')
    expect(url).toContain('/large/ab/cd/')
  })

  it('uses chars 2–4 as the second path segment', () => {
    const url = buildScryfallBackUrl('aabbcc00-0000-0000-0000-000000000000')
    expect(url).toContain('/large/aa/bb/')
  })

  it('appends the full UUID and .jpg extension', () => {
    const url = buildScryfallBackUrl(STANDARD_BACK_ID)
    expect(url).toMatch(/0aeebaf5-8c7d-4636-9e82-8c27447861f7\.jpg$/)
  })
})
