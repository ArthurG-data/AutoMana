import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import {
  AIBadge,
  getAIGroup,
  type AIStatus,
} from '../AIBadge'

describe('getAIGroup', () => {
  it.each<[AIStatus, string]>([
    ['over',     'needs-action'],
    ['under',    'needs-action'],
    ['stale',    'needs-action'],
    ['revised',  'needs-action'],
    ['watching', 'monitoring'],
    ['ready',    'monitoring'],
    ['ok',       'settled'],
    ['listed',   'settled'],
    ['vault',    'settled'],
  ])('maps %s → %s', (status, group) => {
    expect(getAIGroup(status)).toBe(group)
  })
})

describe('AIBadge', () => {
  const ALL: AIStatus[] = ['ok','over','under','revised','stale','ready','watching','listed','vault']

  it.each(ALL)('renders %s without crashing', (status) => {
    const { container } = render(<AIBadge status={status} />)
    expect(container.querySelector('svg')).toBeTruthy()
  })

  it('shows label text when showLabel=true', () => {
    render(<AIBadge status="over" showLabel />)
    expect(screen.getByText('Overpriced')).toBeTruthy()
  })

  it('has title attribute with state label', () => {
    const { container } = render(<AIBadge status="ready" />)
    const badge = container.firstChild as HTMLElement
    expect(badge.title).toBe('Ready to list')
  })
})
