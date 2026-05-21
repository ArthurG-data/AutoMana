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
  totalAmount: number | null      // pricingSummary.total (buyer paid)
  currency: string | null
  lineItems: SoldOrderLineItem[]
  local_status: string | null
  displayStatus: DisplayStatus
  appCode: string
  appName: string

  // Financial breakdown
  itemSubtotal: number | null     // pricingSummary.priceSubtotal (listed price × qty)
  shippingCollected: number | null // pricingSummary.deliveryCost (shipping buyer paid)
  ebayFee: number | null          // totalMarketplaceFee
  netPayout: number | null        // paymentSummary.totalDueSeller
}

/**
 * Derives the display lifecycle stage from eBay's fulfillment status and the
 * AutoMana-local override. Priority:
 * 1. eBay FULFILLED → complete (terminal, eBay always wins)
 * 2. local_status = in_transit → in_transit
 * 3. local_status = sent OR eBay IN_PROGRESS → sent
 * 4. Everything else → sold
 */
export function deriveDisplayStatus(
  ebayStatus: string | null | undefined,
  localStatus: string | null | undefined,
): DisplayStatus {
  if (ebayStatus === 'FULFILLED') return 'complete'
  if (localStatus === 'in_transit') return 'in_transit'
  if (localStatus === 'sent' || ebayStatus === 'IN_PROGRESS') return 'sent'
  return 'sold'
}

// Handles both eBay field names (value/currency) and Pydantic-serialized names (text/currencyID).
function extractAmount(obj: Record<string, unknown> | null | undefined): number | null {
  if (!obj) return null
  const raw = obj.value ?? obj.text
  return raw != null ? Number(raw) : null
}

function extractCurrency(obj: Record<string, unknown> | null | undefined): string | null {
  if (!obj) return null
  return (obj.currency ?? obj.currencyID as string | null) ?? null
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
  const paymentSummary = raw.paymentSummary as Record<string, unknown> | null
  const totalDueSeller = paymentSummary?.totalDueSeller as Record<string, unknown> | null
  const marketplaceFee = raw.totalMarketplaceFee as Record<string, unknown> | null

  return {
    orderId: (raw.orderId as string) ?? '',
    legacyOrderId: (raw.legacyOrderId as string | null) ?? null,
    creationDate: (raw.creationDate as string | null) ?? null,
    orderFulfillmentStatus: ebayStatus,
    orderPaymentStatus: (raw.orderPaymentStatus as string | null) ?? null,
    buyerUsername: (buyer?.username as string | null) ?? null,
    totalAmount: extractAmount(total),
    currency: extractCurrency(total),
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
    itemSubtotal: extractAmount(pricing?.priceSubtotal as Record<string, unknown> | null),
    shippingCollected: extractAmount(pricing?.deliveryCost as Record<string, unknown> | null),
    ebayFee: extractAmount(marketplaceFee),
    netPayout: extractAmount(totalDueSeller),
  }
}

export function mapLocalOrderToSoldOrder(
  raw: Record<string, unknown>,
  appCode: string,
  appName: string,
): SoldOrder {
  const priceCents = raw.total_price_cents as number | null
  const totalAmount = priceCents != null ? priceCents / 100 : null
  const localStatus = (raw.local_status as string | null) ?? null
  const lineItems = (raw.line_items as Record<string, unknown>[] | null) ?? []

  return {
    orderId: (raw.order_id as string) ?? '',
    legacyOrderId: null,
    creationDate: (raw.sold_at as string | null) ?? null,
    orderFulfillmentStatus: null,
    orderPaymentStatus: null,
    buyerUsername: (raw.buyer_username as string | null) ?? null,
    totalAmount,
    currency: (raw.currency as string | null) ?? null,
    lineItems: lineItems.map((li) => ({
      lineItemId: null,
      legacyItemId: (li.legacyItemId as string | null) ?? null,
      title: (li.title as string | null) ?? null,
      quantity: (li.quantity as number | null) ?? null,
      lineItemFulfillmentStatus: null,
    })),
    local_status: localStatus,
    displayStatus: deriveDisplayStatus(null, localStatus),
    appCode,
    appName,
    itemSubtotal: totalAmount,
    shippingCollected: null,
    ebayFee: null,
    netPayout: null,
  }
}
