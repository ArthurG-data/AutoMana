// src/frontend/src/routes/reset-password.tsx
import { createFileRoute, useNavigate, useSearch } from '@tanstack/react-router'
import { useState, useId } from 'react'
import { z } from 'zod'
import { CardArt } from '../components/design-system/CardArt'
import { postResetPassword } from '../features/auth/api'
import styles from './Login.module.css'

const searchSchema = z.object({
  token: z.string().optional(),
})

export const Route = createFileRoute('/reset-password')({
  validateSearch: searchSchema,
  component: ResetPasswordPage,
})

const CARD_NAMES = ['Ragavan', 'Mox Diamond', 'Sheoldred', 'One Ring']

function ResetPasswordPage() {
  const { token } = useSearch({ from: '/reset-password' })
  const navigate = useNavigate()
  const formId = useId()

  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [success, setSuccess] = useState(false)

  if (!token) {
    return (
      <div className={styles.page}>
        <div className={styles.left}>
          <div className={styles.leftGlow} />
          <div className={styles.leftLogo}>
            <div className={styles.logoMark}>a</div>
            <span className={styles.logoText}>
              auto<span className={styles.logoAccent}>mana</span>
            </span>
          </div>
          <div className={styles.leftContent}>
            <div className={styles.leftEyebrow}>● account recovery</div>
            <h1 className={styles.leftHeadline}>
              Reset your<br />
              <span className={styles.leftHeadlineAccent}>password.</span>
            </h1>
          </div>
          <div className={styles.cardStack}>
            {CARD_NAMES.map((name, i) => (
              <div
                key={name}
                style={{ marginLeft: i === 0 ? 0 : -28, transform: `rotate(${(i - 1.5) * 4}deg)` }}
              >
                <CardArt name={name} w={100} h={140} hue={180 + i * 18} label={false} />
              </div>
            ))}
          </div>
        </div>
        <div className={styles.right}>
          <div className={styles.formTitle}>Invalid link</div>
          <div className={styles.formSub}>
            This reset link is missing or malformed.{' '}
            <button
              type="button"
              className={styles.formSubLink}
              onClick={() => navigate({ to: '/login' })}
            >
              Request a new one
            </button>
          </div>
        </div>
      </div>
    )
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setSubmitting(true)
    try {
      await postResetPassword(token, newPassword)
      setSuccess(true)
      setTimeout(() => navigate({ to: '/login' }), 2000)
    } catch (err: unknown) {
      const e = err as { status?: number; message?: string }
      if (e.status === 400) {
        setError('This link has expired or has already been used.')
      } else {
        setError(e.message ?? 'Something went wrong. Please try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className={styles.page}>
      {/* ── Left panel ── */}
      <div className={styles.left}>
        <div className={styles.leftGlow} />
        <div className={styles.leftLogo}>
          <div className={styles.logoMark}>a</div>
          <span className={styles.logoText}>
            auto<span className={styles.logoAccent}>mana</span>
          </span>
        </div>
        <div className={styles.leftContent}>
          <div className={styles.leftEyebrow}>● account recovery</div>
          <h1 className={styles.leftHeadline}>
            Reset your<br />
            <span className={styles.leftHeadlineAccent}>password.</span>
          </h1>
          <p className={styles.leftSub}>Choose a new password for your AutoMana account.</p>
        </div>
        <div className={styles.cardStack}>
          {CARD_NAMES.map((name, i) => (
            <div
              key={name}
              style={{ marginLeft: i === 0 ? 0 : -28, transform: `rotate(${(i - 1.5) * 4}deg)` }}
            >
              <CardArt name={name} w={100} h={140} hue={180 + i * 18} label={false} />
            </div>
          ))}
        </div>
      </div>

      {/* ── Right panel ── */}
      <div className={styles.right}>
        {success ? (
          <>
            <div className={styles.formTitle}>Password updated</div>
            <div className={styles.formSub}>Redirecting you to the login page…</div>
          </>
        ) : (
          <>
            <div className={styles.formTitle}>Set new password</div>
            <div className={styles.formSub}>
              Remembered it?{' '}
              <button
                type="button"
                className={styles.formSubLink}
                onClick={() => navigate({ to: '/login' })}
              >
                Log in
              </button>
            </div>
            <form id={formId} onSubmit={handleSubmit} className={styles.fields} noValidate>
              <div>
                <label htmlFor={`${formId}-new`} className={styles.fieldLabel}>
                  New password
                </label>
                <input
                  id={`${formId}-new`}
                  className={styles.input}
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="new-password"
                  required
                  minLength={8}
                />
              </div>
              <div>
                <label htmlFor={`${formId}-confirm`} className={styles.fieldLabel}>
                  Confirm password
                </label>
                <input
                  id={`${formId}-confirm`}
                  className={styles.input}
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="new-password"
                  required
                  minLength={8}
                />
              </div>
              {error && (
                <div className={styles.errorBanner} role="alert">
                  {error}
                </div>
              )}
              <button
                type="submit"
                className={styles.submitBtn}
                disabled={submitting}
                aria-busy={submitting}
              >
                {submitting ? 'Saving...' : 'Set new password →'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
