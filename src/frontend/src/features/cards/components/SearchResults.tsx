// src/frontend/src/features/cards/components/SearchResults.tsx
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CardArt } from '../../../components/design-system/CardArt'
import { Sparkline } from '../../../components/design-system/Sparkline'
import { AddToCollectionPopover } from '../../collection/components/AddToCollectionPopover'
import { addCollectionEntry, collectionsQueryOptions, collectionEntriesQueryOptions } from '../../collection/api'
import { useAuthStore } from '../../../store/auth'
import { cn } from '../../../lib/cn'
import type { Collection } from '../../collection/api'
import type { CardGroupBy, CardSummary } from '../types'
import styles from './SearchResults.module.css'

interface SearchResultsProps {
  cards: CardSummary[]
  total: number
  fetchNextPage: () => void
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  onSelect?: (card: CardSummary) => void
  selectedId?: string
  groupBy?: CardGroupBy
}

const RARITY_ORDER: Record<string, number> = {
  mythic: 0, rare: 1, uncommon: 2, common: 3,
}

interface CardGroup {
  key: string
  label: string
  cards: CardSummary[]
}

function buildGroups(cards: CardSummary[], groupBy: CardGroupBy | undefined): CardGroup[] {
  if (!groupBy) return [{ key: '__all__', label: '', cards }]

  const buckets = new Map<string, CardGroup>()
  for (const card of cards) {
    const key = card.rarity_name
    const label = card.rarity_name.charAt(0).toUpperCase() + card.rarity_name.slice(1)
    if (!buckets.has(key)) buckets.set(key, { key, label, cards: [] })
    buckets.get(key)!.cards.push(card)
  }

  const groups = Array.from(buckets.values())
  groups.sort((a, b) => (RARITY_ORDER[a.key] ?? 99) - (RARITY_ORDER[b.key] ?? 99))
  return groups
}

