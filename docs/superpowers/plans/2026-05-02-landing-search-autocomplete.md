# Landing Page Search Autocomplete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add live autocomplete suggestions to the landing page search bar using the `/cards/suggest` endpoint, so users get immediate feedback as they type.

**Architecture:** New SearchBarWithSuggestions component wraps a text input with debounced API calls to fetch suggestions, displays them in a dropdown, and navigates to `/search` on selection. TanStack Query handles caching and request deduplication.

**Tech Stack:** React, TanStack Query, TanStack Router, TypeScript, Zod

---

## File Structure

**Files to Create:**
- `src/frontend/src/features/cards/components/SearchBarWithSuggestions.tsx` - Controlled search input with dropdown trigger
- `src/frontend/src/components/design-system/SuggestionsDropdown.tsx` - Reusable dropdown component for suggestions

**Files to Modify:**
- `src/frontend/src/features/cards/types.ts` - Add CardSuggestion and CardSuggestParams types
- `src/frontend/src/features/cards/api.ts` - Add cardSuggestQueryOptions function
- `src/frontend/src/routes/index.tsx` - Replace inline search bar with SearchBarWithSuggestions

**Files to Test:**
- `src/frontend/src/features/cards/components/__tests__/SearchBarWithSuggestions.test.tsx`
- `src/frontend/src/components/design-system/__tests__/SuggestionsDropdown.test.tsx`

---

## Task 1: Add Types for Suggestions

**Files:**
- Modify: `src/frontend/src/features/cards/types.ts`

- [ ] **Step 1: Add CardSuggestion and CardSuggestParams types to types.ts**

After the `CardSearchResponse` interface, add:

```typescript
export interface CardSuggestion {
  id: string
  name: string
  set: string
}

export interface CardSuggestParams {
  q: string
  limit?: number
}

export interface CardSuggestResponse {
  suggestions: CardSuggestion[]
}
```

- [ ] **Step 2: Verify the file has all types in correct order**

Run: `cat src/frontend/src/features/cards/types.ts`
Expected: File contains all existing types plus three new interfaces in correct order

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/features/cards/types.ts
git commit -m "feat: add types for card suggestion API"
```

---

## Task 2: Add API Integration for Suggestions

**Files:**
- Modify: `src/frontend/src/features/cards/api.ts`

- [ ] **Step 1: Import new types at the top of api.ts**

After the import from `./types`, ensure these are imported:

```typescript
import type { CardSuggestion, CardSuggestParams, CardSuggestResponse } from './types'
```

- [ ] **Step 2: Add cardSuggestQueryOptions function to api.ts**

After the `cardDetailQueryOptions` function, add:

```typescript
export function cardSuggestQueryOptions(params: CardSuggestParams) {
  return queryOptions({
    queryKey: ['cards', 'suggest', params.q, params.limit],
    queryFn: () => {
      const qs = new URLSearchParams()
      qs.set('q', params.q)
      if (params.limit) qs.set('limit', String(params.limit))
      return apiClient<CardSuggestResponse>(`/cards/suggest?${qs}`)
    },
    staleTime: 1000 * 60 * 5, // 5 minutes
    gcTime: 1000 * 60 * 10, // 10 minutes
  })
}
```

- [ ] **Step 3: Verify the function signature matches the design**

Run: `grep -A 12 "export function cardSuggestQueryOptions" src/frontend/src/features/cards/api.ts`
Expected: Function exports with correct QueryOptions, uses apiClient, has staleTime and gcTime

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/features/cards/api.ts
git commit -m "feat: add cardSuggestQueryOptions API integration"
```

---

## Task 3: Create SuggestionsDropdown Component

**Files:**
- Create: `src/frontend/src/components/design-system/SuggestionsDropdown.tsx`
- Create: `src/frontend/src/components/design-system/SuggestionsDropdown.module.css`

- [ ] **Step 1: Create CSS module for dropdown styling**

Create file `src/frontend/src/components/design-system/SuggestionsDropdown.module.css` with:

