// src/frontend/src/components/ui/Chip.tsx
import React from 'react'

interface ChipProps {
  children: React.ReactNode
  color?: string
  dim?: boolean
  style?: React.CSSProperties
}

export function Chip({ children, color, dim = false, style = {} }: ChipProps) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '4px 9px',
        borderRadius: 999,
        fontSize: 11,
        background: dim ? 'rgba(255,255,255,0.04)' : 'transparent',
        border: `1px solid var(--hd-border)`,
        color: color ?? 'var(--hd-muted)',
        fontFamily: 'var(--font-sans)',
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {children}
    </span>
  )
}
