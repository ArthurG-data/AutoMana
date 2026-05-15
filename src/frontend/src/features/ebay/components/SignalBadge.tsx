export interface SignalBadgeProps {
  action: 'raise' | 'lower' | 'hold' | 'draft' | null | undefined
  confidence?: number
}

const COLOR_MAP: Record<string, { background: string; color: string }> = {
  raise: { background: '#dcfce7', color: '#16a34a' },
  lower: { background: '#fef9c3', color: '#b45309' },
  hold:  { background: '#f1f5f9', color: '#64748b' },
  draft: { background: '#fee2e2', color: '#dc2626' },
}

const LABEL_MAP: Record<string, string> = {
  raise: '↑ Raise',
  lower: '↓ Lower',
  hold:  '— Hold',
  draft: '✕ Draft',
}

export function SignalBadge({ action, confidence }: SignalBadgeProps) {
  if (action == null) return null

  const { background, color } = COLOR_MAP[action]
  const label = LABEL_MAP[action]
  const pct = confidence !== undefined ? ` ${Math.round(confidence * 100)}%` : ''

  return (
    <span
      title={action}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.25rem',
        padding: '0.125rem 0.5rem',
        borderRadius: '9999px',
        fontSize: '0.75rem',
        fontWeight: 600,
        background,
        color,
        whiteSpace: 'nowrap',
      }}
    >
      {label}
      {pct && (
        <span style={{ fontWeight: 400, opacity: 0.75 }}>
          {pct}
        </span>
      )}
    </span>
  )
}
