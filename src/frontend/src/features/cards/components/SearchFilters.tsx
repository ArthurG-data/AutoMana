// src/frontend/src/features/cards/components/SearchFilters.tsx
import { useNavigate } from '@tanstack/react-router'
import type { CardSearchParams } from '../types'
import styles from './SearchFilters.module.css'

const RARITIES = ['common', 'uncommon', 'rare', 'mythic'] as const
const FINISHES = ['non-foil', 'foil', 'etched'] as const

interface SearchFiltersProps {
  params: CardSearchParams
}

export function SearchFilters({ params }: SearchFiltersProps) {
  const navigate = useNavigate({ from: '/search' })

  function update(patch: Partial<CardSearchParams>) {
    navigate({ search: (prev) => ({ ...prev, ...patch }) })
  }

  return (
    <aside className={styles.filters}>
      <div className={styles.header}>
        <span className={styles.title}>Filters</span>
        <button className={styles.clear} onClick={() => navigate({ search: { q: params.q } })}>
          clear
        </button>
      </div>

      <section className={styles.group}>
        <div className={styles.groupLabel}>Rarity</div>
        {RARITIES.map((r) => (
          <label key={r} className={styles.checkRow}>
            <input
              type="checkbox"
              checked={params.rarity === r}
              onChange={(e) => update({ rarity: e.target.checked ? r : undefined })}
            />
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <span className={[styles.rarityDot, styles[r]].join(' ')} />
              {r.charAt(0).toUpperCase() + r.slice(1)}
            </span>
          </label>
        ))}
      </section>

      <section className={styles.group}>
        <div className={styles.groupLabel}>Finish</div>
        <div className={styles.finishGrid}>
          {FINISHES.map((f) => (
            <button
              key={f}
              className={[styles.finishBtn, params.finish === f ? styles.finishActive : ''].join(' ')}
              onClick={() => update({ finish: params.finish === f ? undefined : f })}
            >
              {f}
            </button>
          ))}
        </div>
      </section>
    </aside>
  )
}