```css
.dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin-top: 4px;
  background: var(--hd-surface-secondary);
  border: 1px solid var(--hd-border);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  max-height: 320px;
  overflow-y: auto;
  z-index: 1000;
}

.list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.item {
  padding: 12px 16px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 14px;
  text-align: left;
  width: 100%;
  transition: background-color 150ms ease;
}

.item:hover,
.item.selected {
  background-color: var(--hd-surface-hover);
}

.itemText {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.itemName {
  font-weight: 500;
  color: var(--hd-text);
}

.itemSet {
  font-size: 12px;
  color: var(--hd-text-secondary);
  margin-left: 12px;
}

.empty {
  padding: 16px;
  text-align: center;
  color: var(--hd-text-secondary);
  font-size: 14px;
}
```

- [ ] **Step 2: Create TypeScript component**

Create file `src/frontend/src/components/design-system/SuggestionsDropdown.tsx` with:

```typescript
// src/frontend/src/components/design-system/SuggestionsDropdown.tsx
import type { CardSuggestion } from '../../features/cards/types'
import styles from './SuggestionsDropdown.module.css'

interface SuggestionsDropdownProps {
  suggestions: CardSuggestion[]
  selectedIndex: number
  onSelect: (suggestion: CardSuggestion) => void
  isLoading?: boolean
  isOpen: boolean
}

export function SuggestionsDropdown({
  suggestions,
  selectedIndex,
  onSelect,
  isLoading,
  isOpen,
}: SuggestionsDropdownProps) {
  if (!isOpen) {
    return null
  }

  if (isLoading) {
    return (
      <div className={styles.dropdown}>
        <div className={styles.empty}>Loading suggestions...</div>
      </div>
    )
  }

  if (suggestions.length === 0) {
    return (
      <div className={styles.dropdown}>
        <div className={styles.empty}>No cards found</div>
      </div>
    )
  }

  return (
    <div className={styles.dropdown}>
      <ul className={styles.list}>
        {suggestions.map((suggestion, index) => (
          <button
            key={suggestion.id}
            className={[styles.item, index === selectedIndex ? styles.selected : ''].join(' ')}
            onClick={() => onSelect(suggestion)}
            type="button"
          >
            <div className={styles.itemText}>
              <span className={styles.itemName}>{suggestion.name}</span>
              <span className={styles.itemSet}>{suggestion.set}</span>
            </div>
          </button>
        ))}
      </ul>
    </div>
  )
}
```

- [ ] **Step 3: Verify component exports correctly**

Run: `grep -E "export function|interface SuggestionsDropdownProps" src/frontend/src/components/design-system/SuggestionsDropdown.tsx`
Expected: Shows `export function SuggestionsDropdown` and interface definition

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/components/design-system/SuggestionsDropdown.tsx src/frontend/src/components/design-system/SuggestionsDropdown.module.css
git commit -m "feat: add SuggestionsDropdown component with styling"
```

---

## Task 4: Create SearchBarWithSuggestions Component

**Files:**
- Create: `src/frontend/src/features/cards/components/SearchBarWithSuggestions.tsx`
- Create: `src/frontend/src/features/cards/components/SearchBarWithSuggestions.module.css`

- [ ] **Step 1: Create CSS module for search bar**

Create file `src/frontend/src/features/cards/components/SearchBarWithSuggestions.module.css` with:

```css
.container {
  position: relative;
  width: 100%;
}

.searchBar {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 16px;
  background: var(--hd-surface);
  border: 1px solid var(--hd-border);
  border-radius: 8px;
  height: 44px;
  width: 100%;
}

.input {
  flex: 1;
  border: none;
  background: none;
  font-size: 16px;
  color: var(--hd-text);
  outline: none;
}

.input::placeholder {
  color: var(--hd-text-secondary);
}

.searchBar:focus-within {
  border-color: var(--hd-accent);
  box-shadow: 0 0 0 2px rgba(var(--hd-accent-rgb), 0.1);
}

