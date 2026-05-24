// src/frontend/src/routes/collection.tsx
import React, { useDeferredValue, useMemo, useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { ToastContainer } from '../components/design-system/Toast'
import { Icon } from '../components/design-system/Icon'
import { CollectionGrid } from '../features/collection/components/CollectionGrid'
import { CollectionTable } from '../features/collection/components/CollectionTable'
import {
  collectionsQueryOptions,
  createCollection,
  deleteCollectionEntry,
} from '../features/collection/api'
import { cn } from '../lib/cn'
import { useInfiniteEntries } from '../features/collection/hooks/useInfiniteEntries'
import { useToast } from '../lib/useToast'
import styles from './Collection.module.css'

export type SortKey = 'name' | 'set' | 'finish' | 'purchase' | 'pl'
export type SortDir = 'asc' | 'desc'

type ViewMode = 'grid' | 'list'

const FINISH_ORDER: Record<string, number> = { NONFOIL: 0, FOIL: 1, ETCHED: 2 }

export const Route = createFileRoute('/collection')({
  component: CollectionCatalogPage,
})

type CatalogTab = 'all' | 'owned' | 'wishlist'

const CATALOG_TABS: { value: CatalogTab; label: string }[] = [
  { value: 'all',      label: 'All' },
  { value: 'owned',    label: 'Owned' },
  { value: 'wishlist', label: 'Wishlist' },
]

function CollectionCatalogPage() {
  const queryClient = useQueryClient()
  const { toasts, toast } = useToast()
  const [query, setQuery] = useState('')
  const [catalogTab, setCatalogTab] = useState<CatalogTab>('all')
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null)
  const [newCollectionName, setNewCollectionName] = useState('')
  const [creatingNew, setCreatingNew] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('grid')
  const [sortBy, setSortBy] = useState<SortKey>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  const deferredQuery = useDeferredValue(query)

  const { data: collections = [] } = useQuery(collectionsQueryOptions())
  const activeCollectionId = selectedCollectionId ?? collections[0]?.collection_id ?? null

  const isWishlistFilter: boolean | undefined =
    catalogTab === 'owned' ? false : catalogTab === 'wishlist' ? true : undefined

  const {
    allEntries: entries,
    isFetchingMore,
    hasMore,
    removeEntry,
    sentinelRef,
  } = useInfiniteEntries(activeCollectionId, isWishlistFilter)

  const isLoading = entries.length === 0 && isFetchingMore

  const filtered = useMemo(() => {
    if (!deferredQuery.trim()) return entries
    const q = deferredQuery.toLowerCase()
    return entries.filter(
      (e) => e.card_name.toLowerCase().includes(q) || e.set_code.toLowerCase().includes(q),
    )
  }, [entries, deferredQuery])

  function handleSort(key: SortKey) {
    if (key === sortBy) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortBy(key); setSortDir('asc') }
  }

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      let cmp = 0
      switch (sortBy) {
        case 'name':     cmp = a.card_name.localeCompare(b.card_name); break
        case 'set':      cmp = a.set_code.localeCompare(b.set_code); break
        case 'finish':   cmp = (FINISH_ORDER[a.finish] ?? 0) - (FINISH_ORDER[b.finish] ?? 0); break
        case 'purchase': cmp = Number(a.purchase_price) - Number(b.purchase_price); break
        case 'pl': {
          const plA = (a.price ?? 0) - Number(a.purchase_price)
          const plB = (b.price ?? 0) - Number(b.purchase_price)
          cmp = plA - plB; break
        }
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [filtered, sortBy, sortDir])

  async function handleRemove(itemId: string) {
    if (!activeCollectionId) return
    await deleteCollectionEntry(activeCollectionId, itemId)
    removeEntry(itemId)
    toast('Card removed')
  }

  async function handleCreateCollection() {
    if (!newCollectionName.trim()) return
    const col = await createCollection(newCollectionName.trim())
    queryClient.invalidateQueries({ queryKey: collectionsQueryOptions().queryKey })
    setSelectedCollectionId(col.collection_id)
    setCreatingNew(false)
    setNewCollectionName('')
  }

  return (
    <AppShell active="collection">
      <TopBar title="Collection" />

      <div className={styles.page}>
        <header className={styles.header}>
          <div className={styles.titleBlock}>
            <div className={styles.eyebrow}>automana / collection</div>
            <h1 className={styles.title}>Your Collection</h1>
          </div>
        </header>

        <div className={styles.collectionTabRow}>
          {collections.map((col) => (
            <button
              key={col.collection_id}
              className={cn(
                styles.collectionTab,
                col.collection_id === activeCollectionId && styles.collectionTabActive,
              )}
              onClick={() => setSelectedCollectionId(col.collection_id)}
            >
              {col.collection_name}
            </button>
          ))}
          {creatingNew ? (
            <input
              className={styles.newCollectionInput}
              autoFocus
              placeholder="Collection name…"
              value={newCollectionName}
              onChange={(e) => setNewCollectionName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreateCollection()
                if (e.key === 'Escape') setCreatingNew(false)
              }}
              onBlur={() => { if (!newCollectionName.trim()) setCreatingNew(false) }}
            />
          ) : (
            <button className={styles.tabNew} onClick={() => setCreatingNew(true)}>
              + New
            </button>
          )}
        </div>

        <div className={styles.tabRow}>
          {CATALOG_TABS.map((t) => (
            <button
              key={t.value}
              className={cn(styles.tab, catalogTab === t.value && styles.tabActive)}
              onClick={() => setCatalogTab(t.value)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className={styles.toolbar}>
          <div className={styles.searchBox}>
            <Icon kind="search" size={14} color="var(--hd-sub)" />
            <input
              className={styles.searchInput}
              type="search"
              placeholder="Search cards, sets…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search collection"
            />
          </div>
          <div className={styles.toolbarRight}>
            <div className={styles.viewToggle} role="group" aria-label="View mode">
              <button
                className={cn(styles.viewBtn, viewMode === 'grid' && styles.viewBtnActive)}
                onClick={() => setViewMode('grid')}
                aria-pressed={viewMode === 'grid'}
                aria-label="Grid view"
                title="Grid view"
              >
                <Icon kind="grid" size={14} color="currentColor" />
              </button>
              <button
                className={cn(styles.viewBtn, viewMode === 'list' && styles.viewBtnActive)}
                onClick={() => setViewMode('list')}
                aria-pressed={viewMode === 'list'}
                aria-label="List view"
                title="List view"
              >
                <Icon kind="list" size={14} color="currentColor" />
              </button>
            </div>
          </div>
        </div>

        {isLoading ? (
          <div className={styles.loading}>Loading…</div>
        ) : viewMode === 'grid' ? (
          <CollectionGrid
            entries={sorted}
            onRemove={handleRemove}
            showFinancials={false}
          />
        ) : (
          <CollectionTable
            entries={sorted}
            onRemove={handleRemove}
            sortBy={sortBy}
            sortDir={sortDir}
            onSort={handleSort}
            collectionId={activeCollectionId ?? undefined}
            showFinancials={false}
          />
        )}

        {isFetchingMore && <div className={styles.loadingMore}>Loading more…</div>}
        {hasMore && !isFetchingMore && <div ref={sentinelRef} className={styles.sentinel} />}
      </div>

      <ToastContainer toasts={toasts} />
    </AppShell>
  )
}
