// src/frontend/src/features/cards/components/SearchResults.tsx
import { useEffect, useMemo, useRef } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { CardArt } from '../../../components/design-system/CardArt'
import { Sparkline } from '../../../components/design-system/Sparkline'
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
const FINISH_ORDER: Record<string, number> = {
  'non-foil': 0, foil: 1, etched: 2,
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
    let key: string
    let label: string
    if (groupBy === 'set') {
      key = card.set_code
      label = `${card.set_name} · ${card.set_code.toUpperCase()}`
    } else if (groupBy === 'rarity') {
      key = card.rarity_name
      label = card.rarity_name.charAt(0).toUpperCase() + card.rarity_name.slice(1)
    } else {
      key = card.finish
      label = card.finish
    }
    if (!buckets.has(key)) buckets.set(key, { key, label, cards: [] })
    buckets.get(key)!.cards.push(card)
  }

  const groups = Array.from(buckets.values())
  if (groupBy === 'rarity') {
    groups.sort((a, b) => (RARITY_ORDER[a.key] ?? 99) - (RARITY_ORDER[b.key] ?? 99))
  } else if (groupBy === 'finish') {
    groups.sort((a, b) => (FINISH_ORDER[a.key] ?? 99) - (FINISH_ORDER[b.key] ?? 99))
  }
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
  const lastCardRef = useRef<HTMLButtonElement>(null)

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
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  const groups = useMemo(() => buildGroups(cards, groupBy), [cards, groupBy])
  const lastCardId = cards.length > 0 ? cards[cards.length - 1].card_version_id : null

  if (cards.length === 0) {
    return <div className={styles.empty}>No cards found. Try a different search.</div>
  }

  const renderCard = (card: CardSummary, i: number) => {
    const delta = card.price_change_1d
    const isLastCard = card.card_version_id === lastCardId
    return (
      <button
        key={card.card_version_id}
        ref={isLastCard ? lastCardRef : null}
        className={[
          styles.card,
          card.card_version_id === selectedId ? styles.cardSelected : '',
        ].filter(Boolean).join(' ')}
        onClick={() =>
          onSelect
            ? onSelect(card)
            : navigate({ to: '/cards/$id', params: { id: card.card_version_id } })
        }
      >
        <CardArt
          name={card.card_name}
          w="100%"
          hue={(i * 47) % 360}
          label={false}
          imageUrl={card.image_normal}
        />
        <div className={styles.cardInfo}>
          <div className={styles.cardName}>{card.card_name}</div>
          <div className={styles.cardMeta}>
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
              {card.set_code.toUpperCase()}
            </span>
            <span className={[styles.price, delta >= 0 ? styles.up : styles.down].join(' ')}>
              {card.price != null ? `$${card.price.toFixed(2)}` : 'N/A'}
            </span>
          </div>
          <Sparkline
            points={card.spark}
            color={delta >= 0 ? 'var(--hd-accent)' : 'var(--hd-red)'}
            width={100}
            height={24}
          />
        </div>
      </button>
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
