// src/frontend/src/components/layout/TopBar.tsx
import React from 'react'
import { Icon } from '../design-system/Icon'
import { useUIStore } from '../../store/ui'
import styles from './TopBar.module.css'

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
  title: string
  subtitle?: string
  breadcrumb?: string
  actions?: React.ReactNode
}

export function TopBar({ title, subtitle, breadcrumb, actions }: TopBarProps) {
  const { toggleTheme, theme } = useUIStore()

  return (
    <div className={styles.topBar}>
      <div className={styles.left}>
        {breadcrumb && <div className={styles.breadcrumb}>{breadcrumb}</div>}
        {subtitle && <div className={styles.subtitle}>{subtitle}</div>}
        <h1 className={styles.title}>{title}</h1>
      </div>
      <div className={styles.right}>
        {actions}
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
        <div className={styles.avatar} />
      </div>
    </div>
  )
}
