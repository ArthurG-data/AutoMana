// src/frontend/src/features/ai/components/ModeToggle.tsx
import type { ChatMode } from '../types'
import styles from './ModeToggle.module.css'

interface ModeToggleProps {
  mode: ChatMode
  onModeChange: (mode: ChatMode) => void
}

export function ModeToggle({ mode, onModeChange }: ModeToggleProps) {
  return (
    <div className={styles.toggle}>
      <button
        className={`${styles.btn} ${mode === 'cards' ? styles.active : ''}`}
        aria-pressed={mode === 'cards'}
        onClick={() => onModeChange('cards')}
      >
        Find Cards
      </button>
      <button
        className={`${styles.btn} ${mode === 'prices' ? styles.active : ''}`}
        aria-pressed={mode === 'prices'}
        onClick={() => onModeChange('prices')}
      >
        Check Prices
      </button>
    </div>
  )
}
