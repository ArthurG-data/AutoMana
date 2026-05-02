export type ManaColor = 'W' | 'U' | 'B' | 'R' | 'G' | 'C'

interface PipConfig {
  bg: string
  fg: string
}

const PIP_COLORS: Record<ManaColor, PipConfig> = {
  W: { bg: '#fffbe6', fg: '#8a7a3b' },
  U: { bg: '#cfe7f5', fg: '#1a5c8a' },
  B: { bg: '#cbc2bf', fg: '#1a1a1a' },
  R: { bg: '#f5b9a4', fg: '#8a2d1a' },
  G: { bg: '#bce3c5', fg: '#1a5c2a' },
  C: { bg: '#dcd6cb', fg: '#5a544a' },
}

interface PipProps {
  color: ManaColor
  size?: number
}

export function Pip({ color, size = 14 }: PipProps) {
  const { bg, fg } = PIP_COLORS[color]

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: size,
        height: size,
        borderRadius: '50%',
        background: bg,
        color: fg,
        fontSize: size * 0.62,
        fontFamily: 'var(--font-serif)',
        fontWeight: 600,
        boxShadow: 'inset 0 0 0 0.5px rgba(0,0,0,0.18)',
        flex: '0 0 auto',
      }}
    >
      {color === 'C' ? '' : color}
    </span>
  )
}
