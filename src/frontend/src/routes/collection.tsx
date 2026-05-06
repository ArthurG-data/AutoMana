// src/frontend/src/routes/collection.tsx
import React, { useDeferredValue, useMemo, useState } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { Button } from '../components/ui/Button'
import { AIBadge, type AIStatus } from '../components/design-system/AIBadge'
import { Icon } from '../components/design-system/Icon'
import { Pip, type ManaColor } from '../components/design-system/Pip'
import { CollectionTable } from '../features/collection/components/CollectionTable'
import {
  MOCK_COLLECTION,
  computeMetrics,
  formatUSD,
  type StatusFilter,
  type ColorFilter,
} from '../features/collection/mockCollection'
import styles from './Collection.module.css'

export const Route = createFileRoute('/collection')({
  component: CollectionPage,
})

// ── Status filter config ────────────────────────────────────────
const STATUS_FILTERS: { label: string; value: StatusFilter }[] = [
  { label: 'All', value: 'all' },
  { label: 'Listed', value: 'listed' },
  { label: 'Ready', value: 'ready' },
  { label: 'Watching', value: 'watching' },
  { label: 'Vault', value: 'vault' },
]

const MANA_COLORS: { color: ManaColor; label: string }[] = [
  { color: 'W', label: 'White' },
  { color: 'U', label: 'Blue' },
  { color: 'B', label: 'Black' },
  { color: 'R', label: 'Red' },
  { color: 'G', label: 'Green' },
  { color: 'C', label: 'Colorless' },
]

// Color split bar fills
const COLOR_FILL: Record<ManaColor, string> = {
  W: '#fffbe6',
  U: '#cfe7f5',
  B: '#cbc2bf',
  R: '#f5b9a4',
  G: '#bce3c5',
  C: '#dcd6cb',
}

type ViewMode = 'list' | 'grid'

