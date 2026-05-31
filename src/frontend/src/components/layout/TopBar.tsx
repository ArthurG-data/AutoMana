// src/frontend/src/components/layout/TopBar.tsx
import React from 'react'
import { Icon } from '../design-system/Icon'
import { useUIStore, type CurrencyCode } from '../../store/ui'
import { UserMenu } from './UserMenu'
import styles from './TopBar.module.css'

// Sitewide display-currency selector. USD/EUR have live data; CAD/JPY are listed
// but disabled until their price sources are ingested.
const CURRENCY_OPTIONS: { code: CurrencyCode; label: string; enabled: boolean }[] = [
  { code: 'USD', label: 'USD $', enabled: true },
  { code: 'EUR', label: 'EUR €', enabled: true },
  { code: 'CAD', label: 'CAD $', enabled: false },
  { code: 'JPY', label: 'JPY ¥', enabled: false },
]

function CurrencySelector() {
  const { currency, setCurrency } = useUIStore()
  return (
    <select
      className={styles.currencySelect}
      value={currency}
      onChange={(e) => setCurrency(e.target.value as CurrencyCode)}
      title="Display currency"
      aria-label="Display currency"
    >
      {CURRENCY_OPTIONS.map((opt) => (
        <option key={opt.code} value={opt.code} disabled={!opt.enabled}>
          {opt.label}{opt.enabled ? '' : ' (soon)'}
        </option>
      ))}
    </select>
  )
}

interface AttentionChipProps {
  count: number
  label: string
}

export function AttentionChip({ count, label }: AttentionChipProps) {
  if (count === 0) return null
  return (
    <span className={styles.attentionChip}>
      <Icon kind="sparkle" size={11} color="var(--hd-bg)" />
      {count} {label}
    </span>
  )
}

interface TopBarProps {
  title?: string
  subtitle?: string
  breadcrumb?: React.ReactNode
  actions?: React.ReactNode
}

export function TopBar({ title, subtitle, breadcrumb, actions }: TopBarProps) {
  const { toggleTheme, theme } = useUIStore()

  return (
    <div className={styles.topBar}>
      <div className={styles.left}>
        {breadcrumb && <div className={styles.breadcrumb}>{breadcrumb}</div>}
        {subtitle && <div className={styles.subtitle}>{subtitle}</div>}
        {title && <h1 className={styles.title}>{title}</h1>}
      </div>
      <div className={styles.right}>
        {actions}
        <CurrencySelector />
        <button
          className={styles.themeToggle}
          onClick={toggleTheme}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
        >
          <Icon
            kind={theme === 'dark' ? 'sun' : 'moon'}
            size={16}
            color="var(--hd-muted)"
          />
        </button>
        <UserMenu />
      </div>
    </div>
  )
}
