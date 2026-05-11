// src/frontend/src/features/cards/components/SearchResults.tsx
import { useEffect, useRef } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { CardArt } from '../../../components/design-system/CardArt'
import { Sparkline } from '../../../components/design-system/Sparkline'
import type { CardSummary } from '../types'
import styles from './SearchResults.module.css'

interface SearchResultsProps {
  cards: CardSummary[]
  total: number
  fetchNextPage: () => void
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  onSelect?: (card: CardSummary) => void
  selectedId?: string
}

export function SearchResults({
  cards,
  total,
  fetchNextPage,
  hasNextPage,
  isFetchingNextPage,
  onSelect,
  selectedId,
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

  if (cards.length === 0) {
    return <div className={styles.empty}>No cards found. Try a different search.</div>
  }

  return (
    <div className={styles.results}>
      <div className={styles.meta}>{total.toLocaleString()} results</div>
      <div className={styles.grid}>
        {cards.map((card, i) => {
          const delta = card.price_change_1d
          const isLastCard = i === cards.length - 1
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
        })}
      </div>
      {isFetchingNextPage && (
        <div className={styles.loading}>Loading more cards...</div>
      )}
    </div>
  )
}
