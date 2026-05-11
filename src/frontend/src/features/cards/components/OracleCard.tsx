// src/frontend/src/features/cards/components/OracleCard.tsx
import { Pip, type ManaColor } from '../../../components/design-system/Pip'
import styles from './OracleCard.module.css'

interface OracleCardProps {
  cardName: string
  manaCost?: string
  typeLine?: string
  oracleText?: string
  artist?: string
  collectorNumber?: string
  rarityName?: string
}

function parseMana(cost: string): ManaColor[] {
  return (cost.match(/[WUBRG]/g) ?? []) as ManaColor[]
}

function rarityClass(rarity?: string): string {
  switch ((rarity ?? '').toLowerCase()) {
    case 'mythic':   return styles.rarityMythic
    case 'rare':     return styles.rarityRare
    case 'uncommon': return styles.rarityUncommon
    case 'common':
    default:         return styles.rarityCommon
  }
}

export function OracleCard({
  cardName,
  manaCost,
  typeLine,
  oracleText,
  artist,
  collectorNumber,
  rarityName,
}: OracleCardProps) {
  return (
    <div className={`${styles.card} ${rarityClass(rarityName)}`}>
      <div className={styles.titleRow}>
        <h1 className={styles.name}>{cardName}</h1>
        {manaCost && (
          <div className={styles.manaRow}>
            {parseMana(manaCost).map((c, i) => <Pip key={i} color={c} size={18} />)}
            <span className={styles.manaCost}>{manaCost}</span>
          </div>
        )}
      </div>

      {typeLine && <div className={styles.typeLine}>{typeLine}</div>}

      {oracleText && (
        <div className={styles.oracleText}>
          {oracleText.split('\n').map((line, i) => (
            <p key={i}>{line}</p>
          ))}
        </div>
      )}

      {(artist || collectorNumber) && (
        <div className={styles.footer}>
          {artist && <span>Illus. {artist}</span>}
          {artist && collectorNumber && <span> · </span>}
          {collectorNumber && <span>#{collectorNumber}</span>}
        </div>
      )}
    </div>
  )
}
