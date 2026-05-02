# Testing Strategy

This guide covers the testing pyramid, unit/integration/E2E testing, mock data setup, and coverage targets for the AutoMana React frontend.

## Testing Pyramid

```
                    /\
                   /  \
                  / E2E \      10% — Critical workflows, cross-browser
                 /______\
                /        \
               /   INT    \  60% — Feature-level, user flows, API integration
              /____________\
             /              \
            /     UNIT       \ 30% — Components, hooks, utilities
           /________________\
```

- **Unit Tests** (30%): Individual components, hooks, utilities in isolation.
- **Integration Tests** (60%): Component interactions, API calls, form submission flows.
- **E2E Tests** (10%): Critical user journeys (login → search → purchase) across browsers.

---

## Unit Testing

### Testing Library Setup

**File:** `src/__tests__/setup.ts`

```typescript
import '@testing-library/jest-dom';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// Cleanup after each test
afterEach(() => {
  cleanup();
});

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock IntersectionObserver
global.IntersectionObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
})) as any;
```

**File:** `vitest.config.ts`

```typescript
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/__tests__/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/**/__tests__/**',
        'src/main.tsx',
        'src/vite-env.d.ts',
      ],
      lines: 70,  // Minimum coverage
      functions: 70,
      branches: 65,
      statements: 70,
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
```

### Unit Test: Component

```typescript
// src/components/Button/__tests__/Button.test.tsx

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button } from '../Button';
import { describe, it, expect, vi } from 'vitest';

describe('Button Component', () => {
  it('renders with text content', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole('button', { name: /click me/i })).toBeInTheDocument();
  });

  it('calls onClick handler when clicked', async () => {
    const user = userEvent.setup();
    const handleClick = vi.fn();

    render(<Button onClick={handleClick}>Click</Button>);
    await user.click(screen.getByRole('button'));

    expect(handleClick).toHaveBeenCalledOnce();
  });

  it('disables button when disabled prop is true', () => {
    render(<Button disabled>Disabled</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('applies variant classes correctly', () => {
    const { rerender } = render(<Button variant="primary">Primary</Button>);
    expect(screen.getByRole('button')).toHaveClass('bg-blue-500');

    rerender(<Button variant="danger">Danger</Button>);
    expect(screen.getByRole('button')).toHaveClass('bg-red-500');
  });

  it('shows loading state with spinner', () => {
    render(<Button isLoading>Loading</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
    expect(screen.getByTestId('spinner')).toBeInTheDocument();
  });
});
```

### Unit Test: Hook

```typescript
// src/hooks/__tests__/useLocalStorage.test.ts

import { renderHook, act } from '@testing-library/react';
import { useLocalStorage } from '../useLocalStorage';
import { beforeEach, afterEach, describe, it, expect } from 'vitest';

describe('useLocalStorage Hook', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('initializes with default value', () => {
    const { result } = renderHook(() => useLocalStorage('test-key', 'default'));
    expect(result.current[0]).toBe('default');
  });

  it('reads from localStorage if value exists', () => {
    localStorage.setItem('test-key', JSON.stringify('stored-value'));
    const { result } = renderHook(() => useLocalStorage('test-key', 'default'));
    expect(result.current[0]).toBe('stored-value');
  });

  it('updates localStorage when state changes', () => {
    const { result } = renderHook(() => useLocalStorage('test-key', 'initial'));

    act(() => {
      result.current[1]('updated');
    });

    expect(result.current[0]).toBe('updated');
    expect(localStorage.getItem('test-key')).toBe(JSON.stringify('updated'));
  });

  it('syncs across tabs', () => {
    const { result: result1 } = renderHook(() => useLocalStorage('sync-key', ''));
    const { result: result2 } = renderHook(() => useLocalStorage('sync-key', ''));

    act(() => {
      result1.current[1]('synced-value');
    });

    // Simulate storage event from another tab
    const event = new StorageEvent('storage', {
      key: 'sync-key',
      newValue: JSON.stringify('synced-value'),
      storageArea: localStorage,
    });

    act(() => {
      window.dispatchEvent(event);
    });

    expect(result2.current[0]).toBe('synced-value');
  });
});
```

### Unit Test: Utility Function

