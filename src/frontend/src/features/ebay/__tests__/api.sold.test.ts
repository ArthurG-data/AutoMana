// src/frontend/src/features/ebay/__tests__/api.sold.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fetchSoldOrders, markOrderSent, markOrderSentWithTracking, updateOrderLocalStatus } from '../api'

vi.mock('../../../lib/apiClient', () => ({
  apiClient: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(msg: string, public status: number) { super(msg) }
  },
}))

import { apiClient } from '../../../lib/apiClient'
const mockApiClient = vi.mocked(apiClient)

beforeEach(() => { mockApiClient.mockReset() })

describe('fetchSoldOrders', () => {
  it('maps raw orders to SoldOrder array', async () => {
    mockApiClient.mockResolvedValue({
      data: [
        {
          orderId: 'ord-1',
          orderFulfillmentStatus: 'NOT_STARTED',
          orderPaymentStatus: 'FULLY_PAID',
          creationDate: '2026-05-09T00:00:00Z',
          buyer: { username: 'buyer_xyz', taxAddress: null, buyerRegistrationAddress: null },
          pricingSummary: { total: { value: '42.00', currency: 'AUD' } },
          lineItems: [],
          local_status: null,
        },
      ],
      pagination: { has_next: false },
    })

    const result = await fetchSoldOrders('myapp', 25, 0)
    expect(result.orders).toHaveLength(1)
    expect(result.orders[0].orderId).toBe('ord-1')
    expect(result.orders[0].displayStatus).toBe('sold')
    expect(result.orders[0].buyerUsername).toBe('buyer_xyz')
    expect(result.orders[0].totalAmount).toBe(42)
    expect(result.hasMore).toBe(false)
  })
})

describe('markOrderSent', () => {
  it('posts to the fulfill endpoint without tracking', async () => {
    mockApiClient.mockResolvedValue({ data: { success: true } })
    await markOrderSent('myapp', 'ord-1', ['line-1'])
    expect(mockApiClient).toHaveBeenCalledWith(
      '/integrations/ebay/listing/orders/ord-1/fulfill',
      expect.objectContaining({ method: 'POST' }),
    )
    const body = JSON.parse(mockApiClient.mock.calls[0][1].body)
    expect(body.app_code).toBe('myapp')
    expect(body.line_item_ids).toEqual(['line-1'])
    expect(body.tracking_number).toBeUndefined()
  })
})

describe('markOrderSentWithTracking', () => {
  it('posts with tracking fields', async () => {
    mockApiClient.mockResolvedValue({ data: { success: true } })
    await markOrderSentWithTracking('myapp', 'ord-1', ['line-1'], 'AusPost', 'TRK999')
    const body = JSON.parse(mockApiClient.mock.calls[0][1].body)
    expect(body.tracking_number).toBe('TRK999')
    expect(body.carrier_code).toBe('AusPost')
  })
})

describe('updateOrderLocalStatus', () => {
  it('patches the status endpoint', async () => {
    mockApiClient.mockResolvedValue({ data: { local_status: 'in_transit' } })
    await updateOrderLocalStatus('myapp', 'ord-1', 'in_transit')
    expect(mockApiClient).toHaveBeenCalledWith(
      '/integrations/ebay/listing/orders/ord-1/status',
      expect.objectContaining({ method: 'PATCH' }),
    )
    const body = JSON.parse(mockApiClient.mock.calls[0][1].body)
    expect(body.local_status).toBe('in_transit')
  })
})
