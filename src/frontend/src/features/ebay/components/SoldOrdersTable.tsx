import { LifecycleBadge } from './LifecycleBadge'
import type { SoldOrder } from '../soldOrders'
import styles from './SoldOrdersTable.module.css'

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

export function SoldOrdersTable({ orders, isLoading, selectedId, onRowClick }: SoldOrdersTableProps) {
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>CARD</th>
          <th>PRICE</th>
          <th>BUYER</th>
          <th>MSG</th>
          <th>STATUS</th>
          <th>SOLD</th>
        </tr>
      </thead>
      <tbody>
        {isLoading
          ? Array.from({ length: 5 }, (_, i) => <SkeletonRow key={i} />)
          : orders.map((order) => (
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
                  {order.totalAmount != null
                    ? `$${order.totalAmount.toFixed(2)}`
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
  )
}
