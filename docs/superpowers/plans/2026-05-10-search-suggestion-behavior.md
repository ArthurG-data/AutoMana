# Search Suggestion Behavior Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a user selects a suggestion from the dropdown, navigate directly to that card's detail page; when ≥ 3 suggestions are returned, suppress those with score < 0.5.

**Architecture:** All changes are confined to `SearchBarWithSuggestions.tsx`. A `useMemo` filters the raw API response before it reaches `SuggestionsDropdown`. The navigation handler switches from the search-results route to the card-detail route. The `score` field already exists on `CardSuggestion` and is returned by the backend.

**Tech Stack:** React 18, TanStack Router, TanStack Query, MSW (tests), Vitest + React Testing Library

---

### Task 1: Update `SearchBarWithSuggestions` — navigation and score filter

**Files:**
- Modify: `src/frontend/src/features/cards/components/SearchBarWithSuggestions.tsx`

- [ ] **Step 1: Add constants and `useMemo` import**

  Replace the top of the file so it reads:

  ```tsx
  // src/frontend/src/features/cards/components/SearchBarWithSuggestions.tsx
  import { useEffect, useMemo, useRef, useState } from 'react'
  import { useNavigate } from '@tanstack/react-router'
  import { useQuery } from '@tanstack/react-query'
  import { Icon } from '../../../components/design-system/Icon'
  import { SuggestionsDropdown } from '../../../components/design-system/SuggestionsDropdown'
  import { cardSuggestQueryOptions } from '../api'
  import type { CardSuggestion } from '../types'
  import styles from './SearchBarWithSuggestions.module.css'

  const MIN_CHARS = 2
  const SUGGESTION_SCORE_THRESHOLD = 0.5
  const SUGGESTION_MIN_COUNT = 3
  ```

- [ ] **Step 2: Replace the `suggestions` derivation with a filtered `useMemo`**

  Find this line (currently line 32):
  ```tsx
  const suggestions = data?.suggestions ?? []
  ```

  Replace it with:
  ```tsx
  const suggestions = useMemo(() => {
    const raw = data?.suggestions ?? []
    if (raw.length < SUGGESTION_MIN_COUNT) return raw
    return raw.filter((s) => s.score >= SUGGESTION_SCORE_THRESHOLD)
  }, [data])
  ```

- [ ] **Step 3: Change `handleSelectSuggestion` to navigate to the card detail page**

  Find `handleSelectSuggestion` (currently lines 57–60):
  ```tsx
  const handleSelectSuggestion = (suggestion: CardSuggestion) => {
    navigate({ to: '/search', search: { q: suggestion.card_name } })
    setShowDropdown(false)
    setQuery('')
  }
  ```

  Replace with:
  ```tsx
  const handleSelectSuggestion = (suggestion: CardSuggestion) => {
    navigate({ to: '/cards/$id', params: { id: suggestion.card_version_id } })
    setShowDropdown(false)
    setQuery('')
  }
  ```

- [ ] **Step 4: Run the existing test suite to confirm no regressions before updating tests**

  ```bash
  cd /home/arthur/projects/AutoMana/src/frontend
  npx vitest run src/features/cards/components/__tests__/SearchBarWithSuggestions.test.tsx
  ```

  Expected: The test "navigates to search page when suggestion is selected" still passes (it only asserts `input.value === ''`, not the navigation target). All other tests pass.

---

### Task 2: Update navigation test to assert correct route

**Files:**
- Modify: `src/frontend/src/features/cards/components/__tests__/SearchBarWithSuggestions.test.tsx`

- [ ] **Step 1: Write the updated navigation assertion**

  Find the test "navigates to search page when suggestion is selected" (lines 102–118). Replace it entirely:

  ```tsx
  it('navigates to card detail page when suggestion is selected', async () => {
    const user = userEvent.setup()
    render(<SearchBarWithSuggestions />, { wrapper: Wrapper })

    const input = screen.getByPlaceholderText(/Search any card/) as HTMLInputElement
    await user.type(input, 'rag')

    await waitFor(() => {
      expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Ragavan, Nimble Pilferer'))

    expect(mockNavigate).toHaveBeenCalledWith({
      to: '/cards/$id',
      params: { id: 'ragavan-mh2' },
    })
    expect(input.value).toBe('')
  })
  ```

- [ ] **Step 2: Run the updated test to verify it passes**

  ```bash
  cd /home/arthur/projects/AutoMana/src/frontend
  npx vitest run src/features/cards/components/__tests__/SearchBarWithSuggestions.test.tsx --reporter=verbose
  ```

  Expected: all tests PASS including the renamed navigation test.

