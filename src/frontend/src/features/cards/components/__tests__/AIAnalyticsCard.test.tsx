// src/frontend/src/features/cards/components/__tests__/AIAnalyticsCard.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AIAnalyticsCard } from '../AIAnalyticsCard'

describe('AIAnalyticsCard', () => {
  it('renders the AI INSIGHTS label and Beta badge', () => {
    render(<AIAnalyticsCard />)
    expect(screen.getByText('AI INSIGHTS')).toBeTruthy()
    expect(screen.getByText('Beta')).toBeTruthy()
  })

  it('shows the placeholder when no insights are provided', () => {
    render(<AIAnalyticsCard />)
    expect(screen.getByText(/coming soon/i)).toBeTruthy()
  })

  it('shows the placeholder when insights is empty', () => {
    render(<AIAnalyticsCard insights={{ summary: '', signals: [] }} />)
    expect(screen.getByText(/coming soon/i)).toBeTruthy()
  })

  it('renders the summary when provided', () => {
    render(<AIAnalyticsCard insights={{ summary: 'Trending up across all formats.' }} />)
    expect(screen.getByText('Trending up across all formats.')).toBeTruthy()
    expect(screen.queryByText(/coming soon/i)).toBeNull()
  })

  it('renders one row per signal', () => {
    render(
      <AIAnalyticsCard
        insights={{
          signals: [
            { label: 'Demand', value: 'High' },
            { label: 'Reprint risk', value: 'Low', tone: 'down' },
            { label: 'EV', value: '+12%', tone: 'up' },
          ],
        }}
      />
    )
    expect(screen.getByText('Demand')).toBeTruthy()
    expect(screen.getByText('Reprint risk')).toBeTruthy()
    expect(screen.getByText('EV')).toBeTruthy()
    expect(screen.getByText('+12%')).toBeTruthy()
  })

  it('applies the up tone class to positive signals', () => {
    const { container } = render(
      <AIAnalyticsCard insights={{ signals: [{ label: 'Trend', value: '+5%', tone: 'up' }] }} />
    )
    expect(container.querySelector('[class*="up"]')).toBeTruthy()
  })
})
