// src/frontend/src/features/cards/components/AIAnalyticsCard.tsx
import styles from './AIAnalyticsCard.module.css'

interface AIAnalyticsCardProps {
  /** Future: insights payload from the backend. Empty/missing renders the placeholder state. */
  insights?: {
    summary?: string
    signals?: { label: string; value: string; tone?: 'up' | 'down' | 'neutral' }[]
  }
}

export function AIAnalyticsCard({ insights }: AIAnalyticsCardProps) {
  const hasData = insights && (insights.summary || (insights.signals && insights.signals.length > 0))

  return (
    <aside className={styles.card}>
      <header className={styles.header}>
        <div className={styles.label}>AI INSIGHTS</div>
        <span className={styles.badge}>Beta</span>
      </header>

      {hasData ? (
        <div className={styles.body}>
          {insights!.summary && <p className={styles.summary}>{insights!.summary}</p>}
          {insights!.signals && insights!.signals.length > 0 && (
            <ul className={styles.signals}>
              {insights!.signals.map((s, i) => (
                <li key={i} className={`${styles.signal} ${s.tone ? styles[s.tone] : ''}`}>
                  <span className={styles.signalLabel}>{s.label}</span>
                  <span className={styles.signalValue}>{s.value}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <div className={styles.placeholder}>
          <div className={styles.placeholderIcon} aria-hidden="true">✦</div>
          <p className={styles.placeholderText}>Predictive analytics coming soon</p>
          <p className={styles.placeholderSub}>Trend signals, price forecasts, and arbitrage hints will land here.</p>
        </div>
      )}
    </aside>
  )
}
