import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SearchFilters } from '../SearchFilters'

const navigateMock = vi.fn()
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
}))

const createTestQueryClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })

const Wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={createTestQueryClient()}>{children}</QueryClientProvider>
)

const BASE_PARAMS = { q: 'ragavan' }

describe('SearchFilters — promo type dropdown', () => {
  it('hides promo section when promoTypeFacets is empty', () => {
    render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} />, { wrapper: Wrapper })
    expect(screen.queryByText(/promo type/i)).toBeNull()
  })

  it('renders promo type section when facets present', () => {
    render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={['buyabox', 'prerelease']} />, { wrapper: Wrapper })
    expect(screen.getByText(/promo type/i)).toBeTruthy()
  })

  it('uses display label for known promo type', () => {
    render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={['buyabox']} />, { wrapper: Wrapper })
    expect(screen.getByText('Buy a Box')).toBeTruthy()
  })

  it('shows selection count in summary when promoTypes selected', () => {
    render(
      <SearchFilters
        params={{ ...BASE_PARAMS, promoTypes: ['buyabox', 'prerelease'] }}
        promoTypeFacets={['buyabox', 'prerelease']}
      />,
      { wrapper: Wrapper },
    )
    expect(screen.getByText(/2 selected/i)).toBeTruthy()
  })

  it('calls navigate when a promo type checkbox is toggled', () => {
    navigateMock.mockClear()
    render(
      <SearchFilters params={BASE_PARAMS} promoTypeFacets={['prerelease']} />,
      { wrapper: Wrapper },
    )
    const checkbox = screen.getByLabelText('Prerelease')
    fireEvent.click(checkbox)
    expect(navigateMock).toHaveBeenCalledOnce()
  })
})
