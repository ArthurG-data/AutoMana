// src/frontend/src/features/ebay/mockAuthorizedUsers.ts
// TODO: replace with useQuery/useMutation when /api/ebay/users is wired

// ── Types ─────────────────────────────────────────────────────────────────

export type UserRole = 'read-only' | 'listing-manager' | 'pricing-bot' | 'full-access'
export type UserStatus = 'active' | 'pending' | 'revoked'

export interface AuthorizedUser {
  id: string
  name: string
  email: string
  initials: string
  role: UserRole
  scopes: string[]
  callsToday: number
  status: UserStatus
  addedAt: string       // ISO date
}

export interface PendingInvite {
  id: string
  email: string
  role: UserRole
  invitedAt: string
  expiresAt: string
}

export interface AuditLogEntry {
  id: string
  timestamp: string
  actorName: string
  action: string
  detail: string
}

export interface QuotaByUser {
  userId: string
  name: string
  initials: string
  calls: number
  color: string
}

// ── Mock data ──────────────────────────────────────────────────────────────

export const DAILY_QUOTA_LIMIT = 5000

export const MOCK_AUTHORIZED_USERS: AuthorizedUser[] = [
  {
    id: 'u1',
    name: 'Arthur G.',
    email: 'arthur@automana.app',
    initials: 'AG',
    role: 'full-access',
    scopes: ['sell.inventory', 'sell.account', 'sell.fulfillment', 'buy.browse', 'commerce.identity'],
    callsToday: 247,
    status: 'active',
    addedAt: '2026-01-15',
  },
  {
    id: 'u2',
    name: 'Pricing Bot',
    email: 'bot@automana.app',
    initials: 'PB',
    role: 'pricing-bot',
    scopes: ['buy.browse'],
    callsToday: 1820,
    status: 'active',
    addedAt: '2026-02-01',
  },
  {
    id: 'u3',
    name: 'Sophie M.',
    email: 'sophie@example.com',
    initials: 'SM',
    role: 'listing-manager',
    scopes: ['sell.inventory', 'sell.fulfillment'],
    callsToday: 312,
    status: 'active',
    addedAt: '2026-03-10',
  },
  {
    id: 'u4',
    name: 'Marcus T.',
    email: 'marcus@example.com',
    initials: 'MT',
    role: 'read-only',
    scopes: ['buy.browse'],
    callsToday: 55,
    status: 'active',
    addedAt: '2026-04-22',
  },
]

export const MOCK_PENDING_INVITES: PendingInvite[] = [
  {
    id: 'i1',
    email: 'jordan@example.com',
    role: 'listing-manager',
    invitedAt: '2026-05-04',
    expiresAt: '2026-05-11',
  },
]

export const MOCK_REVOKED_USERS: AuthorizedUser[] = [
  {
    id: 'r1',
    name: 'Old Bot',
    email: 'oldbot@example.com',
    initials: 'OB',
    role: 'pricing-bot',
    scopes: ['buy.browse'],
    callsToday: 0,
    status: 'revoked',
    addedAt: '2025-11-01',
  },
]

export const MOCK_AUDIT_LOG: AuditLogEntry[] = [
  {
    id: 'al1',
    timestamp: '2026-05-06T09:14:22Z',
    actorName: 'Arthur G.',
    action: 'Granted access',
    detail: 'jordan@example.com invited as listing-manager',
  },
  {
    id: 'al2',
    timestamp: '2026-05-05T14:02:11Z',
    actorName: 'Arthur G.',
    action: 'Revoked access',
    detail: 'oldbot@example.com removed',
  },
  {
    id: 'al3',
    timestamp: '2026-05-01T08:30:00Z',
    actorName: 'System',
    action: 'Token refreshed',
    detail: 'OAuth token auto-renewed for Pricing Bot',
  },
  {
    id: 'al4',
    timestamp: '2026-04-22T16:45:33Z',
    actorName: 'Arthur G.',
    action: 'Granted access',
    detail: 'marcus@example.com added as read-only',
  },
]

export const MOCK_QUOTA_BY_USER: QuotaByUser[] = [
  { userId: 'u2', name: 'Pricing Bot', initials: 'PB', calls: 1820, color: 'var(--hd-blue)' },
  { userId: 'u3', name: 'Sophie M.',   initials: 'SM', calls: 312,  color: 'var(--hd-accent)' },
  { userId: 'u1', name: 'Arthur G.',   initials: 'AG', calls: 247,  color: 'var(--hd-amber)' },
  { userId: 'u4', name: 'Marcus T.',   initials: 'MT', calls: 55,   color: '#a78bfa' },
]

// ── Utilities ─────────────────────────────────────────────────────────────

export const ROLE_LABELS: Record<UserRole, string> = {
  'read-only':       'Read-only',
  'listing-manager': 'Listing manager',
  'pricing-bot':     'Pricing bot',
  'full-access':     'Full access',
}

export const ROLE_COLORS: Record<UserRole, string> = {
  'read-only':       'var(--hd-sub)',
  'listing-manager': 'var(--hd-blue)',
  'pricing-bot':     'var(--hd-accent)',
  'full-access':     'var(--hd-amber)',
}

export const STATUS_COLORS: Record<UserStatus, string> = {
  active:  'var(--hd-accent)',
  pending: 'var(--hd-amber)',
  revoked: 'var(--hd-red)',
}

export function formatTimestamp(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
