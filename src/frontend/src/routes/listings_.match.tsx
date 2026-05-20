// src/frontend/src/routes/listings_.match.tsx
import { useState } from 'react'
import { createFileRoute, useNavigate, useLocation } from '@tanstack/react-router'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { CardPicker } from '../features/ebay/components/CardPicker'
import { addCollectionEntry } from '../features/collection/api'
import type { CollectionEntry } from '../features/collection/api'
import type { EbayLiveListing } from '../features/ebay/mockListings'
import type { CardSummary } from '../features/cards/types'
import styles from './ListingsMatch.module.css'

export const Route = createFileRoute('/listings_/match')({
  component: ListingsMatchPage,
})

type Condition = CollectionEntry['condition']
type Finish = CollectionEntry['finish']

const CONDITIONS: Condition[] = ['NM', 'LP', 'MP', 'HP', 'DMG']
const FINISHES: Finish[] = ['NONFOIL', 'FOIL', 'ETCHED']

function mapCondition(code: string | null | undefined): Condition {
  switch (code?.toUpperCase()) {
    case 'LP':  return 'LP'
    case 'MP':  return 'MP'
    case 'HP':  return 'HP'
    case 'DMG': return 'DMG'
    default:    return 'NM'
  }
}

function mapFinish(code: string | null | undefined): Finish {
  switch (code?.toUpperCase()) {
    case 'FOIL':
    case 'SURGE_FOIL':
    case 'RIPPLE_FOIL':
    case 'RAINBOW_FOIL': return 'FOIL'
    case 'ETCHED':       return 'ETCHED'
    default:             return 'NONFOIL'
  }
}

export function ListingsMatchPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const state = location.state as { unmatched?: EbayLiveListing[]; collectionId?: string } | undefined

  const unmatched: EbayLiveListing[] = state?.unmatched ?? []
  const collectionId: string = state?.collectionId ?? ''

  const [index, setIndex] = useState(0)
  const [selectedCard, setSelectedCard] = useState<CardSummary | null>(null)
  const [condition, setCondition] = useState<Condition>(
    () => mapCondition(unmatched[0]?.catalogConditionCode)
  )
  const [finish, setFinish] = useState<Finish>(
    () => mapFinish(unmatched[0]?.catalogFinishCode)
  )
  const [addedCount, setAddedCount] = useState(0)
  const [isAdding, setIsAdding] = useState(false)

  const listing = unmatched[index]
  const isComplete = index >= unmatched.length

  function handleListingChange(newIndex: number) {
    setIndex(newIndex)
    setSelectedCard(null)
    const next = unmatched[newIndex]
    setCondition(mapCondition(next?.catalogConditionCode))
    setFinish(mapFinish(next?.catalogFinishCode))
  }

  async function handleAdd() {
    if (!selectedCard || !collectionId || isAdding) return
    setIsAdding(true)
    try {
      await addCollectionEntry(
        collectionId,
        selectedCard.card_version_id,
        condition,
        finish,
      )
      setAddedCount((n) => n + 1)
    } catch {
      // continue even on error — user can try again or skip
    } finally {
      setIsAdding(false)
      handleListingChange(index + 1)
    }
  }

  function handleSkip() {
    handleListingChange(index + 1)
  }

  if (!collectionId || unmatched.length === 0) {
    return (
      <AppShell active="listings">
        <TopBar title="Match cards" />
        <div className={styles.empty}>
          <p>No unmatched listings to process.</p>
          <button className={styles.backBtn} onClick={() => navigate({ to: '/listings' })}>
            Back to listings
          </button>
        </div>
      </AppShell>
    )
  }

  if (isComplete) {
    return (
      <AppShell active="listings">
        <TopBar title="Match cards" />
        <div className={styles.complete}>
          <div className={styles.completeTitle}>All done</div>
          <div className={styles.completeSub}>
            Added {addedCount} of {unmatched.length} listing{unmatched.length !== 1 ? 's' : ''} to your collection
          </div>
          <button className={styles.backBtn} onClick={() => navigate({ to: '/listings' })}>
            Back to listings
          </button>
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell active="listings">
      <TopBar
        title="Match cards"
        actions={
          <span className={styles.progress}>
            {index + 1} of {unmatched.length}
          </span>
        }
      />

      <div className={styles.page}>
      <div className={styles.split}>
        {/* Left — listing details + condition */}
        <div className={styles.sidebar}>
          <div className={styles.listingTitle}>{listing.title}</div>

          <div className={styles.badges}>
            {listing.conditionLabel && (
              <span className={styles.badge}>{listing.conditionLabel}</span>
            )}
            {listing.finish && listing.finish !== 'Regular' && (
              <span className={styles.badge}>{listing.finish}</span>
            )}
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
          <div className={styles.pills}>
            {FINISHES.map((f) => (
              <button
                key={f}
                className={[styles.pill, finish === f ? styles.pillActive : ''].join(' ')}
                onClick={() => setFinish(f)}
              >
                {f === 'NONFOIL' ? 'Non-foil' : f === 'FOIL' ? 'Foil' : 'Etched'}
              </button>
            ))}
          </div>

          {selectedCard && (
            <div className={styles.selectedCard}>
              <div className={styles.selectedCardName}>{selectedCard.card_name}</div>
              <div className={styles.selectedCardSet}>{selectedCard.set_code.toUpperCase()} · {selectedCard.finish}</div>
            </div>
          )}

          <div className={styles.actionRow}>
            <button className={styles.skipBtn} onClick={handleSkip}>
              Skip
            </button>
            <button
              className={styles.addBtn}
              disabled={!selectedCard || isAdding}
              onClick={handleAdd}
            >
              {isAdding ? 'Adding…' : 'Add to collection & next'}
            </button>
          </div>
        </div>

        {/* Right — card picker, collapse=false so all prints (incl. Japanese alt-art) are visible */}
        <div className={styles.pickerArea}>
          <CardPicker
            onSelect={(card) => setSelectedCard(card)}
            selectedId={selectedCard?.card_version_id}
            collapse={false}
          />
        </div>
      </div>
      </div>
    </AppShell>
  )
}