export function SearchResults({
  cards,
  total,
  fetchNextPage,
  hasNextPage,
  isFetchingNextPage,
  onSelect,
  selectedId,
  groupBy,
}: SearchResultsProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const lastCardRef = useRef<HTMLButtonElement>(null)
  const [addTarget, setAddTarget] = useState<CardSummary | null>(null)

  const isAuthed = Boolean(useAuthStore((s) => s.token))
  const { data: collections = [] } = useQuery({
    ...collectionsQueryOptions(),
    enabled: isAuthed,
  })

  const firstCollectionId = collections[0]?.collection_id ?? ''
  const { data: firstCollectionEntries = [] } = useQuery({
    ...collectionEntriesQueryOptions(firstCollectionId),
    enabled: Boolean(firstCollectionId) && isAuthed && Boolean(addTarget),
  })

  async function handleAdd(params: {
    collectionId: string
    condition: 'NM' | 'LP' | 'MP' | 'HP' | 'DMG' | 'SP'
    finish: 'NONFOIL' | 'FOIL' | 'ETCHED'
  }) {
    if (!addTarget) return
    await addCollectionEntry(
      params.collectionId,
      addTarget.card_version_id,
      params.condition,
      params.finish,
    )
    queryClient.invalidateQueries({ queryKey: collectionEntriesQueryOptions(params.collectionId).queryKey })
    setAddTarget(null)
  }

  const groups = useMemo(() => buildGroups(cards, groupBy), [cards, groupBy])
  const lastCardId = cards.length > 0 ? cards[cards.length - 1].card_version_id : null

  useEffect(() => {
    if (!lastCardRef.current || !hasNextPage || isFetchingNextPage) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          fetchNextPage()
        }
      },
      { rootMargin: '500px' }
    )
    observer.observe(lastCardRef.current)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage, lastCardId])

  const today = new Date().toISOString().slice(0, 10)

  if (cards.length === 0) {
    return <div className={styles.empty}>No cards found. Try a different search.</div>
  }

  function cardPrice(card: CardSummary, delta: number) {
    if (card.price != null) {
      return (
        <span className={cn(styles.price, delta >= 0 ? styles.up : styles.down)}>
          ${card.price.toFixed(2)}
        </span>
      )
    }
    if (card.released_at != null && card.released_at > today) {
      return <span className={`${styles.price} ${styles.unreleased}`}>Not yet released</span>
    }
    return <span className={styles.price}>N/A</span>
  }

  const renderCard = (card: CardSummary, i: number) => {
    const delta = card.price_change_1d ?? 0
    const isLastCard = card.card_version_id === lastCardId
    const existingCopies = firstCollectionEntries.filter(
      (e) => e.card_version_id === card.card_version_id
    ).length
    return (
      <div key={card.card_version_id} className={styles.cardWrap}>
        <button
          ref={isLastCard ? lastCardRef : null}
          className={cn(styles.card, card.card_version_id === selectedId && styles.cardSelected)}
          onClick={() =>
            onSelect
              ? onSelect(card)
              : navigate({ to: '/cards/$id', params: { id: card.card_version_id } })
          }
        >
          <div style={{ position: 'relative' }}>
            <CardArt
              name={card.card_name}
              w="100%"
              hue={(i * 47) % 360}
              label={false}
              imageUrl={card.image_normal}
              finish={card.finish}
            />
            {(card.version_count ?? 1) > 1 && (
              <span className={styles.versionBadge}>{card.version_count} prints</span>
            )}
          </div>
          <div className={styles.cardInfo}>
            <div className={styles.cardName}>{card.card_name}</div>
            <div className={styles.cardSubtitle}>
              <span
                className={`${styles.set} ${styles.setLink}`}
                role="button"
                tabIndex={0}
                title={`Search ${card.set_code.toUpperCase()} only`}
                onClick={(e) => {
                  e.stopPropagation()
                  navigate({ to: '/search', search: { set: card.set_code } })
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.stopPropagation()
                    e.preventDefault()
                    navigate({ to: '/search', search: { set: card.set_code } })
                  }
                }}
              >
                {card.set_name}
              </span>
              <span className={styles.rarity}>{card.rarity_name}</span>
            </div>
            <div className={styles.cardMeta}>
              {cardPrice(card, delta)}
            </div>
            <Sparkline
              points={card.spark}
              color={delta >= 0 ? 'var(--hd-accent)' : 'var(--hd-red)'}
              width={100}
              height={24}
            />
          </div>
        </button>

        <button
          className={styles.addBtn}
          onClick={(e) => {
            e.stopPropagation()
            setAddTarget(addTarget?.card_version_id === card.card_version_id ? null : card)
          }}
          aria-label={`Add ${card.card_name} to collection`}
        >
          + Add
        </button>

        {addTarget?.card_version_id === card.card_version_id && (
          <AddToCollectionPopover
            cardVersionId={card.card_version_id}
            cardName={card.card_name}
            finish={card.finish}
            collections={collections as Collection[]}
            existingCopies={existingCopies}
            onAdd={handleAdd}
            onClose={() => setAddTarget(null)}
          />
        )}
      </div>
    )
  }

  return (
    <div className={styles.results}>
      <div className={styles.meta}>{total.toLocaleString()} results</div>
      {groupBy ? (
        groups.map((g) => (
          <section key={g.key} className={styles.group}>
            <header className={styles.groupHeader}>
              <span className={styles.groupTitle}>{g.label}</span>
              <span className={styles.groupCount}>{g.cards.length}</span>
            </header>
            <div className={styles.grid}>
              {g.cards.map((card, i) => renderCard(card, i))}
            </div>
          </section>
        ))
      ) : (
        <div className={styles.grid}>
          {cards.map((card, i) => renderCard(card, i))}
        </div>
      )}
      {isFetchingNextPage && (
        <div className={styles.loading}>Loading more cards...</div>
      )}
    </div>
  )
}
