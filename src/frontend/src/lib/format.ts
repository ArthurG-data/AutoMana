export function formatUSD(n: number | null | undefined): string {
  if (n == null) return 'N/A'
  return `$${n.toFixed(2)}`
}
