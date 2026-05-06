// src/frontend/src/routes/ebay/__tests__/share.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    createFileRoute: () => (opts: { component: () => JSX.Element }) => opts,
    useNavigate: () => vi.fn(),
  }
})

vi.mock('../../../components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('../../../components/layout/TopBar', () => ({
  TopBar: ({ title, actions }: { title: string; actions?: React.ReactNode }) => (
    <div data-testid="topbar">
      {title}
      {actions}
    </div>
  ),
}))
vi.mock('../../../components/ui/Button', () => ({
  Button: ({ children, onClick, ...props }: any) => (
    <button onClick={onClick} {...props}>
      {children}
    </button>
  ),
}))
vi.mock('../../../components/design-system/Icon', () => ({
  Icon: ({ kind, ...props }: any) => <span {...props} data-icon={kind} />,
}))

import * as ShareModule from '../share'

const PageComponent = (ShareModule as any).Route?.component
  ?? (ShareModule as any).EbaySharePage

describe('EbaySharePage', () => {
  function renderPage() {
    if (!PageComponent) throw new Error('Could not find EbaySharePage component')
    return render(<PageComponent />)
  }

  it('renders page title', () => {
    renderPage()
    expect(screen.getByText('Authorize other users')).toBeTruthy()
  })

  it('renders the quota strip', () => {
    renderPage()
    expect(screen.getByText(/daily api quota/i)).toBeTruthy()
    expect(screen.getByRole('img', { name: /quota usage/i })).toBeTruthy()
  })

  it('renders all 4 tabs', () => {
    renderPage()
    expect(screen.getByRole('tab', { name: /authorized users/i })).toBeTruthy()
    expect(screen.getByRole('tab', { name: /pending invites/i })).toBeTruthy()
    expect(screen.getByRole('tab', { name: /revoked/i })).toBeTruthy()
    expect(screen.getByRole('tab', { name: /audit log/i })).toBeTruthy()
  })

  it('shows authorized users table by default', () => {
    renderPage()
    expect(screen.getByRole('region', { name: /authorized users table/i })).toBeTruthy()
    expect(screen.getByText('Arthur G.')).toBeTruthy()
    expect(screen.getByText('Pricing Bot')).toBeTruthy()
    expect(screen.getByText('Sophie M.')).toBeTruthy()
  })

  it('shows role badges for users', () => {
    renderPage()
    expect(screen.getByText('Full access')).toBeTruthy()
    expect(screen.getByText('Pricing bot')).toBeTruthy()
    expect(screen.getByText('Listing manager')).toBeTruthy()
    expect(screen.getByText('Read-only')).toBeTruthy()
  })

  it('shows calls today for active users', () => {
    renderPage()
    expect(screen.getByText('247')).toBeTruthy()
    expect(screen.getByText('1820')).toBeTruthy()
  })

  it('switches to Pending invites tab', () => {
    renderPage()
    const pendingTab = screen.getByRole('tab', { name: /pending invites/i })
    fireEvent.click(pendingTab)
    expect(screen.getByRole('region', { name: /pending invites table/i })).toBeTruthy()
    expect(screen.getByText('jordan@example.com')).toBeTruthy()
  })

  it('switches to Revoked tab and shows revoked user', () => {
    renderPage()
    const revokedTab = screen.getByRole('tab', { name: /revoked/i })
    fireEvent.click(revokedTab)
    expect(screen.getByText('Old Bot')).toBeTruthy()
  })

  it('switches to Audit log tab', () => {
    renderPage()
    const auditTab = screen.getByRole('tab', { name: /audit log/i })
    fireEvent.click(auditTab)
    expect(screen.getByRole('region', { name: /audit log/i })).toBeTruthy()
    expect(screen.getByText('Granted access')).toBeTruthy()
    expect(screen.getByText('Revoked access')).toBeTruthy()
  })

  it('opens invite modal when Invite user is clicked', () => {
    renderPage()
    const inviteBtn = screen.getByRole('button', { name: /invite user/i })
    fireEvent.click(inviteBtn)
    expect(screen.getByRole('dialog', { name: /invite user/i })).toBeTruthy()
    expect(screen.getByLabelText('Email address')).toBeTruthy()
    expect(screen.getByLabelText('Role')).toBeTruthy()
  })

  it('closes invite modal when Cancel is clicked', () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: /invite user/i }))
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('shows validation error for invalid email in invite modal', () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: /invite user/i }))
    fireEvent.click(screen.getByRole('button', { name: /send invite/i }))
    expect(screen.getByText(/valid email/i)).toBeTruthy()
  })

  it('submits invite and adds to pending tab', () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: /invite user/i }))
    fireEvent.change(screen.getByLabelText('Email address'), {
      target: { value: 'newuser@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /send invite/i }))
    // Modal should close and we should be on pending tab
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByText('newuser@example.com')).toBeTruthy()
  })

  it('revokes an active user', () => {
    renderPage()
    const revokeBtn = screen.getByRole('button', { name: /revoke access for arthur g/i })
    fireEvent.click(revokeBtn)
    // Arthur should no longer appear in active users table
    // (he'd be moved to revoked tab)
    const rows = screen.queryAllByText('Arthur G.')
    expect(rows.length).toBe(0)
  })

  it('shows Invite user button in top bar', () => {
    renderPage()
    expect(screen.getByRole('button', { name: /invite user/i })).toBeTruthy()
  })

  it('shows quota legend with user names', () => {
    renderPage()
    expect(screen.getByText('Pricing Bot')).toBeTruthy()
    expect(screen.getByText('Sophie M.')).toBeTruthy()
  })
})
