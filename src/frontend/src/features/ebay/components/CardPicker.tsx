// src/frontend/src/features/ebay/components/CardPicker.tsx
import { useState, useEffect } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { cardInfiniteSearchQueryOptions } from '../../cards/api'
import { SearchResults } from '../../cards/components/SearchResults'
import type { CardSummary } from '../../cards/types'
import styles from './CardPicker.module.css'

interface CardPickerProps {
  onSelect: (card: CardSummary) => void
  selectedId: string | undefined
}

export function CardPicker({ onSelect, selectedId }: CardPickerProps) {
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')

  useEffect(() => {
    const id = setTimeout(() => setDebouncedQ(q), 300)
    return () => clearTimeout(id)
  }, [q])

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } =
    useInfiniteQuery(cardInfiniteSearchQueryOptions({ q: debouncedQ || undefined }))

  const cards = data?.pages.flatMap((p) => p.cards) ?? []
  const total = data?.pages[0]?.pagination?.total_count ?? cards.length

  return (
    <div className={styles.picker}>
      <div className={styles.searchBar}>
        <input
          type="text"
          className={styles.searchInput}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search cards…"
          aria-label="Search cards"
        />
      </div>
      {isLoading ? (
        <div className={styles.loading}>Loading…</div>
      ) : (
        <SearchResults
          cards={cards}
          total={total}
          fetchNextPage={fetchNextPage}
          hasNextPage={hasNextPage}
          isFetchingNextPage={isFetchingNextPage}
          onSelect={onSelect}
          selectedId={selectedId}
        />
      )}
    </div>
  )
}
