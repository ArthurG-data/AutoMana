import type { CardSuggestion } from '../../features/cards/types'
import styles from './SuggestionsDropdown.module.css'

interface SuggestionsDropdownProps {
  suggestions: CardSuggestion[]
  selectedIndex: number
  onSelect: (suggestion: CardSuggestion) => void
  isLoading?: boolean
  isOpen: boolean
}

export function SuggestionsDropdown({
  suggestions,
  selectedIndex,
  onSelect,
  isLoading,
  isOpen,
}: SuggestionsDropdownProps) {
  if (!isOpen) {
    return null
  }

  if (isLoading) {
    return (
      <div className={styles.dropdown}>
        <div className={styles.empty}>Loading suggestions...</div>
      </div>
    )
  }

  if (suggestions.length === 0) {
    return (
      <div className={styles.dropdown}>
        <div className={styles.empty}>No cards found</div>
      </div>
    )
  }

  return (
    <div className={styles.dropdown}>
      <ul className={styles.list}>
        {suggestions.map((suggestion, index) => (
          <button
            key={suggestion.card_version_id}
            className={[styles.item, index === selectedIndex ? styles.selected : ''].join(' ')}
            onClick={() => onSelect(suggestion)}
            type="button"
          >
            <div className={styles.itemText}>
              <span className={styles.itemName}>
                {suggestion.card_name} <span className={styles.itemSet}>({suggestion.set_code.toUpperCase()})</span>
              </span>
            </div>
          </button>
        ))}
      </ul>
    </div>
  )
}
