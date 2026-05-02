// src/frontend/src/components/ui/Toggle.tsx
import styles from './Toggle.module.css'

interface ToggleProps {
  on: boolean
  onToggle?: () => void
  label?: string
}

export function Toggle({ on, onToggle, label }: ToggleProps) {
  return (
    <button
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={onToggle}
      className={[styles.track, on ? styles.on : styles.off].join(' ')}
    >
      <span className={[styles.thumb, on ? styles.thumbOn : styles.thumbOff].join(' ')} />
    </button>
  )
}
