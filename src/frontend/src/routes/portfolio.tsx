// src/frontend/src/routes/portfolio.tsx
import React, { useDeferredValue, useMemo, useState, useCallback } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { Button } from '../components/ui/Button'
import { Icon } from '../components/design-system/Icon'
import { ToastContainer } from '../components/design-system/Toast'
import { CollectionTable } from '../features/collection/components/CollectionTable'
import { CollectionGrid } from '../features/collection/components/CollectionGrid'
import {
  collectionsQueryOptions,
  createCollection,
  deleteCollectionEntry,
} from '../features/collection/api'
import { cn } from '../lib/cn'
import { useInfiniteEntries } from '../features/collection/hooks/useInfiniteEntries'
import { formatUSD } from '../lib/format'
import { useToast } from '../lib/useToast'
import styles from './Portfolio.module.css'

export const Route = createFileRoute('/portfolio')({
  component: CollectionPage,
})

type ViewMode = 'list' | 'grid'
export type SortKey = 'name' | 'set' | 'finish' | 'purchase' | 'pl'
export type SortDir = 'asc' | 'desc'

const FINISH_ORDER: Record<string, number> = { NONFOIL: 0, FOIL: 1, ETCHED: 2 }

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'name',     label: 'Name' },
  { value: 'set',      label: 'Set' },
  { value: 'finish',   label: 'Finish' },
  { value: 'purchase', label: 'Purchase' },
  { value: 'pl',       label: 'P/L' },
]

function CollectionPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { toasts, toast } = useToast()
  const [query, setQuery] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('grid')
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null)
  const [newCollectionName, setNewCollectionName] = useState('')
  const [creatingNew, setCreatingNew] = useState(false)
  const [sortBy, setSortBy] = useState<SortKey>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [finishFilter, setFinishFilter] = useState<Set<string>>(new Set())
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set())
  const [filterPanelOpen, setFilterPanelOpen] = useState(false)

  const deferredQuery = useDeferredValue(query)

  const { data: collections = [] } = useQuery(collectionsQueryOptions())

  const activeCollectionId = selectedCollectionId ?? collections[0]?.collection_id ?? null

  const {
    allEntries: entries,
    isFetchingMore,
    hasMore,
    removeEntry,
    sentinelRef,
  } = useInfiniteEntries(activeCollectionId, false)
  const isLoading = entries.length === 0 && isFetchingMore

  const filtered = useMemo(() => {
    let result = entries
    if (deferredQuery.trim()) {
      const q = deferredQuery.toLowerCase()
      result = result.filter(
        (e) => e.card_name.toLowerCase().includes(q) || e.set_code.toLowerCase().includes(q),
      )
    }
    if (finishFilter.size > 0)
      result = result.filter((e) => finishFilter.has(e.finish))
    if (statusFilter.size > 0)
      result = result.filter((e) => statusFilter.has(e.status))
    return result
  }, [entries, deferredQuery, finishFilter, statusFilter])

  function handleSort(key: SortKey) {
    if (key === sortBy) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortBy(key); setSortDir('asc') }
  }

  const toggleFinish = useCallback((value: string) => {
    setFinishFilter((prev) => {
      const next = new Set(prev)
      next.has(value) ? next.delete(value) : next.add(value)
      return next
    })
  }, [])

  const toggleStatus = useCallback((value: string) => {
    setStatusFilter((prev) => {
      const next = new Set(prev)
      next.has(value) ? next.delete(value) : next.add(value)
      return next
    })
  }, [])

  const clearFilters = useCallback(() => {
    setFinishFilter(new Set())
    setStatusFilter(new Set())
  }, [])

  const hasActiveFilters = finishFilter.size > 0 || statusFilter.size > 0

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

  const metrics = useMemo(() => {
    const totalValue = entries.reduce((s, e) => s + (e.price ?? 0), 0)
    const costBasis = entries.reduce((s, e) => s + Number(e.purchase_price), 0)
    return { totalValue, costBasis, pl: totalValue - costBasis, count: entries.length }
  }, [entries])

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

  const plSign = metrics.pl >= 0 ? '+' : '-'

  return (
    <AppShell active="portfolio">
      <TopBar title="Portfolio" />

      <div className={styles.page}>
        <header className={styles.header}>
          <div className={styles.titleBlock}>
            <div className={styles.eyebrow}>automana / portfolio</div>
            <h1 className={styles.title}>Your Portfolio</h1>
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

        <div className={styles.tabRow}>
          {collections.map((col) => (
            <button
              key={col.collection_id}
              className={cn(styles.tab, col.collection_id === activeCollectionId && styles.tabActive)}
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
              <div className={cn(styles.metricValue, metrics.pl >= 0 ? styles.positive : styles.negative)}>
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
          <button
            className={cn(styles.filterBtn, filterPanelOpen && styles.filterBtnActive)}
            onClick={() => setFilterPanelOpen((o) => !o)}
            aria-expanded={filterPanelOpen}
            aria-label="Toggle filters"
          >
            ⊞ Filters{hasActiveFilters ? ` (${finishFilter.size + statusFilter.size})` : ''}
          </button>
          <div className={styles.toolbarRight}>
            <div className={styles.sortControl}>
              <select
                className={styles.sortSelect}
                value={sortBy}
                onChange={(e) => handleSort(e.target.value as SortKey)}
                aria-label="Sort by"
              >
                {SORT_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <button
                className={styles.sortDirBtn}
                onClick={() => setSortDir(d => d === 'asc' ? 'desc' : 'asc')}
                aria-label={sortDir === 'asc' ? 'Sort ascending' : 'Sort descending'}
                title={sortDir === 'asc' ? 'Ascending' : 'Descending'}
              >
                {sortDir === 'asc' ? '↑' : '↓'}
              </button>
            </div>
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

        {filterPanelOpen && (
          <div className={styles.filterPanel}>
            <div className={styles.filterGroup}>
              <div className={styles.filterGroupLabel}>Finish</div>
              <div className={styles.filterGroupPills}>
                {(['NONFOIL', 'FOIL', 'ETCHED'] as const).map((f) => (
                  <button
                    key={f}
                    className={cn(styles.filterPill, finishFilter.has(f) && styles.filterPillActive)}
                    onClick={() => toggleFinish(f)}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>
            <div className={styles.filterGroup}>
              <div className={styles.filterGroupLabel}>Status</div>
              <div className={styles.filterGroupPills}>
                {(['purchased', 'listed', 'stashed', 'sold'] as const).map((s) => (
                  <button
                    key={s}
                    className={cn(styles.filterPill, statusFilter.has(s) && styles.filterPillActive)}
                    onClick={() => toggleStatus(s)}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {hasActiveFilters && (
          <div className={styles.filterRow}>
            {[...finishFilter].map((f) => (
              <button key={f} className={styles.filterPillDismiss} onClick={() => toggleFinish(f)}>
                Finish: {f} ×
              </button>
            ))}
            {[...statusFilter].map((s) => (
              <button key={s} className={styles.filterPillDismiss} onClick={() => toggleStatus(s)}>
                Status: {s} ×
              </button>
            ))}
            <button className={styles.clearAll} onClick={clearFilters}>Clear all</button>
          </div>
        )}

        {isLoading ? (
          <div className={styles.loading}>Loading…</div>
        ) : viewMode === 'grid' ? (
          <CollectionGrid entries={sorted} onRemove={handleRemove} />
        ) : (
          <CollectionTable
            entries={sorted}
            onRemove={handleRemove}
            sortBy={sortBy}
            sortDir={sortDir}
            onSort={handleSort}
            collectionId={activeCollectionId ?? undefined}
          />
        )}

        {isFetchingMore && <div className={styles.loadingMore}>Loading more…</div>}
        {hasMore && !isFetchingMore && <div ref={sentinelRef} className={styles.sentinel} />}
      </div>
      <ToastContainer toasts={toasts} />
    </AppShell>
  )
}
