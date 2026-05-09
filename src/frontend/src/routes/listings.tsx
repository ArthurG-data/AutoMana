// src/frontend/src/routes/listings.tsx
import { useState, useEffect, useRef, useCallback } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { Button } from '../components/ui/Button'
import { Icon } from '../components/design-system/Icon'
import { ListingsTable } from '../features/ebay/components/ListingsTable'
import {
  fetchUserApps,
  fetchActiveListingsPaginated,
  type EbayAppSummary,
} from '../features/ebay/api'
import { enrichWithCatalog } from '../features/ebay/lib/catalogEnrich'
import { useListingsStore } from '../store/listings'
import type { EbayLiveListing } from '../features/ebay/mockListings'
import styles from './Listings.module.css'

export const Route = createFileRoute('/listings')({
  component: ListingsPage,
})

type Tab = 'active' | 'sold' | 'saved'

const LIMIT = 25

export function ListingsPage() {
  const [tab, setTab] = useState<Tab>('active')
  const [listings, setListings] = useState<EbayLiveListing[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [failedApps, setFailedApps] = useState<string[]>([])
  const [dismissedApps, setDismissedApps] = useState<Set<string>>(new Set())
  const storeSet = useListingsStore((s) => s.setListings)

  // Pagination state in refs — updates don't need to trigger re-renders
  const appsRef = useRef<EbayAppSummary[]>([])
  const offsetsRef = useRef<Record<string, number>>({})
  const hasMoreRef = useRef<Record<string, boolean>>({})
  const listingsRef = useRef<EbayLiveListing[]>([])
  const isLoadingMoreRef = useRef(false)
  const sentinelRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setIsLoading(true)
      try {
        const apps = await fetchUserApps()
        const productionApps = apps.filter((a) => a.environment === 'PRODUCTION')
        appsRef.current = productionApps

        const results = await Promise.allSettled(
          productionApps.map((app) =>
            fetchActiveListingsPaginated(app.app_code, LIMIT, 0).then(({ items, hasMore: more }) => {
              hasMoreRef.current[app.app_code] = more
              offsetsRef.current[app.app_code] = items.length
              return items.map((item) => ({ ...item, appName: app.app_name }))
            })
          )
        )

        if (cancelled) return

        const merged: EbayLiveListing[] = []
        const failed: string[] = []
        results.forEach((result, i) => {
          if (result.status === 'fulfilled') {
            merged.push(...result.value)
          } else {
            failed.push(productionApps[i].app_name)
          }
        })

        listingsRef.current = merged
        setListings(merged)
        storeSet(merged)
        setFailedApps(failed)
        setHasMore(Object.values(hasMoreRef.current).some(Boolean))

        // Enrich with canonical names in the background — table is already visible.
        try {
          const enriched = await enrichWithCatalog(merged)
          if (!cancelled) {
            listingsRef.current = enriched
            setListings(enriched)
            storeSet(enriched)
          }
        } catch {
          // Keep title-parsed values
        }
      } catch {
        // fetchUserApps failed — leave table empty
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  const loadMore = useCallback(async () => {
    if (isLoadingMoreRef.current) return
    const pendingApps = appsRef.current.filter((a) => hasMoreRef.current[a.app_code])
    if (pendingApps.length === 0) return

    isLoadingMoreRef.current = true
    setIsLoadingMore(true)

    const results = await Promise.allSettled(
      pendingApps.map((app) =>
        fetchActiveListingsPaginated(
          app.app_code,
          LIMIT,
          offsetsRef.current[app.app_code] ?? 0,
        ).then(({ items, hasMore: more }) => {
          hasMoreRef.current[app.app_code] = more
          offsetsRef.current[app.app_code] = (offsetsRef.current[app.app_code] ?? 0) + items.length
          return items.map((item) => ({ ...item, appName: app.app_name }))
        })
      )
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

      // Enrich only the new batch, then splice into position.
      try {
        const enriched = await enrichWithCatalog(newItems)
        const current = listingsRef.current
        const updated = [...current.slice(0, current.length - newItems.length), ...enriched]
        listingsRef.current = updated
        setListings(updated)
        storeSet(updated)
      } catch {
        // Keep title-parsed values for new batch
      }
    }

    setHasMore(Object.values(hasMoreRef.current).some(Boolean))
    isLoadingMoreRef.current = false
    setIsLoadingMore(false)
  }, [storeSet])

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
                <span className={styles.tabCount}>{listings.length}</span>
              )}
            </button>
          ))}
        </div>

        {/* ── Content ───────────────────────────────────────────── */}
        {tab === 'active' && (
          <>
            <ListingsTable listings={listings} isLoading={isLoading} />
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
          </>
        )}

        {tab === 'sold' && (
          <div className={styles.emptyState}>
            <Icon kind="bag" size={32} color="var(--hd-sub)" />
            <p>Order history coming soon</p>
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
