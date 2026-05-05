// src/frontend/src/features/ebay/components/ListingsTable.tsx
import { Link } from '@tanstack/react-router'
import { AIBadge } from '../../../components/design-system/AIBadge'
import { Icon } from '../../../components/design-system/Icon'
import { formatUSD, priceDeltaPct, type ActiveListing } from '../mockListings'
import styles from './ListingsTable.module.css'

interface ListingsTableProps {
  listings: ActiveListing[]
  onView?: (listing: ActiveListing) => void
  onMore?: (listing: ActiveListing) => void
}

export function ListingsTable({ listings, onView, onMore }: ListingsTableProps) {
  return (
    <div className={styles.wrapper} role="region" aria-label="Listings table">
      <table className={styles.table}>
        <thead className={styles.thead}>
          <tr>
            <th scope="col">Card name</th>
            <th scope="col">Set</th>
            <th scope="col">Condition</th>
            <th scope="col" className={styles.right}>Listed price</th>
            <th scope="col" className={styles.right}>Market price</th>
            <th scope="col" className={styles.center}>Watchers / Days</th>
            <th scope="col" className={styles.center}>AI status</th>
            <th scope="col" className={styles.right}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {listings.length === 0 && (
            <tr>
              <td colSpan={8} className={styles.empty}>
                No listings found
              </td>
            </tr>
          )}
          {listings.map((listing) => {
            const delta = priceDeltaPct(listing.listedPrice, listing.marketPrice)
            const isOver = delta > 5
            const isUnder = delta < -5

            return (
              <tr
                key={listing.id}
                className={[
                  styles.row,
                  listing.aiStatus === 'over' ? styles.rowOver : '',
                  listing.aiStatus === 'under' ? styles.rowUnder : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
              >
                {/* Card name */}
                <td>
                  <div className={styles.nameCell}>
                    <Link
                      to="/listings/$id"
                      params={{ id: listing.id }}
                      className={styles.cardName}
                    >
                      {listing.cardName}
                    </Link>
                    {listing.foil && <span className={styles.foilBadge}>foil</span>}
                  </div>
                </td>

                {/* Set */}
                <td>
                  <span className={styles.setCode}>{listing.setCode}</span>
                </td>

                {/* Condition */}
                <td>
                  <span className={styles.condition}>{listing.condition}</span>
                </td>

                {/* Listed price + delta */}
                <td className={styles.right}>
                  <div className={styles.priceCell}>
                    <span className={styles.listedPrice}>{formatUSD(listing.listedPrice)}</span>
                    {delta !== 0 && (
                      <span
                        className={[
                          styles.deltaBadge,
                          isOver ? styles.deltaOver : '',
                          isUnder ? styles.deltaUnder : '',
                        ]
                          .filter(Boolean)
                          .join(' ')}
                      >
                        {delta > 0 ? '+' : ''}{delta}%
                      </span>
                    )}
                  </div>
                </td>

                {/* Market price */}
                <td className={styles.right}>
                  <span className={styles.marketPrice}>{formatUSD(listing.marketPrice)}</span>
                </td>

                {/* Watchers / Days */}
                <td className={styles.center}>
                  <div className={styles.watchersCell}>
                    <span className={styles.watchers}>
                      <Icon kind="eye" size={11} color="var(--hd-muted)" />
                      {listing.watchers}
                    </span>
                    <span className={styles.days}>{listing.daysListed}d</span>
                  </div>
                </td>

                {/* AI status */}
                <td className={styles.center}>
                  <AIBadge status={listing.aiStatus} showLabel size="sm" />
                </td>

                {/* Actions */}
                <td>
                  <div className={styles.actionsCell}>
                    <Link
                      to="/listings/$id"
                      params={{ id: listing.id }}
                      className={styles.viewBtn}
                      aria-label={`View ${listing.cardName} strategy`}
                      onClick={() => onView?.(listing)}
                    >
                      <Icon kind="chart" size={11} color="currentColor" />
                      Strategy
                    </Link>
                    <button
                      className={styles.moreBtn}
                      onClick={() => onMore?.(listing)}
                      aria-label={`More options for ${listing.cardName}`}
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
