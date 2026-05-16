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

const TILES: { kind: IconKind; title: string; sub: string; to: string }[] = [
  { kind: 'chart',  title: 'Live price history',    sub: 'Every printing, every finish, every day.', to: '/search'     },
  { kind: 'wallet', title: 'Track your collection', sub: 'Cost basis, P/L, and reprint risk.',       to: '/collection' },
  { kind: 'bag',    title: 'List on eBay',           sub: 'Smart pricing & one-click listing.',       to: '/listings'   },
]

const QUICK_SEARCHES = ['Sheoldred, the Apocalypse', 'Force of Will', 'Leyline Binding', 'The One Ring']

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
        <div className={styles.eyebrow}>● real-time mtg pricing</div>
        <h1 className={styles.headline}>
          The data behind<br />
          <span className={styles.headlineAccent}>every deal.</span>
        </h1>
        <p className={styles.subtext}>
          Search {stats?.total_card_versions?.toLocaleString() ?? '—'} cards across every printing and finish. Find arbitrage before the market moves.
        </p>

        <div className={styles.searchBarWrapper}>
          <SearchBarWithSuggestions />
        </div>

        {QUICK_SEARCHES.length > 0 && (
          <div className={styles.pills}>
            <span className={styles.pillLabel}>Trending</span>
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
        )}

        <div className={styles.stats}>
          <span><span className={styles.statValue}>{stats?.total_card_versions?.toLocaleString() ?? '—'}</span><span className={styles.statLabel}>cards</span></span>
          <span><span className={styles.statValue}>16 yrs</span><span className={styles.statLabel}>history</span></span>
          <span><span className={styles.statValue}>Scryfall · MTGStocks · MTGJson</span><span className={styles.statLabel}>sources</span></span>
          <span><span className={styles.statValue}>Daily</span><span className={styles.statLabel}>updates</span></span>
        </div>
      </div>

      <div className={styles.tiles}>
        {TILES.map((t) => (
          <button
            key={t.kind}
            className={styles.tile}
            onClick={() => navigate({ to: t.to as any })}
            aria-label={t.title}
          >
            <div className={styles.tileIcon}>
              <Icon kind={t.kind} size={16} color="var(--hd-accent)" />
            </div>
            <div className={styles.tileTitle}>{t.title}</div>
            <div className={styles.tileSub}>{t.sub}</div>
          </button>
        ))}
      </div>
    </div>
  )
}
