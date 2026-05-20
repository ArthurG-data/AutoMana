// src/frontend/src/features/collection/components/CollectionTable.tsx
import { cn } from '../../../lib/cn'
import { formatUSD } from '../../../lib/format'
import type { CollectionEntry } from '../api'
import type { SortKey, SortDir } from '../../../routes/collection'
import styles from './CollectionTable.module.css'

interface CollectionTableProps {
  entries: CollectionEntry[]
  onRemove?: (entryId: string) => void
  sortBy?: SortKey
  sortDir?: SortDir
  onSort?: (key: SortKey) => void
}

function SortTh({
  label, sortKey, current, dir, onSort, align = 'left',
}: {
  label: string
  sortKey: SortKey
  current?: SortKey
  dir?: SortDir
  onSort?: (k: SortKey) => void
  align?: 'left' | 'right'
}) {
  const active = current === sortKey
  return (
    <th scope="col" className={align === 'right' ? styles.right : undefined}>
      <button className={cn(styles.thBtn, active && styles.thBtnActive)} onClick={() => onSort?.(sortKey)}>
        {label}
        <span className={styles.sortArrow}>{active ? (dir === 'asc' ? '↑' : '↓') : '↕'}</span>
      </button>
    </th>
  )
}

export function CollectionTable({ entries, onRemove, sortBy, sortDir, onSort }: CollectionTableProps) {
  return (
    <div className={styles.wrapper} role="region" aria-label="Collection table">
      <table className={styles.table}>
        <thead className={styles.thead}>
          <tr>
            <SortTh label="Card name" sortKey="name"     current={sortBy} dir={sortDir} onSort={onSort} />
            <SortTh label="Set"       sortKey="set"      current={sortBy} dir={sortDir} onSort={onSort} />
            <SortTh label="Finish"    sortKey="finish"   current={sortBy} dir={sortDir} onSort={onSort} />
            <th scope="col">Condition</th>
            <SortTh label="Purchase"  sortKey="purchase" current={sortBy} dir={sortDir} onSort={onSort} align="right" />
            <th scope="col" className={styles.right}>Market</th>
            <SortTh label="P/L"       sortKey="pl"       current={sortBy} dir={sortDir} onSort={onSort} align="right" />
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
                    <span className={pl >= 0 ? styles.positive : styles.negative}>
                      {plSign}{formatUSD(Math.abs(pl))}
                    </span>
                  ) : (
                    <span className={styles.neutral}>—</span>
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
