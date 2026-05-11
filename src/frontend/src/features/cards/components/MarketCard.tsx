// src/frontend/src/features/cards/components/MarketCard.tsx
import styles from './MarketCard.module.css'

interface MarketCardProps {
  price?: number | null
  selectedFinish: string
  finishes: string[]
  onFinishChange: (finish: string) => void
  delta1d: number
  delta7d: number
  delta30d: number
}

function formatPrice(price: number) {
  const whole = Math.floor(price)
  const cents = (price % 1).toFixed(2).slice(2)
  return { whole, cents }
}

export function MarketCard({
  price,
  selectedFinish,
  finishes,
  onFinishChange,
  delta1d,
  delta7d,
  delta30d,
}: MarketCardProps) {
  const deltas = [
    { value: delta1d, label: '1d' },
    { value: delta7d, label: '7d' },
    { value: delta30d, label: '30d' },
  ]

  return (
    <aside className={styles.card}>
      <div className={styles.label}>
        MARKET PRICE · {selectedFinish}
      </div>

      <div className={styles.priceBlock}>
        {price != null ? (
          <div className={styles.price}>
            ${formatPrice(price).whole}
            <span className={styles.priceCents}>.{formatPrice(price).cents}</span>
          </div>
        ) : (
          <div className={styles.priceMissing}>N/A</div>
        )}

        <div className={styles.deltas}>
          {deltas.map(({ value, label }) => (
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