- [ ] **Step 3: Commit**

  ```bash
  git add src/frontend/src/features/cards/components/SearchBarWithSuggestions.tsx \
          src/frontend/src/features/cards/components/__tests__/SearchBarWithSuggestions.test.tsx
  git commit -m "feat(search): select suggestion navigates to card detail page"
  ```

---

### Task 3: Add score-filtering tests

**Files:**
- Modify: `src/frontend/src/features/cards/components/__tests__/SearchBarWithSuggestions.test.tsx`

The MSW `server` is already started globally by `test-setup.ts` and handlers are reset after each test via `server.resetHandlers()`. Use `server.use()` to override the suggest endpoint per test.

- [ ] **Step 1: Add imports for MSW override**

  Add these imports at the top of the test file, after the existing imports:

  ```tsx
  import { http, HttpResponse } from 'msw'
  import { server } from '../../../../mocks/server'
  ```

- [ ] **Step 2: Write failing test — ≥ 3 results, low-score suggestions are hidden**

  Add this test inside the `describe('SearchBarWithSuggestions')` block:

  ```tsx
  it('hides suggestions with score < 0.5 when 3 or more are returned', async () => {
    server.use(
      http.get('/api/catalog/mtg/card-reference/suggest', () =>
        HttpResponse.json({
          suggestions: [
            { card_version_id: 'ragavan-mh2',    card_name: 'Ragavan, Nimble Pilferer', set_code: 'MH2', collector_number: '1', rarity_name: 'mythic', score: 0.9 },
            { card_version_id: 'one-ring-ltr',   card_name: 'The One Ring',             set_code: 'LTR', collector_number: '1', rarity_name: 'mythic', score: 0.7 },
            { card_version_id: 'bowmasters-ltr', card_name: 'Orcish Bowmasters',        set_code: 'LTR', collector_number: '1', rarity_name: 'rare',   score: 0.3 },
          ],
        })
      )
    )

    const user = userEvent.setup()
    render(<SearchBarWithSuggestions />, { wrapper: Wrapper })

    const input = screen.getByPlaceholderText(/Search any card/)
    await user.type(input, 'rag')

    await waitFor(() => {
      expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeInTheDocument()
    })

    expect(screen.getByText('The One Ring')).toBeInTheDocument()
    expect(screen.queryByText('Orcish Bowmasters')).not.toBeInTheDocument()
  })
  ```

- [ ] **Step 3: Run the test to verify it fails**

  ```bash
  cd /home/arthur/projects/AutoMana/src/frontend
  npx vitest run src/features/cards/components/__tests__/SearchBarWithSuggestions.test.tsx --reporter=verbose 2>&1 | grep -A5 "hides suggestions"
  ```

  Expected: PASS — Task 1 already implemented the filter, so "Orcish Bowmasters" is not in the document.

- [ ] **Step 4: Write failing test — fewer than 3 results, all shown even if low score**

  Add this test:

  ```tsx
  it('shows all suggestions when fewer than 3 are returned, regardless of score', async () => {
    server.use(
      http.get('/api/catalog/mtg/card-reference/suggest', () =>
        HttpResponse.json({
          suggestions: [
            { card_version_id: 'ragavan-mh2', card_name: 'Ragavan, Nimble Pilferer', set_code: 'MH2', collector_number: '1', rarity_name: 'mythic', score: 0.31 },
            { card_version_id: 'one-ring-ltr', card_name: 'The One Ring',            set_code: 'LTR', collector_number: '1', rarity_name: 'mythic', score: 0.32 },
          ],
        })
      )
    )

    const user = userEvent.setup()
    render(<SearchBarWithSuggestions />, { wrapper: Wrapper })

    const input = screen.getByPlaceholderText(/Search any card/)
    await user.type(input, 'ra')

    await waitFor(() => {
      expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeInTheDocument()
    })

    expect(screen.getByText('The One Ring')).toBeInTheDocument()
  })
  ```

- [ ] **Step 5: Run all tests in the file to verify both new tests pass**

  ```bash
  cd /home/arthur/projects/AutoMana/src/frontend
  npx vitest run src/features/cards/components/__tests__/SearchBarWithSuggestions.test.tsx --reporter=verbose
  ```

  Expected: all tests PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add src/frontend/src/features/cards/components/__tests__/SearchBarWithSuggestions.test.tsx
  git commit -m "test(search): add score-filtering and navigation assertions"
  ```
