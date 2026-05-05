// src/frontend/src/components/layout/__tests__/Sidebar.test.tsx
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Sidebar } from '../Sidebar'

const mockNavigate = vi.fn()
vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

describe('Sidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the logo button', () => {
    render(<Sidebar active="dashboard" />)
    expect(screen.getByRole('button', { name: /automana - go to home/i })).toBeInTheDocument()
  })

  it('navigates to / when the logo button is clicked', async () => {
    const user = userEvent.setup()
    render(<Sidebar active="dashboard" />)
    await user.click(screen.getByRole('button', { name: /automana - go to home/i }))
    expect(mockNavigate).toHaveBeenCalledWith({ to: '/' })
  })
})
