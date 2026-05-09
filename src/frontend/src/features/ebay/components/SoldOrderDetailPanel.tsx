// src/frontend/src/features/ebay/components/SoldOrderDetailPanel.tsx
import { useState } from 'react'
import type { SoldOrder, DisplayStatus } from '../soldOrders'
import { markOrderSent, markOrderSentWithTracking, updateOrderLocalStatus } from '../api'
import styles from './SoldOrderDetailPanel.module.css'

const STAGES: DisplayStatus[] = ['sold', 'sent', 'in_transit', 'complete']
const STAGE_ICONS: Record<DisplayStatus, string> = {
  sold: '💰', sent: '📦', in_transit: '🚚', complete: '✅',
}
const STAGE_LABELS: Record<DisplayStatus, string> = {
  sold: 'Sold', sent: 'Sent', in_transit: 'Transit', complete: 'Done',
}

const COMMON_CARRIERS = ['AusPost', 'DHL', 'FedEx', 'UPS', 'TNT', 'StarTrack', 'CouriersPlease']

interface Props {
  order: SoldOrder
  onClose: () => void
  onStatusChange: (orderId: string, newStatus: DisplayStatus) => void
}

export function SoldOrderDetailPanel({ order, onClose, onStatusChange }: Props) {
  const [showTrackingForm, setShowTrackingForm] = useState(false)
  const [carrier, setCarrier] = useState(COMMON_CARRIERS[0])
  const [trackingNum, setTrackingNum] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const lineItemIds = order.lineItems.map((li) => li.lineItemId).filter(Boolean) as string[]

  async function handleMarkSent() {
    setIsSubmitting(true)
    setError(null)
    try {
      await markOrderSent(order.appCode, order.orderId, lineItemIds)
      onStatusChange(order.orderId, 'sent')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to mark as sent')
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleMarkSentWithTracking(e: React.FormEvent) {
    e.preventDefault()
    if (!trackingNum.trim()) return
    setIsSubmitting(true)
    setError(null)
    try {
      await markOrderSentWithTracking(order.appCode, order.orderId, lineItemIds, carrier, trackingNum.trim())
      onStatusChange(order.orderId, 'sent')
      setShowTrackingForm(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to mark as sent')
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleLocalStatus(newStatus: 'in_transit' | 'complete') {
    setIsSubmitting(true)
    setError(null)
    try {
      await updateOrderLocalStatus(order.appCode, order.orderId, newStatus)
      onStatusChange(order.orderId, newStatus)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update status')
    } finally {
      setIsSubmitting(false)
    }
  }

  const currentIdx = STAGES.indexOf(order.displayStatus)
  const cardTitle = order.lineItems[0]?.title ?? 'Order'

  return (
    <aside className={styles.panel}>
      {/* Header */}
      <div className={styles.header}>
        <div>
          <div className={styles.headerTitle}>{cardTitle}</div>
          <div className={styles.headerMeta}>#{order.legacyOrderId ?? order.orderId}</div>
        </div>
        <button className={styles.closeBtn} aria-label="Close panel" onClick={onClose}>✕</button>
      </div>

      {/* Lifecycle strip */}
      <div className={styles.section}>
        <div className={styles.sectionLabel}>Lifecycle</div>
        <div className={styles.strip}>
          {STAGES.map((stage, i) => (
            <div key={stage} className={styles.stripItem}>
              <div className={[styles.stripDot, i === currentIdx ? styles.stripDotActive : i < currentIdx ? styles.stripDotDone : styles.stripDotFuture].join(' ')}>
                {STAGE_ICONS[stage]}
              </div>
              <div className={[styles.stripLabel, i === currentIdx ? styles.stripLabelActive : ''].join(' ')}>
                {STAGE_LABELS[stage]}
              </div>
              {i < STAGES.length - 1 && (
                <div className={[styles.stripLine, i < currentIdx ? styles.stripLineDone : ''].join(' ')} />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Order info */}
      <div className={styles.section}>
        <div className={styles.sectionLabel}>Order</div>
        <div className={styles.infoRow}>
          <span className={styles.infoKey}>Sale price</span>
          <span className={styles.infoVal}>
            {order.totalAmount != null ? `$${order.totalAmount.toFixed(2)} ${order.currency ?? ''}` : '—'}
          </span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.infoKey}>Buyer</span>
          <span className={styles.infoValAccent}>{order.buyerUsername ?? '—'}</span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.infoKey}>Sold</span>
          <span className={styles.infoVal}>
            {order.creationDate ? new Date(order.creationDate).toLocaleDateString() : '—'}
          </span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.infoKey}>Order ID</span>
          <span className={styles.infoValMono}>{order.orderId}</span>
        </div>
      </div>

      {/* Financials */}
      <div className={styles.section}>
        <div className={styles.sectionLabel}>Financials</div>
        <div className={styles.infoRow}>
          <span className={styles.infoKey}>Item price</span>
          <span className={styles.infoVal}>
            {order.itemSubtotal != null ? `$${order.itemSubtotal.toFixed(2)}` : '—'}
          </span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.infoKey}>Shipping (buyer paid)</span>
          <span className={styles.infoVal}>
            {order.shippingCollected != null ? `+$${order.shippingCollected.toFixed(2)}` : '—'}
          </span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.infoKey}>eBay fee</span>
          <span className={styles.infoValNeg}>
            {order.ebayFee != null ? `-$${order.ebayFee.toFixed(2)}` : '—'}
          </span>
        </div>
        <hr className={styles.infoDivider} />
        <div className={styles.infoRow}>
          <span className={styles.infoKeyNet}>You receive</span>
          <span className={styles.infoValNet}>
            {order.netPayout != null
              ? `$${order.netPayout.toFixed(2)}${order.currency ? ` ${order.currency}` : ''}`
              : order.totalAmount != null && order.ebayFee != null
                ? `~$${(order.totalAmount - order.ebayFee).toFixed(2)}`
                : '—'}
          </span>
        </div>
      </div>

      {/* Message banner */}
      <div className={styles.messageBanner}>
        <span className={styles.messageBannerIcon}>💬</span>
        <div className={styles.messageBannerBody}>
          <div className={styles.messageBannerTitle}>Messages from buyer</div>
        </div>
        <a
          className={styles.messageBannerLink}
          href="https://www.ebay.com.au/msg/inbox"
          target="_blank"
          rel="noreferrer"
        >
          View ↗
        </a>
      </div>

      {/* Error */}
      {error && <div className={styles.errorMsg}>{error}</div>}

      {/* Actions */}
      <div className={styles.actions}>
        {order.displayStatus === 'sold' && !showTrackingForm && (
          <>
            <button
              className={styles.btnPrimary}
              disabled={isSubmitting}
              onClick={handleMarkSent}
            >
              📦 Mark as sent
            </button>
            <button
              className={styles.btnSecondary}
              disabled={isSubmitting}
              onClick={() => setShowTrackingForm(true)}
            >
              🔗 Add tracking number
            </button>
          </>
        )}

        {order.displayStatus === 'sold' && showTrackingForm && (
          <form onSubmit={handleMarkSentWithTracking} className={styles.trackingForm}>
            <select
              className={styles.trackingSelect}
              value={carrier}
              onChange={(e) => setCarrier(e.target.value)}
            >
              {COMMON_CARRIERS.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <input
              className={styles.trackingInput}
              placeholder="Tracking number"
              value={trackingNum}
              onChange={(e) => setTrackingNum(e.target.value)}
              required
            />
            <button className={styles.btnPrimary} type="submit" disabled={isSubmitting}>
              📦 Confirm & send
            </button>
            <button
              className={styles.btnGhost}
              type="button"
              onClick={() => setShowTrackingForm(false)}
            >
              Cancel
            </button>
          </form>
        )}

        {order.displayStatus === 'sent' && (
          <button
            className={styles.btnSecondary}
            disabled={isSubmitting}
            onClick={() => handleLocalStatus('in_transit')}
          >
            🚚 Mark in transit
          </button>
        )}

        {order.displayStatus === 'in_transit' && (
          <button
            className={styles.btnSecondary}
            disabled={isSubmitting}
            onClick={() => handleLocalStatus('complete')}
          >
            ✅ Mark complete
          </button>
        )}

        <a
          className={styles.btnGhost}
          href={`https://www.ebay.com.au/vod/FetchOrderDetails?orderId=${order.legacyOrderId ?? order.orderId}`}
          target="_blank"
          rel="noreferrer"
        >
          View order on eBay ↗
        </a>
      </div>
    </aside>
  )
}
