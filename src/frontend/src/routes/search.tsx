// src/frontend/src/routes/search.tsx
import { createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'
import { useSuspenseQuery } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { SearchFilters } from '../features/cards/components/SearchFilters'
import { SearchResults } from '../features/cards/components/SearchResults'
import { cardSearchQueryOptions } from '../features/cards/api'
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
  loaderDeps: ({ search }) => ({ search }),
  loader: ({ deps: { search }, context: { queryClient } }) =>
    queryClient.ensureQueryData(cardSearchQueryOptions(search)),
  component: SearchPage,
})

function SearchPage() {
  const search = Route.useSearch()
  const { data } = useSuspenseQuery(cardSearchQueryOptions(search))

  return (
    <AppShell active="collection">
      <TopBar
        title="Search"
        subtitle={search.q ? `results for "${search.q}"` : 'all cards'}
      />
      <div className={styles.layout}>
        <SearchFilters params={search} />
        <SearchResults cards={data.cards} total={data.total} />
      </div>
    </AppShell>
  )
}