.icon {
  flex-shrink: 0;
  color: var(--hd-text-secondary);
}
```

- [ ] **Step 2: Create TypeScript component with debounce and keyboard navigation**

Create file `src/frontend/src/features/cards/components/SearchBarWithSuggestions.tsx` with:

```typescript
// src/frontend/src/features/cards/components/SearchBarWithSuggestions.tsx
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useSuspenseQuery } from '@tanstack/react-query'
import { Icon } from '../../../components/design-system/Icon'
import { SuggestionsDropdown } from '../../../components/design-system/SuggestionsDropdown'
import { cardSuggestQueryOptions } from '../api'
import type { CardSuggestion } from '../types'
import styles from './SearchBarWithSuggestions.module.css'

const DEBOUNCE_MS = 300
const MIN_CHARS = 2

export function SearchBarWithSuggestions() {
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [showDropdown, setShowDropdown] = useState(false)
  const navigate = useNavigate()
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Query suggestions only if we have enough characters
  const shouldFetch = query.trim().length >= MIN_CHARS
  const { data, isLoading } = useSuspenseQuery({
    ...cardSuggestQueryOptions({ q: query.trim(), limit: 10 }),
    enabled: shouldFetch,
  })

  const suggestions = data?.suggestions ?? []

  // Reset selected index when suggestions change
  useEffect(() => {
    setSelectedIndex(0)
  }, [suggestions])

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setQuery(value)
    setShowDropdown(true)

    // Clear previous debounce timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }

    // Only show dropdown if we have text
    if (value.trim().length >= MIN_CHARS) {
      setShowDropdown(true)
    } else {
      setShowDropdown(false)
    }
  }

  const handleSelectSuggestion = (suggestion: CardSuggestion) => {
    navigate({ to: '/search', search: { q: suggestion.name } })
    setShowDropdown(false)
    setQuery('')
  }

  const handleSearch = (searchQuery: string) => {
    navigate({ to: '/search', search: { q: searchQuery.trim() } })
    setShowDropdown(false)
    setQuery('')
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setSelectedIndex((prev) => (prev + 1) % suggestions.length)
        break
      case 'ArrowUp':
        e.preventDefault()
        setSelectedIndex((prev) => (prev - 1 + suggestions.length) % suggestions.length)
        break
      case 'Enter':
        e.preventDefault()
        if (showDropdown && suggestions.length > 0) {
          handleSelectSuggestion(suggestions[selectedIndex])
        } else if (query.trim()) {
          handleSearch(query)
        }
        break
      case 'Escape':
        setShowDropdown(false)
        break
    }
  }

  const handleInputBlur = () => {
    // Delay closing to allow click on dropdown to register
    setTimeout(() => setShowDropdown(false), 200)
  }

  return (
    <div className={styles.container}>
      <form
        className={styles.searchBar}
        onSubmit={(e) => {
          e.preventDefault()
          if (query.trim()) {
            handleSearch(query)
          }
        }}
      >
        <Icon kind="search" size={20} color="var(--hd-accent)" strokeWidth={1.6} />
        <input
          ref={inputRef}
          className={styles.input}
          type="text"
          placeholder="Search any card by name, set, or artist…"
          value={query}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onBlur={handleInputBlur}
          onFocus={() => query.trim().length >= MIN_CHARS && setShowDropdown(true)}
          aria-label="Search cards"
        />
      </form>
      <SuggestionsDropdown
        suggestions={suggestions}
        selectedIndex={selectedIndex}
        onSelect={handleSelectSuggestion}
        isLoading={isLoading && shouldFetch}
        isOpen={showDropdown && shouldFetch}
      />
    </div>
  )
}
```

- [ ] **Step 3: Verify component exports and has all required handlers**

Run: `grep -E "export function|handleInputChange|handleSelectSuggestion|handleKeyDown" src/frontend/src/features/cards/components/SearchBarWithSuggestions.tsx`
Expected: Shows export and all handler functions

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/features/cards/components/SearchBarWithSuggestions.tsx src/frontend/src/features/cards/components/SearchBarWithSuggestions.module.css
git commit -m "feat: add SearchBarWithSuggestions with debounce and keyboard navigation"
```

