// src/frontend/src/features/ebay/soldOrders.ts

export type DisplayStatus = 'sold' | 'sent' | 'in_transit' | 'complete'

export interface SoldOrderLineItem {
  lineItemId: string | null
  legacyItemId: string | null
  title: string | null
  quantity: number | null
  lineItemFulfillmentStatus: string | null
}

export interface SoldOrder {
  orderId: string
  legacyOrderId: string | null
  creationDate: string | null
  orderFulfillmentStatus: string | null
  orderPaymentStatus: string | null
  buyerUsername: string | null
  totalAmount: number | null
  currency: string | null
  lineItems: SoldOrderLineItem[]
  local_status: string | null
  displayStatus: DisplayStatus
  appCode: string
  appName: string
}

/**
 * Derives the display lifecycle stage from eBay's fulfillment status and the
 * AutoMana-local override. Priority:
 * 1. eBay FULFILLED → complete (terminal, eBay always wins)
 * 2. local_status = in_transit → in_transit
 * 3. eBay IN_PROGRESS → sent
 * 4. Everything else → sold
 */
export function deriveDisplayStatus(
  ebayStatus: string | null | undefined,
  localStatus: string | null | undefined,
): DisplayStatus {
  if (ebayStatus === 'FULFILLED') return 'complete'
  if (localStatus === 'in_transit') return 'in_transit'
  if (ebayStatus === 'IN_PROGRESS') return 'sent'
  return 'sold'
}

export function mapRawToSoldOrder(
  raw: Record<string, unknown>,
  appCode: string,
  appName: string,
): SoldOrder {
  const buyer = raw.buyer as Record<string, unknown> | null
  const pricing = raw.pricingSummary as Record<string, unknown> | null
  const total = pricing?.total as Record<string, unknown> | null
  const lineItems = (raw.lineItems as Record<string, unknown>[] | null) ?? []
  const ebayStatus = (raw.orderFulfillmentStatus as string | null) ?? null
  const localStatus = (raw.local_status as string | null) ?? null

  return {
    orderId: (raw.orderId as string) ?? '',
    legacyOrderId: (raw.legacyOrderId as string | null) ?? null,
    creationDate: (raw.creationDate as string | null) ?? null,
    orderFulfillmentStatus: ebayStatus,
    orderPaymentStatus: (raw.orderPaymentStatus as string | null) ?? null,
    buyerUsername: (buyer?.username as string | null) ?? null,
    totalAmount: total?.value != null ? Number(total.value) : null,
    currency: (total?.currency as string | null) ?? null,
    lineItems: lineItems.map((li) => ({
      lineItemId: (li.lineItemId as string | null) ?? null,
      legacyItemId: (li.legacyItemId as string | null) ?? null,
      title: (li.title as string | null) ?? null,
      quantity: (li.quantity as number | null) ?? null,
      lineItemFulfillmentStatus: (li.lineItemFulfillmentStatus as string | null) ?? null,
    })),
    local_status: localStatus,
    displayStatus: deriveDisplayStatus(ebayStatus, localStatus),
    appCode,
    appName,
  }
}
