import { useState } from 'react'
import { CardArt } from './CardArt'
import styles from './FlippableCardArt.module.css'

interface FlippableCardArtProps {
  name: string
  frontUrl: string | null
  backUrl: string | null
  w?: number | string
  h?: number | string
  finish?: string
  style?: React.CSSProperties
}

export function FlippableCardArt({
  name,
  frontUrl,
  backUrl,
  w = 200,
  h,
  finish,
  style = {},
}: FlippableCardArtProps) {
  const [faceUp, setFaceUp] = useState(true)

  return (
    <div className={styles.wrapper} style={{ width: w, ...style }}>
      <div
        data-testid="flip-card"
        data-flipped={String(!faceUp)}
        className={`${styles.card} ${!faceUp ? styles.flipped : ''}`}
      >
        <div className={styles.front}>
          <CardArt name={name} w={w} h={h} label={false} imageUrl={frontUrl} finish={finish} />
        </div>
        {backUrl && (
          <div className={styles.back}>
            <CardArt name={name} w={w} h={h} label={false} imageUrl={backUrl} finish={finish} />
          </div>
        )}
      </div>
      {backUrl && (
        <button
          className={styles.flipBtn}
          onClick={() => setFaceUp(f => !f)}
          aria-label="Flip card"
        >
          ↻
        </button>
      )}
    </div>
  )
}
