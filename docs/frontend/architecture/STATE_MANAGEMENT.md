# State Management Architecture

## State Library Choice

AutoMana uses **Zustand** for global state management.

### Why Zustand?

1. **Minimal boilerplate**: Stores are plain functions, not classes or decorators
2. **No provider hell**: Opt-in stores, not forced context providers wrapping the entire app
3. **Direct store access**: Subscribe to store changes without re-renders; use hooks for render subscriptions
4. **Tiny bundle**: ~2KB gzipped vs ~40KB for Redux or ~20KB for Pinia
5. **DevTools support**: Time-travel debugging available via middleware
6. **TypeScript-first**: Strong inference without extra effort

### Example: Hello Zustand

```tsx
import { create } from 'zustand';

interface CollectionsStore {
  collections: Card[];
  addCard: (card: Card) => void;
  removeCard: (id: string) => void;
}

export const useCollectionsStore = create<CollectionsStore>((set) => ({
  collections: [],
  addCard: (card) => set((state) => ({
    collections: [...state.collections, card],
  })),
  removeCard: (id) => set((state) => ({
    collections: state.collections.filter(c => c.id !== id),
  })),
}));

// Usage in a component
const collections = useCollectionsStore((state) => state.collections);
const addCard = useCollectionsStore((state) => state.addCard);
```

### Alternatives Considered

| Library | Pros | Cons | Verdict |
|---------|------|------|---------|
| Redux | Battle-tested, time-travel | Verbose boilerplate, steep learning curve | Overkill for AutoMana |
| Pinia | VueJS ecosystem | Not TypeScript-first, Vue-only | Vue, not React |
| Context API | Built-in, simple | Performance issues (re-renders), prop drilling | Only for UI state |
| Recoil | Atom-based, concurrent | Experimental API, smaller community | Unstable |
| Jotai | Minimal, atomic | Smaller ecosystem | Equivalent to Zustand; Zustand chosen first |

---

## Store Structure & Design

Stores are organized by domain. Each store module is independent and cohesive.

### Folder Organization

```
src/store/
  auth.ts                  # User session, login state
  collections.ts           # Card collections, filters
  pricing.ts               # Price data, historical prices
  cart.ts                  # Shopping cart state
  ui.ts                    # UI-only state: modals, sidebars, tooltips
  middleware/
    persistMiddleware.ts    # Persist stores to localStorage
    devtools.ts            # Redux DevTools integration
```

### Store Module Responsibilities

Each store module is **single-concern**. If a store exceeds ~150 lines, split it into multiple stores:

```tsx
// src/store/collections.ts - GOOD: Single responsibility
interface CollectionsStore {
  collections: Collection[];
  loading: boolean;
  error: string | null;
  filters: CollectionFilters;
  fetchCollections: () => Promise<void>;
  setFilters: (filters: Partial<CollectionFilters>) => void;
  deleteCollection: (id: string) => Promise<void>;
}

// src/store/pricing.ts - GOOD: Separate concern
interface PricingStore {
  prices: Map<string, Price>;
  historicalData: PriceHistory[];
  loading: boolean;
  fetchPriceHistory: (cardId: string) => Promise<void>;
}

// NOT: Mixing collections and pricing in one store
```

### Naming Conventions

- **State fields**: camelCase (e.g., `isLoading`, `selectedCardId`)
- **Actions**: verb form starting with a verb (e.g., `fetchCollections`, `setFilter`, `resetFilters`)
- **Computed selectors**: descriptive (e.g., `getFilteredCollections`, `getPricingStats`)
- **Store exports**: `use{Domain}Store` (e.g., `useCollectionsStore`, `usePricingStore`)

### Example: Complete Collections Store

