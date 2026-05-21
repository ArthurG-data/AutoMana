// src/frontend/src/features/ai/components/ResultStrip.tsx
import styles from './ResultStrip.module.css'

interface ResultStripProps {
  toolsCalled: string[]
}

const CARD_TOOLS = new Set(['search_cards'])
const PRICE_TOOLS = new Set(['get_card_prices', 'get_market_comps'])

export function ResultStrip({ toolsCalled }: ResultStripProps) {
  const hasCardTool = toolsCalled.some((t) => CARD_TOOLS.has(t))
  const hasPriceTool = toolsCalled.some((t) => PRICE_TOOLS.has(t))

  if (!hasCardTool && !hasPriceTool) return null

  return (
    <div className={styles.strip}>
      {hasCardTool && (
        <span className={`${styles.pill} ${styles.cards}`}>
          Card search
        </span>
      )}
      {hasPriceTool && (
        <span className={`${styles.pill} ${styles.prices}`}>
          Price lookup
        </span>
      )}
    </div>
  )
}
