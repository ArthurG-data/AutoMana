import { useRef, useState } from 'react'
import { useClickOutside } from '../../../hooks/useClickOutside'
import type { Collection, CollectionEntry } from '../api'
import styles from './AddToCollectionPopover.module.css'

type FinishOut = CollectionEntry['finish']

function normaliseFinish(finish: string): FinishOut {
  const f = finish.toLowerCase()
  if (f === 'foil') return 'FOIL'
  if (f === 'etched') return 'ETCHED'
  return 'NONFOIL'
}

interface Props {
  cardVersionId: string
  cardName: string
  finish: string
  collections: Collection[]
  existingCopies?: number
  onAdd: (params: { collectionId: string; condition: CollectionEntry['condition']; finish: FinishOut; isWishlist: boolean }) => void
  onClose: () => void
}

const CONDITIONS: CollectionEntry['condition'][] = ['NM', 'LP', 'MP', 'HP', 'DMG', 'SP']

export function AddToCollectionPopover({
  cardName,
  finish,
  collections,
  existingCopies = 0,
  onAdd,
  onClose,
}: Props) {
  const [condition, setCondition] = useState<CollectionEntry['condition']>('NM')
  const [collectionId, setCollectionId] = useState(collections[0]?.collection_id ?? '')
  const [isWishlist, setIsWishlist] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useClickOutside(ref, onClose)

  if (collections.length === 0) {
    return (
      <div ref={ref} className={styles.popover}>
        <div className={styles.header}>{cardName}</div>
        <p className={styles.label} style={{ color: 'var(--hd-sub)', textTransform: 'none' }}>
          Create a collection first
        </p>
        <div className={styles.actions}>
          <button className={styles.btnCancel} onClick={onClose}>Close</button>
        </div>
      </div>
    )
  }

  return (
    <div ref={ref} className={styles.popover} role="dialog" aria-label={`Add ${cardName} to collection`}>
      <div className={styles.header}>{cardName}</div>

      <div className={styles.label}>Type</div>
      <div className={styles.pills}>
        <button
          className={[styles.pill, !isWishlist ? styles.pillActive : ''].join(' ')}
          onClick={() => setIsWishlist(false)}
        >
          Owned
        </button>
        <button
          className={[styles.pill, isWishlist ? styles.pillActive : ''].join(' ')}
          onClick={() => setIsWishlist(true)}
        >
          Wishlist
        </button>
      </div>

      <div className={styles.label}>Condition</div>
      <div className={styles.pills}>
        {CONDITIONS.map((c) => (
          <button
            key={c}
            className={[styles.pill, condition === c ? styles.pillActive : ''].join(' ')}
            onClick={() => setCondition(c)}
          >
            {c}
          </button>
        ))}
      </div>

      <div className={styles.label}>Finish</div>
      <span className={styles.finishLabel}>{finish}</span>

      {collections.length > 1 && (
        <>
          <div className={styles.label}>Collection</div>
          <select
            className={styles.select}
            value={collectionId}
            onChange={(e) => setCollectionId(e.target.value)}
          >
            {collections.map((col) => (
              <option key={col.collection_id} value={col.collection_id}>
                {col.collection_name}
              </option>
            ))}
          </select>
        </>
      )}

      {existingCopies > 0 && (
        <p className={styles.label}>
          {`You already have ${existingCopies} — add another?`}
        </p>
      )}

      <div className={styles.actions}>
        <button className={styles.btnCancel} onClick={onClose}>
          Cancel
        </button>
        <button
          className={styles.btnAdd}
          disabled={!collectionId}
          onClick={() =>
            onAdd({ collectionId, condition, finish: normaliseFinish(finish), isWishlist })
          }
        >
          Add to Collection
        </button>
      </div>
    </div>
  )
}
