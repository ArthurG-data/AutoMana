// src/frontend/src/components/ui/Button.tsx
import React from 'react'
import styles from './Button.module.css'

type ButtonVariant = 'ghost' | 'solid' | 'accent' | 'danger'
type ButtonSize = 'sm' | 'md'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  icon?: React.ReactNode
}

export function Button({
  variant = 'ghost',
  size = 'md',
  icon,
  children,
  className,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={[
        styles.button,
        styles[variant],
        styles[size],
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      {...rest}
    >
      {icon && <span className={styles.icon}>{icon}</span>}
      {children}
    </button>
  )
}
