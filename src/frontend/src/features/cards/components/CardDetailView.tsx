// src/frontend/src/features/cards/components/CardDetailView.tsx
import { CardArt } from '../../../components/design-system/CardArt'
import { AreaChart } from '../../../components/design-system/AreaChart'
import { Pip, type ManaColor } from '../../../components/design-system/Pip'
import { Chip } from '../../../components/ui/Chip'
import { Button } from '../../../components/ui/Button'
import type { CardDetail } from '../types'
import styles from './CardDetailView.module.css'

interface CardDetailViewProps {
  card: CardDetail
}

const RANGE_LABELS = ['1W', '1M', '3M', '1Y', 'ALL']

function parseMana(cost: string): ManaColor[] {
  return (cost.match(/[WUBRG]/g) ?? []) as ManaColor[]
}

export function CardDetailView({ card }: CardDetailViewProps) {
  const delta1d = card.price_change_1d
  const delta7d = card.price_change_7d
  const delta30d = card.price_change_30d

  return (
    <div className={styles.layout}>
      <div className={styles.artCol}>
        <CardArt
          name={card.card_name}
          w={420}
          h={585}
          hue={20}
          label={false}
          imageUrl={card.image_large}
          style={{ borderRadius: 16 }}
        />
        <div className={styles.printChips}>
          <Chip color="var(--hd-accent)" style={{ border: '1px solid var(--hd-accent)' }}>
            ● Non-foil · {card.set_code}
          </Chip>
          {card.prints?.map((p) => (
            <Chip key={p.id}>{p.finish} · {p.set}</Chip>
          ))}
        </div>
      </div>

      <div className={styles.infoCol}>
        <div className={styles.meta}>
          {card.set_code} · {card.rarity_name?.charAt(0).toUpperCase() + card.rarity_name?.slice(1)} · {card.type_line}
        </div>
        <h1 className={styles.name}>{card.card_name}</h1>

        {card.mana_cost && (
          <div className={styles.manaRow}>
            {parseMana(card.mana_cost).map((c, i) => <Pip key={i} color={c} size={18} />)}
            <span className={styles.manaCost}>{card.mana_cost}</span>
            <span className={styles.artist}>by {card.artist}</span>
          </div>
        )}

        <div className={styles.priceSection}>
          <div className={styles.priceLabel}>Market price</div>
          <div className={styles.priceRow}>
            <div className={styles.price}>
              {card.price != null ? (
                <>
                  ${Math.floor(card.price)}<span className={styles.priceCents}>.{(card.price % 1).toFixed(2).slice(2)}</span>
                </>
              ) : (
                'N/A'
              )}
            </div>
            <div className={styles.deltas}>
              <span className={delta1d >= 0 ? styles.up : styles.down}>
                {delta1d >= 0 ? '▲' : '▼'} {Math.abs(delta1d).toFixed(2)}% 1d
              </span>
              <span className={delta7d >= 0 ? styles.up : styles.down}>
                {delta7d >= 0 ? '▲' : '▼'} {Math.abs(delta7d).toFixed(2)}% 7d
              </span>
              <span className={delta30d >= 0 ? styles.up : styles.down}>
                {delta30d >= 0 ? '▲' : '▼'} {Math.abs(delta30d).toFixed(2)}% 30d
              </span>
            </div>
          </div>
        </div>

        {card.price_history && card.price_history.length > 0 ? (
          <div className={styles.chartSection}>
            <div className={styles.chartHeader}>
              <span className={styles.chartLabel}>Price · 1y</span>
              <div className={styles.rangeButtons}>
                {RANGE_LABELS.map((r, i) => (
                  <button key={r} className={[styles.rangeBtn, i === 3 ? styles.rangeActive : ''].join(' ')}>{r}</button>
                ))}
              </div>
            </div>
            <AreaChart
              points={card.price_history.slice(-365)}
              color="var(--hd-accent)"
              height={220}
              gridColor="rgba(150,200,255,0.05)"
            />
          </div>
        ) : null}

        <div className={styles.actions}>
          <Button variant="accent" style={{ flex: 1 }}>+ Add to collection</Button>
          <Button variant="ghost">Watch</Button>
          <Button variant="ghost">Set alert</Button>
        </div>
      </div>
    </div>
  )
}
