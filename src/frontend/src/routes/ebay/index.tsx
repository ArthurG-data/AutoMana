// src/frontend/src/routes/ebay/index.tsx
import React, { useEffect, useState } from 'react'
import { createFileRoute, Link } from '@tanstack/react-router'
import { AppShell } from '../../components/layout/AppShell'
import { TopBar } from '../../components/layout/TopBar'
import { Icon, type IconKind } from '../../components/design-system/Icon'
import { QuotaStrip } from '../../features/ebay/components/QuotaStrip'
import { verifyEbayConnection } from '../../features/ebay/api'
import { type ConnectionStatus } from '../../features/ebay/mockEbayApp'
import { MOCK_AUTHORIZED_USERS } from '../../features/ebay/mockAuthorizedUsers'
import styles from './EbayHub.module.css'

export const Route = createFileRoute('/ebay/')({
  component: EbayHubPage,
})

export { EbayHubPage }

function ConnectionBadge({ connected }: { connected: boolean }) {
  return (
    <span
      className={[styles.badge, connected ? styles.badgeConnected : styles.badgeDisconnected].join(' ')}
      aria-label={connected ? 'Connected to eBay' : 'Not connected to eBay'}
    >
      <span className={styles.badgeDot} aria-hidden="true" />
      {connected ? 'Connected' : 'Not Connected'}
    </span>
  )
}

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

interface StatTileProps {
  label: string
  value: string
  valueColor?: string
}

function StatTile({ label, value, valueColor }: StatTileProps) {
  return (
    <div className={styles.statTile}>
      <div className={styles.statLabel}>{label}</div>
      <div className={styles.statValue} style={valueColor ? { color: valueColor } : undefined}>
        {value}
      </div>
    </div>
  )
}

const DISCONNECTED_DEFAULT: ConnectionStatus = {
  connected: false,
  environment: 'production',
  lastVerified: null,
  tokenExpires: null,
  dailyQuota: 5000,
  usedToday: 0,
}

function EbayHubPage() {
  const [status, setStatus] = useState<ConnectionStatus>(DISCONNECTED_DEFAULT)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const appCode = localStorage.getItem('ebay_app_code')
    if (!appCode) {
      setLoading(false)
      return
    }

    verifyEbayConnection(appCode)
      .then((data) => {
        setStatus({
          connected: true,
          environment: 'production',
          lastVerified: new Date().toISOString(),
          tokenExpires: data.expires_on ?? null,
          dailyQuota: 5000,
          usedToday: 0,
        })
      })
      .catch(() => {
        setStatus({ ...DISCONNECTED_DEFAULT })
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

  return (
    <AppShell active="settings">
      <TopBar
        title="eBay Integration"
        subtitle="BYOA · production"
        actions={<ConnectionBadge connected={status.connected} />}
      />

      <div className={styles.page}>
        {!status.connected && (
          <div className={styles.warningBanner} role="alert">
            <Icon kind="shield" size={14} color="var(--hd-amber)" />
            <span>eBay is not connected.</span>
            <Link to="/ebay/setup" className={styles.warningLink}>
              Go to App Setup
            </Link>
          </div>
        )}

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

        <section className={styles.statsStrip} aria-label="Connection stats">
          <StatTile
            label="Status"
            value={status.connected ? 'Connected' : 'Not Connected'}
            valueColor={status.connected ? 'var(--hd-accent)' : 'var(--hd-red)'}
          />
          <StatTile
            label="Environment"
            value={status.environment}
          />
          <StatTile
            label="Token expires"
            value={
              status.tokenExpires
                ? new Date(status.tokenExpires).toLocaleDateString()
                : '—'
            }
          />
          <StatTile
            label="Authorized users"
            value={String(MOCK_AUTHORIZED_USERS.length)}
          />
        </section>

        <QuotaStrip />
      </div>
    </AppShell>
  )
}
