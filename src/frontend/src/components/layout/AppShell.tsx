// src/frontend/src/components/layout/AppShell.tsx
import React from 'react'
import { Sidebar } from './Sidebar'
import styles from './AppShell.module.css'

interface AppShellProps {
  active: string
  children: React.ReactNode
}

export function AppShell({ active, children }: AppShellProps) {
  return (
    <div className={styles.shell}>
      <Sidebar active={active} />
      <main className={styles.content}>{children}</main>
    </div>
  )
}