```tsx
// src/store/collections.ts
import { create } from 'zustand';
import { collectionApi } from '../features/collections/services/collectionApi';

export interface Collection {
  id: string;
  name: string;
  cardCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface CollectionFilters {
  searchQuery: string;
  sortBy: 'name' | 'createdAt' | 'cardCount';
  sortOrder: 'asc' | 'desc';
}

interface CollectionsState {
  // State
  collections: Collection[];
  loading: boolean;
  error: string | null;
  filters: CollectionFilters;

  // Actions
  fetchCollections: () => Promise<void>;
  createCollection: (name: string) => Promise<Collection>;
  deleteCollection: (id: string) => Promise<void>;
  setFilters: (filters: Partial<CollectionFilters>) => void;
  resetFilters: () => void;

  // Computed
  getFilteredCollections: () => Collection[];
}

const initialFilters: CollectionFilters = {
  searchQuery: '',
  sortBy: 'createdAt',
  sortOrder: 'desc',
};

export const useCollectionsStore = create<CollectionsState>((set, get) => ({
  // State
  collections: [],
  loading: false,
  error: null,
  filters: initialFilters,

  // Actions
  fetchCollections: async () => {
    set({ loading: true, error: null });
    try {
      const collections = await collectionApi.list();
      set({ collections, loading: false });
    } catch (error) {
      set({ error: error.message, loading: false });
    }
  },

  createCollection: async (name) => {
    try {
      const collection = await collectionApi.create(name);
      set((state) => ({
        collections: [...state.collections, collection],
      }));
      return collection;
    } catch (error) {
      set({ error: error.message });
      throw error;
    }
  },

  deleteCollection: async (id) => {
    try {
      await collectionApi.delete(id);
      set((state) => ({
        collections: state.collections.filter((c) => c.id !== id),
      }));
    } catch (error) {
      set({ error: error.message });
      throw error;
    }
  },

  setFilters: (filters) => {
    set((state) => ({
      filters: { ...state.filters, ...filters },
    }));
  },

  resetFilters: () => {
    set({ filters: initialFilters });
  },

  // Computed
  getFilteredCollections: () => {
    const state = get();
    const { collections, filters } = state;
    const { searchQuery, sortBy, sortOrder } = filters;

    let filtered = collections;

    // Apply search filter
    if (searchQuery) {
      filtered = filtered.filter((c) =>
        c.name.toLowerCase().includes(searchQuery.toLowerCase())
      );
    }

    // Apply sorting
    const sorted = [...filtered].sort((a, b) => {
      const aVal = a[sortBy];
      const bVal = b[sortBy];
      const cmp = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
      return sortOrder === 'asc' ? cmp : -cmp;
    });

    return sorted;
  },
}));
```

---

## Global vs. Local State Decisions

### Decision Matrix

| Type | Storage | Example | Rationale |
|------|---------|---------|-----------|
| **User session** | Global (Zustand) | Logged-in user ID, role, email | Needed by many components (header, sidebar, API auth) |
| **Domain data** | Global (Zustand) | Collections, cards, prices | Shared across multiple routes and components |
| **Filters** | Global (URL + Zustand) | Search query, sort order, rarity filter | Bookmarkable; survives page refresh |
| **Form input** | Local (React `useState`) | Text field value during editing | Not needed elsewhere; high-frequency updates |
| **Modal open/close** | Local (React `useState`) | "Delete confirmation" dialog visible | Only affects one component tree |
| **Scroll position** | Local (Ref) | Scroll top of list | Not needed outside component |
| **Theme (light/dark)** | Global (Zustand) + localStorage | Dark mode toggle | Affects all pages |
| **Toast notifications** | Global (Zustand) | Error/success messages | Displayed globally |
| **Tab selection** | URL query param | Active tab in settings page | Bookmarkable; survives refresh |

### Global State Examples

```tsx
// Global: User session (every component needs this)
const user = useAuthStore((state) => state.user);

// Global: Collections data (list, detail, and form pages all use it)
const collections = useCollectionsStore((state) => state.collections);

// Global: Pricing filters (bookmarkable URL + persistent state)
const { minPrice, maxPrice } = usePricingStore((state) => state.filters);
```

### Local State Examples

```tsx
// Local: Form field during edit (not needed elsewhere)
const [cardName, setCardName] = useState('Black Lotus');

// Local: Modal visibility (only affects this component)
const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);

// Local: Dropdown menu (keyboard-only state, high-frequency updates)
const [isMenuOpen, setIsMenuOpen] = useState(false);
```

