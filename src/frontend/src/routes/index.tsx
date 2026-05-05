// src/frontend/src/routes/index.tsx
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { Icon, type IconKind } from '../components/design-system/Icon'
import { Button } from '../components/ui/Button'
import { UserMenu } from '../components/layout/UserMenu'
import { SearchBarWithSuggestions } from '../features/cards/components/SearchBarWithSuggestions'
import { cardCatalogStatsQueryOptions } from '../features/cards/api'
import { useAuthStore } from '../store/auth'
import styles from './Landing.module.css'

export const Route = createFileRoute('/')({
  component: LandingPage,
})

const TILES: { kind: IconKind; title: string; sub: string }[] = [
  { kind: 'chart',  title: 'Live price history',    sub: 'Every printing, every finish, every day.' },
  { kind: 'wallet', title: 'Track your collection', sub: 'Cost basis, P/L, and reprint risk.'        },
  { kind: 'bag',    title: 'List on eBay',           sub: 'Smart pricing & one-click listing.'       },
]

const QUICK_SEARCHES: string[] = []

function LandingPage() {
  const navigate = useNavigate()
  const token = useAuthStore((s) => s.token)
  const { data: stats } = useQuery(cardCatalogStatsQueryOptions())

  return (
    <div className={styles.page}>
      <div className={styles.glow} />

      <nav className={styles.nav}>
        <div className={styles.navLogo}>
          <div className={styles.logoMark}>a</div>
          auto<span className={styles.logoAccent}>mana</span>
        </div>
        <ul className={styles.navLinks}>
          <li>Markets</li><li>Sets</li><li>Pricing</li><li>About</li>
        </ul>
        <div className={styles.navActions}>
          {token
            ? <UserMenu />
            : <Button variant="accent" size="sm" onClick={() => navigate({ to: '/login' })}>Log in / Sign Up</Button>
          }
        </div>
      </nav>

      <div className={styles.hero}>
        <div className={styles.eyebrow}>● mtg market intelligence</div>
        <h1 className={styles.headline}>
          Track every card.<br />
          <span className={styles.headlineAccent}>Price the market.</span>
        </h1>
        <p className={styles.subtext}>
          Search {stats?.total_card_versions?.toLocaleString() ?? '—'} cards across every set. Real-time prices, full history, and your
          collection — all in one place.
        </p>

        <div className={styles.searchBarWrapper}>
          <SearchBarWithSuggestions />
        </div>

        <div className={styles.pills}>
          {QUICK_SEARCHES.map((s) => (
            <button
              key={s}
              className={styles.pill}
              onClick={() => navigate({ to: '/search', search: { q: s } as any })}
            >
              {s}
            </button>
          ))}
        </div>

        <div className={styles.stats}>
          <span>● {stats?.total_card_versions?.toLocaleString() ?? '—'} cards</span>
          <span>● 16 yrs of history</span>
          <span>● {stats?.data_source ?? '—'}</span>
          <span>● updated daily</span>
        </div>
      </div>

      <div className={styles.tiles}>
        {TILES.map((t) => (
          <div key={t.kind} className={styles.tile}>
            <div className={styles.tileIcon}>
              <Icon kind={t.kind} size={16} color="var(--hd-accent)" />
            </div>
            <div className={styles.tileTitle}>{t.title}</div>
            <div className={styles.tileSub}>{t.sub}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