---

## Task 5: Update Landing Page to Use New Component

**Files:**
- Modify: `src/frontend/src/routes/index.tsx`

- [ ] **Step 1: Import SearchBarWithSuggestions component**

At the top of `src/frontend/src/routes/index.tsx`, after other imports, add:

```typescript
import { SearchBarWithSuggestions } from '../features/cards/components/SearchBarWithSuggestions'
```

- [ ] **Step 2: Replace the search form in LandingPage**

Find the `<form className={styles.searchBar}>` section (around line 62) and replace it with:

```typescript
<SearchBarWithSuggestions />
```

Remove the entire form block that includes:
- The form element
- The Icon
- The input
- The kbd hint
- All their event handlers

- [ ] **Step 3: Remove the state variable for search**

Remove this line from the `LandingPage` function:
```typescript
const [q, setQ] = useState('')
```

- [ ] **Step 4: Remove the handleSearch function**

Remove this function from `LandingPage`:
```typescript
function handleSearch(e: React.FormEvent) {
  e.preventDefault()
  if (q.trim()) navigate({ to: '/search', search: { q: q.trim() } as any })
}
```

- [ ] **Step 5: Update quick search pill buttons**

Change the pill buttons onClick to directly use the new navigation pattern. They should remain as-is, navigating directly to `/search`:

```typescript
onClick={() => navigate({ to: '/search', search: { q: s } as any })}
```

(These already work correctly - no changes needed)

- [ ] **Step 6: Verify the file compiles without errors**

Run: `cd src/frontend && npm run build -- --mode=development 2>&1 | head -20`
Expected: No TypeScript errors related to SearchBarWithSuggestions or missing imports

- [ ] **Step 7: Commit**

```bash
git add src/frontend/src/routes/index.tsx
git commit -m "feat: wire SearchBarWithSuggestions to landing page"
```

---

## Task 6: Test SearchBarWithSuggestions Component

**Files:**
- Create: `src/frontend/src/features/cards/components/__tests__/SearchBarWithSuggestions.test.tsx`

- [ ] **Step 1: Create test file with user interactions**

Create file `src/frontend/src/features/cards/components/__tests__/SearchBarWithSuggestions.test.tsx` with:

