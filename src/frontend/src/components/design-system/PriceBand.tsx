// src/frontend/src/components/design-system/PriceBand.tsx
import styles from './PriceBand.module.css'

interface PriceBandProps {
  low: number
  p25: number
  market: number
  p75: number
  high: number
  listed?: number
}

export function PriceBand({ low, p25, market, p75, high, listed }: PriceBandProps) {
  const total = high - low || 1
  const pct = (v: number) => ((v - low) / total) * 100

  return (
    <div className={styles.root}>
      <div className={styles.track} />
      <div
        className={styles.band}
        style={{ left: `${pct(p25)}%`, right: `${100 - pct(p75)}%` }}
      />
      <div className={styles.median} style={{ left: `${pct(market)}%` }} />
      <div className={styles.extreme} style={{ left: `${pct(low)}%` }}>
        <span className={styles.extremeLabel}>${low}</span>
      </div>
      <div className={styles.extreme} style={{ left: `${pct(high)}%` }}>
        <span className={styles.extremeLabel}>${high}</span>
      </div>
      {listed != null && (
        <>
          <div
            className={styles.listedDot}
            style={{ left: `calc(${pct(listed)}% - 6px)` }}
          />
          <div
            className={styles.listedLabel}
            style={{ left: `${pct(listed)}%` }}
          >
            ${listed}
          </div>
        </>
      )}
    </div>
  )
}
