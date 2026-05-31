import type { CurrencyCode } from '../store/ui'

/** Format a number as a localized currency string, e.g. $12.34, €12.34, ¥1234. */
export function formatPrice(
  n: number | null | undefined,
  currency: CurrencyCode = 'USD'
): string {
  if (n == null) return 'N/A'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(n)
}

/**
 * Split a price into display parts for layouts that style the symbol/whole/cents
 * separately (e.g. MarketCard). Currency-aware: respects each currency's decimal
 * count (USD/EUR = 2, JPY = 0) via Intl, so JPY yields an empty `cents`.
 */
export function formatPriceParts(
  n: number | null | undefined,
  currency: CurrencyCode = 'USD'
): { symbol: string; whole: string; cents: string } | null {
  if (n == null) return null
  const parts = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
  }).formatToParts(n)
  const symbol = parts.find((p) => p.type === 'currency')?.value ?? ''
  const whole = parts
    .filter((p) => p.type === 'integer' || p.type === 'group')
    .map((p) => p.value)
    .join('')
  const cents = parts.find((p) => p.type === 'fraction')?.value ?? ''
  return { symbol, whole, cents }
}

/** Legacy USD-only helper retained for call sites outside the currency-toggle scope. */
export function formatUSD(n: number | null | undefined): string {
  if (n == null) return 'N/A'
  return `$${n.toFixed(2)}`
}
