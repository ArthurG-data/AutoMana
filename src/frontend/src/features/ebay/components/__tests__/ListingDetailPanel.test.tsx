import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ListingDetailPanel } from '../ListingDetailPanel'
import type { EbayLiveListing } from '../../mockListings'

// Mock the api module so fetchRecommendation and stageAction are controllable
vi.mock('../../api', () => ({
  fetchRecommendation: vi.fn(),
  stageAction: vi.fn(),
}))

// Import after mock so we get the mocked versions
import * as api from '../../api'

const mockFetchRecommendation = vi.mocked(api.fetchRecommendation)
const mockStageAction = vi.mocked(api.stageAction)

function makeListing(overrides: Partial<EbayLiveListing> = {}): EbayLiveListing {
  return {
    itemId: 'l1',
    title: 'Sheoldred MOM NM MTG',
    cardName: 'Sheoldred, the Apocalypse',
    setCode: 'MOM',
    setInfo: 'MOM',
    price: 55,
    currency: 'AUD',
    conditionLabel: 'Near Mint (NM)',
    finish: 'Regular',
    style: '',
    daysListed: 3,
    watchCount: 7,
    viewItemUrl: 'https://www.ebay.com.au/itm/l1',
    imageUrl: null,
    appCode: 'app1',
    appName: 'AutoMana AU',
    ...overrides,
  }
}

const makeRecommendation = () => ({
  item_id: 'l1',
  suggested_action: 'raise' as const,
  strategy_kind: 'balanced',
  suggested_price: 59.99,
  confidence: 0.82,
  signals_used: 'market' as const,
  all_strategies: {
    quick: { price: 49.5, description: 'Quick sale', confidence: 0.7 },
    balanced: { price: 55.0, description: 'Balanced', confidence: 0.82 },
    max: { price: 62.0, description: 'Max return', confidence: 0.6 },
  },
})

beforeEach(() => {
  vi.clearAllMocks()
  // Default: never resolves — keeps existing tests free of act() warnings from async
  // state updates that fire after the test assertion has already completed.
  // Individual tests that need a resolved recommendation override this per-test.
  mockFetchRecommendation.mockReturnValue(new Promise(() => {}))
  mockStageAction.mockResolvedValue({ action_id: 'act-1', created: true })
})

describe('ListingDetailPanel', () => {
  it('renders card name, price, condition, and watchers', () => {
    render(
      <ListingDetailPanel
        listing={makeListing()}
        onEdit={vi.fn()}
        onClose={vi.fn()}
        onCompare={vi.fn()}
      />
    )
    expect(screen.getByText('Sheoldred, the Apocalypse')).toBeInTheDocument()
    expect(screen.getByText(/55\.00/)).toBeInTheDocument()
    expect(screen.getByText('Near Mint (NM)')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
  })

  it('calls onEdit when Edit listing button is clicked', async () => {
    const onEdit = vi.fn()
    render(
      <ListingDetailPanel
        listing={makeListing()}
        onEdit={onEdit}
        onClose={vi.fn()}
        onCompare={vi.fn()}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: /edit listing/i }))
    expect(onEdit).toHaveBeenCalledOnce()
  })

  it('calls onClose when close button is clicked', async () => {
    const onClose = vi.fn()
    render(
      <ListingDetailPanel
        listing={makeListing()}
        onEdit={vi.fn()}
        onClose={onClose}
        onCompare={vi.fn()}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onCompare when Compare market button is clicked', async () => {
    const onCompare = vi.fn()
    render(
      <ListingDetailPanel
        listing={makeListing()}
        onEdit={vi.fn()}
        onClose={vi.fn()}
        onCompare={onCompare}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: /compare market/i }))
    expect(onCompare).toHaveBeenCalledOnce()
  })

  it('shows thumbnail when imageUrl is present', () => {
    render(
      <ListingDetailPanel
        listing={makeListing({ imageUrl: 'https://example.com/img.jpg' })}
        onEdit={vi.fn()}
        onClose={vi.fn()}
        onCompare={vi.fn()}
      />
    )
    expect(screen.getByRole('img')).toHaveAttribute('src', 'https://example.com/img.jpg')
  })

  it('shows eBay link', () => {
    render(
      <ListingDetailPanel
        listing={makeListing()}
        onEdit={vi.fn()}
        onClose={vi.fn()}
        onCompare={vi.fn()}
      />
    )
    expect(screen.getByRole('link', { name: /view/i })).toHaveAttribute('href', 'https://www.ebay.com.au/itm/l1')
  })

  // ── Strategy Advisor tests ────────────────────────────────────────────────

  it('shows "Loading recommendation..." while fetch is in flight', () => {
    // Default mock never resolves — simulates a fetch in flight
    render(
      <ListingDetailPanel
        listing={makeListing()}
        onEdit={vi.fn()}
        onClose={vi.fn()}
        onCompare={vi.fn()}
      />
    )

    expect(screen.getByText('Loading recommendation...')).toBeInTheDocument()
  })

  it('renders SignalBadge with correct action once recommendation loads', async () => {
    mockFetchRecommendation.mockResolvedValue(makeRecommendation())

    render(
      <ListingDetailPanel
        listing={makeListing()}
        onEdit={vi.fn()}
        onClose={vi.fn()}
        onCompare={vi.fn()}
      />
    )

    // Wait for recommendation to appear — SignalBadge renders span with title="raise"
    await waitFor(() => {
      expect(screen.getByTitle(/↑ Raise/)).toBeInTheDocument()
    })
  })

  it('clicking Stage Action calls stageAction and shows "Action queued"', async () => {
    mockFetchRecommendation.mockResolvedValue(makeRecommendation())

    render(
      <ListingDetailPanel
        listing={makeListing()}
        onEdit={vi.fn()}
        onClose={vi.fn()}
        onCompare={vi.fn()}
      />
    )

    // Wait for recommendation to load and Stage Action button to appear
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /stage action/i })).toBeInTheDocument()
    })

    const stageBtn = screen.getByRole('button', { name: /stage action/i })
    expect(stageBtn).not.toBeDisabled()

    await userEvent.click(stageBtn)

    expect(mockStageAction).toHaveBeenCalledWith('app1', 'l1', {
      action_type: 'raise',
      strategy_kind: 'balanced',
      suggested_price: 59.99,
    })

    await waitFor(() => {
      expect(screen.getAllByText(/action queued/i).length).toBeGreaterThan(0)
    })
  })
})
