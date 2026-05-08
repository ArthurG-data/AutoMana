// src/frontend/src/routes/ebay/setup.tsx
import React, { useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { AppShell } from '../../components/layout/AppShell'
import { TopBar } from '../../components/layout/TopBar'
import { Button } from '../../components/ui/Button'
import { Toggle } from '../../components/ui/Toggle'
import { Icon } from '../../components/design-system/Icon'
import {
  MOCK_OAUTH_SCOPES,
  REDIRECT_URI,
  SETUP_STEPS,
  HELP_LINKS,
  BYOA_BENEFITS,
  MOCK_CONNECTION_STATUS,
  type OAuthScope,
  type ConnectionStatus,
  type RegistrationResult,
} from '../../features/ebay/mockEbayApp'
import { registerEbayApp } from '../../features/ebay/api'
import styles from './Setup.module.css'

export const Route = createFileRoute('/ebay/setup')({
  component: EbaySetupPage,
})

export { EbaySetupPage }

// ── Step 1: Create app instructions ───────────────────────────────────────

function StepCreateApp() {
  return (
    <div className={styles.stepContent}>
      <h2 className={styles.stepHeading}>Create your eBay app</h2>
      <p className={styles.stepDesc}>
        You'll need a free eBay developer account to generate API credentials for AutoMana.
      </p>
      <ol className={styles.instructionList}>
        <li>
          Go to{' '}
          <a
            href="https://developer.ebay.com"
            target="_blank"
            rel="noopener noreferrer"
            className={styles.externalLink}
          >
            developer.ebay.com
          </a>{' '}
          and sign in (or create a free account).
        </li>
        <li>
          Navigate to <strong>Application Keys</strong> in the top navigation.
        </li>
        <li>
          Click <strong>Create a keyset</strong>, choose <em>Production</em>, and name your app
          (e.g., "AutoMana").
        </li>
        <li>
          Copy the <strong>App ID (Client ID)</strong> and <strong>Cert ID</strong> — you'll
          paste them in the next step.
        </li>
      </ol>
      <div className={styles.infoBox}>
        <Icon kind="shield" size={14} color="var(--hd-blue)" />
        <span>
          eBay developer accounts are free. Your credentials are encrypted at rest and never
          shared with other AutoMana users.
        </span>
      </div>
    </div>
  )
}

// ── Step 2: Paste credentials ──────────────────────────────────────────────

type Environment = 'SANDBOX' | 'PRODUCTION'

interface StepCredentialsProps {
  appName: string
  description: string
  environment: Environment
  appId: string
  certId: string
  onAppNameChange: (v: string) => void
  onDescriptionChange: (v: string) => void
  onEnvironmentChange: (v: Environment) => void
  onAppIdChange: (v: string) => void
  onCertIdChange: (v: string) => void
  errors: Record<string, string>
}

function StepCredentials({
  appName,
  description,
  environment,
  appId,
  certId,
  onAppNameChange,
  onDescriptionChange,
  onEnvironmentChange,
  onAppIdChange,
  onCertIdChange,
  errors,
}: StepCredentialsProps) {
  const [certRevealed, setCertRevealed] = useState(false)
  const [copied, setCopied] = useState(false)

  function copyRuName() {
    navigator.clipboard.writeText(REDIRECT_URI).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className={styles.stepContent}>
      <h2 className={styles.stepHeading}>Paste your eBay credentials</h2>
      <p className={styles.stepDesc}>
        Find these in the eBay Developer Portal under <strong>Application Keys</strong>.
      </p>

      <div className={styles.formGrid}>
        {/* App Name */}
        <div className={styles.field}>
          <label className={styles.fieldLabel} htmlFor="ebay-app-name">
            App Name
          </label>
          <div className={styles.inputWrapper}>
            <Icon kind="key" size={14} color="var(--hd-muted)" />
            <input
              id="ebay-app-name"
              className={[styles.input, errors.appName ? styles.inputError : ''].filter(Boolean).join(' ')}
              type="text"
              placeholder="My AutoMana Store"
              value={appName}
              onChange={(e) => onAppNameChange(e.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          {errors.appName && <span className={styles.errorMsg}>{errors.appName}</span>}
        </div>

        {/* Description */}
        <div className={styles.field}>
          <label className={styles.fieldLabel} htmlFor="ebay-description">
            Description
            <span className={styles.readOnlyTag}>optional</span>
          </label>
          <div className={styles.inputWrapper}>
            <input
              id="ebay-description"
              className={styles.input}
              type="text"
              placeholder="e.g. My main eBay seller account"
              value={description}
              onChange={(e) => onDescriptionChange(e.target.value)}
              autoComplete="off"
            />
          </div>
        </div>

        {/* Environment */}
        <div className={styles.field}>
          <label className={styles.fieldLabel}>
            Environment
          </label>
          <div className={styles.envToggle}>
            <button
              type="button"
              className={[styles.envOption, environment === 'SANDBOX' ? styles.envOptionActive : ''].filter(Boolean).join(' ')}
              onClick={() => onEnvironmentChange('SANDBOX')}
              aria-pressed={environment === 'SANDBOX'}
            >
              Sandbox
            </button>
            <button
              type="button"
              className={[styles.envOption, environment === 'PRODUCTION' ? styles.envOptionActive : ''].filter(Boolean).join(' ')}
              onClick={() => onEnvironmentChange('PRODUCTION')}
              aria-pressed={environment === 'PRODUCTION'}
            >
              Production
            </button>
          </div>
        </div>

        {/* App ID */}
        <div className={styles.field}>
          <label className={styles.fieldLabel} htmlFor="ebay-app-id">
            App ID (Client ID)
          </label>
          <div className={styles.inputWrapper}>
            <Icon kind="key" size={14} color="var(--hd-muted)" />
            <input
              id="ebay-app-id"
              className={[styles.input, errors.appId ? styles.inputError : ''].filter(Boolean).join(' ')}
              type="text"
              placeholder="YourApp-1234-5678-ABCD-efg12345"
              value={appId}
              onChange={(e) => onAppIdChange(e.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          {errors.appId && <span className={styles.errorMsg}>{errors.appId}</span>}
        </div>

        {/* Cert ID */}
        <div className={styles.field}>
          <label className={styles.fieldLabel} htmlFor="ebay-cert-id">
            Cert ID (Client Secret)
          </label>
          <div className={styles.inputWrapper}>
            <Icon kind="shield" size={14} color="var(--hd-muted)" />
            <input
              id="ebay-cert-id"
              className={[styles.input, errors.certId ? styles.inputError : ''].filter(Boolean).join(' ')}
              type={certRevealed ? 'text' : 'password'}
              placeholder="SBX-1234abcd-efgh-5678"
              value={certId}
              onChange={(e) => onCertIdChange(e.target.value)}
              autoComplete="new-password"
              spellCheck={false}
            />
            <button
              type="button"
              className={styles.revealBtn}
              onClick={() => setCertRevealed((v) => !v)}
              aria-label={certRevealed ? 'Hide Cert ID' : 'Show Cert ID'}
            >
              <Icon kind="eye" size={13} color="var(--hd-muted)" />
            </button>
          </div>
          {errors.certId && <span className={styles.errorMsg}>{errors.certId}</span>}
        </div>

        {/* Redirect URI (read-only) */}
        <div className={styles.field}>
          <label className={styles.fieldLabel} htmlFor="ebay-runame">
            Redirect URI (RuName)
            <span className={styles.readOnlyTag}>read-only</span>
          </label>
          <div className={styles.inputWrapper}>
            <Icon kind="link" size={14} color="var(--hd-muted)" />
            <input
              id="ebay-runame"
              className={[styles.input, styles.inputReadOnly].join(' ')}
              type="text"
              value={REDIRECT_URI}
              readOnly
              aria-readonly="true"
            />
            <button
              type="button"
              className={styles.copyBtn}
              onClick={copyRuName}
              title="Copy redirect URI"
            >
              {copied ? (
                <Icon kind="check" size={13} color="var(--hd-accent)" />
              ) : (
                <Icon kind="copy" size={13} color="var(--hd-muted)" />
              )}
            </button>
          </div>
          <p className={styles.fieldHint}>
            Paste this URL into your eBay app's <strong>Auth accepted URL</strong> field in the
            developer portal, then add it as an allowed RuName.
          </p>
        </div>
      </div>
    </div>
  )
}

// ── Step 3: OAuth scopes ───────────────────────────────────────────────────

interface StepScopesProps {
  scopes: OAuthScope[]
  onToggle: (id: string) => void
}

function StepScopes({ scopes, onToggle }: StepScopesProps) {
  return (
    <div className={styles.stepContent}>
      <h2 className={styles.stepHeading}>Configure OAuth scopes</h2>
      <p className={styles.stepDesc}>
        These permissions determine what AutoMana can do on your eBay account. Required scopes
        cannot be disabled.
      </p>

      <div className={styles.scopeList} role="list">
        {scopes.map((scope) => (
          <div key={scope.id} className={styles.scopeRow} role="listitem">
            <div className={styles.scopeInfo}>
              <div className={styles.scopeNameRow}>
                <span className={styles.scopeName}>{scope.name}</span>
                {scope.required && (
                  <span className={styles.requiredBadge}>REQUIRED</span>
                )}
              </div>
              <span className={styles.scopeDesc}>{scope.description}</span>
            </div>
            <Toggle
              on={scope.enabled}
              onToggle={scope.required ? undefined : () => onToggle(scope.id)}
              label={`Toggle ${scope.name}`}
            />
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Step 4: Registration result ────────────────────────────────────────────

interface StepResultProps {
  result: RegistrationResult
}

function StepResult({ result }: StepResultProps) {
  if (result.success) {
    return (
      <div className={styles.stepContent}>
        <h2 className={styles.stepHeading}>App registered</h2>
        <div className={styles.verifyBox}>
          <div className={styles.verifySuccess}>
            <div className={styles.verifyIcon}>
              <Icon kind="check" size={24} color="var(--hd-accent)" />
            </div>
            <div>
              <div className={styles.verifyTitle}>App registered successfully</div>
              <div className={styles.verifySubtitle}>
                App code: <code>{result.appCode}</code>
              </div>
            </div>
          </div>
        </div>
        <p className={styles.verifyNote}>
          Your eBay app is registered. Use the app code above to start the OAuth flow and
          connect your eBay account.
        </p>
      </div>
    )
  }
  return (
    <div className={styles.stepContent}>
      <h2 className={styles.stepHeading}>Registration failed</h2>
      <div className={styles.verifyBox}>
        <div className={styles.verifyIdle}>
          <div className={styles.verifyIcon}>
            <Icon kind="shield" size={24} color="var(--hd-red)" />
          </div>
          <div>
            <div className={styles.verifyTitle}>Could not register app</div>
            <div className={styles.verifySubtitle}>{result.error}</div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Stepper indicator ──────────────────────────────────────────────────────

interface StepperProps {
  steps: { label: string }[]
  current: number
  completed: Set<number>
}

function Stepper({ steps, current, completed }: StepperProps) {
  return (
    <div className={styles.stepper} role="list" aria-label="Setup steps">
      {steps.map((step, i) => {
        const isDone = completed.has(i)
        const isActive = i === current
        return (
          <div
            key={i}
            className={[
              styles.stepItem,
              isActive ? styles.stepItemActive : '',
              isDone ? styles.stepItemDone : '',
            ].filter(Boolean).join(' ')}
            role="listitem"
          >
            <div className={styles.stepNumber} aria-hidden="true">
              {isDone ? <Icon kind="check" size={11} color="var(--hd-bg)" /> : i + 1}
            </div>
            <span className={styles.stepLabel}>{step.label}</span>
            {i < steps.length - 1 && <div className={styles.stepConnector} aria-hidden="true" />}
          </div>
        )
      })}
    </div>
  )
}

// ── Connection status sidebar panel ───────────────────────────────────────

interface StatusPanelProps {
  status: ConnectionStatus
}

function StatusPanel({ status }: StatusPanelProps) {
  const quotaPct = status.dailyQuota > 0
    ? Math.round((status.usedToday / status.dailyQuota) * 100)
    : 0

  return (
    <div className={styles.sidePanel}>
      <div className={styles.sidePanelTitle}>Connection status</div>
      <div className={styles.statusDot}>
        <span
          className={styles.statusIndicator}
          style={{ background: status.connected ? 'var(--hd-accent)' : 'var(--hd-sub)' }}
          aria-hidden="true"
        />
        <span className={styles.statusLabel}>
          {status.connected ? 'Connected' : 'Not connected'}
        </span>
      </div>

      <div className={styles.metricList}>
        <div className={styles.metricRow}>
          <span className={styles.metricKey}>Environment</span>
          <span className={styles.metricVal}>{status.environment}</span>
        </div>
        <div className={styles.metricRow}>
          <span className={styles.metricKey}>Last verified</span>
          <span className={styles.metricVal}>
            {status.lastVerified
              ? new Date(status.lastVerified).toLocaleDateString()
              : '—'}
          </span>
        </div>
        <div className={styles.metricRow}>
          <span className={styles.metricKey}>Token expires</span>
          <span className={styles.metricVal}>
            {status.tokenExpires
              ? new Date(status.tokenExpires).toLocaleDateString()
              : '—'}
          </span>
        </div>
        <div className={styles.metricRow}>
          <span className={styles.metricKey}>Daily quota</span>
          <span className={styles.metricVal}>{status.dailyQuota.toLocaleString()}</span>
        </div>
        <div className={styles.metricRow}>
          <span className={styles.metricKey}>Used today</span>
          <span className={styles.metricVal}>{status.usedToday}</span>
        </div>
      </div>

      {status.connected && (
        <div className={styles.quotaBarWrapper}>
          <div
            className={styles.quotaBar}
            role="progressbar"
            aria-valuenow={status.usedToday}
            aria-valuemax={status.dailyQuota}
            aria-label="Daily quota usage"
          >
            <div
              className={styles.quotaFill}
              style={{
                width: `${quotaPct}%`,
                background: quotaPct > 80 ? 'var(--hd-red)' : 'var(--hd-accent)',
              }}
            />
          </div>
          <span className={styles.quotaPct}>{quotaPct}%</span>
        </div>
      )}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────

function EbaySetupPage() {
  const [step, setStep] = useState<number>(0)
  const [completed, setCompleted] = useState<Set<number>>(new Set())

  // Step 2 form state
  const [appName, setAppName] = useState('')
  const [description, setDescription] = useState('')
  const [environment, setEnvironment] = useState<Environment>('SANDBOX')
  const [appId, setAppId] = useState('')
  const [certId, setCertId] = useState('')
  const [formErrors, setFormErrors] = useState<Record<string, string>>({})

  // Step 3 state
  const [scopes, setScopes] = useState(MOCK_OAUTH_SCOPES)

  // Step 4 state
  const [submitting, setSubmitting] = useState(false)
  const [registrationResult, setRegistrationResult] = useState<RegistrationResult | null>(null)

  function validateCredentials(): boolean {
    const errors: Record<string, string> = {}
    if (!appName.trim()) errors.appName = 'App name is required'
    if (!appId.trim()) errors.appId = 'App ID is required'
    if (!certId.trim()) errors.certId = 'Cert ID is required'
    setFormErrors(errors)
    return Object.keys(errors).length === 0
  }

  function toggleScope(id: string) {
    setScopes((prev) =>
      prev.map((s) => (s.id === id && !s.required ? { ...s, enabled: !s.enabled } : s))
    )
  }

  async function handleNext() {
    if (step === 1 && !validateCredentials()) return

    if (step === 2) {
      setSubmitting(true)
      try {
        const enabledScopeUrls = scopes.filter((s) => s.enabled).map((s) => s.scopeUrl)
        const result = await registerEbayApp({
          app_name: appName,
          description,
          environment,
          ebay_app_id: appId,
          client_secret: certId,
          redirect_uri: REDIRECT_URI,
          allowed_scopes: enabledScopeUrls,
        })
        setRegistrationResult({ success: true, appCode: result.app_code })
      } catch (err) {
        setRegistrationResult({
          success: false,
          error: err instanceof Error ? err.message : 'Registration failed',
        })
      } finally {
        setSubmitting(false)
        setCompleted((prev) => new Set(prev).add(step))
        setStep((s) => s + 1)
      }
      return
    }

    setCompleted((prev) => new Set(prev).add(step))
    setStep((s) => Math.min(s + 1, SETUP_STEPS.length - 1))
  }

  function handleBack() {
    setStep((s) => Math.max(s - 1, 0))
  }

  return (
    <AppShell active="settings">
      <TopBar
        title="Connect your eBay app"
        subtitle="eBay Developer"
        breadcrumb="Settings / Integrations"
      />

      <div className={styles.page}>
        <Stepper steps={SETUP_STEPS} current={step} completed={completed} />

        <div className={styles.contentGrid}>
          <div className={styles.mainPanel}>
            {step === 0 && <StepCreateApp />}
            {step === 1 && (
              <StepCredentials
                appName={appName}
                description={description}
                environment={environment}
                appId={appId}
                certId={certId}
                onAppNameChange={(v) => { setAppName(v); setFormErrors((e) => ({ ...e, appName: '' })) }}
                onDescriptionChange={setDescription}
                onEnvironmentChange={setEnvironment}
                onAppIdChange={(v) => { setAppId(v); setFormErrors((e) => ({ ...e, appId: '' })) }}
                onCertIdChange={(v) => { setCertId(v); setFormErrors((e) => ({ ...e, certId: '' })) }}
                errors={formErrors}
              />
            )}
            {step === 2 && <StepScopes scopes={scopes} onToggle={toggleScope} />}
            {step === 3 && registrationResult && <StepResult result={registrationResult} />}

            <div className={styles.navButtons}>
              {step > 0 && step < SETUP_STEPS.length - 1 && (
                <Button variant="ghost" size="md" onClick={handleBack}>
                  Back
                </Button>
              )}
              {step < SETUP_STEPS.length - 1 && (
                <Button
                  variant="accent"
                  size="md"
                  onClick={handleNext}
                  disabled={submitting}
                  icon={step === 2 ? undefined : <Icon kind="arrowRight" size={13} color="currentColor" />}
                >
                  {step === 2
                    ? submitting ? 'Registering…' : 'Register App'
                    : 'Next'}
                </Button>
              )}
            </div>
          </div>

          <aside className={styles.sidebar} aria-label="eBay setup sidebar">
            <StatusPanel status={MOCK_CONNECTION_STATUS} />

            <div className={styles.sidePanel}>
              <div className={styles.sidePanelTitle}>Why bring your own app?</div>
              <ul className={styles.benefitList}>
                {BYOA_BENEFITS.map((benefit) => (
                  <li key={benefit} className={styles.benefitItem}>
                    <Icon kind="check" size={12} color="var(--hd-accent)" />
                    <span>{benefit}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className={styles.sidePanel}>
              <div className={styles.sidePanelTitle}>Need help?</div>
              <div className={styles.helpLinks}>
                {HELP_LINKS.map((link) => (
                  <a
                    key={link.href}
                    href={link.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={styles.helpLink}
                  >
                    <Icon kind="link" size={11} color="var(--hd-muted)" />
                    {link.label}
                  </a>
                ))}
              </div>
            </div>
          </aside>
        </div>
      </div>
    </AppShell>
  )
}
