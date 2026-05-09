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

const normalise = (id: string) => id.split('|')[1] ?? id

function PriceTable({
  rows,
  showSoldDate,
  showListedAt,
  ownItemId,
}: {
  rows: PricePoint[]
  showSoldDate: boolean
  showListedAt: boolean
  ownItemId?: string
}) {
  if (rows.length === 0) return <p className={styles.empty}>No results</p>
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Title</th>
          <th>Price</th>
          <th>Shipping</th>
          <th>Total</th>
          <th>Condition</th>
          {showSoldDate && <th>Sold</th>}
          {showListedAt && <th>Listed</th>}
          <th>Origin</th>
          <th>Similarity</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const total = r.shipping_cost != null ? r.price + r.shipping_cost : null
          const isOwn = ownItemId != null && normalise(r.item_id) === normalise(ownItemId)
          return (
            <tr key={r.item_id} className={isOwn ? styles.ownRow : undefined}>
              <td className={styles.titleCell}>
                {isOwn && (
                  <span className={styles.ownBadge} title="Your listing">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                      <path d="M21.41 11.58l-9-9A2 2 0 0 0 11 2H4a2 2 0 0 0-2 2v7c0 .53.21 1.04.59 1.41l9 9c.37.37.88.59 1.41.59s1.04-.22 1.41-.59l7-7c.38-.37.59-.88.59-1.41s-.21-1.04-.59-1.42zM5.5 7a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3z"/>
                    </svg>
                  </span>
                )}
                {r.title}
              </td>
              <td className={styles.priceCell}>{fmt(r.price, r.currency)}</td>
              <td className={styles.shippingCell}>
                {r.shipping_cost != null ? fmt(r.shipping_cost, r.currency) : '—'}
              </td>
              <td className={styles.totalCell}>
                {total != null ? fmt(total, r.currency) : '—'}
              </td>
              <td>{r.condition ?? '—'}</td>
              {showSoldDate && <td>{fmtDate(r.sold_date)}</td>}
              {showListedAt && <td className={styles.dateCell}>{fmtDate(r.listed_at)}</td>}
              <td className={styles.originCell}>
                {r.item_country === 'AU' ? (
                  <span className={styles.badgeLocal}>Local</span>
                ) : r.item_country ? (
                  <span className={styles.badgeIntl}>{r.item_country}</span>
                ) : '—'}
              </td>
              <td>{(r.relevance_score * 100).toFixed(0)}%</td>
              <td>
                {r.url ? (
                  <a href={r.url} target="_blank" rel="noreferrer" className={styles.link}>
                    View
                  </a>
                ) : '—'}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export function MarketComparePanel({ listing, onBack }: MarketComparePanelProps) {
  const [data, setData] = useState<CardMarketData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [localOnly, setLocalOnly] = useState(true)

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

  const filteredActive = data
    ? localOnly
      ? data.active.filter((r) => r.item_country === 'AU')
      : data.active
    : []

  const activeFloor = filteredActive.length > 0
    ? Math.min(...filteredActive.map((r) => r.price))
    : null

  const listedDates = filteredActive
    .map((r) => r.listed_at)
    .filter((d): d is string => d !== null)
    .sort()
  const minListed = listedDates[0] ?? null
  const maxListed = listedDates[listedDates.length - 1] ?? null

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
                {activeFloor != null ? fmt(activeFloor, listing.currency) : '—'}
              </span>
            </div>
            <div className={styles.summaryCell}>
              <span className={styles.summaryLabel}>Listings</span>
              <span className={styles.summaryValue}>{filteredActive.length}</span>
            </div>
            <div className={styles.summaryCell}>
              <span className={styles.summaryLabel}>Oldest listed</span>
              <span className={styles.summaryValueSm}>{fmtDate(minListed)}</span>
            </div>
            <div className={styles.summaryCell}>
              <span className={styles.summaryLabel}>Newest listed</span>
              <span className={styles.summaryValueSm}>{fmtDate(maxListed)}</span>
            </div>
          </div>

          <section>
            <h3 className={styles.sectionTitle}>
              Sold listings ({data.sold_aggregates.count})
            </h3>
            <PriceTable rows={data.sold} showSoldDate={true} showListedAt={false} />
          </section>

          <section>
            <div className={styles.sectionHeader}>
              <h3 className={styles.sectionTitle}>
                Active listings ({filteredActive.length})
              </h3>
              <div className={styles.toggle}>
                <button
                  className={localOnly ? styles.toggleActive : styles.toggleBtn}
                  onClick={() => setLocalOnly(true)}
                >
                  Local
                </button>
                <button
                  className={!localOnly ? styles.toggleActive : styles.toggleBtn}
                  onClick={() => setLocalOnly(false)}
                >
                  All
                </button>
              </div>
            </div>
            <PriceTable
              rows={filteredActive}
              showSoldDate={false}
              showListedAt={true}
              ownItemId={listing.itemId}
            />
          </section>
        </>
      )}
    </div>
  )
}
