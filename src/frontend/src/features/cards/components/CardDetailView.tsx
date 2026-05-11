// src/frontend/src/features/cards/components/CardDetailView.tsx
import { useState } from 'react'
import { FlippableCardArt } from '../../../components/design-system/FlippableCardArt'
import { buildScryfallBackUrl } from '../utils/scryfallBackUrl'
import { Pip, type ManaColor } from '../../../components/design-system/Pip'
import { Button } from '../../../components/ui/Button'
import { PriceCharts } from './PriceCharts'
import { SetInfoBox } from './SetInfoBox'
import { LegalityGrid } from './LegalityGrid'
import type { CardDetail } from '../types'
import styles from './CardDetailView.module.css'

interface CardDetailViewProps {
  card: CardDetail
}

function parseMana(cost: string): ManaColor[] {
  return (cost.match(/[WUBRG]/g) ?? []) as ManaColor[]
}

export function CardDetailView({ card }: CardDetailViewProps) {
  const finishes = card.available_finishes?.length ? card.available_finishes : ['nonfoil']
  const [selectedFinish, setSelectedFinish] = useState(finishes[0])

  const backUrl = card.is_multifaced
    ? (card.back_face_image_uri ?? null)
    : card.card_back_id
      ? buildScryfallBackUrl(card.card_back_id)
      : null

  const delta1d = card.price_change_1d
  const delta7d = card.price_change_7d
  const delta30d = card.price_change_30d

  return (
    <div className={styles.layout}>
      <div className={styles.imagePanel}>
        <FlippableCardArt
          name={card.card_name}
          w={240}
          frontUrl={card.image_large ?? null}
          backUrl={backUrl}
        />
        <div className={styles.imageFade} aria-hidden="true" />
      </div>

      <div className={styles.dataPanel}>
        <SetInfoBox
          setCode={card.set_code}
          setName={card.set_name}
          rarityName={card.rarity_name}
          collectorNumber={card.collector_number}
          promoTypes={card.promo_types}
        />

        <div className={styles.identity}>
          <h1 className={styles.name}>{card.card_name}</h1>
          {card.mana_cost && (
            <div className={styles.manaRow}>
              {parseMana(card.mana_cost).map((c, i) => <Pip key={i} color={c} size={18} />)}
              <span className={styles.manaCost}>{card.mana_cost}</span>
            </div>
          )}
          {card.type_line && <div className={styles.typeLine}>{card.type_line}</div>}
        </div>

        {card.oracle_text && (
          <div className={styles.oracleBox}>
            <p>{card.oracle_text}</p>
            {card.artist && (
              <div className={styles.artistLine}>
                Illus. {card.artist}
                {card.collector_number && <span> · #{card.collector_number}</span>}
              </div>
            )}
          </div>
        )}

        <div className={styles.finishSelector}>
          {finishes.map((f) => (
            <button
              key={f}
              onClick={() => setSelectedFinish(f)}
              aria-pressed={f === selectedFinish}
              className={f === selectedFinish ? styles.finishActive : styles.finishBtn}
            >
              {f}
            </button>
          ))}
        </div>

        <div className={styles.priceSection}>
          <div className={styles.priceLabel}>MARKET PRICE · {selectedFinish}</div>
          <div className={styles.priceRow}>
            <div className={styles.price}>
              {card.price != null ? (
                <>
                  ${Math.floor(card.price)}
                  <span className={styles.priceCents}>
                    .{(card.price % 1).toFixed(2).slice(2)}
                  </span>
                </>
              ) : 'N/A'}
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

        <PriceCharts card={card} finish={selectedFinish} />

        {card.legalities && Object.keys(card.legalities).length > 0 && (
          <LegalityGrid legalities={card.legalities} />
        )}

        <div className={styles.actions}>
          <Button variant="accent" style={{ flex: 1 }}>+ Add to collection</Button>
          <Button variant="ghost">Watch</Button>
          <Button variant="ghost">Set alert</Button>
        </div>
      </div>
    </div>
  )
}
