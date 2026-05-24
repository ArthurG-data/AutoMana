import { CardArt } from '../../../components/design-system/CardArt'
import { formatUSD } from '../../../lib/format'
import type { CollectionEntry } from '../api'
import { groupEntries } from '../groupEntries'
import styles from './CollectionGrid.module.css'

interface CollectionGridProps {
  entries: CollectionEntry[]
  onRemove: (itemId: string) => void
  showFinancials?: boolean
}

function finishBadgeClass(finish: CollectionEntry['finish']): string {
  if (finish === 'FOIL') return `${styles.badge} ${styles.badgeFoil}`
  if (finish === 'ETCHED') return `${styles.badge} ${styles.badgeEtched}`
  return styles.badge
}

function toCardArtFinish(finish: CollectionEntry['finish']): 'non-foil' | 'foil' | 'etched' {
  if (finish === 'NONFOIL') return 'non-foil'
  if (finish === 'FOIL') return 'foil'
  return 'etched'
}

export function CollectionGrid({ entries, onRemove, showFinancials = true }: CollectionGridProps) {
  const groups = groupEntries(entries)

  if (groups.length === 0) {
    return (
      <div className={styles.grid}>
        <p className={styles.empty}>
          No cards yet — search for cards and hit + Add to start
        </p>
      </div>
    )
  }

  return (
    <div className={styles.grid}>
      {groups.map((group, i) => {
        const { key, representative: entry, copies } = group

        return (
          <div key={key} className={styles.cardWrap}>
            <span className={styles.copyBadge}>×{copies.length}</span>
            <CardArt
              name={entry.card_name}
              w="100%"
              hue={(i * 47) % 360}
              label={false}
              imageUrl={entry.image_normal ?? undefined}
              finish={toCardArtFinish(entry.finish)}
            />
            <div className={styles.cardInfo}>
              <div className={styles.cardName}>{entry.card_name}</div>
              <div className={styles.badges}>
                <span className={styles.badge}>{entry.set_code.toUpperCase()}</span>
              </div>
              <ul className={styles.copyList}>
                {copies.map((copy) => {
                  const pl = copy.price != null ? copy.price - Number(copy.purchase_price) : null
                  const plLabel = pl != null ? `${pl >= 0 ? '+' : ''}${formatUSD(pl)}` : null
                  return (
                    <li key={copy.item_id} className={styles.copyRow}>
                      <span className={styles.badge}>{copy.condition}</span>
                      {copy.finish !== 'NONFOIL' && (
                        <span className={finishBadgeClass(copy.finish)}>
                          {copy.finish.toLowerCase()}
                        </span>
                      )}
                      {showFinancials && (
                        <>
                          <span className={styles.copyPrice}>{formatUSD(copy.price)}</span>
                          {plLabel != null && (
                            <span className={`${styles.pl} ${pl! >= 0 ? styles.plUp : styles.plDown}`}>
                              {plLabel}
                            </span>
                          )}
                        </>
                      )}
                      <span className={`${styles.badge} ${styles.badgeStatus}`}>{copy.status}</span>
                      <button
                        className={styles.removeBtn}
                        onClick={() => onRemove(copy.item_id)}
                        aria-label={`Remove copy of ${copy.card_name}`}
                      >
                        ×
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          </div>
        )
      })}
    </div>
  )
}