### URL State Examples

```tsx
// Filters in URL for bookmarkability
// URL: /collections?search=lotus&rarity=M&sort=-price&page=1

const location = useLocation();
const params = new URLSearchParams(location.search);
const searchQuery = params.get('search') || '';
const rarity = params.get('rarity') || null;
const sortBy = params.get('sort') || 'name';
const page = parseInt(params.get('page') || '1');
```

---

## Data Normalization Strategy

### Why Normalize?

Nested data structures create consistency problems:

```tsx
// BAD: Nested structure (duplicates data)
{
  collections: [
    {
      id: '1',
      name: 'Legacy',
      cards: [
        { id: 'card-1', name: 'Black Lotus', price: { current: 1000, trend: 'up' } }
      ]
    }
  ]
}

// Problem: Same card appears in multiple collections
// Update price in one, forget to update in others = inconsistency
```

### GOOD: Flat Normalization

```tsx
// GOOD: Flat, normalized structure
{
  collections: {
    '1': { id: '1', name: 'Legacy', cardIds: ['card-1'] }
  },
  cards: {
    'card-1': { id: 'card-1', name: 'Black Lotus', collectionIds: ['1'] }
  },
  prices: {
    'price-card-1': { id: 'price-card-1', cardId: 'card-1', current: 1000, trend: 'up' }
  }
}
```

**Benefits**:
- Single source of truth: Each entity exists once
- Update consistency: Change a price once, it's updated everywhere
- Query efficiency: Look up by ID is O(1)
- Subscription efficiency: Zustand re-renders only affected components

### Zustand Store with Normalization

```tsx
interface NormalizedCollectionsState {
  // Normalized data
  byId: Map<string, Collection>;
  allIds: string[];

  // Actions
  addCollection: (collection: Collection) => void;
  updateCollection: (id: string, updates: Partial<Collection>) => void;

  // Computed: Get collection by ID
  getCollection: (id: string) => Collection | undefined;

  // Computed: Get all collections as array
  getCollections: () => Collection[];
}

export const useCollectionsStore = create<NormalizedCollectionsState>((set, get) => ({
  byId: new Map(),
  allIds: [],

  addCollection: (collection) => {
    set((state) => {
      const newById = new Map(state.byId);
      newById.set(collection.id, collection);
      return {
        byId: newById,
        allIds: [...state.allIds, collection.id],
      };
    });
  },

  updateCollection: (id, updates) => {
    set((state) => {
      const existing = state.byId.get(id);
      if (!existing) return state;

      const newById = new Map(state.byId);
      newById.set(id, { ...existing, ...updates });
      return { byId: newById };
    });
  },

  getCollection: (id) => get().byId.get(id),

  getCollections: () => {
    const state = get();
    return state.allIds.map((id) => state.byId.get(id)).filter(Boolean);
  },
}));
```

---

## Store Patterns & Best Practices

### Async Action Handling

Actions that fetch data should manage loading and error states:

```tsx
fetchCollections: async () => {
  set({ loading: true, error: null });
  try {
    const data = await api.getCollections();
    set({ collections: data, loading: false });
  } catch (err) {
    set({ error: err.message, loading: false });
    throw err; // Re-throw to let the caller handle it
  }
},
```

### Error State Management

Keep error state alongside the data it failed to load:

```tsx
interface CollectionsStore {
  collections: Collection[];
  collectionsError: string | null;
  prices: PriceData[];
  pricesError: string | null;
  // Separate errors for each data type
}

// Usage in component:
const { collections, collectionsError } = useCollectionsStore();
const { prices, pricesError } = usePricingStore();

if (collectionsError) return <Error message={collectionsError} />;
```

### Loading State Patterns

Use granular loading flags for different operations:

