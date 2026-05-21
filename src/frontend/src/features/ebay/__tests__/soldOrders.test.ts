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

  it('returns sold when eBay status is NOT_STARTED and no local override', () => {
    expect(deriveDisplayStatus('NOT_STARTED', null)).toBe('sold')
  })

  it('returns sent when local_status is sent and eBay has not caught up yet', () => {
    expect(deriveDisplayStatus('NOT_STARTED', 'sent')).toBe('sent')
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

import { mapLocalOrderToSoldOrder } from '../soldOrders'

const BASE_RAW = {
  order_id: 'ord-123',
  local_status: 'sold',
  buyer_username: 'buyer_oz',
  sold_at: '2025-01-01T00:00:00Z',
  currency: 'AUD',
  total_price_cents: 1250,
  line_items: [
    { legacyItemId: 'item-1', title: 'Lightning Bolt', quantity: 2 },
  ],
}

describe('mapLocalOrderToSoldOrder', () => {
  it('maps core fields', () => {
    const order = mapLocalOrderToSoldOrder(BASE_RAW, 'myapp', '')
    expect(order.orderId).toBe('ord-123')
    expect(order.buyerUsername).toBe('buyer_oz')
    expect(order.totalAmount).toBe(12.5)
    expect(order.currency).toBe('AUD')
    expect(order.creationDate).toBe('2025-01-01T00:00:00Z')
    expect(order.appCode).toBe('myapp')
  })

  it('maps line items', () => {
    const order = mapLocalOrderToSoldOrder(BASE_RAW, 'myapp', '')
    expect(order.lineItems).toHaveLength(1)
    expect(order.lineItems[0].legacyItemId).toBe('item-1')
    expect(order.lineItems[0].title).toBe('Lightning Bolt')
    expect(order.lineItems[0].quantity).toBe(2)
    expect(order.lineItems[0].lineItemId).toBeNull()
    expect(order.lineItems[0].lineItemFulfillmentStatus).toBeNull()
  })

  it('sets fee and payout fields to null', () => {
    const order = mapLocalOrderToSoldOrder(BASE_RAW, 'myapp', '')
    expect(order.ebayFee).toBeNull()
    expect(order.netPayout).toBeNull()
    expect(order.shippingCollected).toBeNull()
    expect(order.orderFulfillmentStatus).toBeNull()
    expect(order.legacyOrderId).toBeNull()
  })

  it('derives displayStatus from local_status only', () => {
    const inTransit = mapLocalOrderToSoldOrder({ ...BASE_RAW, local_status: 'in_transit' }, 'myapp', '')
    expect(inTransit.displayStatus).toBe('in_transit')
    const noStatus = mapLocalOrderToSoldOrder({ ...BASE_RAW, local_status: null }, 'myapp', '')
    expect(noStatus.displayStatus).toBe('sold')
    const sent = mapLocalOrderToSoldOrder({ ...BASE_RAW, local_status: 'sent' }, 'myapp', '')
    expect(sent.displayStatus).toBe('sent')
  })

  it('handles null price gracefully', () => {
    const order = mapLocalOrderToSoldOrder({ ...BASE_RAW, total_price_cents: null }, 'myapp', '')
    expect(order.totalAmount).toBeNull()
    expect(order.itemSubtotal).toBeNull()
  })

  it('handles missing line_items gracefully', () => {
    const order = mapLocalOrderToSoldOrder({ ...BASE_RAW, line_items: null }, 'myapp', '')
    expect(order.lineItems).toEqual([])
  })
})
