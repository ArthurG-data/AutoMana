// src/frontend/src/components/layout/UserMenu.tsx
import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useAuthStore } from '../../store/auth'
import styles from './UserMenu.module.css'

export function UserMenu() {
  const navigate = useNavigate()
  const token = useAuthStore((s) => s.token)
  const currentUser = useAuthStore((s) => s.currentUser)
  const logout = useAuthStore((s) => s.logout)

  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    if (!open) return
    function handlePointerDown(e: PointerEvent) {
      const target = e.target as Node
      if (
        !triggerRef.current?.contains(target) &&
        !menuRef.current?.contains(target)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener('pointerdown', handlePointerDown)
    return () => document.removeEventListener('pointerdown', handlePointerDown)
  }, [open])

  // Close on Escape, return focus to trigger
  useEffect(() => {
    if (!open) return
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setOpen(false)
        triggerRef.current?.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open])

  const handleLogout = useCallback(() => {
    setOpen(false)
    logout()
    // Navigation is handled by the __root.tsx effect watching token → null
  }, [logout])

  // Unauthenticated: show a login link styled as an avatar-slot button
  if (!token || !currentUser) {
    return (
      <button
        className={styles.loginBtn}
        onClick={() => navigate({ to: '/login' })}
        aria-label="Log in or sign up"
      >
        Login / Sign Up
      </button>
    )
  }

  // Authenticated: avatar button that opens a dropdown
  const initials = currentUser.username.slice(0, 2).toUpperCase()

  return (
    <div className={styles.root}>
      <button
        ref={triggerRef}
        className={styles.avatarBtn}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`User menu for ${currentUser.username}`}
        title={currentUser.username}
      >
        {initials}
      </button>

      {open && (
        <div
          ref={menuRef}
          className={styles.dropdown}
          role="menu"
          aria-label="User menu"
        >
          <div className={styles.profile} role="none">
            <div className={styles.profileInitials}>{initials}</div>
            <div className={styles.profileInfo}>
              <div className={styles.profileUsername}>{currentUser.username}</div>
              {currentUser.email && (
                <div className={styles.profileEmail}>{currentUser.email}</div>
              )}
            </div>
          </div>

          <div className={styles.divider} role="none" />

          <button
            className={styles.menuItem}
            role="menuitem"
            onClick={handleLogout}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 16 16"
              style={{ display: 'block', flex: '0 0 auto' }}
              aria-hidden="true"
            >
              <path
                d="M6 3H3a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h3M11 5l3 3-3 3M14 8H6"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                fill="none"
              />
            </svg>
            Log out
          </button>
        </div>
      )}
    </div>
  )
}
