import styles from './VersionsTable.module.css'

interface PriceDeltaProps {
  price?: number | null
  priceChange1d: number
}

export function PriceDelta({ price, priceChange1d }: PriceDeltaProps) {
  return (
    <div className={styles.priceCell}>
      {price != null ? `$${price.toFixed(2)}` : 'N/A'}
      {price != null && priceChange1d !== 0 && (
        <span className={priceChange1d >= 0 ? styles.up : styles.down}>
          {priceChange1d >= 0 ? '▲' : '▼'} {Math.abs(priceChange1d).toFixed(1)}%
        </span>
      )}
    </div>
  )
}
