import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createListing, updateListing } from '../api'

vi.mock('../../../lib/apiClient', () => ({
  apiClient: vi.fn(),
}))

import { apiClient } from '../../../lib/apiClient'
const mockApiClient = vi.mocked(apiClient)

beforeEach(() => {
  mockApiClient.mockReset()
  // crypto.randomUUID is available in jsdom via vitest
})

describe('createListing', () => {
  it('POSTs to the correct URL with Idempotency-Key header', async () => {
    mockApiClient.mockResolvedValueOnce(undefined)

    await createListing('automana_au', {
      title: 'Ragavan NM MTG',
      startPrice: { currency: 'AUD', value: 12.5 },
      quantity: 1,
      conditionID: 3000,
    })

    expect(mockApiClient).toHaveBeenCalledOnce()
    const [url, opts] = mockApiClient.mock.calls[0] as [string, RequestInit & { headers: Record<string, string> }]
    expect(url).toBe('/integrations/ebay/listing/?app_code=automana_au')
    expect(opts.method).toBe('POST')
    expect(opts.headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/)
    const body = JSON.parse(opts.body as string)
    expect(body.title).toBe('Ragavan NM MTG')
    expect(body.startPrice).toEqual({ currency: 'AUD', value: 12.5 })
    expect(body.quantity).toBe(1)
    expect(body.conditionID).toBe(3000)
  })

  it('includes description when provided', async () => {
    mockApiClient.mockResolvedValueOnce(undefined)

    await createListing('automana_au', {
      title: 'Test',
      startPrice: { currency: 'AUD', value: 5 },
      quantity: 2,
      conditionID: 4000,
      description: 'Lightly played card',
    })

    const [, opts] = mockApiClient.mock.calls[0] as [string, RequestInit]
    const body = JSON.parse(opts.body as string)
    expect(body.description).toBe('Lightly played card')
  })
})

describe('updateListing', () => {
  it('PUTs to the correct URL with itemID in the body', async () => {
    mockApiClient.mockResolvedValueOnce(undefined)

    await updateListing('automana_au', '123456789', {
      title: 'Sheoldred NM MTG',
      startPrice: { currency: 'AUD', value: 55 },
      quantity: 1,
      conditionID: 3000,
    })

    expect(mockApiClient).toHaveBeenCalledOnce()
    const [url, opts] = mockApiClient.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/integrations/ebay/listing/123456789?app_code=automana_au')
    expect(opts.method).toBe('PUT')
    const body = JSON.parse(opts.body as string)
    expect(body.itemID).toBe('123456789')
    expect(body.title).toBe('Sheoldred NM MTG')
    expect(body.startPrice).toEqual({ currency: 'AUD', value: 55 })
  })
})
