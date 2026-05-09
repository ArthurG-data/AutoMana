// src/frontend/src/features/ebay/components/ListingDetailPanel.tsx
import { Icon } from '../../../components/design-system/Icon'
import type { EbayLiveListing } from '../mockListings'
import styles from './ListingDetailPanel.module.css'

interface ListingDetailPanelProps {
  listing: EbayLiveListing
  onEdit: () => void
  onClose: () => void
  onCompare: () => void
}

export function ListingDetailPanel({ listing, onEdit, onClose, onCompare }: ListingDetailPanelProps) {
  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <span className={styles.title}>{listing.cardName}</span>
        <button onClick={onClose} className={styles.closeBtn} aria-label="Close panel">
          <Icon kind="close" size={14} color="currentColor" />
        </button>
      </div>

      {listing.imageUrl ? (
        <img src={listing.imageUrl} alt={listing.cardName} className={styles.image} />
      ) : (
        <div className={styles.imagePlaceholder}>
          <span className={styles.placeholderSet}>{listing.setCode}</span>
        </div>
      )}

      <div className={styles.fields}>
        {[
          { label: 'Set', value: listing.setCode || '—' },
          { label: 'Condition', value: listing.conditionLabel || '—' },
          { label: 'Days listed', value: listing.daysListed > 0 ? `${listing.daysListed}d` : '—' },
          { label: 'App', value: listing.appName || listing.appCode },
        ].map(({ label, value }) => (
          <div key={label} className={styles.row}>
            <span className={styles.label}>{label}</span>
            <span className={styles.value}>{value}</span>
          </div>
        ))}
        <div className={styles.row}>
          <span className={styles.label}>Price</span>
          <span className={styles.valueAccent}>
            {listing.currency} {listing.price.toFixed(2)}
          </span>
        </div>
        <div className={styles.row}>
          <span className={styles.label}>Watchers</span>
          <span className={styles.value}>{listing.watchCount}</span>
        </div>
        <div className={styles.row}>
          <span className={styles.label}>eBay</span>
          <a
            href={listing.viewItemUrl}
            target="_blank"
            rel="noopener noreferrer"
            className={styles.link}
          >
            View ↗
          </a>
        </div>
      </div>

      <div className={styles.actions}>
        <button onClick={onCompare} className={styles.compareBtn}>
          Compare market
        </button>
        <button onClick={onEdit} className={styles.editBtn}>
          Edit listing
        </button>
      </div>
    </div>
  )
}