```typescript
// src/utils/__tests__/formatPrice.test.ts

import { formatPrice, parseCurrency } from '../currency';
import { describe, it, expect } from 'vitest';

describe('Currency Utilities', () => {
  describe('formatPrice', () => {
    it('formats number to USD string', () => {
      expect(formatPrice(19.99)).toBe('$19.99');
      expect(formatPrice(1000)).toBe('$1,000.00');
      expect(formatPrice(0.5)).toBe('$0.50');
    });

    it('handles negative numbers', () => {
      expect(formatPrice(-19.99)).toBe('-$19.99');
    });

    it('handles large numbers', () => {
      expect(formatPrice(1000000)).toBe('$1,000,000.00');
    });
  });

  describe('parseCurrency', () => {
    it('parses currency string to number', () => {
      expect(parseCurrency('$19.99')).toBe(19.99);
      expect(parseCurrency('$1,000.00')).toBe(1000);
    });

    it('returns 0 for invalid input', () => {
      expect(parseCurrency('invalid')).toBe(0);
      expect(parseCurrency('')).toBe(0);
    });
  });
});
```

---

## Integration Testing

### Integration Test: Form + API

```typescript
// src/features/auth/__tests__/LoginFlow.test.tsx

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import { LoginForm } from '../components/LoginForm';
import { describe, it, expect, beforeAll, afterEach, afterAll, vi } from 'vitest';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from '@/utils/react-query-config';

const server = setupServer(
  http.post('http://localhost:8000/api/auth/login', async ({ request }) => {
    const body = await request.json() as any;

    if (body.email === 'test@example.com' && body.password === 'Password123') {
      return HttpResponse.json({
        access_token: 'mock-jwt-token',
        refresh_token: 'mock-refresh-token',
        expires_in: 3600,
        token_type: 'Bearer',
      });
    }

    return HttpResponse.json(
      { message: 'Invalid credentials' },
      { status: 401 }
    );
  })
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}

describe('Login Flow', () => {
  it('submits form with valid credentials', async () => {
    const user = userEvent.setup();

    render(
      <Wrapper>
        <LoginForm />
      </Wrapper>
    );

    const emailInput = screen.getByPlaceholderText(/you@example/i);
    const passwordInput = screen.getByPlaceholderText(/password/i);
    const submitButton = screen.getByRole('button', { name: /log in/i });

    await user.type(emailInput, 'test@example.com');
    await user.type(passwordInput, 'Password123');
    await user.click(submitButton);

    await waitFor(() => {
      expect(submitButton).not.toBeDisabled();
    });

    // Token should be stored
    const storedToken = localStorage.getItem('automana_auth_tokens');
    expect(storedToken).toBeTruthy();
  });

  it('displays error on invalid credentials', async () => {
    const user = userEvent.setup();

    render(
      <Wrapper>
        <LoginForm />
      </Wrapper>
    );

    await user.type(screen.getByPlaceholderText(/you@example/i), 'wrong@example.com');
    await user.type(screen.getByPlaceholderText(/password/i), 'WrongPass123');
    await user.click(screen.getByRole('button', { name: /log in/i }));

    await waitFor(() => {
      expect(screen.getByText(/invalid email or password/i)).toBeInTheDocument();
    });
  });

  it('disables submit button while loading', async () => {
    const user = userEvent.setup();

    render(
      <Wrapper>
        <LoginForm />
      </Wrapper>
    );

    const submitButton = screen.getByRole('button', { name: /log in/i });

    await user.type(screen.getByPlaceholderText(/you@example/i), 'test@example.com');
    await user.type(screen.getByPlaceholderText(/password/i), 'Password123');

    await user.click(submitButton);

    // Button should show loading state
    expect(submitButton).toHaveTextContent(/logging in/i);
  });
});
```

### Integration Test: Feature with Multiple Components

