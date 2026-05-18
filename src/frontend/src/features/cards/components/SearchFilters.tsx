// src/frontend/src/features/cards/components/SearchFilters.tsx
import { useNavigate } from '@tanstack/react-router'
import type { CardGroupBy, CardSearchParams } from '../types'
import { SearchBarWithSuggestions } from './SearchBarWithSuggestions'
import styles from './SearchFilters.module.css'

const FINISHES = ['non-foil', 'foil', 'etched'] as const
const LAYOUTS = ['normal', 'token', 'transform', 'saga', 'adventure'] as const
const GROUPINGS: ReadonlyArray<{ value: CardGroupBy | 'none'; label: string }> = [
  { value: 'none',   label: 'None' },
  { value: 'rarity', label: 'Rarity' },
]

type SortOption = { label: string; sort_by: 'card_name' | 'released_at' | 'price'; sort_order: 'asc' | 'desc' }
const SORT_OPTIONS: ReadonlyArray<SortOption> = [
  { label: 'Name A→Z', sort_by: 'card_name',   sort_order: 'asc'  },
  { label: 'Newest',   sort_by: 'released_at', sort_order: 'desc' },
  { label: 'Oldest',   sort_by: 'released_at', sort_order: 'asc'  },
  { label: 'Cheapest', sort_by: 'price',        sort_order: 'asc'  },
  { label: 'Priciest', sort_by: 'price',        sort_order: 'desc' },
]

type ColorCode = 'White' | 'Blue' | 'Black' | 'Red' | 'Green' | 'Colorless' | 'Multi'
const COLOR_OPTIONS: ReadonlyArray<{ label: string; value: ColorCode }> = [
  { label: 'W', value: 'White' },
  { label: 'U', value: 'Blue' },
  { label: 'B', value: 'Black' },
  { label: 'R', value: 'Red' },
  { label: 'G', value: 'Green' },
  { label: 'C', value: 'Colorless' },
  { label: 'Multi', value: 'Multi' },
]

const CARD_TYPES = ['Creature', 'Instant', 'Sorcery', 'Enchantment', 'Artifact', 'Land', 'Planeswalker'] as const

const PROMO_TYPE_LABELS: Record<string, string> = {
  arenaleague:        'Arena League',
  boosterfun:         'Booster Fun',
  boxtopper:          'Box Topper',
  brawldeck:          'Brawl Deck',
  bundle:             'Bundle',
  buyabox:            'Buy a Box',
  convention:         'Convention',
  datestamped:        'Datestamped',
  draftweekend:       'Draft Weekend',
  duels:              'Duels',
  event:              'Event',
  fnm:                'Friday Night Magic',
  gameday:            'Game Day',
  gateway:            'Gateway',
  giftbox:            'Gift Box',
  gilded:             'Gilded',
  instore:            'In-Store',
  intropack:          'Intro Pack',
  jpwalker:           'JP Planeswalker',
  judgegift:          'Judge Gift',
  league:             'League',
  mediainsert:        'Media Insert',
  neonink:            'Neon Ink',
  openhouse:          'Open House',
  planeswalkerdeck:   'Planeswalker Deck',
  playerrewards:      'Player Rewards',
  playpromo:          'Play Promo',
  premiumdeck:        'Premium Deck',
  prerelease:         'Prerelease',
  promopack:          'Promo Pack',
  release:            'Release',
  serialized:         'Serialized',
  setpromo:           'Set Promo',
  starterdeck:        'Starter Deck',
  stepandcompleat:    'Step and Compleat',
  store:              'Store',
  textured:           'Textured',
  themepack:          'Theme Pack',
  tourney:            'Tourney',
  wizardsplaynetwork: 'Wizards Play Network',
}

function promoLabel(code: string): string {
  return PROMO_TYPE_LABELS[code] ?? code.charAt(0).toUpperCase() + code.slice(1)
}

export type PriceTrend = 'rising' | 'stable' | 'falling'

interface SearchFiltersProps {
  params: CardSearchParams
  promoTypeFacets: string[]
  rarityFacets: string[]
  priceTrend: PriceTrend | undefined
  onPriceTrendChange: (v: PriceTrend | undefined) => void
  upcomingOnly: boolean
  onUpcomingOnlyChange: (v: boolean) => void
}

