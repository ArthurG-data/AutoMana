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

describe('SearchFilters — filter facets', () => {
  it('hides promo section when promoTypeFacets is empty', () => {
    render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={vi.fn()} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />, { wrapper: Wrapper })
    expect(screen.queryByText(/promo type/i)).toBeNull()
  })

  it('renders promo type section when facets present', () => {
    render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={['buyabox', 'prerelease']} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={vi.fn()} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />, { wrapper: Wrapper })
    expect(screen.getByText(/promo type/i)).toBeTruthy()
  })

  it('uses display label for known promo type', () => {
    render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={['buyabox']} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={vi.fn()} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />, { wrapper: Wrapper })
    expect(screen.getByText('Buy a Box')).toBeTruthy()
  })

  it('shows selection count in summary when promoTypes selected', () => {
    render(
      <SearchFilters
        params={{ ...BASE_PARAMS, promoTypes: ['buyabox', 'prerelease'] }}
        promoTypeFacets={['buyabox', 'prerelease']}
        rarityFacets={[]}
        priceTrend={undefined}
        onPriceTrendChange={vi.fn()}
        upcomingOnly={false}
        onUpcomingOnlyChange={vi.fn()}
      />,
      { wrapper: Wrapper },
    )
    expect(screen.getByText(/2 selected/i)).toBeTruthy()
  })

  it('calls navigate when a promo type checkbox is toggled', () => {
    navigateMock.mockClear()
    render(
      <SearchFilters params={BASE_PARAMS} promoTypeFacets={['prerelease']} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={vi.fn()} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />,
      { wrapper: Wrapper },
    )
    const checkbox = screen.getByLabelText('Prerelease')
    fireEvent.click(checkbox)
    expect(navigateMock).toHaveBeenCalledOnce()
  })

  it('hides rarity section when rarityFacets is empty', () => {
    render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={vi.fn()} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />, { wrapper: Wrapper })
    // No rarity facet rows should render — checking specific rarity labels rather
    // than the word "Rarity" (which now also appears as a Group-by option).
    expect(screen.queryByText('Common')).toBeNull()
    expect(screen.queryByText('Uncommon')).toBeNull()
    expect(screen.queryByText('Mythic')).toBeNull()
  })

  it('renders only rarities from rarityFacets', () => {
    render(
      <SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} rarityFacets={['mythic', 'rare']} priceTrend={undefined} onPriceTrendChange={vi.fn()} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />,
      { wrapper: Wrapper },
    )
    expect(screen.getByText('Mythic')).toBeTruthy()
    expect(screen.getByText('Rare')).toBeTruthy()
    expect(screen.queryByText('Common')).toBeNull()
  })

  it('renders sort section with Name A→Z button', () => {
    render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={vi.fn()} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />, { wrapper: Wrapper })
    expect(screen.getByRole('button', { name: /name a→z/i })).toBeTruthy()
  })

  it('renders sort section with Newest and Cheapest buttons', () => {
    render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={vi.fn()} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />, { wrapper: Wrapper })
    expect(screen.getByRole('button', { name: /newest/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /cheapest/i })).toBeTruthy()
  })

  it('does not render Set or Finish as group-by options', () => {
    render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={vi.fn()} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />, { wrapper: Wrapper })
    const groupSection = screen.getByText(/group by/i).closest('section')!
    expect(groupSection.querySelector('[data-group="set"]')).toBeNull()
    expect(groupSection.querySelector('[data-group="finish"]')).toBeNull()
  })

  it('renders Color section with W U B R G C Multi pills', () => {
    render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={vi.fn()} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />, { wrapper: Wrapper })
    expect(screen.getByRole('button', { name: 'W' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'U' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Multi' })).toBeTruthy()
  })

  it('toggles a color on click — adds to colors array', () => {
    navigateMock.mockClear()
    render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={vi.fn()} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />, { wrapper: Wrapper })
    fireEvent.click(screen.getByRole('button', { name: 'U' }))
    expect(navigateMock).toHaveBeenCalledOnce()
  })

  it('renders Price trend section with Rising Stable Falling', () => {
    render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={vi.fn()} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />, { wrapper: Wrapper })
    expect(screen.getByText(/rising/i)).toBeTruthy()
    expect(screen.getByText(/falling/i)).toBeTruthy()
  })

  it('calls onPriceTrendChange when Rising is clicked', () => {
    const onChange = vi.fn()
    render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={onChange} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />, { wrapper: Wrapper })
    fireEvent.click(screen.getByText(/↑ rising/i))
    expect(onChange).toHaveBeenCalledWith('rising')
  })
})
