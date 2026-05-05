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
        onClick={() => navigate({ to: '/collection' })}
        aria-label="automana - go to collection"
        title="Go to collection"
      >
        a
      </button>
      {NAV_ITEMS.map((item) => {
        const isActive = item.id === active
        return (
          <div
            key={item.id}
            className={[styles.navItem, isActive ? styles.navItemActive : ''].join(' ')}
            title={item.label}
          >
            {isActive && <div className={styles.activePill} />}
            <Icon
              kind={item.kind}
              size={18}
              color={isActive ? 'var(--hd-text)' : 'var(--hd-muted)'}
              strokeWidth={1.6}
            />
          </div>
        )
      })}
    </nav>
  )
}
