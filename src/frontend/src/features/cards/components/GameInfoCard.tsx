// src/frontend/src/features/cards/components/GameInfoCard.tsx
import { Pip, type ManaColor } from '../../../components/design-system/Pip'
import styles from './GameInfoCard.module.css'

interface GameInfoCardProps {
  cardName: string
  setCode: string
  setName: string
  rarityName: string
  collectorNumber?: string
  promoTypes?: string[]
  manaCost?: string
  typeLine?: string
  oracleText?: string
  artist?: string
}

function parseMana(cost: string): ManaColor[] {
  return (cost.match(/[WUBRG]/g) ?? []) as ManaColor[]
}

function rarityClass(rarity: string): string {
  switch (rarity.toLowerCase()) {
    case 'mythic':   return styles.rarityMythic
    case 'rare':     return styles.rarityRare
    case 'uncommon': return styles.rarityUncommon
    case 'common':
    default:         return styles.rarityCommon
  }
}

export function GameInfoCard({
  cardName,
  setCode,
  setName,
  rarityName,
  collectorNumber,
  promoTypes = [],
  manaCost,
  typeLine,
  oracleText,
  artist,
}: GameInfoCardProps) {
  const rarity = rarityName.toLowerCase()

  return (
    <div className={`${styles.card} ${rarityClass(rarityName)}`}>
      <header className={styles.setHeader}>
        <div className={styles.iconCol}>
          <i
            className={`ss ss-${setCode.toLowerCase()} ss-${rarity}`}
            aria-hidden="true"
          />
        </div>
        <div className={styles.setText}>
          <div className={styles.setLine}>
            <span className={styles.setName}>{setName}</span>
            <span className={styles.setCode}>({setCode.toUpperCase()})</span>
          </div>
          <div className={styles.metaLine}>
            <span className={styles.rarity}>
              {rarityName.charAt(0).toUpperCase() + rarityName.slice(1)}
            </span>
            {collectorNumber && (
              <>
                <span className={styles.metaSep}>·</span>
                <span>#{collectorNumber}</span>
              </>
            )}
            {promoTypes.length > 0 && (
              <span className={styles.badges}>
                {promoTypes.map((pt) => (
                  <span key={pt} className={styles.badge}>✦ {pt}</span>
                ))}
              </span>
            )}
          </div>
        </div>
      </header>

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

      {artist && (
        <footer className={styles.footer}>Illus. {artist}</footer>
      )}
    </div>
  )
}