function CollectionPage() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [colorFilter, setColorFilter] = useState<ColorFilter>('all')
  // TODO: implement grid view card display; only list view is built
  const [viewMode, setViewMode] = useState<ViewMode>('list')

  // Defer expensive re-filter on each keystroke
  const deferredQuery = useDeferredValue(query)

  const filtered = useMemo(() => {
    let cards = MOCK_COLLECTION

    if (statusFilter !== 'all') {
      cards = cards.filter((c) => c.aiStatus === statusFilter)
    }
    if (colorFilter !== 'all') {
      cards = cards.filter((c) => c.colors.includes(colorFilter as ManaColor))
    }
    if (deferredQuery.trim()) {
      const q = deferredQuery.toLowerCase()
      cards = cards.filter(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          c.setCode.toLowerCase().includes(q) ||
          c.set.toLowerCase().includes(q)
      )
    }

    return cards
  }, [deferredQuery, statusFilter, colorFilter])

  const metrics = useMemo(() => computeMetrics(MOCK_COLLECTION), [])
  const readyCards = useMemo(
    () => MOCK_COLLECTION.filter((c) => c.aiStatus === 'ready'),
    []
  )

  // Color split calculation
  const colorSplit = useMemo(() => {
    const counts: Record<ManaColor, number> = { W: 0, U: 0, B: 0, R: 0, G: 0, C: 0 }
    for (const card of MOCK_COLLECTION) {
      for (const color of card.colors) {
        counts[color] += card.qty
      }
    }
    const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1
    return MANA_COLORS.map(({ color, label }) => ({
      color,
      label,
      pct: Math.round((counts[color] / total) * 100),
    }))
  }, [])

  function handleList(_card: { name: string }) {
    navigate({ to: '/listings' })
  }

  function handleMore(_card: unknown) {
    // TODO: open card context menu / drawer
  }

  function handleBulkList() {
    navigate({ to: '/listings' })
  }

  const plSign = metrics.unrealizedPL >= 0 ? '+' : ''

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
            <Button variant="ghost" size="sm">
              Import CSV
            </Button>
            <Button variant="ghost" size="sm" icon={<Icon kind="plus" size={13} color="currentColor" />}>
              Add cards
            </Button>
            <Button
              variant="accent"
              size="sm"
              icon={<Icon kind="tag" size={13} color="currentColor" />}
              onClick={handleBulkList}
            >
              Bulk list
            </Button>
          </div>
        </header>

        {/* ── Metrics strip ─────────────────────── */}
        <section aria-label="Portfolio metrics">
          <div className={styles.metricsStrip}>
            <div className={styles.metricCard}>
              <div className={styles.metricLabel}>Total value</div>
              <div className={styles.metricValue}>{formatUSD(metrics.totalValue)}</div>
              <div className={styles.metricSub}>across {metrics.cardsOwned} cards</div>
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
                  metrics.unrealizedPL >= 0 ? styles.positive : styles.negative,
                ].join(' ')}
              >
                {plSign}{formatUSD(metrics.unrealizedPL)}
              </div>
              <div className={styles.metricSub}>vs cost basis</div>
            </div>
            <div className={styles.metricCard}>
              <div className={styles.metricLabel}>Cards owned</div>
              <div className={styles.metricValue}>{metrics.cardsOwned}</div>
              <div className={styles.metricSub}>unique printings</div>
            </div>
            <button
              className={[styles.metricCard, styles.metricCardLink].join(' ')}
              onClick={() => navigate({ to: '/listings' })}
              aria-label="View eBay listings"
            >
              <div className={styles.metricLabel}>Listed on eBay</div>
              <div className={styles.metricValue}>{metrics.listedOnEbay}</div>
              <div className={styles.metricSub}>active listings</div>
            </button>
          </div>
        </section>

        {/* ── AI banner ─────────────────────────── */}
        {readyCards.length > 0 && (
          <section aria-label="AI listing recommendations">
            <div className={styles.aiBanner}>
              <div className={styles.aiBannerLeft}>
                <div className={styles.aiBannerIcon}>
                  <Icon kind="sparkle" size={18} color="var(--hd-accent)" />
                </div>
                <div className={styles.aiBannerText}>
                  <div className={styles.aiBannerHeadline}>
                    {readyCards.length} card{readyCards.length !== 1 ? 's' : ''} ready to list
                  </div>
                  <div className={styles.aiBannerSub}>
                    Price strategy met — list now to lock in gains
                  </div>
                </div>
              </div>
              <div className={styles.aiBannerActions}>
                <Button variant="ghost" size="sm" onClick={() => setStatusFilter('ready')}>
                  Review
                </Button>
                <Button
                  variant="accent"
                  size="sm"
                  icon={<Icon kind="tag" size={12} color="currentColor" />}
                  onClick={handleBulkList}
                >
                  List all {readyCards.length}
                </Button>
              </div>
            </div>
          </section>
        )}

        {/* ── Main content grid ─────────────────── */}
        <div className={styles.contentGrid}>
          {/* Left: table */}
          <div>
            {/* Toolbar */}
            <div className={styles.toolbar} role="toolbar" aria-label="Collection filters">
              {/* Search */}
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

              {/* Status chips */}
              <div className={styles.filterChips} role="group" aria-label="Filter by status">
                {STATUS_FILTERS.map(({ label, value }) => (
                  <button
                    key={value}
                    className={[
                      styles.filterChip,
                      statusFilter === value ? styles.filterChipActive : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    onClick={() => setStatusFilter(value)}
                    aria-pressed={statusFilter === value}
                  >
                    {value !== 'all' && (
                      <AIBadge status={value as AIStatus} showLabel={false} />
                    )}
                    {label}
                  </button>
                ))}
              </div>

              {/* Color pip filter */}
              <div className={styles.colorFilters} role="group" aria-label="Filter by color">
                {MANA_COLORS.map(({ color, label }) => (
                  <button
                    key={color}
                    className={[
                      styles.colorFilterBtn,
                      colorFilter === color ? styles.colorFilterBtnActive : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    onClick={() =>
                      setColorFilter((prev) => (prev === color ? 'all' : color))
                    }
                    aria-pressed={colorFilter === color}
                    aria-label={`Filter by ${label}`}
                    title={label}
                  >
                    <Pip color={color} size={20} />
                  </button>
                ))}
              </div>

              {/* View toggle */}
              <div className={styles.toolbarRight}>
                <div
                  className={styles.viewToggle}
                  role="group"
                  aria-label="View mode"
                >
                  <button
                    className={[
                      styles.viewBtn,
                      viewMode === 'list' ? styles.viewBtnActive : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    onClick={() => setViewMode('list')}
                    aria-pressed={viewMode === 'list'}
                    aria-label="List view"
                    title="List view"
                  >
                    <Icon kind="list" size={14} color="currentColor" />
                  </button>
                  <button
                    className={[
                      styles.viewBtn,
                      viewMode === 'grid' ? styles.viewBtnActive : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    onClick={() => setViewMode('grid')}
                    aria-pressed={viewMode === 'grid'}
                    aria-label="Grid view"
                    title="Grid view (coming soon)"
                  >
                    <Icon kind="grid" size={14} color="currentColor" />
                  </button>
                </div>
              </div>
            </div>

            {/* Collection table */}
            <CollectionTable
              cards={filtered}
              onList={handleList}
              onMore={handleMore}
            />
          </div>

          {/* Right: sidebar */}
          <aside className={styles.sidebar} aria-label="Collection sidebar">
            {/* Listing status legend */}
            <div className={styles.sidePanel}>
              <div className={styles.sidePanelTitle}>Listing status</div>
              {(
                [
                  { status: 'listed', desc: 'Currently on eBay' },
                  { status: 'ready', desc: 'Price meets strategy' },
                  { status: 'watching', desc: 'Bot watching for peak' },
                  { status: 'vault', desc: 'No automation' },
                ] as { status: AIStatus; desc: string }[]
              ).map(({ status, desc }) => (
                <div key={status} className={styles.legendRow}>
                  <AIBadge status={status} showLabel />
                  <span style={{ fontSize: 11, color: 'var(--hd-sub)', marginLeft: 8 }}>
                    {desc}
                  </span>
                </div>
              ))}
            </div>

            {/* Ready to list */}
            {readyCards.length > 0 && (
              <div className={styles.sidePanel}>
                <div className={styles.sidePanelTitle}>
                  Ready to list ({readyCards.length})
                </div>
                {readyCards.map((card) => (
                  <div key={card.id} className={styles.readyCard}>
                    <div className={styles.readyCardName}>{card.name}</div>
                    <div className={styles.readyCardPrice}>
                      {formatUSD(card.marketPrice)}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Color split */}
            <div className={styles.sidePanel}>
              <div className={styles.sidePanelTitle}>Color split</div>
              {colorSplit
                .filter(({ pct }) => pct > 0)
                .map(({ color, label, pct }) => (
                  <div key={color} className={styles.colorSplitRow}>
                    <Pip color={color} size={13} />
                    <span className={styles.colorSplitLabel}>{label}</span>
                    <div className={styles.colorSplitBar}>
                      <div
                        className={styles.colorSplitFill}
                        style={{
                          width: `${pct}%`,
                          background: COLOR_FILL[color],
                        }}
                        role="progressbar"
                        aria-valuenow={pct}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-label={`${label} ${pct}%`}
                      />
                    </div>
                    <span className={styles.colorSplitValue}>{pct}%</span>
                  </div>
                ))}
            </div>
          </aside>
        </div>
      </div>
    </AppShell>
  )
}