```typescript
// src/features/cards/__tests__/CardSearch.integration.test.tsx

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import { CardSearchPage } from '../pages/CardSearchPage';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from '@/utils/react-query-config';

const server = setupServer(
  http.get('http://localhost:8000/api/cards/search', ({ request }) => {
    const url = new URL(request.url);
    const query = url.searchParams.get('q');

    if (!query || query.length < 2) {
      return HttpResponse.json({ cards: [] });
    }

    return HttpResponse.json({
      cards: [
        { id: '1', name: `Card matching "${query}"`, rarity: 'rare' },
        { id: '2', name: `Another ${query}`, rarity: 'uncommon' },
      ],
    });
  })
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('Card Search Integration', () => {
  it('searches and displays results', async () => {
    const user = userEvent.setup();

    render(
      <QueryClientProvider client={queryClient}>
        <CardSearchPage />
      </QueryClientProvider>
    );

    const searchInput = screen.getByPlaceholderText(/search cards/i);

    await user.type(searchInput, 'Blue');

    // Wait for results
    await waitFor(() => {
      expect(screen.getByText(/Card matching "Blue"/i)).toBeInTheDocument();
    });
  });

  it('filters results by rarity', async () => {
    const user = userEvent.setup();

    render(
      <QueryClientProvider client={queryClient}>
        <CardSearchPage />
      </QueryClientProvider>
    );

    // Type search
    await user.type(screen.getByPlaceholderText(/search cards/i), 'Blue');

    // Select rarity filter
    const raritySelect = screen.getByDisplayValue(/all rarities/i);
    await user.selectOptions(raritySelect, 'rare');

    // Results should still display (filtered on server side)
    await waitFor(() => {
      expect(screen.queryByText(/another blue/i)).toBeInTheDocument();
    });
  });
});
```

---

## E2E Testing with Playwright

### E2E Test: Complete User Journey

**File:** `e2e/auth.spec.ts`

```typescript
import { test, expect } from '@playwright/test';

test.describe('Authentication Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:5173/login');
  });

  test('user can log in with valid credentials', async ({ page }) => {
    // Fill login form
    await page.fill('input[placeholder="you@example.com"]', 'test@example.com');
    await page.fill('input[placeholder="••••••••"]', 'Password123');

    // Submit
    await page.click('button:has-text("Log In")');

    // Wait for redirect to dashboard
    await page.waitForURL('/dashboard');
    expect(page.url()).toContain('/dashboard');

    // Verify dashboard loaded
    await expect(page.locator('h1:has-text("Dashboard")')).toBeVisible();
  });

  test('user sees error on invalid credentials', async ({ page }) => {
    await page.fill('input[placeholder="you@example.com"]', 'wrong@example.com');
    await page.fill('input[placeholder="••••••••"]', 'WrongPass123');

    await page.click('button:has-text("Log In")');

    // Error message should appear
    const errorMessage = page.locator('text=/Invalid email or password/i');
    await expect(errorMessage).toBeVisible();

    // Should stay on login page
    expect(page.url()).toContain('/login');
  });

  test('user can toggle remember me', async ({ page }) => {
    const checkbox = page.locator('input[type="checkbox"]');
    await expect(checkbox).not.toBeChecked();

    await checkbox.check();
    await expect(checkbox).toBeChecked();
  });
});
```

### E2E Test: Card Search + Add to Collection

**File:** `e2e/cards.spec.ts`

```typescript
import { test, expect } from '@playwright/test';

test.describe('Card Collection Management', () => {
  test.beforeEach(async ({ page }) => {
    // Log in first
    await page.goto('http://localhost:5173/login');
    await page.fill('input[placeholder="you@example.com"]', 'test@example.com');
    await page.fill('input[placeholder="••••••••"]', 'Password123');
    await page.click('button:has-text("Log In")');
    await page.waitForURL('/dashboard');

    // Navigate to cards page
    await page.click('a:has-text("Cards")');
    await page.waitForURL('/cards');
  });

  test('search for cards and add to collection', async ({ page }) => {
    // Search for a card
    const searchInput = page.locator('input[placeholder="Search cards..."]');
    await searchInput.fill('Black Lotus');

    // Wait for results
    await page.waitForSelector('text=Black Lotus');

    // Click on first result
    await page.click('button:has-text("Add to Collection"):first-of-type');

    // Confirm quantity dialog
    await page.fill('input[type="number"]', '1');
    await page.click('button:has-text("Confirm")');

    // Success notification should appear
    await expect(page.locator('text=/added to collection/i')).toBeVisible();

    // Card should appear in my collection
    await page.click('a:has-text("My Collection")');
    await expect(page.locator('text=Black Lotus')).toBeVisible();
  });

  test('filter cards by rarity', async ({ page }) => {
    // Open filter
    await page.click('button:has-text("Filter")');

    // Select rarity
    await page.selectOption('select[name="rarity"]', 'rare');

    // Results should update
    await page.waitForSelector('text=Rare');
  });
});
```

---

## Mock Data & Fixtures

### Factory Pattern for Test Data

**File:** `src/__tests__/factories/card.factory.ts`

