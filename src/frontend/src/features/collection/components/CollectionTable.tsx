// src/frontend/src/features/collection/components/CollectionTable.tsx
import React from 'react'
import { AIBadge } from '../../../components/design-system/AIBadge'
import { Pip } from '../../../components/design-system/Pip'
import { Icon } from '../../../components/design-system/Icon'
import type { CollectionCard } from '../mockCollection'
import { formatUSD } from '../mockCollection'
import styles from './CollectionTable.module.css'

interface CollectionTableProps {
  cards: CollectionCard[]
  onList?: (card: CollectionCard) => void
  onMore?: (card: CollectionCard) => void
}

export function CollectionTable({ cards, onList, onMore }: CollectionTableProps) {
  return (
    <div className={styles.wrapper} role="region" aria-label="Collection table">
      <table className={styles.table}>
        <thead className={styles.thead}>
          <tr>
            <th scope="col">Card name</th>
            <th scope="col">Set</th>
            <th scope="col" className={styles.center}>Qty</th>
            <th scope="col" className={styles.right}>Market price</th>
            <th scope="col" className={styles.right}>30d peak</th>
            <th scope="col" className={styles.right}>P/L</th>
            <th scope="col" className={styles.center}>Status</th>
            <th scope="col" className={styles.right}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {cards.length === 0 && (
            <tr>
              <td colSpan={8} className={styles.empty}>
                No cards match your filters
              </td>
            </tr>
          )}
          {cards.map((card) => {
            const pl = (card.marketPrice - card.costBasis) * card.qty
            const isReady = card.aiStatus === 'ready'

            return (
              <tr
                key={card.id}
                className={[
                  styles.row,
                  isReady ? styles.rowReady : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
              >
                {/* Card name + pips */}
                <td>
                  <div className={styles.nameCell}>
                    <div className={styles.pips}>
                      {card.colors.map((c) => (
                        <Pip key={c} color={c} size={13} />
                      ))}
                    </div>
                    <span className={styles.cardName}>{card.name}</span>
                    {card.foil && <span className={styles.foilBadge}>foil</span>}
                  </div>
                </td>

                {/* Set */}
                <td>
                  <span className={styles.setCode}>{card.setCode}</span>
                </td>

                {/* Qty */}
                <td className={styles.center}>{card.qty}</td>

                {/* Market price */}
                <td className={styles.right}>
                  {formatUSD(card.marketPrice)}
                </td>

                {/* 30d peak */}
                <td className={styles.right}>
                  <span className={styles.neutral}>{formatUSD(card.peak30d)}</span>
                </td>

                {/* P/L */}
                <td className={styles.right}>
                  <span className={pl >= 0 ? styles.positive : styles.negative}>
                    {pl >= 0 ? '+' : ''}{formatUSD(pl)}
                  </span>
                </td>

                {/* Status badge */}
                <td className={styles.center}>
                  <AIBadge status={card.aiStatus} showLabel size="sm" />
                </td>

                {/* Actions */}
                <td>
                  <div className={styles.actionsCell}>
                    {isReady ? (
                      <button
                        className={styles.listBtn}
                        onClick={() => onList?.(card)}
                        aria-label={`List ${card.name} on eBay`}
                      >
                        <Icon kind="tag" size={11} color="currentColor" />
                        List
                      </button>
                    ) : null}
                    <button
                      className={styles.moreBtn}
                      onClick={() => onMore?.(card)}
                      aria-label={`More options for ${card.name}`}
                    >
                      <Icon kind="more" size={14} color="currentColor" />
                    </button>
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
