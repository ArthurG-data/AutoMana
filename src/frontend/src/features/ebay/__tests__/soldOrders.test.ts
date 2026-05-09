// src/frontend/src/features/ebay/__tests__/soldOrders.test.ts
import { describe, it, expect } from 'vitest'
import { deriveDisplayStatus } from '../soldOrders'

describe('deriveDisplayStatus', () => {
  it('returns complete when eBay status is FULFILLED regardless of local', () => {
    expect(deriveDisplayStatus('FULFILLED', 'in_transit')).toBe('complete')
    expect(deriveDisplayStatus('FULFILLED', null)).toBe('complete')
  })

  it('returns in_transit when local_status is in_transit and eBay is not FULFILLED', () => {
    expect(deriveDisplayStatus('NOT_STARTED', 'in_transit')).toBe('in_transit')
    expect(deriveDisplayStatus('IN_PROGRESS', 'in_transit')).toBe('in_transit')
  })

  it('returns sold when eBay status is NOT_STARTED and no in_transit override', () => {
    expect(deriveDisplayStatus('NOT_STARTED', null)).toBe('sold')
    expect(deriveDisplayStatus('NOT_STARTED', 'sent')).toBe('sold')
  })

  it('returns sent when eBay status is IN_PROGRESS and not in_transit', () => {
    expect(deriveDisplayStatus('IN_PROGRESS', null)).toBe('sent')
    expect(deriveDisplayStatus('IN_PROGRESS', 'sent')).toBe('sent')
  })

  it('returns sold for unknown eBay status', () => {
    expect(deriveDisplayStatus(null, null)).toBe('sold')
    expect(deriveDisplayStatus(undefined, null)).toBe('sold')
  })
})
