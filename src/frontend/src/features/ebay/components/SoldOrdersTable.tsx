import { useState, useMemo } from 'react'
import { LifecycleBadge } from './LifecycleBadge'
import type { SoldOrder, DisplayStatus } from '../soldOrders'
import styles from './SoldOrdersTable.module.css'

type SortKey = 'card' | 'price' | 'net' | 'buyer' | 'status' | 'sold'
type SortDir = 'asc' | 'desc'
type StatusFilter = 'all' | DisplayStatus

const STATUS_ORDER: Record<DisplayStatus, number> = { sold: 0, sent: 1, in_transit: 2, complete: 3 }

const FILTER_LABELS: Array<{ key: StatusFilter; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'sold', label: 'Sold' },
  { key: 'sent', label: 'Sent' },
  { key: 'in_transit', label: 'In Transit' },
  { key: 'complete', label: 'Done' },
]

interface SoldOrdersTableProps {
  orders: SoldOrder[]
  isLoading: boolean
  selectedId: string | undefined
  onRowClick: (orderId: string) => void
}

function MsgIcon({ orderId: _orderId }: { orderId: string }) {
  return (
    <a
      data-testid="msg-icon"
      href={`https://www.ebay.com.au/msg/inbox`}
      target="_blank"
      rel="noreferrer"
      className={styles.msgIcon}
      title="View messages on eBay"
      onClick={(e) => e.stopPropagation()}
    >
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden>
        <path
          d="M2 3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H9l-3 2v-2H3a1 1 0 0 1-1-1V3Z"
          stroke="currentColor"
          strokeWidth="1.4"
          fill="none"
        />
      </svg>
    </a>
  )
}

function SkeletonRow() {
  return (
    <tr data-testid="skeleton-row" className={styles.skeletonRow}>
      <td><div className={styles.skeletonCell} /></td>
      <td><div className={styles.skeletonCell} style={{ width: 50 }} /></td>
      <td><div className={styles.skeletonCell} style={{ width: 50 }} /></td>
      <td><div className={styles.skeletonCell} style={{ width: 70 }} /></td>
      <td />
      <td><div className={styles.skeletonCell} style={{ width: 80 }} /></td>
      <td><div className={styles.skeletonCell} style={{ width: 55 }} /></td>
    </tr>
  )
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  const diff = Math.floor((Date.now() - d.getTime()) / 3_600_000)
  if (diff < 1) return 'Just now'
  if (diff < 24) return `${diff}h ago`
  const days = Math.floor(diff / 24)
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days} days ago`
  return d.toLocaleDateString()
}

function netValue(order: SoldOrder): number | null {
  if (order.netPayout != null) return order.netPayout
  if (order.totalAmount != null && order.ebayFee != null) return order.totalAmount - order.ebayFee
  return null
}

function SortArrow({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <span className={styles.sortArrowInactive}>↕</span>
  return <span className={styles.sortArrowActive}>{dir === 'asc' ? '↑' : '↓'}</span>
}

export function SoldOrdersTable({ orders, isLoading, selectedId, onRowClick }: SoldOrdersTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('sold')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [filterStatus, setFilterStatus] = useState<StatusFilter>('all')

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const displayed = useMemo(() => {
    const filtered = filterStatus === 'all'
      ? orders
      : orders.filter((o) => o.displayStatus === filterStatus)

    return [...filtered].sort((a, b) => {
      let cmp = 0
      switch (sortKey) {
        case 'card':
          cmp = (a.lineItems[0]?.title ?? '').localeCompare(b.lineItems[0]?.title ?? '')
          break
        case 'price':
          cmp = (a.totalAmount ?? -Infinity) - (b.totalAmount ?? -Infinity)
          break
        case 'net':
          cmp = (netValue(a) ?? -Infinity) - (netValue(b) ?? -Infinity)
          break
        case 'buyer':
          cmp = (a.buyerUsername ?? '').localeCompare(b.buyerUsername ?? '')
          break
        case 'status':
          cmp = STATUS_ORDER[a.displayStatus] - STATUS_ORDER[b.displayStatus]
          break
        case 'sold':
          cmp = new Date(a.creationDate ?? 0).getTime() - new Date(b.creationDate ?? 0).getTime()
          break
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [orders, sortKey, sortDir, filterStatus])

  function th(key: SortKey, label: string, className?: string) {
    return (
      <th
        className={[styles.thSortable, className].filter(Boolean).join(' ')}
        onClick={() => handleSort(key)}
        aria-sort={sortKey === key ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
      >
        {label} <SortArrow active={sortKey === key} dir={sortDir} />
      </th>
    )
  }

  return (
    <div>
      <div className={styles.filterBar} role="toolbar" aria-label="Filter by status">
        {FILTER_LABELS.map(({ key, label }) => (
          <button
            key={key}
            className={[styles.filterChip, filterStatus === key ? styles.filterChipActive : ''].filter(Boolean).join(' ')}
            onClick={() => setFilterStatus(key)}
          >
            {label}
            {key !== 'all' && (
              <span className={styles.filterChipCount}>
                {orders.filter((o) => o.displayStatus === key).length}
              </span>
            )}
          </button>
        ))}
      </div>

      <table className={styles.table}>
        <thead>
          <tr>
            {th('card', 'CARD')}
            {th('price', 'PRICE')}
            {th('net', 'NET')}
            {th('buyer', 'BUYER')}
            <th>MSG</th>
            {th('status', 'STATUS')}
            {th('sold', 'SOLD')}
          </tr>
        </thead>
        <tbody>
          {isLoading
            ? Array.from({ length: 5 }, (_, i) => <SkeletonRow key={i} />)
            : displayed.map((order) => (
                <tr
                  key={order.orderId}
                  className={[styles.row, order.displayStatus === 'complete' ? styles.rowFaded : ''].filter(Boolean).join(' ')}
                  data-selected={order.orderId === selectedId ? 'true' : undefined}
                  onClick={() => onRowClick(order.orderId)}
                >
                  <td className={styles.cardCell}>
                    <div className={styles.cardTitle}>
                      {order.lineItems[0]?.title ?? 'Order'}
                    </div>
                    <div className={styles.cardMeta}>#{order.legacyOrderId ?? order.orderId}</div>
                  </td>
                  <td className={styles.priceCell}>
                    {order.totalAmount != null ? `$${order.totalAmount.toFixed(2)}` : '—'}
                  </td>
                  <td className={styles.netCell}>
                    {order.netPayout != null
                      ? `$${order.netPayout.toFixed(2)}`
                      : order.totalAmount != null && order.ebayFee != null
                        ? `~$${(order.totalAmount - order.ebayFee).toFixed(2)}`
                        : '—'}
                  </td>
                  <td className={styles.buyerCell}>{order.buyerUsername ?? '—'}</td>
                  <td className={styles.msgCell}>
                    {order.displayStatus !== 'complete' && <MsgIcon orderId={order.orderId} />}
                  </td>
                  <td>
                    <LifecycleBadge status={order.displayStatus} />
                  </td>
                  <td className={styles.dateCell}>{formatDate(order.creationDate)}</td>
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  )
}