export function SearchFilters({
  params,
  promoTypeFacets,
  rarityFacets,
  priceTrend,
  onPriceTrendChange,
  upcomingOnly,
  onUpcomingOnlyChange,
}: SearchFiltersProps) {
  const navigate = useNavigate({ from: '/search' })

  function update(patch: Partial<CardSearchParams>) {
    navigate({ search: (prev) => ({ ...prev, ...patch }) })
  }

  function toggleColor(value: string) {
    const current = params.colors ?? []
    const next = current.includes(value) ? current.filter((c) => c !== value) : [...current, value]
    update({ colors: next.length > 0 ? next : undefined })
  }

  function togglePromoType(pt: string) {
    const current = params.promoTypes ?? []
    const next = current.includes(pt) ? current.filter((x) => x !== pt) : [...current, pt]
    update({ promoTypes: next.length > 0 ? next : undefined })
  }

  const selectedPromoCount = params.promoTypes?.length ?? 0

  return (
    <aside className={styles.filters}>
      <div className={styles.searchWrapper}>
        <SearchBarWithSuggestions placeholder="" />
      </div>

      <div className={styles.header}>
        <span className={styles.title}>Filters</span>
        <button className={styles.clear} onClick={() => navigate({ search: { q: params.q } })}>
          clear
        </button>
      </div>

      {/* SORT */}
      <section className={styles.group}>
        <div className={styles.groupLabel}>Sort</div>
        <div className={styles.finishGrid} style={{ gridTemplateColumns: '1fr 1fr' }}>
          {SORT_OPTIONS.map(({ label, sort_by, sort_order }) => {
            const active = (params.sort_by ?? 'card_name') === sort_by &&
                           (params.sort_order ?? 'asc') === sort_order
            return (
              <button
                key={label}
                className={[styles.finishBtn, active ? styles.finishActive : ''].join(' ')}
                onClick={() => update({ sort_by, sort_order })}
              >
                {label}
              </button>
            )
          })}
        </div>
      </section>

      <section className={styles.group}>
        <div className={styles.groupLabel}>Group by</div>
        <div className={styles.finishGrid}>
          {GROUPINGS.map(({ value, label }) => {
            const active =
              value === 'none' ? !params.group : params.group === value
            return (
              <button
                key={value}
                data-group={value}
                className={[styles.finishBtn, active ? styles.finishActive : ''].join(' ')}
                onClick={() => update({ group: value === 'none' ? undefined : value })}
              >
                {label}
              </button>
            )
          })}
        </div>
      </section>

      {/* COLOR */}
      <section className={styles.group}>
        <div className={styles.groupLabel}>Color</div>
        <div className={styles.colorGrid}>
          {COLOR_OPTIONS.map(({ label, value }) => {
            const active = params.colors?.includes(value) ?? false
            return (
              <button
                key={value}
                className={[
                  styles.colorBtn,
                  styles[`color${value}`],
                  active ? styles.colorActive : '',
                ].filter(Boolean).join(' ')}
                onClick={() => toggleColor(value)}
              >
                {label}
              </button>
            )
          })}
        </div>
      </section>

      {/* TYPE */}
      <section className={styles.group}>
        <div className={styles.groupLabel}>Type</div>
        <div className={styles.finishGrid} style={{ gridTemplateColumns: '1fr 1fr' }}>
          {CARD_TYPES.map((t) => (
            <button
              key={t}
              className={[styles.finishBtn, params.card_type === t ? styles.finishActive : ''].join(' ')}
              onClick={() => update({ card_type: params.card_type === t ? undefined : t })}
            >
              {t}
            </button>
          ))}
        </div>
      </section>

      {/* PRICE TREND */}
      <section className={styles.group}>
        <div className={styles.groupLabel}>Price trend (7d)</div>
        <div className={styles.finishGrid}>
          {([['rising', '↑ Rising'], ['stable', '→ Stable'], ['falling', '↓ Falling']] as const).map(([val, label]) => (
            <button
              key={val}
              className={[styles.finishBtn, priceTrend === val ? styles.finishActive : ''].join(' ')}
              onClick={() => onPriceTrendChange(priceTrend === val ? undefined : val)}
            >
              {label}
            </button>
          ))}
        </div>
      </section>

      {/* UPCOMING */}
      <section className={styles.group}>
        <div className={styles.groupLabel}>Upcoming</div>
        <label className={styles.checkRow}>
          <input
            type="checkbox"
            checked={upcomingOnly}
            onChange={(e) => onUpcomingOnlyChange(e.target.checked)}
          />
          Show upcoming only
        </label>
      </section>

      {rarityFacets.length > 0 && (
        <section className={styles.group}>
          <div className={styles.groupLabel}>Rarity</div>
          {rarityFacets.map((r) => (
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
      )}

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

      {promoTypeFacets.length > 0 && (
        <section className={styles.group}>
          <div className={styles.groupLabel}>Promo type</div>
          <details className={styles.promoDropdown}>
            <summary className={styles.promoSummary}>
              <span>{selectedPromoCount > 0 ? `${selectedPromoCount} selected` : 'All types'}</span>
              <span aria-hidden="true" className={styles.promoCaret}>▾</span>
            </summary>
            <div className={styles.promoList}>
              {promoTypeFacets.map((pt) => (
                <label key={pt} className={styles.checkRow}>
                  <input
                    type="checkbox"
                    checked={params.promoTypes?.includes(pt) ?? false}
                    onChange={() => togglePromoType(pt)}
                  />
                  {promoLabel(pt)}
                </label>
              ))}
            </div>
          </details>
        </section>
      )}
    </aside>
  )
}
