// src/frontend/src/components/design-system/ManaSymbol.tsx
import React from 'react'
import styles from './ManaSymbol.module.css'

/**
 * Converts an MTG cost token (the bit between curly braces) to its
 * corresponding mana-font CSS class. Examples:
 *   "W"   -> "ms-w"
 *   "R"   -> "ms-r"
 *   "3"   -> "ms-3"
 *   "X"   -> "ms-x"
 *   "T"   -> "ms-tap"
 *   "Q"   -> "ms-untap"
 *   "W/U" -> "ms-wu"
 *   "2/W" -> "ms-2w"
 *   "W/P" -> "ms-wp"
 *   "E"   -> "ms-e"
 */
function symbolToClass(token: string): string {
  const lower = token.toLowerCase().replace(/\//g, '')
  if (lower === 't') return 'ms-tap'
  if (lower === 'q') return 'ms-untap'
  return `ms-${lower}`
}

interface ManaSymbolProps {
  symbol: string
  size?: number
  /** Apply the rounded "cost" background (true for mana cost row, false for inline oracle symbols). */
  cost?: boolean
}

export function ManaSymbol({ symbol, size = 13, cost = true }: ManaSymbolProps) {
  return (
    <i
      className={`${styles.symbol} ms ${symbolToClass(symbol)}${cost ? ' ms-cost' : ''}`}
      style={{ fontSize: size }}
      aria-label={`{${symbol}}`}
      title={`{${symbol}}`}
    />
  )
}

/**
 * Splits a string containing `{X}` cost tokens (mana, tap, numbers, etc.)
 * and returns a list of React nodes where each token is rendered as a
 * <ManaSymbol /> and the rest is plain text.
 *
 * Usage: <p>{renderSymbolsInText("Tap: Add {R} or {G}.")}</p>
 */
export function renderSymbolsInText(
  text: string,
  options: { size?: number; cost?: boolean } = {},
): React.ReactNode[] {
  const { size = 11, cost = false } = options
  const parts = text.split(/(\{[^}]+\})/)
  return parts.map((part, i) => {
    const match = part.match(/^\{([^}]+)\}$/)
    if (match) {
      return <ManaSymbol key={i} symbol={match[1]} size={size} cost={cost} />
    }
    return <React.Fragment key={i}>{part}</React.Fragment>
  })
}
