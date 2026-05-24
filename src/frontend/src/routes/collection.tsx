// src/frontend/src/routes/collection.tsx
import React, { useDeferredValue, useMemo, useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { ToastContainer } from '../components/design-system/Toast'
import { Icon } from '../components/design-system/Icon'
import { CollectionGrid } from '../features/collection/components/CollectionGrid'
import {
  collectionsQueryOptions,
  createCollection,
  deleteCollectionEntry,
} from '../features/collection/api'
import { cn } from '../lib/cn'
import { useInfiniteEntries } from '../features/collection/hooks/useInfiniteEntries'
import { useToast } from '../lib/useToast'
import styles from './Collection.module.css'

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

  const deferredQuery = useDeferredValue(query)

  const { data: collections = [] } = useQuery(collectionsQueryOptions())
  const activeCollectionId = selectedCollectionId ?? collections[0]?.collection_id ?? null

  const {
    allEntries: entries,
    isFetchingMore,
    hasMore,
    removeEntry,
    sentinelRef,
  } = useInfiniteEntries(activeCollectionId)

  const isLoading = entries.length === 0 && isFetchingMore

  const filtered = useMemo(() => {
    let result = entries

    if (catalogTab === 'owned')    result = result.filter((e) => !e.is_wishlist)
    if (catalogTab === 'wishlist') result = result.filter((e) => e.is_wishlist)

    if (deferredQuery.trim()) {
      const q = deferredQuery.toLowerCase()
      result = result.filter(
        (e) => e.card_name.toLowerCase().includes(q) || e.set_code.toLowerCase().includes(q),
      )
    }

    return result
  }, [entries, catalogTab, deferredQuery])

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
        </div>

        {isLoading ? (
          <div className={styles.loading}>Loading…</div>
        ) : (
          <CollectionGrid
            entries={filtered}
            onRemove={handleRemove}
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
