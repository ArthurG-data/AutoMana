import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { SoldOrderDetailPanel } from '../SoldOrderDetailPanel'
import type { SoldOrder } from '../../soldOrders'

vi.mock('../../api', () => ({
  markOrderSent: vi.fn().mockResolvedValue(undefined),
  markOrderSentWithTracking: vi.fn().mockResolvedValue(undefined),
  updateOrderLocalStatus: vi.fn().mockResolvedValue(undefined),
}))

import { markOrderSent, updateOrderLocalStatus } from '../../api'

function makeOrder(overrides: Partial<SoldOrder> = {}): SoldOrder {
  return {
    orderId: 'ord-1',
    legacyOrderId: '12-34567',
    creationDate: '2026-05-09T00:00:00Z',
    orderFulfillmentStatus: 'NOT_STARTED',
    orderPaymentStatus: 'FULLY_PAID',
    buyerUsername: 'buyer_xyz',
    totalAmount: 42,
    currency: 'AUD',
    lineItems: [{ lineItemId: 'li-1', legacyItemId: null, title: 'Sheoldred', quantity: 1, lineItemFulfillmentStatus: null }],
    local_status: null,
    displayStatus: 'sold',
    appCode: 'myapp',
    appName: 'My App',
    itemSubtotal: 40,
    shippingCollected: 2,
    ebayFee: 4.2,
    netPayout: 37.8,
    ...overrides,
  }
}

describe('SoldOrderDetailPanel', () => {
  beforeEach(() => {
    vi.mocked(markOrderSent).mockClear()
    vi.mocked(updateOrderLocalStatus).mockClear()
  })

  it('renders order info', () => {
    render(<SoldOrderDetailPanel order={makeOrder()} onClose={vi.fn()} onStatusChange={vi.fn()} />)
    expect(screen.getByText('buyer_xyz')).toBeTruthy()
    expect(screen.getByText('$42.00 AUD')).toBeTruthy()
  })

  it('shows Mark as sent and Add tracking buttons for sold stage', () => {
    render(<SoldOrderDetailPanel order={makeOrder()} onClose={vi.fn()} onStatusChange={vi.fn()} />)
    expect(screen.getByText(/Mark as sent/i)).toBeTruthy()
    expect(screen.getByText(/Add tracking/i)).toBeTruthy()
  })

  it('calls markOrderSent and onStatusChange on mark sent click', async () => {
    const onStatusChange = vi.fn()
    render(<SoldOrderDetailPanel order={makeOrder()} onClose={vi.fn()} onStatusChange={onStatusChange} />)
    fireEvent.click(screen.getByText(/Mark as sent/i))
    await waitFor(() => expect(markOrderSent).toHaveBeenCalledWith('myapp', 'ord-1', ['li-1']))
    expect(onStatusChange).toHaveBeenCalledWith('ord-1', 'sent')
  })

  it('shows Mark in transit button for sent stage', () => {
    render(<SoldOrderDetailPanel order={makeOrder({ displayStatus: 'sent' })} onClose={vi.fn()} onStatusChange={vi.fn()} />)
    expect(screen.getByText(/Mark in transit/i)).toBeTruthy()
  })

  it('shows Mark complete button for in_transit stage', () => {
    render(<SoldOrderDetailPanel order={makeOrder({ displayStatus: 'in_transit' })} onClose={vi.fn()} onStatusChange={vi.fn()} />)
    expect(screen.getByText(/Mark complete/i)).toBeTruthy()
  })

  it('shows no action buttons for complete stage', () => {
    render(<SoldOrderDetailPanel order={makeOrder({ displayStatus: 'complete' })} onClose={vi.fn()} onStatusChange={vi.fn()} />)
    expect(screen.queryByText(/Mark/i)).toBeNull()
  })

  it('reveals tracking form when Add tracking clicked', () => {
    render(<SoldOrderDetailPanel order={makeOrder()} onClose={vi.fn()} onStatusChange={vi.fn()} />)
    fireEvent.click(screen.getByText(/Add tracking/i))
    expect(screen.getByPlaceholderText(/Tracking number/i)).toBeTruthy()
  })

  it('calls onClose when close button clicked', () => {
    const onClose = vi.fn()
    render(<SoldOrderDetailPanel order={makeOrder()} onClose={onClose} onStatusChange={vi.fn()} />)
    fireEvent.click(screen.getByLabelText('Close panel'))
    expect(onClose).toHaveBeenCalled()
  })
})