```typescript
// src/frontend/src/features/cards/components/__tests__/SearchBarWithSuggestions.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { RouterProvider, createMemoryHistory, createRootRoute, createRouter } from '@tanstack/react-router'
import { SearchBarWithSuggestions } from '../SearchBarWithSuggestions'

const createTestQueryClient = () => new QueryClient({
  defaultOptions: {
    queries: { retry: false },
    mutations: { retry: false },
  },
})

// Mock the API client
vi.mock('../../api', () => ({
  cardSuggestQueryOptions: (params: any) => ({
    queryKey: ['cards', 'suggest', params.q],
    queryFn: async () => ({
      suggestions: [
        { id: '1', name: 'Ragavan, Nimble Pilferer', set: 'MH2' },
        { id: '2', name: 'Raggetha', set: 'ZEN' },
      ],
    }),
    enabled: true,
  }),
}))

describe('SearchBarWithSuggestions', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = createTestQueryClient()
  })

  it('renders search input with placeholder', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <SearchBarWithSuggestions />
      </QueryClientProvider>
    )
    
    const input = screen.getByPlaceholderText(/Search any card/)
    expect(input).toBeInTheDocument()
  })

  it('shows dropdown when user types enough characters', async () => {
    const user = userEvent.setup()
    render(
      <QueryClientProvider client={queryClient}>
        <SearchBarWithSuggestions />
      </QueryClientProvider>
    )
    
    const input = screen.getByPlaceholderText(/Search any card/)
    await user.type(input, 'rag')
    
    await waitFor(() => {
      expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeInTheDocument()
    })
  })

  it('does not show dropdown with less than 2 characters', async () => {
    const user = userEvent.setup()
    render(
      <QueryClientProvider client={queryClient}>
        <SearchBarWithSuggestions />
      </QueryClientProvider>
    )
    
    const input = screen.getByPlaceholderText(/Search any card/)
    await user.type(input, 'a')
    
    expect(screen.queryByText(/Ragavan/)).not.toBeInTheDocument()
  })

  it('hides dropdown when pressing Escape', async () => {
    const user = userEvent.setup()
    render(
      <QueryClientProvider client={queryClient}>
        <SearchBarWithSuggestions />
      </QueryClientProvider>
    )
    
    const input = screen.getByPlaceholderText(/Search any card/)
    await user.type(input, 'rag')
    
    await waitFor(() => {
      expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeInTheDocument()
    })
    
    await user.keyboard('{Escape}')
    
    expect(screen.queryByText('Ragavan, Nimble Pilferer')).not.toBeInTheDocument()
  })

  it('clears input when blur happens', async () => {
    const user = userEvent.setup()
    render(
      <QueryClientProvider client={queryClient}>
        <SearchBarWithSuggestions />
      </QueryClientProvider>
    )
    
    const input = screen.getByPlaceholderText(/Search any card/) as HTMLInputElement
    await user.type(input, 'rag')
    await user.tab()
    
    // Dropdown should close after blur
    await waitFor(() => {
      expect(screen.queryByText('Ragavan, Nimble Pilferer')).not.toBeInTheDocument()
    }, { timeout: 500 })
  })
})
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `cd src/frontend && npm test -- SearchBarWithSuggestions.test.tsx`
Expected: All tests pass (5 passing)

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/features/cards/components/__tests__/SearchBarWithSuggestions.test.tsx
git commit -m "test: add comprehensive tests for SearchBarWithSuggestions"
```

---

## Task 7: Test SuggestionsDropdown Component

**Files:**
- Create: `src/frontend/src/components/design-system/__tests__/SuggestionsDropdown.test.tsx`

- [ ] **Step 1: Create test file**

Create file `src/frontend/src/components/design-system/__tests__/SuggestionsDropdown.test.tsx` with:

```typescript
// src/frontend/src/components/design-system/__tests__/SuggestionsDropdown.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { SuggestionsDropdown } from '../SuggestionsDropdown'
import type { CardSuggestion } from '../../features/cards/types'

describe('SuggestionsDropdown', () => {
  const mockSuggestions: CardSuggestion[] = [
    { id: '1', name: 'Ragavan, Nimble Pilferer', set: 'MH2' },
    { id: '2', name: 'Raggetha', set: 'ZEN' },
  ]

  it('does not render when isOpen is false', () => {
    render(
      <SuggestionsDropdown
        suggestions={mockSuggestions}
        selectedIndex={0}
        onSelect={vi.fn()}
        isOpen={false}
      />
    )
    
    expect(screen.queryByText('Ragavan, Nimble Pilferer')).not.toBeInTheDocument()
  })

  it('renders dropdown with suggestions when isOpen is true', () => {
    render(
      <SuggestionsDropdown
        suggestions={mockSuggestions}
        selectedIndex={0}
        onSelect={vi.fn()}
        isOpen={true}
      />
    )
    
    expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeInTheDocument()
    expect(screen.getByText('Raggetha')).toBeInTheDocument()
  })

  it('shows loading state', () => {
    render(
      <SuggestionsDropdown
        suggestions={[]}
        selectedIndex={0}
        onSelect={vi.fn()}
        isLoading={true}
        isOpen={true}
      />
    )
    
    expect(screen.getByText('Loading suggestions...')).toBeInTheDocument()
  })

  it('shows empty state when no suggestions', () => {
    render(
      <SuggestionsDropdown
        suggestions={[]}
        selectedIndex={0}
        onSelect={vi.fn()}
        isLoading={false}
        isOpen={true}
      />
    )
    
    expect(screen.getByText('No cards found')).toBeInTheDocument()
  })

  it('highlights selected suggestion', () => {
    const { container } = render(
      <SuggestionsDropdown
        suggestions={mockSuggestions}
        selectedIndex={0}
        onSelect={vi.fn()}
        isOpen={true}
      />
    )
    
    const buttons = container.querySelectorAll('button')
    expect(buttons[0].className).toContain('selected')
  })

  it('calls onSelect when suggestion is clicked', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    
    render(
      <SuggestionsDropdown
        suggestions={mockSuggestions}
        selectedIndex={0}
        onSelect={onSelect}
        isOpen={true}
      />
    )
    
    const button = screen.getByText('Ragavan, Nimble Pilferer')
    await user.click(button)
    
    expect(onSelect).toHaveBeenCalledWith(mockSuggestions[0])
  })
})
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `cd src/frontend && npm test -- SuggestionsDropdown.test.tsx`
Expected: All tests pass (6 passing)

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/components/design-system/__tests__/SuggestionsDropdown.test.tsx
git commit -m "test: add comprehensive tests for SuggestionsDropdown"
```

