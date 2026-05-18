import { useEffect, useRef, useState } from 'react'
import type { Collection } from '../api'
import styles from './AddToCollectionPopover.module.css'

type Condition = 'NM' | 'LP' | 'MP' | 'HP'
type FinishOut = 'NONFOIL' | 'FOIL' | 'ETCHED'

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
  onAdd: (params: { collectionId: string; condition: Condition; finish: FinishOut }) => void
  onClose: () => void
}

const CONDITIONS: Condition[] = ['NM', 'LP', 'MP', 'HP']

export function AddToCollectionPopover({
  cardName,
  finish,
  collections,
  onAdd,
  onClose,
}: Props) {
  const [condition, setCondition] = useState<Condition>('NM')
  const [collectionId, setCollectionId] = useState(collections[0]?.collection_id ?? '')
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [onClose])

  return (
    <div ref={ref} className={styles.popover} role="dialog" aria-label={`Add ${cardName} to collection`}>
      <div className={styles.header}>{cardName}</div>

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

      <div className={styles.actions}>
        <button className={styles.btnCancel} onClick={onClose}>
          Cancel
        </button>
        <button
          className={styles.btnAdd}
          disabled={!collectionId}
          onClick={() =>
            onAdd({ collectionId, condition, finish: normaliseFinish(finish) })
          }
        >
          Add to Collection
        </button>
      </div>
    </div>
  )
}
