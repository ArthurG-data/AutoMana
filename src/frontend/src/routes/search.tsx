// src/frontend/src/routes/search.tsx
import { createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'
import { useInfiniteQuery } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { SearchFilters } from '../features/cards/components/SearchFilters'
import { SearchResults } from '../features/cards/components/SearchResults'
import { cardInfiniteSearchQueryOptions } from '../features/cards/api'
import styles from './Search.module.css'

const searchSchema = z.object({
  q:        z.string().optional(),
  set:      z.string().optional(),
  rarity:   z.string().optional(),
  finish:   z.string().optional(),
  minPrice: z.number().optional(),
  maxPrice: z.number().optional(),
})

export const Route = createFileRoute('/search')({
  validateSearch: searchSchema,
  component: SearchPage,
})

function SearchPage() {
  const search = Route.useSearch()
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery(
    cardInfiniteSearchQueryOptions(search)
  )

  const cards = data?.pages.flatMap(p => p.cards) ?? []
  const total = data?.pages[0]?.pagination?.total_count ?? 0

  return (
    <AppShell active="collection">
      <TopBar
        title="Search"
        subtitle={search.q ? `results for "${search.q}"` : 'all cards'}
      />
      <div className={styles.layout}>
        <SearchFilters params={search} />
        <SearchResults
          cards={cards}
          total={total}
          fetchNextPage={fetchNextPage}
          hasNextPage={hasNextPage}
          isFetchingNextPage={isFetchingNextPage}
        />
      </div>
    </AppShell>
  )
}
