// src/frontend/src/features/cards/components/SetInfoBox.tsx
import styles from './SetInfoBox.module.css'

interface SetInfoBoxProps {
  setCode: string
  setName: string
  rarityName: string
  collectorNumber?: string
  promoTypes?: string[]
}

export function SetInfoBox({
  setCode,
  setName,
  rarityName,
  collectorNumber,
  promoTypes = [],
}: SetInfoBoxProps) {
  const rarity = rarityName.toLowerCase()

  return (
    <div className={styles.box}>
      <div className={styles.iconCol}>
        <i
          className={`ss ss-${setCode.toLowerCase()} ss-${rarity}`}
          aria-hidden="true"
        />
      </div>
      <div className={styles.textCol}>
        <div className={styles.setLine}>
          <span className={styles.setName}>{setName}</span>
          <span className={styles.setCode}>({setCode.toUpperCase()})</span>
        </div>
        <div className={styles.rarityLine}>
          {rarityName.charAt(0).toUpperCase() + rarityName.slice(1)}
        </div>
        {collectorNumber != null && (
          <div className={styles.collectorLine}>#{collectorNumber}</div>
        )}
        {promoTypes.length > 0 && (
          <div className={styles.badges}>
            {promoTypes.map((pt) => (
              <span key={pt} className={styles.badge}>✦ {pt}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
