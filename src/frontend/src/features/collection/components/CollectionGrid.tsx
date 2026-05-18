// src/frontend/src/features/collection/components/CollectionGrid.tsx
import { CardArt } from '../../../components/design-system/CardArt'
import type { CollectionEntry } from '../api'
import styles from './CollectionGrid.module.css'

interface CollectionGridProps {
  entries: CollectionEntry[]
  onRemove: (itemId: string) => void
}

function finishBadgeClass(finish: CollectionEntry['finish']): string {
  if (finish === 'FOIL') return `${styles.badge} ${styles.badgeFoil}`
  if (finish === 'ETCHED') return `${styles.badge} ${styles.badgeEtched}`
  return styles.badge
}

/** Map backend finish enum to CardArt finish prop (lowercase, hyphenated) */
function toCardArtFinish(finish: CollectionEntry['finish']): 'non-foil' | 'foil' | 'etched' {
  if (finish === 'NONFOIL') return 'non-foil'
  if (finish === 'FOIL') return 'foil'
  return 'etched'
}

export function CollectionGrid({ entries, onRemove }: CollectionGridProps) {
  if (entries.length === 0) {
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
      {entries.map((entry, i) => {
        const pl =
          entry.price != null
            ? entry.price - Number(entry.purchase_price)
            : null
        const plLabel =
          pl != null
            ? `${pl >= 0 ? '+' : '-'}$${Math.abs(pl).toFixed(2)}`
            : null

        return (
          <div key={entry.item_id} className={styles.cardWrap}>
            <button
              className={styles.removeBtn}
              onClick={() => onRemove(entry.item_id)}
              aria-label={`Remove ${entry.card_name}`}
            >
              ×
            </button>
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
                <span className={styles.badge}>{entry.condition}</span>
                {entry.finish !== 'NONFOIL' && (
                  <span className={finishBadgeClass(entry.finish)}>
                    {entry.finish.toLowerCase()}
                  </span>
                )}
              </div>
              <div className={styles.priceRow}>
                <span className={styles.price}>
                  {entry.price != null ? `$${entry.price.toFixed(2)}` : 'N/A'}
                </span>
                {plLabel != null && pl != null && (
                  <span className={`${styles.pl} ${pl >= 0 ? styles.plUp : styles.plDown}`}>
                    {plLabel}
                  </span>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