```tsx
interface CollectionsStore {
  loading: boolean;           // Initial fetch
  isCreating: boolean;        // Create operation
  isDeleting: Set<string>;    // Delete per item (can delete while list loads)
}

// Usage:
const { loading, isCreating, isDeleting } = useCollectionsStore();

if (loading) return <Spinner />;

{collections.map((c) => (
  <button
    key={c.id}
    disabled={isDeleting.has(c.id)}
    onClick={() => deleteCollection(c.id)}
  >
    {isDeleting.has(c.id) ? 'Deleting...' : 'Delete'}
  </button>
))}
```

### Reset/Cleanup Patterns

When leaving a feature, reset its state to avoid stale data:

```tsx
// In page component cleanup
useEffect(() => {
  return () => {
    // Reset collections state when leaving the page
    useCollectionsStore.setState({
      collections: [],
      filters: initialFilters,
      error: null,
    });
  };
}, []);
```

Or provide explicit reset action:

```tsx
interface CollectionsStore {
  reset: () => void;
}

reset: () => {
  set({
    collections: [],
    filters: initialFilters,
    error: null,
    loading: false,
  });
},
```

---

## Testing State Logic

### Unit Testing Store Actions

Test actions in isolation using a fresh store instance:

```tsx
// src/store/__tests__/collections.test.ts
import { useCollectionsStore } from '../collections';

describe('Collections Store', () => {
  beforeEach(() => {
    useCollectionsStore.setState({
      collections: [],
      filters: { searchQuery: '', sortBy: 'createdAt', sortOrder: 'desc' },
    });
  });

  it('adds a collection', () => {
    const store = useCollectionsStore.getState();
    const newCollection = { id: '1', name: 'Deck', cardCount: 5, createdAt: '', updatedAt: '' };
    store.collections = [...store.collections, newCollection];

    expect(store.collections).toHaveLength(1);
    expect(store.collections[0].name).toBe('Deck');
  });

  it('filters collections by search query', () => {
    const store = useCollectionsStore.getState();
    store.collections = [
      { id: '1', name: 'Legacy Deck', cardCount: 5, createdAt: '', updatedAt: '' },
      { id: '2', name: 'Modern Deck', cardCount: 10, createdAt: '', updatedAt: '' },
    ];
    store.setFilters({ searchQuery: 'Legacy' });

    const filtered = store.getFilteredCollections();
    expect(filtered).toHaveLength(1);
    expect(filtered[0].name).toBe('Legacy Deck');
  });

  it('handles async fetch errors', async () => {
    jest.spyOn(global, 'fetch').mockRejectedValue(new Error('Network error'));
    const store = useCollectionsStore.getState();

    await expect(store.fetchCollections()).rejects.toThrow();
    expect(store.error).toBe('Network error');
    expect(store.loading).toBe(false);
  });
});
```

### Mock Store Setup

For component tests, provide mock store state:

```tsx
// src/features/collections/__tests__/CollectionList.test.tsx
import { render, screen } from '@testing-library/react';
import { CollectionList } from '../components/CollectionList';
import { useCollectionsStore } from '../store/collections';

jest.mock('../store/collections');

describe('CollectionList', () => {
  it('renders collections from store', () => {
    (useCollectionsStore as jest.Mock).mockReturnValue({
      collections: [
        { id: '1', name: 'Black Lotus', cardCount: 1 },
      ],
      loading: false,
      error: null,
    });

    render(<CollectionList />);
    expect(screen.getByText('Black Lotus')).toBeInTheDocument();
  });

  it('shows spinner when loading', () => {
    (useCollectionsStore as jest.Mock).mockReturnValue({
      collections: [],
      loading: true,
      error: null,
    });

    render(<CollectionList />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});
```

---

## Summary

AutoMana's state management architecture balances **simplicity** and **scalability**:

- **Zustand** provides a minimal, type-safe store with no boilerplate
- **Normalized data** ensures single source of truth and prevents inconsistency
- **Clear separation** of global state (Zustand), local state (React hooks), and URL state (query params)
- **Granular loading/error states** for each async operation
- **Testable actions** that are easy to mock and verify

The result: predictable, debuggable state that scales from a simple app to a complex feature-rich system.
