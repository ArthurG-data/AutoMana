// src/frontend/src/routes/login.tsx
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { CardArt } from '../components/design-system/CardArt'
import { Icon } from '../components/design-system/Icon'
import { useAuthStore } from '../store/auth'
import styles from './Login.module.css'

export const Route = createFileRoute('/login')({
  component: LoginPage,
})

const SOCIAL = [
  { icon: 'G', label: 'Continue with Google' },
  { icon: '⌘', label: 'Continue with Apple'  },
  { icon: '◐', label: 'Continue with Discord' },
]

const CARD_NAMES = ['Ragavan', 'Mox Diamond', 'Sheoldred', 'One Ring']

function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    // Stubbed: accepts any non-empty email+password
    login('dev-stub-token', { id: 'dev', email: email || 'dev@automana.local' })
    navigate({ to: '/collection' } as any)
  }

  return (
    <div className={styles.page}>
      <div className={styles.left}>
        <div className={styles.leftGlow} />
        <div className={styles.leftLogo}>
          <div className={styles.logoMark}>a</div>
          <span className={styles.logoText}>auto<span className={styles.logoAccent}>mana</span></span>
        </div>
        <div className={styles.leftContent}>
          <div className={styles.leftEyebrow}>● welcome back</div>
          <h1 className={styles.leftHeadline}>
            The market<br />
            <span className={styles.leftHeadlineAccent}>moves while you sleep.</span>
          </h1>
          <p className={styles.leftSub}>
            Sign in to see what your collection did overnight, manage active eBay listings,
            and catch every price swing.
          </p>
        </div>
        <div className={styles.cardStack}>
          {CARD_NAMES.map((name, i) => (
            <div key={name} style={{ marginLeft: i === 0 ? 0 : -28, transform: `rotate(${(i - 1.5) * 4}deg)` }}>
              <CardArt name={name} w={100} h={140} hue={180 + i * 18} label={false} />
            </div>
          ))}
        </div>
      </div>

      <div className={styles.right}>
        <div className={styles.formTitle}>Log in</div>
        <div className={styles.formSub}>
          Don't have an account?{' '}
          <span className={styles.formSubLink}>Create one</span>
        </div>

        <div className={styles.socialButtons}>
          {SOCIAL.map((s) => (
            <button key={s.label} className={styles.socialBtn}>
              <span className={styles.socialIcon}>{s.icon}</span>
              <span className={styles.socialLabel}>{s.label}</span>
              <Icon kind="arrowRight" size={14} color="var(--hd-sub)" />
            </button>
          ))}
        </div>

        <div className={styles.divider}>
          <div className={styles.dividerLine} />
          <span className={styles.dividerText}>or with email</span>
          <div className={styles.dividerLine} />
        </div>

        <form onSubmit={handleSubmit} className={styles.fields}>
          <div>
            <div className={styles.fieldLabel}>Email</div>
            <input
              className={styles.input}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
            />
          </div>
          <div>
            <div className={styles.fieldHeader}>
              <div className={styles.fieldLabel}>Password</div>
              <span className={styles.forgotLink}>Forgot?</span>
            </div>
            <input
              className={styles.input}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
            />
          </div>
          <button type="submit" className={styles.submitBtn}>Log in →</button>
        </form>

        <div className={styles.terms}>By continuing you agree to the Terms · Privacy</div>
      </div>
    </div>
  )
}
