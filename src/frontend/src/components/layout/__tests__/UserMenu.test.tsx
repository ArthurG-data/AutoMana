// src/frontend/src/components/layout/__tests__/UserMenu.test.tsx
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useAuthStore } from '../../../store/auth'
import { UserMenu } from '../UserMenu'

const mockNavigate = vi.fn()
vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

describe('UserMenu', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuthStore.setState({ token: null, currentUser: null })
  })

  // ── Unauthenticated state ──────────────────────────────────────────────────
  describe('unauthenticated', () => {
    it('renders the Login / Sign Up button', () => {
      render(<UserMenu />)
      expect(screen.getByRole('button', { name: /log in or sign up/i })).toBeInTheDocument()
      expect(screen.getByText('Login / Sign Up')).toBeInTheDocument()
    })

    it('navigates to /login when the button is clicked', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)
      await user.click(screen.getByRole('button', { name: /log in or sign up/i }))
      expect(mockNavigate).toHaveBeenCalledWith({ to: '/login' })
    })

    it('does not render an avatar button', () => {
      render(<UserMenu />)
      expect(screen.queryByRole('button', { name: /user menu/i })).not.toBeInTheDocument()
    })
  })

  // ── Authenticated state ────────────────────────────────────────────────────
  describe('authenticated', () => {
    beforeEach(() => {
      useAuthStore.setState({
        token: 'test-token',
        currentUser: { username: 'arthur', email: 'arthur@example.com' },
      })
    })

    it('renders an avatar button with the user initials', () => {
      render(<UserMenu />)
      expect(screen.getByRole('button', { name: /user menu for arthur/i })).toBeInTheDocument()
      expect(screen.getByText('AR')).toBeInTheDocument()
    })

    it('does not show a dropdown by default', () => {
      render(<UserMenu />)
      expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    })

    it('opens the dropdown when the avatar button is clicked', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)
      await user.click(screen.getByRole('button', { name: /user menu for arthur/i }))
      expect(screen.getByRole('menu')).toBeInTheDocument()
    })

    it('shows a "Hello, [username]" greeting at the top of the dropdown', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)
      await user.click(screen.getByRole('button', { name: /user menu for arthur/i }))
      expect(screen.getByText('Hello, arthur')).toBeInTheDocument()
    })

    it('shows a Collection menu item', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)
      await user.click(screen.getByRole('button', { name: /user menu for arthur/i }))
      expect(screen.getByRole('menuitem', { name: /collection/i })).toBeInTheDocument()
    })

    it('navigates to /collection and closes dropdown when Collection is clicked', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)
      await user.click(screen.getByRole('button', { name: /user menu for arthur/i }))
      await user.click(screen.getByRole('menuitem', { name: /collection/i }))
      expect(mockNavigate).toHaveBeenCalledWith({ to: '/collection' })
      expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    })

    it('shows a Listings menu item', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)
      await user.click(screen.getByRole('button', { name: /user menu for arthur/i }))
      expect(screen.getByRole('menuitem', { name: /listings/i })).toBeInTheDocument()
    })

    it('navigates to /listings and closes dropdown when Listings is clicked', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)
      await user.click(screen.getByRole('button', { name: /user menu for arthur/i }))
      await user.click(screen.getByRole('menuitem', { name: /listings/i }))
      expect(mockNavigate).toHaveBeenCalledWith({ to: '/listings' })
      expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    })

    it('shows a Log out menu item', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)
      await user.click(screen.getByRole('button', { name: /user menu for arthur/i }))
      expect(screen.getByRole('menuitem', { name: /logout/i })).toBeInTheDocument()
    })

    it('sets aria-expanded=true when dropdown is open', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)
      const trigger = screen.getByRole('button', { name: /user menu for arthur/i })
      expect(trigger).toHaveAttribute('aria-expanded', 'false')
      await user.click(trigger)
      expect(trigger).toHaveAttribute('aria-expanded', 'true')
    })

    it('closes the dropdown on Escape and returns focus to trigger', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)
      const trigger = screen.getByRole('button', { name: /user menu for arthur/i })
      await user.click(trigger)
      expect(screen.getByRole('menu')).toBeInTheDocument()
      await user.keyboard('{Escape}')
      expect(screen.queryByRole('menu')).not.toBeInTheDocument()
      expect(document.activeElement).toBe(trigger)
    })

    it('closes the dropdown on outside click', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <UserMenu />
          <button>Outside</button>
        </div>
      )
      await user.click(screen.getByRole('button', { name: /user menu for arthur/i }))
      expect(screen.getByRole('menu')).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'Outside' }))
      await waitFor(() => {
        expect(screen.queryByRole('menu')).not.toBeInTheDocument()
      })
    })

    it('calls logout and closes dropdown when Log out is clicked', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)
      await user.click(screen.getByRole('button', { name: /user menu for arthur/i }))
      await user.click(screen.getByRole('menuitem', { name: /logout/i }))
      expect(useAuthStore.getState().token).toBeNull()
      expect(useAuthStore.getState().currentUser).toBeNull()
      expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    })

    it('does not navigate explicitly on logout (root handles it)', async () => {
      // __root.tsx watches for token → null and navigates; UserMenu must not also call navigate
      const user = userEvent.setup()
      render(<UserMenu />)
      await user.click(screen.getByRole('button', { name: /user menu for arthur/i }))
      await user.click(screen.getByRole('menuitem', { name: /logout/i }))
      expect(mockNavigate).not.toHaveBeenCalled()
    })
  })

  // ── Edge cases ─────────────────────────────────────────────────────────────
  describe('edge cases', () => {
    it('truncates long usernames to 2 initials', () => {
      useAuthStore.setState({
        token: 'test-token',
        currentUser: { username: 'alexandergreat', email: null },
      })
      render(<UserMenu />)
      expect(screen.getByText('AL')).toBeInTheDocument()
    })

  })
})
