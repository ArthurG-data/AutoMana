// src/frontend/src/routes/listings.tsx
import { useState, useEffect, useRef, useCallback } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { Button } from '../components/ui/Button'
import { Icon } from '../components/design-system/Icon'
import { ListingsTable } from '../features/ebay/components/ListingsTable'
import { ListingDetailPanel } from '../features/ebay/components/ListingDetailPanel'
import { ListingFormPanel, CONDITION_OPTIONS, type ListingFormValues } from '../features/ebay/components/ListingFormPanel'
import { MarketComparePanel } from '../features/ebay/components/MarketComparePanel'
import {
  updateListing,
  fetchRecommendation,
  userAppsQueryOptions,
  activeListingsPageQueryOptions,
  soldOrdersPageQueryOptions,
  type EbayAppSummary,
} from '../features/ebay/api'
import { SoldOrdersTable } from '../features/ebay/components/SoldOrdersTable'
import { SoldOrderDetailPanel } from '../features/ebay/components/SoldOrderDetailPanel'
import type { SoldOrder, DisplayStatus } from '../features/ebay/soldOrders'
import { enrichWithCatalog } from '../features/ebay/lib/catalogEnrich'
import { useListingsStore } from '../store/listings'
import type { EbayLiveListing } from '../features/ebay/mockListings'
import styles from './Listings.module.css'

const LIMIT = 25

export const Route = createFileRoute('/listings')({
  loader: async ({ context: { queryClient } }) => {
    const apps = await queryClient.fetchQuery(userAppsQueryOptions())
    const productionApps = apps.filter((a) => a.environment === 'PRODUCTION')
    await Promise.allSettled(
      productionApps.map((app) =>
        queryClient.prefetchQuery(activeListingsPageQueryOptions(app.app_code, LIMIT, 0))
      )
    )
  },
  component: ListingsPage,
})

type Tab = 'active' | 'sold' | 'saved'

