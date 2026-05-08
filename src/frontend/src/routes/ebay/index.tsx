// src/frontend/src/routes/ebay/index.tsx
import React, { useEffect, useState } from 'react'
import { createFileRoute, Link } from '@tanstack/react-router'
import { AppShell } from '../../components/layout/AppShell'
import { TopBar } from '../../components/layout/TopBar'
import { Icon, type IconKind } from '../../components/design-system/Icon'
import { fetchUserApps, fetchAppRateLimits, type EbayAppSummary, type EbayRateLimit } from '../../features/ebay/api'
import styles from './EbayHub.module.css'

export const Route = createFileRoute('/ebay/')({
  component: EbayHubPage,
})

export { EbayHubPage }

interface FeatureCardProps {
  icon: IconKind
  title: string
  subtitle: string
  to: string
}

function FeatureCard({ icon, title, subtitle, to }: FeatureCardProps) {
  return (
    <Link to={to as any} className={styles.featureCard}>
      <div className={styles.featureCardIcon}>
        <Icon kind={icon} size={20} color="var(--hd-accent)" />
      </div>
      <div className={styles.featureCardBody}>
        <div className={styles.featureCardTitle}>{title}</div>
        <div className={styles.featureCardSubtitle}>{subtitle}</div>
      </div>
      <Icon kind="arrowRight" size={14} color="var(--hd-sub)" />
    </Link>
  )
}

function totalCalls(limits: EbayRateLimit[]): { used: number; total: number } | null {
  if (!limits.length) return null
  const total = limits.reduce((s, r) => s + (r.limit ?? 0), 0)
  const remaining = limits.reduce((s, r) => s + (r.remaining ?? 0), 0)
  return { used: total - remaining, total }
}

function AppRow({ app }: { app: EbayAppSummary }) {
  const [rateLimits, setRateLimits] = React.useState<EbayRateLimit[] | null>(null)

  React.useEffect(() => {
    fetchAppRateLimits(app.app_code)
      .then(setRateLimits)
      .catch(() => setRateLimits([]))
  }, [app.app_code])

  const envColor = app.environment === 'PRODUCTION' ? 'var(--hd-accent)' : 'var(--hd-amber)'
  const calls = rateLimits ? totalCalls(rateLimits) : null

  return (
    <div className={styles.appRow}>
      <div className={styles.appRowName}>
        <span className={styles.appRowNameText}>{app.app_name}</span>
        {app.description && (
          <span className={styles.appRowDesc}>{app.description}</span>
        )}
      </div>
      <span
        className={styles.appRowEnvBadge}
        style={{ color: envColor, borderColor: `${envColor}44`, background: `${envColor}11` }}
      >
        {app.environment}
      </span>
      <span className={styles.appRowMeta}>
        <span className={styles.appRowMetaLabel}>Users</span>
        <span className={styles.appRowMetaValue}>{app.other_user_count + 1}</span>
      </span>
      <span className={styles.appRowMeta}>
        <span className={styles.appRowMetaLabel}>API calls</span>
        <span className={styles.appRowMetaValue}>
          {rateLimits === null
            ? '…'
            : calls
            ? `${calls.used.toLocaleString()} / ${calls.total.toLocaleString()}`
            : '—'}
        </span>
      </span>
      <span
        className={styles.appRowStatus}
        style={{ color: app.is_connected ? 'var(--hd-accent)' : 'var(--hd-red)' }}
      >
        <span
          className={styles.appCardStatusDot}
          style={{ background: app.is_connected ? 'var(--hd-accent)' : 'var(--hd-red)' }}
        />
        {app.is_connected
          ? app.token_expires_at
            ? `Expires ${new Date(app.token_expires_at).toLocaleDateString()}`
            : 'Connected'
          : 'Not connected'}
      </span>
    </div>
  )
}

function EbayHubPage() {
  const [apps, setApps] = useState<EbayAppSummary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchUserApps()
      .then(setApps)
      .catch(() => setApps([]))
      .finally(() => setLoading(false))
  }, [])

  return (
    <AppShell active="settings">
      <TopBar
        title="eBay Integration"
        subtitle="BYOA · production"
      />

      <div className={styles.page}>
        <div className={styles.cardsGrid}>
          <FeatureCard
            icon="key"
            title="App Setup"
            subtitle="Credentials & OAuth scopes"
            to="/ebay/setup"
          />
          <FeatureCard
            icon="users"
            title="Users"
            subtitle="Access control & invites"
            to="/ebay/share"
          />
          <FeatureCard
            icon="bag"
            title="Listings"
            subtitle="Smart pricing & one-click listing"
            to="/listings"
          />
        </div>

        {!loading && apps.length > 0 && (
          <section aria-label="Registered apps">
            <div className={styles.sectionTitle}>Registered Apps</div>
            <div className={styles.appsTable}>
              {apps.map(app => (
                <AppRow key={app.app_id} app={app} />
              ))}
            </div>
          </section>
        )}

        {!loading && apps.length === 0 && (
          <div className={styles.emptyApps}>
            No apps registered yet.{' '}
            <Link to="/ebay/setup" className={styles.warningLink}>Set one up</Link>
          </div>
        )}

      </div>
    </AppShell>
  )
}
