// src/frontend/src/features/cards/components/SearchFilters.tsx
import { useNavigate } from '@tanstack/react-router'
import { useState, useEffect } from 'react'
import { Icon } from '../../../components/design-system/Icon'
import type { CardSearchParams } from '../types'
import styles from './SearchFilters.module.css'

const RARITIES = ['common', 'uncommon', 'rare', 'mythic'] as const
const FINISHES = ['non-foil', 'foil', 'etched'] as const
const LAYOUTS = ['normal', 'token', 'transform', 'saga', 'adventure'] as const

interface SearchFiltersProps {
  params: CardSearchParams
}

export function SearchFilters({ params }: SearchFiltersProps) {
  const navigate = useNavigate({ from: '/search' })
  const [query, setQuery] = useState(params.q ?? '')

  useEffect(() => {
    setQuery(params.q ?? '')
  }, [params.q])

  function update(patch: Partial<CardSearchParams>) {
    navigate({ search: (prev) => ({ ...prev, ...patch }) })
  }

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (query.trim()) {
      update({ q: query.trim() })
    }
  }

  return (
    <aside className={styles.filters}>
      <form className={styles.searchForm} onSubmit={handleSearchSubmit}>
        <Icon kind="search" size={16} color="var(--hd-muted)" />
        <input
          type="text"
          className={styles.searchInput}
          placeholder="Search cards…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search cards"
        />
      </form>

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

      <section className={styles.group}>
        <div className={styles.groupLabel}>Layout</div>
        <div className={styles.finishGrid}>
          {LAYOUTS.map((l) => (
            <button
              key={l}
              className={[styles.finishBtn, params.layout === l ? styles.finishActive : ''].join(' ')}
              onClick={() => update({ layout: params.layout === l ? undefined : l })}
            >
              {l.charAt(0).toUpperCase() + l.slice(1)}
            </button>
          ))}
        </div>
      </section>
    </aside>
  )
}
