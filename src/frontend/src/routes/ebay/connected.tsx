// src/frontend/src/routes/ebay/connected.tsx
import React from 'react'
import { createFileRoute, Link } from '@tanstack/react-router'
import { AppShell } from '../../components/layout/AppShell'
import { TopBar } from '../../components/layout/TopBar'
import { Icon } from '../../components/design-system/Icon'
import { Button } from '../../components/ui/Button'
import styles from './Connected.module.css'

export const Route = createFileRoute('/ebay/connected')({
  component: EbayConnectedPage,
})

export { EbayConnectedPage }

function EbayConnectedPage() {
  const search = new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '')
  const status = search.get('status')
  const appCode = search.get('app_code')
  const message = search.get('message')

  const success = status === 'authorized'

  return (
    <AppShell active="settings">
      <TopBar
        title={success ? 'eBay connected' : 'Connection failed'}
        subtitle="eBay Integration"
        breadcrumb="Settings / Integrations"
      />
      <div className={styles.page}>
        <div className={styles.card}>
          <div className={styles.iconRow}>
            <Icon
              kind={success ? 'check' : 'shield'}
              size={40}
              color={success ? 'var(--hd-accent)' : 'var(--hd-red)'}
            />
          </div>
          <h1 className={styles.heading}>
            {success ? 'eBay account connected' : 'Authorization failed'}
          </h1>
          {success ? (
            <>
              <p className={styles.body}>
                Your eBay account has been authorized. AutoMana can now access your eBay
                listings, orders, and account data.
              </p>
              {appCode && (
                <p className={styles.appCodeNote}>
                  App: <code>{appCode}</code>
                </p>
              )}
            </>
          ) : (
            <p className={styles.body}>
              {message
                ? decodeURIComponent(message)
                : 'eBay declined the authorization request. You can try again from the setup wizard.'}
            </p>
          )}
          <div className={styles.actions}>
            {success ? (
              <Link to="/ebay">
                <Button variant="accent" size="md">
                  Go to eBay Dashboard
                </Button>
              </Link>
            ) : (
              <Link to="/ebay/setup">
                <Button variant="accent" size="md">
                  Back to Setup
                </Button>
              </Link>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  )
}
