import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { SoldOrdersTable } from '../SoldOrdersTable'
import type { SoldOrder } from '../../soldOrders'

function makeOrder(overrides: Partial<SoldOrder> = {}): SoldOrder {
  return {
    orderId: 'ord-1',
    legacyOrderId: null,
    creationDate: '2026-05-09T00:00:00Z',
    orderFulfillmentStatus: 'NOT_STARTED',
    orderPaymentStatus: 'FULLY_PAID',
    buyerUsername: 'buyer_xyz',
    totalAmount: 42,
    currency: 'AUD',
    lineItems: [],
    local_status: null,
    displayStatus: 'sold',
    appCode: 'myapp',
    appName: 'My App',
    ...overrides,
  }
}

describe('SoldOrdersTable', () => {
  it('renders column headers', () => {
    render(<SoldOrdersTable orders={[]} isLoading={false} selectedId={undefined} onRowClick={vi.fn()} />)
    expect(screen.getByText('CARD')).toBeTruthy()
    expect(screen.getByText('PRICE')).toBeTruthy()
    expect(screen.getByText('BUYER')).toBeTruthy()
    expect(screen.getByText('STATUS')).toBeTruthy()
  })

  it('shows skeleton rows when loading', () => {
    const { container } = render(
      <SoldOrdersTable orders={[]} isLoading={true} selectedId={undefined} onRowClick={vi.fn()} />
    )
    expect(container.querySelectorAll('[data-testid="skeleton-row"]').length).toBeGreaterThan(0)
  })

  it('renders order row with buyer name', () => {
    render(
      <SoldOrdersTable orders={[makeOrder()]} isLoading={false} selectedId={undefined} onRowClick={vi.fn()} />
    )
    expect(screen.getByText('buyer_xyz')).toBeTruthy()
  })

  it('calls onRowClick with orderId when row clicked', () => {
    const onClick = vi.fn()
    render(
      <SoldOrdersTable orders={[makeOrder()]} isLoading={false} selectedId={undefined} onRowClick={onClick} />
    )
    fireEvent.click(screen.getByText('buyer_xyz').closest('tr')!)
    expect(onClick).toHaveBeenCalledWith('ord-1')
  })

  it('highlights the selected row', () => {
    const { container } = render(
      <SoldOrdersTable orders={[makeOrder()]} isLoading={false} selectedId="ord-1" onRowClick={vi.fn()} />
    )
    const row = container.querySelector('[data-selected="true"]')
    expect(row).toBeTruthy()
  })

  it('shows message icon for non-complete orders', () => {
    const { container } = render(
      <SoldOrdersTable orders={[makeOrder({ displayStatus: 'sold' })]} isLoading={false} selectedId={undefined} onRowClick={vi.fn()} />
    )
    expect(container.querySelector('[data-testid="msg-icon"]')).toBeTruthy()
  })

  it('hides message icon for complete orders', () => {
    const { container } = render(
      <SoldOrdersTable orders={[makeOrder({ displayStatus: 'complete' })]} isLoading={false} selectedId={undefined} onRowClick={vi.fn()} />
    )
    expect(container.querySelector('[data-testid="msg-icon"]')).toBeNull()
  })
})
