// src/frontend/src/routes/index.tsx
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { Icon, type IconKind } from '../components/design-system/Icon'
import { Button } from '../components/ui/Button'
import styles from './Landing.module.css'

export const Route = createFileRoute('/')({
  component: LandingPage,
})

const TILES: { kind: IconKind; title: string; sub: string }[] = [
  { kind: 'chart',  title: 'Live price history',    sub: 'Every printing, every finish, every day.' },
  { kind: 'wallet', title: 'Track your collection', sub: 'Cost basis, P/L, and reprint risk.'        },
  { kind: 'bag',    title: 'List on eBay',           sub: 'Smart pricing & one-click listing.'       },
]

const QUICK_SEARCHES = [
  'Ragavan, Nimble Pilferer',
  'Mox Diamond',
  'modern horizons 3',
]

function LandingPage() {
  const [q, setQ] = useState('')
  const navigate = useNavigate()

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    if (q.trim()) navigate({ to: '/search', search: { q: q.trim() } as any })
  }

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
          <Button variant="ghost" size="sm" onClick={() => navigate({ to: '/login' })}>Log in</Button>
          <Button variant="accent" size="sm" onClick={() => navigate({ to: '/login' })}>Sign up</Button>
        </div>
      </nav>

      <div className={styles.hero}>
        <div className={styles.eyebrow}>● mtg market intelligence</div>
        <h1 className={styles.headline}>
          Track every card.<br />
          <span className={styles.headlineAccent}>Price the market.</span>
        </h1>
        <p className={styles.subtext}>
          Search 27,840 cards across every set. Real-time prices, full history, and your
          collection — all in one place.
        </p>

        <form className={styles.searchBar} onSubmit={handleSearch}>
          <Icon kind="search" size={20} color="var(--hd-accent)" strokeWidth={1.6} />
          <input
            className={styles.searchInput}
            placeholder="Search any card by name, set, or artist…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Search cards"
          />
          <kbd className={styles.searchHint}>⌘K</kbd>
        </form>

        <div className={styles.pills}>
          <span className={styles.pillLabel}>try:</span>
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
          <span>● 27,840 cards</span>
          <span>● 16 yrs of history</span>
          <span>● tcg · scg · ck · ebay</span>
          <span>● updated every 15 min</span>
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
