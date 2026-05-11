// src/frontend/src/routes/search.tsx
import { useState } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { z } from 'zod'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { SearchFilters } from '../features/cards/components/SearchFilters'
import { SearchResults } from '../features/cards/components/SearchResults'
import { SearchBarWithSuggestions } from '../features/cards/components/SearchBarWithSuggestions'
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

type Mode = 'set' | 'card'

function SearchPage() {
  const search = Route.useSearch()
  const navigate = useNavigate({ from: '/search' })

  // Always pre-fetch browse data so SelectedSetBanner can resolve metadata
  // even when the user lands directly at /search?set=mkm
  useQuery(setBrowseQueryOptions())

  // Entry-point tab mode (only used when no set is selected).
  // Defaults to 'card' if the URL already has a name query, else 'set'.
  const [mode, setMode] = useState<Mode>(search.q ? 'card' : 'set')

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
      : mode === 'card'
        ? 'search by card name'
        : 'browse by set'

  // ---- Set selected: banner + filters + results (unchanged) ----
  if (search.set) {
    return (
      <AppShell active="search">
        <TopBar title="Search" subtitle={subtitle} />
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
        <div className={styles.cardMode}>
          <SearchBarWithSuggestions placeholder="Search any card by name…" />
          {search.q ? (
            <SearchResults
              cards={cards}
              total={total}
              fetchNextPage={fetchNextPage}
              hasNextPage={hasNextPage}
              isFetchingNextPage={isFetchingNextPage}
            />
          ) : (
            <p className={styles.cardModeHint}>
              Type a card name above — suggestions appear after 2 characters.
            </p>
          )}
        </div>
      )}
    </AppShell>
  )
}