```typescript
import { Card } from '@/types';

export const createCard = (overrides?: Partial<Card>): Card => {
  return {
    id: Math.random().toString(),
    name: 'Test Card',
    manaCost: '{2}{U}',
    type: 'Creature — Wizard',
    rarity: 'rare',
    power: '2',
    toughness: '3',
    text: 'Draw a card.',
    imageUrl: 'https://example.com/card.jpg',
    createdAt: new Date().toISOString(),
    ...overrides,
  };
};

export const createCardList = (count: number = 5): Card[] => {
  return Array.from({ length: count }).map((_, i) =>
    createCard({
      id: `card-${i}`,
      name: `Test Card ${i}`,
    })
  );
};
```

### Using Factories in Tests

```typescript
import { createCard } from '@/__tests__/factories/card.factory';

describe('CardItem Component', () => {
  it('displays card details', () => {
    const card = createCard({
      name: 'Black Lotus',
      rarity: 'mythic',
    });

    render(<CardItem card={card} />);

    expect(screen.getByText('Black Lotus')).toBeInTheDocument();
    expect(screen.getByText(/Mythic/i)).toBeInTheDocument();
  });
});
```

### MSW Handlers Library

**File:** `src/mocks/card-handlers.ts`

```typescript
import { http, HttpResponse } from 'msw';

export const cardHandlers = [
  http.get('http://localhost:8000/api/cards/search', ({ request }) => {
    const url = new URL(request.url);
    const query = url.searchParams.get('q') || '';

    if (query.length < 2) {
      return HttpResponse.json({ cards: [] });
    }

    return HttpResponse.json({
      cards: [
        {
          id: '1',
          name: `${query} Card`,
          rarity: 'rare',
          manaCost: '{2}{U}',
        },
      ],
    });
  }),

  http.post('http://localhost:8000/api/collections/add-card', async () => {
    return HttpResponse.json({
      id: 'collection-item-1',
      cardId: '1',
      quantity: 1,
    });
  }),
];
```

---

## Test Coverage Targets

| File Type | Target | Why |
|-----------|--------|-----|
| Components | 80% | Core UI; must test render, interactions, states |
| Hooks | 85% | Business logic; test all branches |
| Utils | 90% | Pure functions; exhaustive test paths |
| Services | 70% | Integration with API; test happy path + errors |
| Routes | 40% | Integration; test critical paths only |
| Stores | 75% | State management; test mutations, selectors |
| Types/Interfaces | 0% | Don't test (compile-time only) |

### What NOT to Test

- Implementation details (internal state, function calls to other functions)
- Snapshot tests (fragile; use visual regression tests instead)
- Third-party library behavior (assume it works)
- Styling/CSS (use visual regression tests)
- Console logs or side effects unrelated to the test goal

---

## Testing Accessibility

### Rendering with Accessibility Checks

```typescript
// Install: npm install jest-axe
import { render } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';

expect.extend(toHaveNoViolations);

test('Button component is accessible', async () => {
  const { container } = render(<Button>Click me</Button>);
  const results = await axe(container);
  expect(results).toHaveNoViolations();
});
```

### Keyboard Navigation Tests

```typescript
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

test('form is keyboard navigable', async () => {
  const user = userEvent.setup();

  render(
    <form>
      <input placeholder="Name" />
      <input type="email" placeholder="Email" />
      <button type="submit">Submit</button>
    </form>
  );

  // Tab through fields
  await user.tab();
  expect(screen.getByPlaceholderText('Name')).toHaveFocus();

  await user.tab();
  expect(screen.getByPlaceholderText('Email')).toHaveFocus();

  await user.tab();
  expect(screen.getByRole('button')).toHaveFocus();

  // Submit with Enter
  await user.keyboard('{Enter}');
  // Form should submit...
});
```

---

## Running Tests

```bash
# Run all tests
npm run test

# Watch mode
npm run test:watch

# Coverage report
npm run test:coverage

# E2E tests
npm run test:e2e

# E2E tests with UI
npm run test:e2e -- --ui
```

---

## Summary

- **Pyramid**: Unit 30% (components, hooks, utils), Integration 60% (features, API), E2E 10% (critical flows).
- **Tools**: Vitest + React Testing Library for unit/integration; Playwright for E2E.
- **Factories**: Use factory functions for test data consistency.
- **MSW**: Mock API responses for offline testing.
- **Coverage**: 70% lines/functions, 65% branches across the codebase.
- **Accessibility**: Test keyboard navigation, ARIA labels, and axe violations.
- **What NOT to test**: Implementation details, snapshots, third-party libraries, CSS.
