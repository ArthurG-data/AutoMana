// src/frontend/src/features/cards/components/LegalityGrid.tsx
import styles from './LegalityGrid.module.css'

const FORMATS = [
  'standard', 'pioneer', 'modern', 'legacy',
  'vintage', 'pauper', 'commander', 'oathbreaker',
] as const

interface LegalityGridProps {
  legalities: Record<string, string>
}

export function LegalityGrid({ legalities }: LegalityGridProps) {
  return (
    <div className={styles.grid}>
      {FORMATS.map((fmt) => {
        const status = legalities[fmt] ?? 'not_legal'
        const statusClass =
          status === 'legal' ? styles.legal
          : status === 'banned' ? styles.banned
          : status === 'restricted' ? styles.restricted
          : styles.notLegal
        return (
          <div key={fmt} className={`${styles.cell} ${statusClass}`}>
            <div className={styles.label}>{fmt}</div>
            <div className={styles.status}>{status.replace('_', ' ')}</div>
          </div>
        )
      })}
    </div>
  )
}
