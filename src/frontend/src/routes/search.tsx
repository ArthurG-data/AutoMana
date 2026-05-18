// src/frontend/src/routes/search.tsx
import { useState, useMemo } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { z } from 'zod'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { SearchFilters, type PriceTrend } from '../features/cards/components/SearchFilters'
import { SearchResults } from '../features/cards/components/SearchResults'
import { SetBrowser } from '../features/cards/components/SetBrowser'
import { SelectedSetBanner } from '../features/cards/components/SelectedSetBanner'
import { cardInfiniteSearchQueryOptions, setBrowseQueryOptions } from '../features/cards/api'
import styles from './Search.module.css'

const searchSchema = z.object({
  q:              z.string().optional(),
  set:            z.string().optional(),
  artist:         z.string().optional(),
  unique_card_id: z.string().uuid().optional(),
  rarity:         z.string().optional(),
  finish:         z.string().optional(),
  layout:         z.string().optional().default('normal'),
  minPrice:       z.number().optional(),
  maxPrice:       z.number().optional(),
  promoTypes:     z.array(z.string()).optional(),
  group:          z.enum(['rarity']).optional(),
  sort_by:        z.enum(['card_name', 'released_at', 'price']).optional(),
  sort_order:     z.enum(['asc', 'desc']).optional(),
  colors:         z.array(z.string()).optional(),
  card_type:      z.string().optional(),
  frame_effects:  z.array(z.string()).optional(),
})

export const Route = createFileRoute('/search')({
  validateSearch: searchSchema,
  component: SearchPage,
})

type Mode = 'set' | 'card'

function SearchPage() {
  const search = Route.useSearch()
  const navigate = useNavigate({ from: '/search' })

  // Always pre-fetch browse data so SelectedSetBanner can resolve metadata
  // even when the user lands directly at /search?set=mkm
  useQuery(setBrowseQueryOptions())

  // Default to card mode — the landing experience shows cards immediately.
  const [mode, setMode] = useState<Mode>('card')
  const [priceTrend, setPriceTrend] = useState<PriceTrend | undefined>(undefined)
  const [upcomingOnly, setUpcomingOnly] = useState(false)

  // Fetch cards whenever in card mode (even without a query — shows recent
  // releases), when a set is selected, or when resolving a unique card id.
  const shouldFetchCards =
    !!search.set || !!search.unique_card_id || mode === 'card'

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    ...cardInfiniteSearchQueryOptions(search),
    enabled: shouldFetchCards,
  })

  const rawCards = data?.pages?.flatMap(p => p.cards) ?? []
  const total = data?.pages?.[0]?.pagination?.total_count ?? 0
  const promoTypeFacets = data?.pages?.[0]?.facets?.promo_types ?? []
  const rarityFacets = data?.pages?.[0]?.facets?.rarities ?? []

  const cards = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10)
    let result = rawCards
    if (upcomingOnly) result = result.filter(c => c.released_at != null && c.released_at > today)
    if (priceTrend === 'rising')  result = result.filter(c => (c.price_change_7d ?? 0) > 0.05)
    if (priceTrend === 'stable')  result = result.filter(c => (c.price_change_7d ?? 0) >= -0.05 && (c.price_change_7d ?? 0) <= 0.05)
    if (priceTrend === 'falling') result = result.filter(c => (c.price_change_7d ?? 0) < -0.05)
    return result
  }, [rawCards, upcomingOnly, priceTrend])

  const subtitle = search.set
    ? search.set.toUpperCase()
    : search.unique_card_id
      ? cards[0]?.card_name
        ? `all versions of "${cards[0].card_name}"`
        : 'all versions'
      : search.q
        ? `results for "${search.q}"`
        : mode === 'card'
          ? 'search by card name'
          : 'browse by set'

  const filterProps = {
    params: search,
    promoTypeFacets,
    rarityFacets,
    priceTrend,
    onPriceTrendChange: setPriceTrend,
    upcomingOnly,
    onUpcomingOnlyChange: setUpcomingOnly,
  }

  const resultsProps = {
    cards,
    total,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    groupBy: search.group,
  }

  // ---- Set selected: banner + filters + results ----
  if (search.set) {
    return (
      <AppShell active="search">
        <TopBar title="Search" subtitle={subtitle} />
        <SelectedSetBanner
          setCode={search.set}
          onClear={() => navigate({ search: prev => ({ ...prev, set: undefined }) })}
        />
        <div className={styles.layout}>
          <SearchFilters {...filterProps} />
          <SearchResults {...resultsProps} />
        </div>
      </AppShell>
    )
  }

  // ---- Entry-point: mode tabs + chosen mode body ----
  return (
    <AppShell active="search">
      <TopBar title="Search" subtitle={subtitle} />

      <div className={styles.tabs} role="tablist" aria-label="Search mode">
        <button
          role="tab"
          aria-selected={mode === 'set'}
          className={`${styles.tab} ${mode === 'set' ? styles.tabActive : ''}`}
          onClick={() => setMode('set')}
        >
          {mode === 'set' && <span className={styles.tabDot} aria-hidden />}
          By Set
        </button>
        <button
          role="tab"
          aria-selected={mode === 'card'}
          className={`${styles.tab} ${mode === 'card' ? styles.tabActive : ''}`}
          onClick={() => setMode('card')}
        >
          {mode === 'card' && <span className={styles.tabDot} aria-hidden />}
          By Card Name
        </button>
      </div>

      {mode === 'set' ? (
        <SetBrowser
          onSelect={(code) => navigate({ search: prev => ({ ...prev, set: code }) })}
        />
      ) : (
        <div className={styles.layout}>
          <SearchFilters {...filterProps} />
          <SearchResults {...resultsProps} />
        </div>
      )}
    </AppShell>
  )
}
