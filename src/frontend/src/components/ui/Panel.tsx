// src/frontend/src/components/ui/Panel.tsx
import React from 'react'
import styles from './Panel.module.css'

interface PanelProps {
  children: React.ReactNode
  eyebrow?: string
  padding?: string
  style?: React.CSSProperties
  className?: string
}

export function Panel({
  children,
  eyebrow,
  padding = '14px 18px',
  style = {},
  className,
}: PanelProps) {
  return (
    <div
      className={[styles.panel, className].filter(Boolean).join(' ')}
      style={{ padding, ...style }}
    >
      {eyebrow && <div className={styles.eyebrow}>{eyebrow}</div>}
      {children}
    </div>
  )
}
