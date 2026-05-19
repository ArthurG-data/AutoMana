export interface SignalBadgeProps {
  action: 'raise' | 'lower' | 'hold' | 'draft' | null | undefined
  confidence?: number
  strategies?: Record<string, { price: number; confidence: number; description?: string }>
  currency?: string
}

const PALETTE = {
  raise: { bg: 'rgba(34,197,94,0.10)',   border: 'rgba(34,197,94,0.30)',   text: '#22c55e' },
  lower: { bg: 'rgba(245,158,11,0.10)',  border: 'rgba(245,158,11,0.30)',  text: '#f59e0b' },
  hold:  { bg: 'rgba(148,163,184,0.08)', border: 'rgba(148,163,184,0.25)', text: '#94a3b8' },
  draft: { bg: 'rgba(248,113,113,0.10)', border: 'rgba(248,113,113,0.30)', text: '#f87171' },
}

const LABEL = { raise: '↑ Raise', lower: '↓ Lower', hold: '— Hold', draft: '✕ Draft' }

function buildTooltip(
  action: string,
  confidence: number | undefined,
  strategies?: SignalBadgeProps['strategies'],
  currency = 'AUD',
): string {
  const label = LABEL[action as keyof typeof LABEL] ?? action
  const pctStr = confidence !== undefined ? ` (${Math.round(confidence * 100)}%)` : ''
  let tip = `${label}${pctStr}`
  if (strategies && Object.keys(strategies).length > 0) {
    const alts = Object.entries(strategies)
      .map(([k, s]) => `  ${k}: ${currency} ${s.price.toFixed(2)} · ${Math.round(s.confidence * 100)}%`)
      .join('\n')
    tip += `\n\nAlternatives:\n${alts}`
  }
  return tip
}

export function SignalBadge({ action, confidence, strategies, currency = 'AUD' }: SignalBadgeProps) {
  if (action == null) return null

  const { bg, border, text } = PALETTE[action]
  const label = LABEL[action]
  const pct = confidence !== undefined ? ` ${Math.round(confidence * 100)}%` : ''
  const hasAlts = strategies && Object.keys(strategies).length > 0

  return (
    <span
      title={buildTooltip(action, confidence, strategies, currency)}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.2rem',
        padding: '2px 7px',
        borderRadius: '4px',
        fontSize: '11px',
        fontWeight: 600,
        fontFamily: 'var(--font-mono)',
        letterSpacing: '0.02em',
        background: bg,
        color: text,
        border: `1px solid ${border}`,
        whiteSpace: 'nowrap',
        cursor: hasAlts ? 'help' : 'default',
      }}
    >
      {label}
      {pct && (
        <span style={{ fontWeight: 400, opacity: 0.65, fontSize: '10px' }}>
          {pct}
        </span>
      )}
      {hasAlts && (
        <span style={{ opacity: 0.35, fontSize: '8px', marginLeft: '2px', letterSpacing: '0.1em' }}>
          ···
        </span>
      )}
    </span>
  )
}
