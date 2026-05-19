import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { EbayLiveListing } from '../../ebay/mockListings'
import { collectionsQueryOptions, addCollectionEntry } from '../api'
import type { CollectionEntry } from '../api'
import styles from './BackfillConfirmDialog.module.css'

type Condition = CollectionEntry['condition']
type Finish = CollectionEntry['finish']

function mapFinish(code: string | null | undefined): Finish {
  switch (code?.toUpperCase()) {
    case 'FOIL':        return 'FOIL'
    case 'ETCHED':      return 'ETCHED'
    // Exotic foils → FOIL
    case 'SURGE_FOIL':
    case 'RIPPLE_FOIL':
    case 'RAINBOW_FOIL': return 'FOIL'
    default:             return 'NONFOIL'
  }
}

function mapCondition(code: string | null | undefined): Condition {
  switch (code?.toUpperCase()) {
    case 'LP':  return 'LP'
    case 'MP':  return 'MP'
    case 'HP':  return 'HP'
    case 'DMG': return 'DMG'
    case 'SP':  return 'SP'
    default:    return 'NM'
  }
}

interface Props {
  listings: EbayLiveListing[]
  onClose: () => void
  onDone: (unmatched: EbayLiveListing[], collectionId: string) => void
}

type Phase = 'confirm' | 'adding' | 'done'

export function BackfillConfirmDialog({ listings, onClose, onDone }: Props) {
  const { data: collections = [] } = useQuery(collectionsQueryOptions())
  const [collectionId, setCollectionId] = useState<string>('')
  const [phase, setPhase] = useState<Phase>('confirm')
  const [addedCount, setAddedCount] = useState(0)
  const [errorCount, setErrorCount] = useState(0)

  const matched = listings.filter((l) => l.cardVersionId)
  const unmatched = listings.filter((l) => !l.cardVersionId)

  const selectedCollectionId = collectionId || collections[0]?.collection_id || ''

  async function handleConfirm() {
    if (!selectedCollectionId || matched.length === 0) return
    setPhase('adding')

    const results = await Promise.allSettled(
      matched.map((listing) =>
        addCollectionEntry(
          selectedCollectionId,
          listing.cardVersionId!,
          mapCondition(listing.catalogConditionCode),
          mapFinish(listing.catalogFinishCode),
        )
      )
    )

    const succeeded = results.filter((r) => r.status === 'fulfilled').length
    const failed = results.filter((r) => r.status === 'rejected').length
    setAddedCount(succeeded)
    setErrorCount(failed)
    setPhase('done')
  }

  if (phase === 'adding') {
    return (
      <div className={styles.overlay}>
        <div className={styles.dialog}>
          <div className={styles.title}>Adding to collection…</div>
          <div className={styles.sub}>Adding {matched.length} card{matched.length !== 1 ? 's' : ''}</div>
        </div>
      </div>
    )
  }

  if (phase === 'done') {
    return (
      <div className={styles.overlay}>
        <div className={styles.dialog}>
          <div className={styles.title}>Done</div>
          <div className={styles.summary}>
            <span className={styles.summaryGood}>{addedCount} added</span>
            {errorCount > 0 && <span className={styles.summaryBad}> · {errorCount} failed</span>}
          </div>

          {unmatched.length > 0 && (
            <div className={styles.unmatchedNote}>
              {unmatched.length} listing{unmatched.length !== 1 ? 's' : ''} need card selection
            </div>
          )}

          <div className={styles.actions}>
            <button className={styles.btnCancel} onClick={onClose}>
              Close
            </button>
            {unmatched.length > 0 && (
              <button
                className={styles.btnPrimary}
                onClick={() => onDone(unmatched, selectedCollectionId)}
              >
                Match remaining {unmatched.length}
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.dialog} role="dialog" aria-modal="true">
        <div className={styles.title}>Add listings to collection</div>

        <div className={styles.counts}>
          <div className={styles.countRow}>
            <span className={styles.countNum}>{matched.length}</span>
            <span className={styles.countLabel}>matched — ready to add</span>
          </div>
          <div className={styles.countRow}>
            <span className={styles.countNum}>{unmatched.length}</span>
            <span className={styles.countLabel}>need card selection</span>
          </div>
        </div>

        <div className={styles.label}>Collection</div>
        <select
          className={styles.select}
          value={selectedCollectionId}
          onChange={(e) => setCollectionId(e.target.value)}
        >
          {collections.map((col) => (
            <option key={col.collection_id} value={col.collection_id}>
              {col.collection_name}
            </option>
          ))}
        </select>

        {matched.length === 0 && unmatched.length > 0 && (
          <div className={styles.unmatchedNote}>
            No matched listings. Use "Match cards" to link unmatched ones.
          </div>
        )}

        <div className={styles.actions}>
          <button className={styles.btnCancel} onClick={onClose}>
            Cancel
          </button>
          {matched.length > 0 && (
            <button
              className={styles.btnPrimary}
              disabled={!selectedCollectionId}
              onClick={handleConfirm}
            >
              Add {matched.length} to collection
            </button>
          )}
          {matched.length === 0 && unmatched.length > 0 && (
            <button
              className={styles.btnPrimary}
              onClick={() => onDone(unmatched, selectedCollectionId)}
            >
              Match {unmatched.length} cards
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
