import type { DisplayStatus } from '../soldOrders'
import styles from './LifecycleBadge.module.css'

interface LifecycleBadgeProps {
  status: DisplayStatus
}

const CONFIG: Record<DisplayStatus, { icon: string; label: string; mod: string }> = {
  sold:       { icon: '💰', label: 'Sold',    mod: 'sold' },
  sent:       { icon: '📦', label: 'Sent',    mod: 'sent' },
  in_transit: { icon: '🚚', label: 'Transit', mod: 'transit' },
  complete:   { icon: '✅', label: 'Done',    mod: 'complete' },
}

export function LifecycleBadge({ status }: LifecycleBadgeProps) {
  const { icon, label, mod } = CONFIG[status]
  return (
    <span className={`${styles.badge} ${styles[mod]}`}>
      {icon} {label}
    </span>
  )
}
