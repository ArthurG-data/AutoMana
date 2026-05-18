// src/frontend/src/routes/collection.tsx
import React, { useDeferredValue, useMemo, useState } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { Button } from '../components/ui/Button'
import { Icon } from '../components/design-system/Icon'
import { CollectionTable } from '../features/collection/components/CollectionTable'
import { CollectionGrid } from '../features/collection/components/CollectionGrid'
import {
  collectionsQueryOptions,
  collectionEntriesQueryOptions,
  createCollection,
  deleteCollectionEntry,
} from '../features/collection/api'
import styles from './Collection.module.css'

export const Route = createFileRoute('/collection')({
  component: CollectionPage,
})

type ViewMode = 'list' | 'grid'

function formatUSD(n: number): string {
  return `$${n.toFixed(2)}`
}

function CollectionPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [query, setQuery] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('grid')
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null)
  const [newCollectionName, setNewCollectionName] = useState('')
  const [creatingNew, setCreatingNew] = useState(false)

  const deferredQuery = useDeferredValue(query)

  const { data: collections = [] } = useQuery(collectionsQueryOptions())

  const activeCollectionId = selectedCollectionId ?? collections[0]?.collection_id ?? null

  const { data: entries = [], isLoading } = useQuery(
    collectionEntriesQueryOptions(activeCollectionId ?? ''),
  )

  const filtered = useMemo(() => {
    if (!deferredQuery.trim()) return entries
    const q = deferredQuery.toLowerCase()
    return entries.filter(
      (e) =>
        e.card_name.toLowerCase().includes(q) ||
        e.set_code.toLowerCase().includes(q),
    )
  }, [entries, deferredQuery])

  const metrics = useMemo(() => {
    const totalValue = entries.reduce((s, e) => s + (e.price ?? 0), 0)
    const costBasis = entries.reduce((s, e) => s + Number(e.purchase_price), 0)
    return { totalValue, costBasis, pl: totalValue - costBasis, count: entries.length }
  }, [entries])

  async function handleRemove(itemId: string) {
    if (!activeCollectionId) return
    await deleteCollectionEntry(activeCollectionId, itemId)
    queryClient.invalidateQueries({
      queryKey: collectionEntriesQueryOptions(activeCollectionId).queryKey,
    })
  }

  async function handleCreateCollection() {
    if (!newCollectionName.trim()) return
    const col = await createCollection(newCollectionName.trim())
    queryClient.invalidateQueries({ queryKey: collectionsQueryOptions().queryKey })
    setSelectedCollectionId(col.collection_id)
    setCreatingNew(false)
    setNewCollectionName('')
  }

  const plSign = metrics.pl >= 0 ? '+' : ''

  return (
    <AppShell active="collection">
      <TopBar title="Collection" />

      <div className={styles.page}>
        {/* ── Header ──────────────────────────────── */}
        <header className={styles.header}>
          <div className={styles.titleBlock}>
            <div className={styles.eyebrow}>automana / collection</div>
            <h1 className={styles.title}>Your vault</h1>
          </div>
          <div className={styles.headerActions}>
            <Button
              variant="accent"
              size="sm"
              icon={<Icon kind="tag" size={13} color="currentColor" />}
              onClick={() => navigate({ to: '/listings' })}
            >
              Bulk list
            </Button>
          </div>
        </header>

        {/* ── Collection tabs ──────────────────────── */}
        <div className={styles.tabRow}>
          {collections.map((col) => (
            <button
              key={col.collection_id}
              className={[
                styles.tab,
                col.collection_id === activeCollectionId ? styles.tabActive : '',
              ].filter(Boolean).join(' ')}
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

        {/* ── Metrics strip ─────────────────────── */}
        <section aria-label="Portfolio metrics">
          <div className={styles.metricsStrip}>
            <div className={styles.metricCard}>
              <div className={styles.metricLabel}>Total value</div>
              <div className={styles.metricValue}>{formatUSD(metrics.totalValue)}</div>
              <div className={styles.metricSub}>across {metrics.count} cards</div>
            </div>
            <div className={styles.metricCard}>
              <div className={styles.metricLabel}>Cost basis</div>
              <div className={styles.metricValue}>{formatUSD(metrics.costBasis)}</div>
              <div className={styles.metricSub}>total invested</div>
            </div>
            <div className={styles.metricCard}>
              <div className={styles.metricLabel}>Unrealized P/L</div>
              <div
                className={[
                  styles.metricValue,
                  metrics.pl >= 0 ? styles.positive : styles.negative,
                ].join(' ')}
              >
                {plSign}{formatUSD(Math.abs(metrics.pl))}
              </div>
              <div className={styles.metricSub}>vs cost basis</div>
            </div>
            <div className={styles.metricCard}>
              <div className={styles.metricLabel}>Cards owned</div>
              <div className={styles.metricValue}>{metrics.count}</div>
              <div className={styles.metricSub}>unique entries</div>
            </div>
          </div>
        </section>

        {/* ── Toolbar ───────────────────────────── */}
        <div className={styles.toolbar} role="toolbar" aria-label="Collection filters">
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
                className={[
                  styles.viewBtn,
                  viewMode === 'grid' ? styles.viewBtnActive : '',
                ].filter(Boolean).join(' ')}
                onClick={() => setViewMode('grid')}
                aria-pressed={viewMode === 'grid'}
                aria-label="Grid view"
                title="Grid view"
              >
                <Icon kind="grid" size={14} color="currentColor" />
              </button>
              <button
                className={[
                  styles.viewBtn,
                  viewMode === 'list' ? styles.viewBtnActive : '',
                ].filter(Boolean).join(' ')}
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

        {/* ── Main content ──────────────────────── */}
        {isLoading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--hd-sub)' }}>
            Loading…
          </div>
        ) : viewMode === 'grid' ? (
          <CollectionGrid entries={filtered} onRemove={handleRemove} />
        ) : (
          <CollectionTable entries={filtered} onRemove={handleRemove} />
        )}
      </div>
    </AppShell>
  )
}
