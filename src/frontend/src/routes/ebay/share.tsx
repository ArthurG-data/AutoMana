// src/frontend/src/routes/ebay/share.tsx
import React, { useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { AppShell } from '../../components/layout/AppShell'
import { TopBar } from '../../components/layout/TopBar'
import { Button } from '../../components/ui/Button'
import { Icon } from '../../components/design-system/Icon'
import { QuotaStrip } from '../../features/ebay/components/QuotaStrip'
import {
  MOCK_AUTHORIZED_USERS,
  MOCK_PENDING_INVITES,
  MOCK_REVOKED_USERS,
  MOCK_AUDIT_LOG,
  MOCK_QUOTA_BY_USER,
  DAILY_QUOTA_LIMIT,
  ROLE_LABELS,
  ROLE_COLORS,
  STATUS_COLORS,
  formatTimestamp,
  type AuthorizedUser,
  type PendingInvite,
  type UserRole,
} from '../../features/ebay/mockAuthorizedUsers'
import styles from './Share.module.css'

export const Route = createFileRoute('/ebay/share')({
  component: EbaySharePage,
})

export { EbaySharePage }

type ShareTab = 'users' | 'pending' | 'revoked' | 'audit'

// ── Avatar ─────────────────────────────────────────────────────────────────

interface AvatarProps {
  initials: string
  color?: string
}

function Avatar({ initials, color = 'var(--hd-blue)' }: AvatarProps) {
  return (
    <div
      className={styles.avatar}
      style={{ background: `${color}22`, color }}
      aria-hidden="true"
    >
      {initials}
    </div>
  )
}

// ── Role badge ─────────────────────────────────────────────────────────────

interface RoleBadgeProps {
  role: UserRole
}

function RoleBadge({ role }: RoleBadgeProps) {
  return (
    <span
      className={styles.roleBadge}
      style={{
        color: ROLE_COLORS[role],
        borderColor: `${ROLE_COLORS[role]}44`,
        background: `${ROLE_COLORS[role]}11`,
      }}
    >
      {ROLE_LABELS[role]}
    </span>
  )
}

// ── Users table ────────────────────────────────────────────────────────────

interface UsersTableProps {
  users: AuthorizedUser[]
  onRevoke?: (user: AuthorizedUser) => void
}

function UsersTable({ users, onRevoke }: UsersTableProps) {
  if (users.length === 0) {
    return (
      <div className={styles.emptyState}>
        <Icon kind="users" size={28} color="var(--hd-sub)" />
        <p>No users in this list</p>
      </div>
    )
  }

  return (
    <div className={styles.tableWrapper} role="region" aria-label="Authorized users table">
      <table className={styles.table}>
        <thead>
          <tr>
            <th>User</th>
            <th>Role</th>
            <th>Scopes</th>
            <th className={styles.right}>Calls today</th>
            <th>Status</th>
            <th className={styles.right}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.id} className={styles.tableRow}>
              <td>
                <div className={styles.userCell}>
                  <Avatar initials={user.initials} color={ROLE_COLORS[user.role]} />
                  <div>
                    <div className={styles.userName}>{user.name}</div>
                    <div className={styles.userEmail}>{user.email}</div>
                  </div>
                </div>
              </td>
              <td>
                <RoleBadge role={user.role} />
              </td>
              <td>
                <div className={styles.scopeChips}>
                  {user.scopes.map((s) => (
                    <span key={s} className={styles.scopeChip}>{s}</span>
                  ))}
                </div>
              </td>
              <td className={[styles.right, styles.mono].join(' ')}>
                {user.callsToday}
              </td>
              <td>
                <div className={styles.statusBadge}>
                  <span
                    className={styles.statusDot}
                    style={{ background: STATUS_COLORS[user.status] }}
                    aria-hidden="true"
                  />
                  <span style={{ color: STATUS_COLORS[user.status] }}>
                    {user.status.charAt(0).toUpperCase() + user.status.slice(1)}
                  </span>
                </div>
              </td>
              <td>
                <div className={styles.actionsCell}>
                  {user.status === 'active' && onRevoke && (
                    <button
                      className={styles.revokeBtn}
                      onClick={() => onRevoke(user)}
                      aria-label={`Revoke access for ${user.name}`}
                    >
                      Revoke
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Pending invites table ──────────────────────────────────────────────────

interface PendingTableProps {
  invites: PendingInvite[]
  onCancel?: (invite: PendingInvite) => void
}

function PendingTable({ invites, onCancel }: PendingTableProps) {
  if (invites.length === 0) {
    return (
      <div className={styles.emptyState}>
        <Icon kind="bell" size={28} color="var(--hd-sub)" />
        <p>No pending invites</p>
      </div>
    )
  }

  return (
    <div className={styles.tableWrapper} role="region" aria-label="Pending invites table">
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Email</th>
            <th>Role</th>
            <th>Invited</th>
            <th>Expires</th>
            <th className={styles.right}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {invites.map((invite) => (
            <tr key={invite.id} className={styles.tableRow}>
              <td className={styles.userEmail}>{invite.email}</td>
              <td><RoleBadge role={invite.role} /></td>
              <td className={[styles.mono, styles.muted].join(' ')}>{invite.invitedAt}</td>
              <td className={[styles.mono, styles.muted].join(' ')}>{invite.expiresAt}</td>
              <td>
                <div className={styles.actionsCell}>
                  {onCancel && (
                    <button
                      className={styles.revokeBtn}
                      onClick={() => onCancel(invite)}
                      aria-label={`Cancel invite for ${invite.email}`}
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Audit log table ────────────────────────────────────────────────────────

function AuditLog() {
  return (
    <div className={styles.tableWrapper} role="region" aria-label="Audit log">
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Actor</th>
            <th>Action</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {MOCK_AUDIT_LOG.map((entry) => (
            <tr key={entry.id} className={styles.tableRow}>
              <td className={[styles.mono, styles.muted].join(' ')}>
                {formatTimestamp(entry.timestamp)}
              </td>
              <td className={styles.userName}>{entry.actorName}</td>
              <td>
                <span className={styles.auditAction}>{entry.action}</span>
              </td>
              <td className={[styles.muted, styles.small].join(' ')}>{entry.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Invite modal (inline) ──────────────────────────────────────────────────

interface InviteModalProps {
  onClose: () => void
  onSubmit: (email: string, role: UserRole) => void
}

function InviteModal({ onClose, onSubmit }: InviteModalProps) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<UserRole>('read-only')
  const [error, setError] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!email.trim() || !email.includes('@')) {
      setError('Enter a valid email address')
      return
    }
    onSubmit(email.trim(), role)
  }

  return (
    <div className={styles.modalOverlay} role="dialog" aria-modal="true" aria-label="Invite user">
      <div className={styles.modal}>
        <div className={styles.modalHeader}>
          <h2 className={styles.modalTitle}>Invite user</h2>
          <button
            className={styles.modalClose}
            onClick={onClose}
            aria-label="Close invite modal"
          >
            <Icon kind="close" size={14} color="var(--hd-muted)" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className={styles.modalForm}>
          <div className={styles.field}>
            <label className={styles.fieldLabel} htmlFor="invite-email">Email address</label>
            <input
              id="invite-email"
              className={styles.modalInput}
              type="email"
              placeholder="user@example.com"
              value={email}
              onChange={(e) => { setEmail(e.target.value); setError('') }}
              autoFocus
            />
            {error && <span className={styles.errorMsg}>{error}</span>}
          </div>

          <div className={styles.field}>
            <label className={styles.fieldLabel} htmlFor="invite-role">Role</label>
            <select
              id="invite-role"
              className={styles.modalSelect}
              value={role}
              onChange={(e) => setRole(e.target.value as UserRole)}
            >
              {(Object.keys(ROLE_LABELS) as UserRole[]).map((r) => (
                <option key={r} value={r}>{ROLE_LABELS[r]}</option>
              ))}
            </select>
          </div>

          <div className={styles.modalActions}>
            <Button variant="ghost" size="sm" type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button variant="accent" size="sm" type="submit">
              Send invite
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────

function EbaySharePage() {
  const [tab, setTab] = useState<ShareTab>('users')
  const [activeUsers, setActiveUsers] = useState(MOCK_AUTHORIZED_USERS)
  const [pendingInvites, setPendingInvites] = useState(MOCK_PENDING_INVITES)
  const [revokedUsers, setRevokedUsers] = useState(MOCK_REVOKED_USERS)
  const [showInviteModal, setShowInviteModal] = useState(false)

  const tabs: { id: ShareTab; label: string; count?: number }[] = [
    { id: 'users',   label: 'Authorized users', count: activeUsers.length },
    { id: 'pending', label: 'Pending invites',  count: pendingInvites.length },
    { id: 'revoked', label: 'Revoked',          count: revokedUsers.length },
    { id: 'audit',   label: 'Audit log' },
  ]

  function handleRevoke(user: AuthorizedUser) {
    setActiveUsers((prev) => prev.filter((u) => u.id !== user.id))
    setRevokedUsers((prev) => [...prev, { ...user, status: 'revoked', callsToday: 0 }])
  }

  function handleCancelInvite(invite: PendingInvite) {
    setPendingInvites((prev) => prev.filter((i) => i.id !== invite.id))
  }

  function handleInviteSubmit(email: string, role: UserRole) {
    const newInvite: PendingInvite = {
      id: `i-${Date.now()}`,
      email,
      role,
      invitedAt: new Date().toISOString().split('T')[0],
      expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
    }
    setPendingInvites((prev) => [...prev, newInvite])
    setShowInviteModal(false)
    setTab('pending')
  }

  return (
    <AppShell active="settings">
      <TopBar
        title="Authorize other users"
        subtitle="eBay App"
        breadcrumb="Settings / Integrations"
        actions={
          <Button
            variant="accent"
            size="sm"
            icon={<Icon kind="plus" size={12} color="currentColor" />}
            onClick={() => setShowInviteModal(true)}
          >
            Invite user
          </Button>
        }
      />

      <div className={styles.page}>
        {/* Quota strip */}
        <QuotaStrip />

        {/* Tabs */}
        <div className={styles.tabRow} role="tablist" aria-label="Authorization tabs">
          {tabs.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              className={[styles.tab, tab === t.id ? styles.tabActive : ''].filter(Boolean).join(' ')}
              onClick={() => setTab(t.id)}
            >
              {t.label}
              {t.count !== undefined && t.count > 0 && (
                <span className={styles.tabCount}>{t.count}</span>
              )}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {tab === 'users' && (
          <UsersTable users={activeUsers} onRevoke={handleRevoke} />
        )}
        {tab === 'pending' && (
          <PendingTable invites={pendingInvites} onCancel={handleCancelInvite} />
        )}
        {tab === 'revoked' && (
          <UsersTable users={revokedUsers} />
        )}
        {tab === 'audit' && <AuditLog />}
      </div>

      {/* Invite modal */}
      {showInviteModal && (
        <InviteModal
          onClose={() => setShowInviteModal(false)}
          onSubmit={handleInviteSubmit}
        />
      )}
    </AppShell>
  )
}
