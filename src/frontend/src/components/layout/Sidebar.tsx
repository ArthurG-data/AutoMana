// src/frontend/src/components/layout/Sidebar.tsx
import { useNavigate } from '@tanstack/react-router'
import { Icon, type IconKind } from '../design-system/Icon'
import styles from './Sidebar.module.css'

interface NavItem {
  kind: IconKind
  label: string
  id: string
}

const NAV_ITEMS: NavItem[] = [
  { kind: 'chart',    label: 'Dashboard',  id: 'dashboard'  },
  { kind: 'wallet',   label: 'Portfolio',  id: 'portfolio'  },
  { kind: 'cards',    label: 'Collection', id: 'collection' },
  { kind: 'bag',      label: 'Listings',   id: 'listings'   },
  { kind: 'eye',      label: 'Watchlist',  id: 'watchlist'  },
  { kind: 'list',     label: 'Journal',    id: 'journal'    },
  { kind: 'bell',     label: 'Alerts',     id: 'alerts'     },
  { kind: 'settings', label: 'Settings',   id: 'settings'   },
]

interface SidebarProps {
  active: string
}

export function Sidebar({ active }: SidebarProps) {
  const navigate = useNavigate()

  return (
    <nav className={styles.sidebar} aria-label="Main navigation">
      <button
        className={styles.logo}
        onClick={() => navigate({ to: '/' })}
        aria-label="automana - go to home"
        title="Go to home"
      >
        a
      </button>
      {NAV_ITEMS.map((item) => {
        const isActive = item.id === active
        return (
          <button
            key={item.id}
            className={[styles.navItem, isActive ? styles.navItemActive : ''].join(' ')}
            title={item.label}
            aria-label={item.label}
            aria-current={isActive ? 'page' : undefined}
            onClick={() => navigate({ to: `/${item.id}` as any })}
          >
            {isActive && <div className={styles.activePill} />}
            <Icon
              kind={item.kind}
              size={18}
              color={isActive ? 'var(--hd-text)' : 'var(--hd-muted)'}
              strokeWidth={1.6}
            />
          </button>
        )
      })}
    </nav>
  )
}
