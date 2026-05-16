// Versions in this set — all card_version rows for the same (unique_card_id, set_code)
import { useNavigate } from '@tanstack/react-router'
import type { CardVersionRow } from '../types'
import { PriceDelta } from './PriceDelta'
import styles from './VersionsTable.module.css'

interface VersionsTableProps {
  versions: CardVersionRow[]
  currentVersionId: string
  setCode: string
}

function treatmentLabel(promoTypes: string[]): string {
  if (!promoTypes.length) return 'Regular'
  return promoTypes
    .map(pt => pt.charAt(0).toUpperCase() + pt.slice(1).replace(/_/g, ' '))
    .join(' · ')
}

const FINISH_LABEL: Record<string, string> = {
  nonfoil: 'NF',
  'non-foil': 'NF',
  foil: 'Foil',
  etched: 'Etched',
}

export function VersionsTable({ versions, currentVersionId, setCode }: VersionsTableProps) {
  const navigate = useNavigate()

  if (!versions.length) return null

  return (
    <div className={styles.section}>
      <div className={styles.label}>Versions in {setCode.toUpperCase()}</div>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Treatment</th>
            <th>Finishes</th>
            <th>Price</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {versions.map(v => {
            const isCurrent = v.card_version_id === currentVersionId
            return (
              <tr
                key={v.card_version_id}
                className={isCurrent ? styles.activeRow : styles.row}
                onClick={() => !isCurrent && navigate({ to: '/cards/$id', params: { id: v.card_version_id } })}
              >
                <td>
                  <div className={styles.thumbCell}>
                    {v.image_normal ? (
                      <img className={styles.thumb} src={v.image_normal} alt={v.card_name} />
                    ) : (
                      <div className={styles.thumbPlaceholder} />
                    )}
                    <div>
                      <div className={isCurrent ? styles.labelActive : styles.rowLabel}>
                        {treatmentLabel(v.promo_types)}
                      </div>
                      {v.collector_number && (
                        <div className={styles.cn}>#{v.collector_number}</div>
                      )}
                    </div>
                  </div>
                </td>
                <td>
                  <div className={styles.finishPills}>
                    {(v.available_finishes.length ? v.available_finishes : ['nonfoil']).map(f => (
                      <span
                        key={f}
                        className={[
                          styles.pill,
                          f === 'foil' ? styles.pillFoil : '',
                          f === 'etched' ? styles.pillEtched : '',
                        ].filter(Boolean).join(' ')}
                      >
                        {FINISH_LABEL[f] ?? f}
                      </span>
                    ))}
                  </div>
                </td>
                <td>
                  <PriceDelta price={v.price} priceChange1d={v.price_change_1d} />
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
