// src/frontend/src/routes/listings.tsx
import { useState, useEffect } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { Button } from '../components/ui/Button'
import { Icon } from '../components/design-system/Icon'
import { ListingsTable } from '../features/ebay/components/ListingsTable'
import { fetchUserApps, fetchActiveListings } from '../features/ebay/api'
import type { EbayLiveListing } from '../features/ebay/mockListings'
import styles from './Listings.module.css'

export const Route = createFileRoute('/listings')({
  component: ListingsPage,
})

type Tab = 'active' | 'sold' | 'saved'

export function ListingsPage() {
  const [tab, setTab] = useState<Tab>('active')
  const [listings, setListings] = useState<EbayLiveListing[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [failedApps, setFailedApps] = useState<string[]>([])
  const [dismissedApps, setDismissedApps] = useState<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false
    async function load() {
      setIsLoading(true)
      try {
        const apps = await fetchUserApps()
        const productionApps = apps.filter((a) => a.environment === 'PRODUCTION')

        const results = await Promise.allSettled(
          productionApps.map((app) =>
            fetchActiveListings(app.app_code, 50, 0).then((items) =>
              items.map((item) => ({ ...item, appName: app.app_name }))
            )
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

        setListings(merged)
        setFailedApps(failed)
      } catch {
        // fetchUserApps itself failed — leave listings empty, no per-app banners
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

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
          <ListingsTable listings={listings} isLoading={isLoading} />
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
