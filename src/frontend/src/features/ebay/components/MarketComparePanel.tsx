import { useEffect, useState } from 'react'
import type { EbayLiveListing } from '../mockListings'
import { fetchMarketPrice } from '../api'
import type { CardMarketData, PricePoint } from '../api'
import styles from './MarketComparePanel.module.css'

interface MarketComparePanelProps {
  listing: EbayLiveListing
  onBack: () => void
}

function fmt(n: number | null | undefined, currency = 'USD'): string {
  if (n == null) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(n)
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function PriceTable({
  rows,
  showSoldDate,
}: {
  rows: PricePoint[]
  showSoldDate: boolean
}) {
  if (rows.length === 0) return <p className={styles.empty}>No results</p>
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Title</th>
          <th>Price</th>
          <th>Condition</th>
          {showSoldDate && <th>Sold date</th>}
          <th>Score</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.item_id}>
            <td className={styles.titleCell}>{r.title}</td>
            <td className={styles.priceCell}>{fmt(r.price, r.currency)}</td>
            <td>{r.condition ?? '—'}</td>
            {showSoldDate && <td>{fmtDate(r.sold_date)}</td>}
            <td>{(r.relevance_score * 100).toFixed(0)}%</td>
            <td>
              {r.url ? (
                <a
                  href={r.url}
                  target="_blank"
                  rel="noreferrer"
                  className={styles.link}
                >
                  View
                </a>
              ) : (
                '—'
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function MarketComparePanel({ listing, onBack }: MarketComparePanelProps) {
  const [data, setData] = useState<CardMarketData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchMarketPrice(listing)
      .then((d) => {
        if (!cancelled) {
          setData(d)
          setLoading(false)
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Failed to fetch market data')
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [listing.itemId])

  const suggestedPrice = data?.suggested_price ?? null
  const priceColor =
    suggestedPrice == null
      ? undefined
      : listing.price <= suggestedPrice
        ? 'var(--hd-accent)'
        : 'var(--hd-red, #e55)'

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <button onClick={onBack} className={styles.backBtn}>
          ← Back
        </button>
        <h2 className={styles.title}>Market comparison: {listing.cardName}</h2>
        {data && <span className={styles.query}>Query: &quot;{data.query}&quot;</span>}
      </div>

      {loading && <p className={styles.status}>Loading market data…</p>}

      {error && (
        <div className={styles.errorBox}>
          <p>{error}</p>
          <button onClick={onBack} className={styles.backBtn}>
            ← Go back
          </button>
        </div>
      )}

      {data && !loading && (
        <>
          <div className={styles.summary}>
            <div className={styles.summaryCell}>
              <span className={styles.summaryLabel}>Your price</span>
              <span className={styles.summaryValue} style={{ color: priceColor }}>
                {fmt(listing.price, listing.currency)}
              </span>
            </div>
            <div className={styles.summaryCell}>
              <span className={styles.summaryLabel}>Sold median</span>
              <span className={styles.summaryValue}>
                {fmt(data.sold_aggregates.median)}
              </span>
            </div>
            <div className={styles.summaryCell}>
              <span className={styles.summaryLabel}>Suggested price</span>
              <span className={styles.summaryValue}>
                {fmt(data.suggested_price)}
              </span>
            </div>
            <div className={styles.summaryCell}>
              <span className={styles.summaryLabel}>Active floor</span>
              <span className={styles.summaryValue}>
                {fmt(data.active_aggregates.min)}
              </span>
            </div>
          </div>

          <section>
            <h3 className={styles.sectionTitle}>
              Sold listings ({data.sold_aggregates.count})
            </h3>
            <PriceTable rows={data.sold} showSoldDate={true} />
          </section>

          <section>
            <h3 className={styles.sectionTitle}>
              Active listings ({data.active_aggregates.count})
            </h3>
            <PriceTable rows={data.active} showSoldDate={false} />
          </section>
        </>
      )}
    </div>
  )
}
