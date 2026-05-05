// src/frontend/src/features/ebay/components/StrategyCard.tsx
import { formatUSD, feeEstimate } from '../mockListings'
import styles from './StrategyCard.module.css'

export type StrategyKind = 'quick' | 'balanced' | 'max' | 'auction7' | 'auctionReserve'

export interface Strategy {
  kind: StrategyKind
  icon: string          // unicode glyph — matches spec exactly
  name: string
  description: string
  pctRange: [number, number]  // e.g. [-10, -6] means −6 to −10%
  daysRange: string
  marketPrice: number
}

interface StrategyCardProps {
  strategy: Strategy
  selected: boolean
  onSelect: (kind: StrategyKind) => void
}

function midPrice(strategy: Strategy): number {
  const mid = (strategy.pctRange[0] + strategy.pctRange[1]) / 2
  return strategy.marketPrice * (1 + mid / 100)
}

export function StrategyCard({ strategy, selected, onSelect }: StrategyCardProps) {
  const recommended = midPrice(strategy)
  const payout = feeEstimate(recommended)

  return (
    <button
      className={[styles.card, selected ? styles.selected : ''].filter(Boolean).join(' ')}
      onClick={() => onSelect(strategy.kind)}
      aria-pressed={selected}
      aria-label={`Select ${strategy.name} strategy`}
      data-testid={`strategy-${strategy.kind}`}
    >
      <div className={styles.header}>
        <span className={styles.icon} aria-hidden="true">{strategy.icon}</span>
        <div className={styles.titleGroup}>
          <div className={styles.name}>{strategy.name}</div>
          <div className={styles.description}>{strategy.description}</div>
        </div>
        {selected && <div className={styles.selectedDot} aria-hidden="true" />}
      </div>

      <div className={styles.stats}>
        <div className={styles.stat}>
          <div className={styles.statLabel}>Recommended</div>
          <div className={styles.statValue}>{formatUSD(recommended)}</div>
        </div>
        <div className={styles.stat}>
          <div className={styles.statLabel}>Est. days</div>
          <div className={styles.statValue}>{strategy.daysRange}</div>
        </div>
        <div className={styles.stat}>
          <div className={styles.statLabel}>After fees</div>
          <div className={[styles.statValue, styles.payout].join(' ')}>
            {formatUSD(payout)}
          </div>
        </div>
      </div>
    </button>
  )
}

// ── Strategy definitions ───────────────────────────────────────────────────

export function buildStrategies(marketPrice: number): Strategy[] {
  return [
    {
      kind: 'quick',
      icon: '⚡',
      name: 'Quick sale',
      description: '−6 to −10% — sell in days',
      pctRange: [-10, -6],
      daysRange: '1–3 days',
      marketPrice,
    },
    {
      kind: 'balanced',
      icon: '⚖',
      name: 'Balanced',
      description: '±2% — balanced speed & return',
      pctRange: [-2, 2],
      daysRange: '5–9 days',
      marketPrice,
    },
    {
      kind: 'max',
      icon: '↑',
      name: 'Max return',
      description: '+8 to +14% — wait for top buyer',
      pctRange: [8, 14],
      daysRange: '2–5 weeks',
      marketPrice,
    },
    {
      kind: 'auction7',
      icon: '⌬',
      name: 'Auction 7d',
      description: 'Let the market decide — 7-day run',
      pctRange: [-5, 5],
      daysRange: '7 days',
      marketPrice,
    },
    {
      kind: 'auctionReserve',
      icon: '◇',
      name: 'Auction + reserve',
      description: 'Auction with price floor protection',
      pctRange: [-2, 8],
      daysRange: '7–14 days',
      marketPrice,
    },
  ]
}
