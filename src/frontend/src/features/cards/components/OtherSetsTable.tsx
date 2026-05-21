// Other Sets — one representative row per set for the same unique_card_id
import { useNavigate } from '@tanstack/react-router'
import type { OtherSetRow } from '../types'
import { formatMonth } from '../utils/formatMonth'
import { PriceDelta } from './PriceDelta'
import styles from './VersionsTable.module.css'

interface OtherSetsTableProps {
  sets: OtherSetRow[]
}

export function OtherSetsTable({ sets }: OtherSetsTableProps) {
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
          {sets.map(s => (
            <tr
              key={s.set_code}
              className={styles.row}
              onClick={() => navigate({ to: '/cards/$id', params: { id: s.card_version_id } })}
            >
              <td>
                <div className={styles.thumbCell}>
                  <div className={styles.setCircle}>
                    <img
                      src={`https://svgs.scryfall.io/sets/${s.set_code.toLowerCase()}.svg`}
                      alt=""
                      aria-hidden
                      className={styles.setIcon}
                    />
                  </div>
                  <div className={styles.rowLabel}>{s.set_name}</div>
                </div>
              </td>
              <td><span className={styles.cn}>{formatMonth(s.released_at)}</span></td>
              <td><span className={styles.cn}>{s.version_count} {s.version_count === 1 ? 'print' : 'prints'}</span></td>
              <td><PriceDelta price={s.price} priceChange1d={s.price_change_1d} /></td>
              <td><span className={styles.viewLink}>View →</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
