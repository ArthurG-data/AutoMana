// src/frontend/src/routes/search.tsx
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { z } from 'zod'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { SearchFilters } from '../features/cards/components/SearchFilters'
import { SearchResults } from '../features/cards/components/SearchResults'
import { SetBrowser } from '../features/cards/components/SetBrowser'
import { SelectedSetBanner } from '../features/cards/components/SelectedSetBanner'
import { cardInfiniteSearchQueryOptions, setBrowseQueryOptions } from '../features/cards/api'
import styles from './Search.module.css'

const searchSchema = z.object({
  q:          z.string().optional(),
  set:        z.string().optional(),
  rarity:     z.string().optional(),
  finish:     z.string().optional(),
  layout:     z.string().optional().default('normal'),
  minPrice:   z.number().optional(),
  maxPrice:   z.number().optional(),
  promoTypes: z.array(z.string()).optional(),
})

export const Route = createFileRoute('/search')({
  validateSearch: searchSchema,
  component: SearchPage,
})

function SearchPage() {
  const search = Route.useSearch()
  const navigate = useNavigate({ from: '/search' })

  // Always pre-fetch browse data so SelectedSetBanner can resolve metadata
  // even when the user lands directly at /search?set=mkm
  useQuery(setBrowseQueryOptions())

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery(
    cardInfiniteSearchQueryOptions(search)
  )

  const cards = data?.pages?.flatMap(p => p.cards) ?? []
  const total = data?.pages?.[0]?.pagination?.total_count ?? 0
  const promoTypeFacets = data?.pages?.[0]?.facets?.promo_types ?? []
  const rarityFacets = data?.pages?.[0]?.facets?.rarities ?? []

  const subtitle = search.set
    ? search.set.toUpperCase()
    : search.q
      ? `results for "${search.q}"`
      : 'browse by set'

  return (
    <AppShell active="collection">
      <TopBar title="Search" subtitle={subtitle} />

      {!search.set ? (
        <SetBrowser
          onSelect={(code) => navigate({ search: prev => ({ ...prev, set: code }) })}
        />
      ) : (
        <>
          <SelectedSetBanner
            setCode={search.set}
            onClear={() => navigate({ search: prev => ({ ...prev, set: undefined }) })}
          />
          <div className={styles.layout}>
            <SearchFilters
              params={search}
              promoTypeFacets={promoTypeFacets}
              rarityFacets={rarityFacets}
            />
            <SearchResults
              cards={cards}
              total={total}
              fetchNextPage={fetchNextPage}
              hasNextPage={hasNextPage}
              isFetchingNextPage={isFetchingNextPage}
            />
          </div>
        </>
      )}
    </AppShell>
  )
}
