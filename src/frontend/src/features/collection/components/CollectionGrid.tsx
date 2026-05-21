import { useState } from 'react'
import { CardArt } from '../../../components/design-system/CardArt'
import { formatUSD } from '../../../lib/format'
import type { CollectionEntry } from '../api'
import { groupEntries } from '../groupEntries'
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

function toCardArtFinish(finish: CollectionEntry['finish']): 'non-foil' | 'foil' | 'etched' {
  if (finish === 'NONFOIL') return 'non-foil'
  if (finish === 'FOIL') return 'foil'
  return 'etched'
}

export function CollectionGrid({ entries, onRemove }: CollectionGridProps) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null)
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
        const isExpanded = expandedKey === key
        const pl =
          entry.price != null ? entry.price - Number(entry.purchase_price) : null
        const plLabel =
          pl != null ? `${pl >= 0 ? '+' : '-'}${formatUSD(Math.abs(pl))}` : null

        return (
          <div key={key} className={styles.cardWrap}>
            {copies.length > 1 && (
              <span className={styles.copyBadge}>×{copies.length}</span>
            )}
            <button
              className={styles.expandBtn}
              onClick={() => setExpandedKey(isExpanded ? null : key)}
              aria-label={
                isExpanded
                  ? `Collapse ${entry.card_name} copies`
                  : `Expand ${entry.card_name} copies`
              }
            >
              <CardArt
                name={entry.card_name}
                w="100%"
                hue={(i * 47) % 360}
                label={false}
                imageUrl={entry.image_normal ?? undefined}
                finish={toCardArtFinish(entry.finish)}
              />
            </button>
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
                <span className={styles.price}>{formatUSD(entry.price)}</span>
                {plLabel != null && (
                  <span className={`${styles.pl} ${pl! >= 0 ? styles.plUp : styles.plDown}`}>
                    {plLabel}
                  </span>
                )}
              </div>
            </div>
            {isExpanded && (
              <ul className={styles.copyList}>
                {copies.map((copy) => (
                  <li key={copy.item_id} className={styles.copyRow}>
                    <span className={styles.badge}>{copy.condition}</span>
                    <span className={styles.copyPrice}>
                      {formatUSD(Number(copy.purchase_price))}
                    </span>
                    <span className={styles.badge}>{copy.status}</span>
                    <button
                      className={styles.removeBtn}
                      onClick={() => onRemove(copy.item_id)}
                      aria-label={`Remove copy of ${copy.card_name}`}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )
      })}
    </div>
  )
}
