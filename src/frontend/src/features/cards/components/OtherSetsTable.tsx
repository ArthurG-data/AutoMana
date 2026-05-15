// Other Sets — one representative row per set for the same unique_card_id
import { useNavigate } from '@tanstack/react-router'
import type { OtherSetRow } from '../types'
import styles from './VersionsTable.module.css'

interface OtherSetsTableProps {
  sets: OtherSetRow[]
  currentVersionId: string
}

function formatMonth(dateStr?: string): string {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}

export function OtherSetsTable({ sets, currentVersionId }: OtherSetsTableProps) {
  const navigate = useNavigate()

  if (!sets.length) return null

  return (
    <div className={styles.section}>
      <div className={styles.label}>Other Sets</div>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Set</th>
            <th>Released</th>
            <th>Versions</th>
            <th>Price</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {sets.map(s => {
            const isCurrent = s.card_version_id === currentVersionId
            return (
              <tr
                key={s.set_code}
                className={isCurrent ? styles.activeRow : styles.row}
                onClick={() => !isCurrent && navigate({ to: '/cards/$id', params: { id: s.card_version_id } })}
              >
                <td>
                  <div className={styles.thumbCell}>
                    <div className={[styles.setCircle, isCurrent ? styles.setCircleActive : ''].filter(Boolean).join(' ')}>
                      {s.set_code.toUpperCase()}
                    </div>
                    <div className={isCurrent ? styles.labelActive : styles.rowLabel}>
                      {s.set_name}
                    </div>
                  </div>
                </td>
                <td><span className={styles.cn}>{formatMonth(s.released_at)}</span></td>
                <td>
                  <span className={isCurrent ? styles.labelActive : styles.cn}>
                    {s.version_count} {s.version_count === 1 ? 'print' : 'prints'}
                  </span>
                </td>
                <td>
                  <div className={styles.priceCell}>
                    {s.price != null ? `$${s.price.toFixed(2)}` : 'N/A'}
                    {s.price != null && s.price_change_1d !== 0 && (
                      <span className={s.price_change_1d >= 0 ? styles.up : styles.down}>
                        {s.price_change_1d >= 0 ? '▲' : '▼'} {Math.abs(s.price_change_1d).toFixed(1)}%
                      </span>
                    )}
                  </div>
                </td>
                <td>
                  {isCurrent ? (
                    <span className={styles.viewingLabel}>Viewing</span>
                  ) : (
                    <span className={styles.viewLink}>View →</span>
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