export function ListingsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<Tab>('active')
  const [listings, setListings] = useState<EbayLiveListing[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [failedApps, setFailedApps] = useState<string[]>([])
  const [dismissedApps, setDismissedApps] = useState<Set<string>>(new Set())
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [panelMode, setPanelMode] = useState<'detail' | 'edit' | 'compare'>('detail')
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [imageUrls, setImageUrls] = useState<string[]>([])
  const [productionApps, setProductionApps] = useState<EbayAppSummary[]>([])
  const [soldOrders, setSoldOrders] = useState<SoldOrder[]>([])
  const [isSoldLoading, setIsSoldLoading] = useState(false)
  const [isSoldLoadingMore, setIsSoldLoadingMore] = useState(false)
  const [hasSoldMore, setHasSoldMore] = useState(false)
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null)
  const [totalActive, setTotalActive] = useState<number | null>(null)
  const storeSet = useListingsStore((s) => s.setListings)
  const selectedListing = useListingsStore((s) => s.getById(selectedId ?? ''))
  const storeUpdateListing = useListingsStore((s) => s.updateListing)

  // Pagination state in refs — updates don't need to trigger re-renders
  const appsRef = useRef<EbayAppSummary[]>([])
  const offsetsRef = useRef<Record<string, number>>({})
  const hasMoreRef = useRef<Record<string, boolean>>({})
  const listingsRef = useRef<EbayLiveListing[]>([])
  const isLoadingMoreRef = useRef(false)
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  const soldOffsetsRef = useRef<Record<string, number>>({})
  const soldHasMoreRef = useRef<Record<string, boolean>>({})
  const isSoldLoadingMoreRef = useRef(false)
  const soldSentinelRef = useRef<HTMLDivElement | null>(null)

  // Fire-and-forget: fetch a recommendation for each listing that doesn't already have one.
  // Results update the ref and both the table state and the store, so the detail panel stays in sync.
  const fetchRecommendationsForBatch = useCallback(
    (batch: EbayLiveListing[], cancelledRef: { current: boolean }) => {
      batch.forEach((listing) => {
        if (listing.recommendation) return
        fetchRecommendation(listing.appCode, listing)
          .then((result) => {
            if (cancelledRef.current) return
            const { item_id: _item_id, ...rec } = result
            const updated = listingsRef.current.map((l) =>
              l.itemId === listing.itemId ? { ...l, recommendation: rec } : l
            )
            listingsRef.current = updated
            setListings(updated)
            storeUpdateListing(listing.itemId, { recommendation: rec })
          })
          .catch(() => {
            // Silently ignore per-listing failures — badge stays absent
          })
      })
    },
    [storeUpdateListing]
  )

  useEffect(() => {
    const cancelledRef = { current: false }
    async function load() {
      setIsLoading(true)
      try {
        // fetchQuery returns cached data if still fresh (staleTime not exceeded),
        // otherwise fetches from network and populates the persisted cache.
        const apps = await queryClient.fetchQuery(userAppsQueryOptions())
        const productionApps = apps.filter((a) => a.environment === 'PRODUCTION')
        appsRef.current = productionApps
        setProductionApps(productionApps)

        const results = await Promise.allSettled(
          productionApps.map((app) =>
            queryClient
              .fetchQuery(activeListingsPageQueryOptions(app.app_code, LIMIT, 0))
              .then(({ items, hasMore: more, total }) => {
                hasMoreRef.current[app.app_code] = more
                offsetsRef.current[app.app_code] = items.length
                return { items: items.map((item) => ({ ...item, appName: app.app_name })), total }
              })
          )
        )

        if (cancelledRef.current) return

        const merged: EbayLiveListing[] = []
        const failed: string[] = []
        let knownTotal: number | null = null
        results.forEach((result, i) => {
          if (result.status === 'fulfilled') {
            merged.push(...result.value.items)
            if (result.value.total !== null) {
              knownTotal = (knownTotal ?? 0) + result.value.total
            }
          } else {
            failed.push(productionApps[i].app_name)
          }
        })
        setTotalActive(knownTotal)

        listingsRef.current = merged
        setListings(merged)
        storeSet(merged)
        setFailedApps(failed)
        setHasMore(Object.values(hasMoreRef.current).some(Boolean))

        // queryClient.fetchQuery inside enrichWithCatalog deduplicates concurrent
        // name lookups and caches results for 24h via cardSuggestQueryOptions.
        try {
          const enriched = await enrichWithCatalog(merged, queryClient)
          if (!cancelledRef.current) {
            listingsRef.current = enriched
            setListings(enriched)
            storeSet(enriched)
            // Fire-and-forget recommendation fetches after enrichment is stable
            fetchRecommendationsForBatch(enriched, cancelledRef)
          }
        } catch {
          // Keep title-parsed values; still try recommendations on the unenriched batch
          if (!cancelledRef.current) {
            fetchRecommendationsForBatch(merged, cancelledRef)
          }
        }
      } catch {
        // fetchUserApps failed — leave table empty
      } finally {
        if (!cancelledRef.current) setIsLoading(false)
      }
    }
    load()
    return () => { cancelledRef.current = true }
  }, [queryClient, storeSet, fetchRecommendationsForBatch])

  const loadMore = useCallback(async () => {
    if (isLoadingMoreRef.current) return
    const pendingApps = appsRef.current.filter((a) => hasMoreRef.current[a.app_code])
    if (pendingApps.length === 0) return

    isLoadingMoreRef.current = true
    setIsLoadingMore(true)

    const results = await Promise.allSettled(
      pendingApps.map((app) => {
        const offset = offsetsRef.current[app.app_code] ?? 0
        return queryClient
          .fetchQuery(activeListingsPageQueryOptions(app.app_code, LIMIT, offset))
          .then(({ items, hasMore: more }) => {
            hasMoreRef.current[app.app_code] = more
            offsetsRef.current[app.app_code] = offset + items.length
            return items.map((item) => ({ ...item, appName: app.app_name }))
          })
      })
    )

    const newItems: EbayLiveListing[] = []
    results.forEach((r) => {
      if (r.status === 'fulfilled') newItems.push(...r.value)
    })

    if (newItems.length > 0) {
      const merged = [...listingsRef.current, ...newItems]
      listingsRef.current = merged
      setListings(merged)
      storeSet(merged)

      // loadMore has no cancellation token — component is mounted while pagination runs
      const loadMoreCancelledRef = { current: false }
      try {
        const enriched = await enrichWithCatalog(newItems, queryClient)
        const current = listingsRef.current
        const updated = [...current.slice(0, current.length - newItems.length), ...enriched]
        listingsRef.current = updated
        setListings(updated)
        storeSet(updated)
        fetchRecommendationsForBatch(enriched, loadMoreCancelledRef)
      } catch {
        // Keep title-parsed values for new batch; still fetch recommendations
        fetchRecommendationsForBatch(newItems, loadMoreCancelledRef)
      }
    }

    setHasMore(Object.values(hasMoreRef.current).some(Boolean))
    isLoadingMoreRef.current = false
    setIsLoadingMore(false)
  }, [queryClient, storeSet, fetchRecommendationsForBatch])

  useEffect(() => {
    if (tab !== 'sold') return
    soldOffsetsRef.current = {}
    soldHasMoreRef.current = {}
    let cancelled = false
    async function loadSold() {
      setIsSoldLoading(true)
      try {
        const results = await Promise.allSettled(
          productionApps.map((app) =>
            queryClient
              .fetchQuery(soldOrdersPageQueryOptions(app.app_code, LIMIT, 0))
              .then(({ orders, hasMore: more }) => {
                soldHasMoreRef.current[app.app_code] = more
                soldOffsetsRef.current[app.app_code] = orders.length
                return orders.map((o) => ({ ...o, appName: app.app_name }))
              })
          )
        )
        if (cancelled) return
        const merged: SoldOrder[] = []
        results.forEach((r) => { if (r.status === 'fulfilled') merged.push(...r.value) })
        setSoldOrders(merged)
        setHasSoldMore(Object.values(soldHasMoreRef.current).some(Boolean))
      } finally {
        if (!cancelled) setIsSoldLoading(false)
      }
    }
    loadSold()
    return () => { cancelled = true }
  }, [tab, productionApps, queryClient])

  const loadMoreSold = useCallback(async () => {
    if (isSoldLoadingMoreRef.current) return
    const pendingApps = appsRef.current.filter((a) => soldHasMoreRef.current[a.app_code])
    if (pendingApps.length === 0) return

    isSoldLoadingMoreRef.current = true
    setIsSoldLoadingMore(true)

    const results = await Promise.allSettled(
      pendingApps.map((app) => {
        const offset = soldOffsetsRef.current[app.app_code] ?? 0
        return queryClient
          .fetchQuery(soldOrdersPageQueryOptions(app.app_code, LIMIT, offset))
          .then(({ orders, hasMore: more }) => {
            soldHasMoreRef.current[app.app_code] = more
            soldOffsetsRef.current[app.app_code] = offset + orders.length
            return orders.map((o) => ({ ...o, appName: app.app_name }))
          })
      })
    )

    const newOrders: SoldOrder[] = []
    results.forEach((r) => { if (r.status === 'fulfilled') newOrders.push(...r.value) })
    if (newOrders.length > 0) setSoldOrders((prev) => [...prev, ...newOrders])

    setHasSoldMore(Object.values(soldHasMoreRef.current).some(Boolean))
    isSoldLoadingMoreRef.current = false
    setIsSoldLoadingMore(false)
  }, [queryClient])

  function handleRowClick(id: string) {
    setSelectedId(id)
    setPanelMode('detail')
    setSaveError(null)
    const listing = listingsRef.current.find((l) => l.itemId === id)
    setImageUrls(listing?.imageUrl ? [listing.imageUrl] : [])
  }

  function handleOrderStatusChange(orderId: string, newStatus: DisplayStatus) {
    setSoldOrders((prev) =>
      prev.map((o) => o.orderId === orderId ? { ...o, displayStatus: newStatus, local_status: newStatus } : o)
    )
  }

  async function handleUpdateListing(values: ListingFormValues, appCode: string) {
    if (!selectedId || !selectedListing) return
    setIsSaving(true)
    setSaveError(null)
    try {
      await updateListing(appCode, selectedId, {
        title: values.title,
        startPrice: { currency: 'AUD', value: values.price },
        quantity: values.quantity,
        conditionID: values.conditionId,
        ...(values.description ? { description: values.description } : {}),
        pictureUrls: imageUrls,
      })
      const conditionLabel =
        CONDITION_OPTIONS.find((o) => o.value === values.conditionId)?.label ?? ''
      const patch = {
        price: values.price,
        title: values.title,
        conditionId: values.conditionId,
        conditionLabel,
        imageUrl: imageUrls[0] ?? null,
      }
      storeUpdateListing(selectedId, patch)
      const updated = listingsRef.current.map((l) =>
        l.itemId === selectedId ? { ...l, ...patch } : l
      )
      listingsRef.current = updated
      setListings(updated)
      setPanelMode('detail')
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to update listing')
    } finally {
      setIsSaving(false)
    }
  }

  useEffect(() => {
    if (isSoldLoading || tab !== 'sold') return
    const el = soldSentinelRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting) loadMoreSold() },
      { rootMargin: '200px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [isSoldLoading, tab, loadMoreSold])

  // Set up IntersectionObserver once the sentinel is in the DOM (after initial load).
  useEffect(() => {
    if (isLoading || tab !== 'active') return
    const el = sentinelRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting) loadMore() },
      { rootMargin: '200px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [isLoading, tab, loadMore])

  const visibleBanners = failedApps.filter((name) => !dismissedApps.has(name))

  return (
    <AppShell active="listings">
      <TopBar
        title="Your listings"
        actions={
          <div style={{ display: 'flex', gap: 8 }}>
            <Button variant="ghost" size="sm">Import</Button>
            <Button
              variant="accent"
              size="sm"
              icon={<Icon kind="plus" size={12} color="currentColor" />}
              onClick={() => navigate({ to: '/listings/new' })}
            >
              New listing
            </Button>
          </div>
        }
      />

      <div className={styles.page}>
        {/* ── Error banners ────────────────────────────────────── */}
        {visibleBanners.map((appName) => (
          <div key={appName} className={styles.errorBanner} role="alert">
            <span>Could not load listings for {appName}.</span>
            <button
              className={styles.errorBannerDismiss}
              aria-label="Dismiss"
              onClick={() => setDismissedApps((prev) => new Set([...prev, appName]))}
            >
              <Icon kind="close" size={12} color="currentColor" />
            </button>
          </div>
        ))}

        {/* ── Tabs ─────────────────────────────────────────────── */}
        <div className={styles.tabRow} role="tablist" aria-label="Listing tabs">
          {(['active', 'sold', 'saved'] as Tab[]).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              className={[styles.tab, tab === t ? styles.tabActive : ''].filter(Boolean).join(' ')}
              onClick={() => setTab(t)}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
              {t === 'active' && !isLoading && (
                <span className={styles.tabCount}>
                  {totalActive !== null ? totalActive : `${listings.length}${hasMore ? '+' : ''}`}
                </span>
              )}
              {t === 'sold' && !isSoldLoading && soldOrders.length > 0 && (
                <span className={styles.tabCount}>{soldOrders.length}</span>
              )}
            </button>
          ))}
        </div>

        {/* ── Content ───────────────────────────────────────────── */}
        {tab === 'active' && (
          <div className={selectedId && panelMode !== 'compare' ? styles.withPanel : undefined}>
            {panelMode !== 'compare' && (
              <div>
                <ListingsTable
                  listings={listings}
                  isLoading={isLoading}
                  selectedId={selectedId ?? undefined}
                  onRowClick={handleRowClick}
                />
                {!isLoading && (
                  <>
                    <div ref={sentinelRef} style={{ height: 1 }} aria-hidden />
                    {isLoadingMore && (
                      <div className={styles.loadingMore}>Loading more listings…</div>
                    )}
                    {!hasMore && listings.length > 0 && !isLoadingMore && (
                      <div className={styles.endOfList}>
                        {listings.length} listing{listings.length !== 1 ? 's' : ''} total
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            {selectedId && selectedListing && panelMode !== 'compare' && (
              <div>
                {panelMode === 'detail' ? (
                  <ListingDetailPanel
                    listing={selectedListing}
                    onEdit={() => setPanelMode('edit')}
                    onClose={() => { setSelectedId(null); setPanelMode('detail') }}
                    onCompare={() => setPanelMode('compare')}
                  />
                ) : (
                  <ListingFormPanel
                    mode="edit"
                    initialValues={{
                      title: selectedListing.title,
                      price: selectedListing.price,
                      quantity: selectedListing.quantity ?? 1,
                      conditionId: selectedListing.conditionId ?? 3000,
                      description: '',
                    }}
                    availableApps={productionApps}
                    appCode={selectedListing.appCode}
                    imageUrls={imageUrls}
                    onImageChange={setImageUrls}
                    onSave={handleUpdateListing}
                    onCancel={() => setPanelMode('detail')}
                    isSaving={isSaving}
                    error={saveError}
                  />
                )}
              </div>
            )}

            {selectedId && selectedListing && panelMode === 'compare' && (
              <MarketComparePanel
                listing={selectedListing}
                onBack={() => setPanelMode('detail')}
              />
            )}
          </div>
        )}

        {tab === 'sold' && (
          <div className={selectedOrderId ? styles.withPanel : undefined}>
            <div>
              <SoldOrdersTable
                orders={soldOrders}
                isLoading={isSoldLoading}
                selectedId={selectedOrderId ?? undefined}
                onRowClick={(id) => setSelectedOrderId(id)}
              />
              {!isSoldLoading && (
                <>
                  <div ref={soldSentinelRef} style={{ height: 1 }} aria-hidden />
                  {isSoldLoadingMore && (
                    <div className={styles.loadingMore}>Loading more orders…</div>
                  )}
                  {!hasSoldMore && soldOrders.length > 0 && !isSoldLoadingMore && (
                    <div className={styles.endOfList}>
                      {soldOrders.length} order{soldOrders.length !== 1 ? 's' : ''} total
                    </div>
                  )}
                </>
              )}
            </div>
            {selectedOrderId && (() => {
              const order = soldOrders.find((o) => o.orderId === selectedOrderId)
              return order ? (
                <div>
                  <SoldOrderDetailPanel
                    order={order}
                    onClose={() => setSelectedOrderId(null)}
                    onStatusChange={handleOrderStatusChange}
                  />
                </div>
              ) : null
            })()}
          </div>
        )}

        {tab === 'saved' && (
          <div className={styles.emptyState}>
            <Icon kind="tag" size={32} color="var(--hd-sub)" />
            <p>No saved drafts</p>
          </div>
        )}
      </div>
    </AppShell>
  )
}