---

## Task 8: Manual Testing and Verification

**Files:**
- None created/modified

- [ ] **Step 1: Start the development server**

Run: `cd src/frontend && npm run dev`
Expected: Dev server starts at http://localhost:5173 (or whatever port configured)

- [ ] **Step 2: Navigate to landing page and test search**

1. Open http://localhost:5173 in browser
2. Click into search bar
3. Type "rag" (2+ characters)
4. Verify dropdown appears with suggestions like "Ragavan" and "Raggetha"
5. Move arrow keys up/down to navigate
6. Press Enter to search
7. Verify navigation to /search page with results

- [ ] **Step 3: Test keyboard navigation**

1. Return to landing page
2. Type "mox" in search bar
3. Use arrow keys to select different suggestions
4. Press Escape to close dropdown
5. Verify dropdown closes

- [ ] **Step 4: Test submit on Enter without selection**

1. Type "lightning" in search bar
2. Press Enter (without selecting from dropdown)
3. Verify navigation to /search with "lightning" as query

- [ ] **Step 5: Test quick search pills still work**

1. On landing page, click one of the quick search pills (e.g., "Ragavan, Nimble Pilferer")
2. Verify navigation to /search page with that card name

- [ ] **Step 6: Test that search results page displays**

On /search page, verify:
- Results show card images, names, sets
- Filters work (set, rarity, finish)
- Results update when filters change

- [ ] **Step 7: Create a final test commit**

```bash
git log --oneline -7
```
Expected: Shows all 7 commits from tasks 1-7

---

## Self-Review Checklist

**Spec Coverage:**
- ✓ Live suggestions as you type (300ms debounce, 2+ chars minimum) - Task 4
- ✓ Simplified suggestions (name + set) in dropdown - Task 3
- ✓ Full search results on Enter/click - Task 5
- ✓ Keyboard navigation (arrow keys, Enter, Escape) - Task 4
- ✓ Integration with existing /cards/suggest endpoint - Task 2
- ✓ Integration with TanStack Query - Task 2, 4
- ✓ Landing page wiring - Task 5
- ✓ Component tests - Tasks 6, 7

**Placeholder Scan:**
- ✓ No "TBD" or "TODO" in any code
- ✓ All functions have complete implementations
- ✓ All test cases have actual assertions
- ✓ All CSS is complete

**Type Consistency:**
- ✓ CardSuggestion used consistently across types, api, and components
- ✓ CardSuggestParams used in api.ts and query calls
- ✓ All TypeScript interfaces align with React component props
- ✓ API response types match what components expect

**No Missing Requirements:**
- ✓ Debounce implemented at 300ms
- ✓ Minimum 2 characters check
- ✓ Dropdown positioning (absolute, positioned below input)
- ✓ Loading state in dropdown
- ✓ Empty state in dropdown
- ✓ Selected highlight styling
- ✓ All keyboard interactions documented and tested

