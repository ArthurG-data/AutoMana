// src/frontend/src/features/collection/components/CollectionTable.tsx
import type { CollectionEntry } from '../api'
import styles from './CollectionTable.module.css'

interface CollectionTableProps {
  entries: CollectionEntry[]
  onRemove?: (entryId: string) => void
}

function formatUSD(n: number | null | undefined): string {
  if (n == null) return 'N/A'
  return `$${n.toFixed(2)}`
}

export function CollectionTable({ entries, onRemove }: CollectionTableProps) {
  return (
    <div className={styles.wrapper} role="region" aria-label="Collection table">
      <table className={styles.table}>
        <thead className={styles.thead}>
          <tr>
            <th scope="col">Card name</th>
            <th scope="col">Set</th>
            <th scope="col">Finish</th>
            <th scope="col">Condition</th>
            <th scope="col" className={styles.right}>Purchase</th>
            <th scope="col" className={styles.right}>Market</th>
            <th scope="col" className={styles.right}>P/L</th>
            <th scope="col" className={styles.right}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {entries.length === 0 && (
            <tr>
              <td colSpan={8} className={styles.empty}>
                No cards match your filters
              </td>
            </tr>
          )}
          {entries.map((entry) => {
            const pl =
              entry.price != null
                ? entry.price - Number(entry.purchase_price)
                : null
            const plSign = pl != null && pl >= 0 ? '+' : '-'

            return (
              <tr key={entry.item_id} className={styles.row}>
                <td>
                  <span className={styles.cardName}>{entry.card_name}</span>
                </td>
                <td>
                  <span className={styles.setCode}>{entry.set_code.toUpperCase()}</span>
                </td>
                <td>
                  <span className={styles.finish}>{entry.finish.toLowerCase()}</span>
                </td>
                <td>
                  <span className={styles.condition}>{entry.condition}</span>
                </td>
                <td className={styles.right}>
                  {formatUSD(Number(entry.purchase_price))}
                </td>
                <td className={styles.right}>
                  {formatUSD(entry.price ?? null)}
                </td>
                <td className={styles.right}>
                  {pl != null ? (
                    <span style={{ color: pl >= 0 ? 'var(--hd-accent)' : 'var(--hd-red)' }}>
                      {plSign}{formatUSD(Math.abs(pl))}
                    </span>
                  ) : (
                    <span style={{ color: 'var(--hd-muted)' }}>—</span>
                  )}
                </td>
                <td className={styles.right}>
                  {onRemove && (
                    <button
                      className={styles.removeBtn}
                      onClick={() => onRemove(entry.item_id)}
                      aria-label={`Remove ${entry.card_name}`}
                    >
                      ×
                    </button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
