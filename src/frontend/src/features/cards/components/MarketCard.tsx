// src/frontend/src/features/cards/components/MarketCard.tsx
import { useQuery } from '@tanstack/react-query'
import { useUIStore } from '../../../store/ui'
import { formatPriceParts } from '../../../lib/format'
import { cardPriceHistoryQueryOptions } from '../api'
import styles from './MarketCard.module.css'

interface MarketCardProps {
  cardVersionId: string
  price?: number | null
  selectedFinish: string
  finishes: string[]
  onFinishChange: (finish: string) => void
  delta1d: number
  delta7d: number
  delta30d: number
}

interface Deltas {
  d1: number
  d7: number
  d30: number
}

interface SpotAndDeltas {
  current: number
  deltas: Deltas
}

/**
 * Derive the current spot price and its 1d/7d/30d percentage deltas from a single
 * dense daily series (oldest→newest, nulls for gaps). Spot is the latest non-null
 * point; deltas mirror the USD spark MV: (current - price_n_days_ago) / past * 100.
 * Deriving both from one series keeps the big number and its deltas mutually
 * consistent, and makes the spot equal the chart's right edge. Returns null when
 * there is no usable point.
 */
function spotAndDeltasFromSeries(series: (number | null)[]): SpotAndDeltas | null {
  let lastIdx = series.length - 1
  while (lastIdx >= 0 && series[lastIdx] == null) lastIdx--
  if (lastIdx < 0) return null
  const current = series[lastIdx] as number

  const pctBack = (days: number): number => {
    let i = lastIdx - days
    while (i >= 0 && series[i] == null) i--
    if (i < 0) return 0
    const past = series[i] as number
    if (!past) return 0
    return ((current - past) / past) * 100
  }

  return { current, deltas: { d1: pctBack(1), d7: pctBack(7), d30: pctBack(30) } }
}

export function MarketCard({
  cardVersionId,
  price,
  selectedFinish,
  finishes,
  onFinishChange,
  delta1d,
  delta7d,
  delta30d,
}: MarketCardProps) {
  const currency = useUIStore((s) => s.currency)
  const isUSD = currency === 'USD'

  // Non-USD: both spot AND deltas are derived from the SAME currency-scoped daily
  // history series (e.g. cardmarket/EUR for this finish — cardmarket is the only EUR
  // source, so the currency-scoped history IS the cardmarket series). Using one series
  // guarantees the price and its deltas agree and that the spot equals the chart's
  // most-recent point. A fixed 3m window ensures the 30d delta is always computable.
  // USD keeps the pre-aggregated props (zero network). NOTE: spot here is the latest
  // daily aggregate, which can lag the true latest snapshot by ~1 day — an accepted
  // v1 tradeoff (the dedicated /prices snapshot endpoint has a pre-existing bug).
  const { data: historyData } = useQuery({
    ...cardPriceHistoryQueryOptions(cardVersionId, '3m', selectedFinish, currency),
    enabled: !isUSD,
  })

  let displayPrice: number | null | undefined = price
  let deltas: Deltas | null = { d1: delta1d, d7: delta7d, d30: delta30d }

  if (!isUSD) {
    const spot = historyData
      ? spotAndDeltasFromSeries(historyData.price_history_list_avg ?? [])
      : null
    displayPrice = spot ? spot.current : null
    deltas = spot ? spot.deltas : null
  }

  const parts = formatPriceParts(displayPrice, currency)

  const deltaItems = deltas
    ? [
        { value: deltas.d1, label: '1d' },
        { value: deltas.d7, label: '7d' },
        { value: deltas.d30, label: '30d' },
      ]
    : []

  return (
    <aside className={styles.card}>
      <div className={styles.label}>
        MARKET PRICE · {selectedFinish}
      </div>

      <div className={styles.priceBlock}>
        {parts ? (
          <div className={styles.price}>
            {parts.symbol}{parts.whole}
            {parts.cents && <span className={styles.priceCents}>.{parts.cents}</span>}
          </div>
        ) : (
          <div className={styles.priceMissing}>N/A</div>
        )}

        <div className={styles.deltas}>
          {deltaItems.map(({ value, label }) => (
            <div key={label} className={value >= 0 ? styles.up : styles.down}>
              <span className={styles.arrow} aria-hidden="true">
                {value >= 0 ? '▲' : '▼'}
              </span>
              {Math.abs(value).toFixed(2)}%
              <span className={styles.period}>{label}</span>
            </div>
          ))}
        </div>
      </div>

      <div className={styles.finishSelector}>
        {finishes.map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => onFinishChange(f)}
            aria-pressed={f === selectedFinish}
            className={f === selectedFinish ? styles.finishActive : styles.finishBtn}
          >
            {f}
          </button>
        ))}
      </div>
    </aside>
  )
}
