// src/frontend/src/routes/login.tsx
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useState, useId } from 'react'
import { CardArt } from '../components/design-system/CardArt'
import { useAuthStore } from '../store/auth'
import { postLogin, postSignup, getMe, postForgotPassword } from '../features/auth/api'
import styles from './Login.module.css'

export const Route = createFileRoute('/login')({
  component: LoginPage,
})

const CARD_NAMES = ['Ragavan', 'Mox Diamond', 'Sheoldred', 'One Ring']

type Mode = 'login' | 'signup' | 'forgot'

function LoginPage() {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [resetSent, setResetSent] = useState(false)

  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)
  const formId = useId()

  function switchMode(next: Mode) {
    setMode(next)
    setError(null)
    setEmail('')
    setUsername('')
    setPassword('')
    setResetSent(false)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)

    try {
      if (mode === 'forgot') {
        await postForgotPassword(email)
        setResetSent(true)
        return
      }

      if (mode === 'signup') {
        await postSignup({ username, email, password })
      }

      const tokens = await postLogin(email, password)
      const me = await getMe(tokens.access_token)
      login(tokens.access_token, { username: me.username, email })
      navigate({ to: '/' })
    } catch (err: unknown) {
      const e = err as { status?: number; message?: string }
      if (mode === 'signup' && e.status === 409) {
        setError('An account with that email or username already exists.')
      } else if (mode === 'signup' && e.status === 422) {
        setError('Please fill in all required fields correctly.')
      } else if (mode === 'login' && e.status === 401) {
        setError('Invalid email or password.')
      } else {
        setError(e.message ?? 'Something went wrong. Please try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const isLogin = mode === 'login'
  const isForgot = mode === 'forgot'

  const leftEyebrow = isLogin ? '● welcome back' : isForgot ? '● account recovery' : '● get started'
  const leftHeadline = isLogin ? (
    <>The market<br /><span className={styles.leftHeadlineAccent}>moves while you sleep.</span></>
  ) : isForgot ? (
    <>Reset your<br /><span className={styles.leftHeadlineAccent}>password.</span></>
  ) : (
    <>Track every card,<br /><span className={styles.leftHeadlineAccent}>every price move.</span></>
  )
  const leftSub = isLogin
    ? 'Sign in to see what your collection did overnight, manage active eBay listings, and catch every price swing.'
    : isForgot
    ? "Enter your email and we'll send you a link to reset your password."
    : 'Create your account and start tracking your MTG collection with real-time pricing and eBay integration.'

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
          <div className={styles.leftEyebrow}>{leftEyebrow}</div>
          <h1 className={styles.leftHeadline}>{leftHeadline}</h1>
          <p className={styles.leftSub}>{leftSub}</p>
        </div>
        <div className={styles.cardStack}>
          {CARD_NAMES.map((name, i) => (
            <div
              key={name}
              style={{
                marginLeft: i === 0 ? 0 : -28,
                transform: `rotate(${(i - 1.5) * 4}deg)`,
              }}
            >
              <CardArt name={name} w={100} h={140} hue={180 + i * 18} label={false} />
            </div>
          ))}
        </div>
      </div>

      {/* ── Right panel ── */}
      <div className={styles.right}>
        {isForgot ? (
          resetSent ? (
            <>
              <div className={styles.formTitle}>Check your inbox</div>
              <div className={styles.formSub}>
                A reset link is on its way. It expires in 30 minutes.
              </div>
              <div style={{ marginTop: 24 }}>
                <button
                  type="button"
                  className={styles.formSubLink}
                  onClick={() => switchMode('login')}
                >
                  ← Back to log in
                </button>
              </div>
            </>
          ) : (
            <>
              <div className={styles.formTitle}>Reset password</div>
              <div className={styles.formSub}>
                Remembered it?{' '}
                <button
                  type="button"
                  className={styles.formSubLink}
                  onClick={() => switchMode('login')}
                >
                  Log in
                </button>
              </div>
              <form id={formId} onSubmit={handleSubmit} className={styles.fields} noValidate>
                <div>
                  <label htmlFor={`${formId}-email`} className={styles.fieldLabel}>
                    Email
                  </label>
                  <input
                    id={`${formId}-email`}
                    className={styles.input}
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    autoComplete="email"
                    required
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
                  {submitting ? 'Sending...' : 'Send reset link →'}
                </button>
              </form>
            </>
          )
        ) : (
          <>
            <div className={styles.formTitle}>{isLogin ? 'Log in' : 'Create account'}</div>
            <div className={styles.formSub}>
              {isLogin ? (
                <>
                  Don't have an account?{' '}
                  <button
                    type="button"
                    className={styles.formSubLink}
                    onClick={() => switchMode('signup')}
                  >
                    Create one
                  </button>
                </>
              ) : (
                <>
                  Already have an account?{' '}
                  <button
                    type="button"
                    className={styles.formSubLink}
                    onClick={() => switchMode('login')}
                  >
                    Log in
                  </button>
                </>
              )}
            </div>

            <form
              id={formId}
              onSubmit={handleSubmit}
              className={styles.fields}
              noValidate
            >
              {!isLogin && (
                <div>
                  <label htmlFor={`${formId}-username`} className={styles.fieldLabel}>
                    Username
                  </label>
                  <input
                    id={`${formId}-username`}
                    className={styles.input}
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="yourname"
                    autoComplete="username"
                    required
                    minLength={3}
                    maxLength={50}
                  />
                </div>
              )}

              <div>
                <label htmlFor={`${formId}-email`} className={styles.fieldLabel}>
                  Email
                </label>
                <input
                  id={`${formId}-email`}
                  className={styles.input}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  autoComplete="email"
                  required
                />
              </div>

              <div>
                <div className={styles.fieldHeader}>
                  <label htmlFor={`${formId}-password`} className={styles.fieldLabel}>
                    Password
                  </label>
                  {isLogin && (
                    <button
                      type="button"
                      className={styles.forgotLink}
                      onClick={() => switchMode('forgot')}
                    >
                      Forgot?
                    </button>
                  )}
                </div>
                <input
                  id={`${formId}-password`}
                  className={styles.input}
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete={isLogin ? 'current-password' : 'new-password'}
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
                {submitting
                  ? isLogin ? 'Logging in...' : 'Creating account...'
                  : isLogin ? 'Log in →' : 'Create account →'}
              </button>
            </form>

            <div className={styles.terms}>
              By continuing you agree to the Terms · Privacy
            </div>
          </>
        )}
      </div>
    </div>
  )
}
