# Component Architecture & Design System

## Component Organization Philosophy

The AutoMana frontend uses a **feature-based component organization** rather than atomic design. This structure collocates all code related to a feature—components, hooks, stores, tests, and utilities—into a single directory, making features self-contained and easier to maintain, refactor, or remove.

### Why Feature-Based Organization?

1. **Colocation**: Related code lives together, reducing cognitive load during feature development
2. **Encapsulation**: Feature-specific components and logic don't leak into other features
3. **Easier to maintain**: Changes to a feature are isolated to a single directory tree
4. **Natural scaling**: New developers can understand a feature by exploring one folder
5. **Clear boundaries**: Prevents the "atomic design" trap of deeply nested component hierarchies

### Why Not Atomic Design?

Atomic design (atoms → molecules → organisms → templates → pages) introduces unnecessary indirection. A "Button" atom lives in `components/ui/`, but a "CardSearch" molecule might live in `features/pricing/components/`. This mixed approach adds cognitive overhead: you must know whether a component is "pure UI" or "feature-specific" to locate it.

**AutoMana's approach**: Pure, reusable UI components live in `src/components/ui/`. Everything else—container components, feature-specific layouts, business logic—lives in the feature folder.

### Example Directory Structure

```
src/
  components/
    ui/
      Button/
        Button.tsx
        Button.test.tsx
        Button.stories.tsx
      Input/
        Input.tsx
        Input.test.tsx
      Select/
      Modal/
      Tabs/
      Pagination/
  features/
    collections/
      components/
        CollectionList.tsx           # Container: fetches data, manages filters
        CollectionListFilters.tsx    # Presentational: renders filter UI
        CollectionCard.tsx           # Presentational: renders a single card
        CollectionForm.tsx           # Container: form submission logic
      hooks/
        useCollections.ts            # Custom hook: fetch and cache logic
        useCollectionFilters.ts      # Custom hook: filter state and URL sync
      store/
        collections.ts               # Zustand store: global collection state
      services/
        collectionApi.ts             # API call helpers
      types/
        index.ts                     # Feature-specific types
      CollectionsPage.tsx            # Route-level container
    pricing/
      components/
        PricingTable.tsx
        PriceHistoryChart.tsx
      hooks/
        usePricing.ts
      store/
        pricing.ts
      PricingPage.tsx
    auth/
      components/
        LoginForm.tsx
        ProtectedRoute.tsx
      hooks/
        useAuth.ts
      store/
        auth.ts
```

---

## Shared UI Component Library (src/components/ui/)

The shared UI library provides reusable, unstyled, accessible components that have no business logic or feature knowledge. These are the atomic building blocks.

### Purpose

- **Accessibility first**: All components meet WCAG 2.1 AA standards
- **Unstyled by default**: Styled with CSS modules or Tailwind utility classes, not hardcoded colors
- **Composable**: Used by both feature components and page layouts
- **Testable**: Each component has unit tests covering keyboard navigation, ARIA attributes, and rendering

### Component Inventory

| Component | Purpose | Props | Notes |
|-----------|---------|-------|-------|
| `Button` | Clickable action trigger | `variant`, `size`, `disabled`, `onClick` | Supports loading state |
| `Input` | Text, email, password, number fields | `type`, `value`, `onChange`, `placeholder`, `error` | Integrates with error display |
| `Select` | Dropdown option selection | `options`, `value`, `onChange`, `multiple` | Keyboard accessible |
| `Checkbox` | Single boolean toggle | `checked`, `onChange`, `label` | With label included |
| `Radio` | Mutually exclusive options | `options`, `value`, `onChange` | Grouped with fieldset |
| `Modal` | Dialog box overlay | `open`, `onClose`, `title`, `children` | Focus trap included |
| `Tabs` | Tabbed content navigation | `tabs[]`, `activeTab`, `onChange` | Arrow key navigation |
| `Pagination` | Page navigation for lists | `total`, `page`, `pageSize`, `onChange` | Displays "Page X of Y" |
| `Card` | Bordered content container | `children`, `variant` | Consistent spacing |
| `Badge` | Status label | `variant`, `children` | For chips and labels |
| `Spinner` | Loading indicator | `size`, `variant` | Animated SVG |
| `Toast` | Notification popup | `message`, `type`, `onClose`, `duration` | Auto-dismiss option |

### Component API Consistency Rules

1. **Naming**: Props use camelCase. Event handlers are `onAction` (e.g., `onClick`, `onChange`, `onSubmit`).
2. **Sizing**: `size` prop uses `"sm" | "md" | "lg"` for consistency.
3. **Variants**: Visual variations use `variant` prop (e.g., `variant="primary" | "secondary" | "danger"`).
4. **Disabled state**: All interactive components support `disabled` boolean prop.
5. **Aria labels**: Components with text-less variants (icon buttons) require `aria-label` prop.

### Example: Button Component

```tsx
// src/components/ui/Button/Button.tsx
import React from 'react';
import styles from './Button.module.css';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
  children: React.ReactNode;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', isLoading, className, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={`${styles.button} ${styles[variant]} ${styles[size]} ${isLoading ? styles.loading : ''} ${className || ''}`}
        disabled={isLoading || props.disabled}
        {...props}
      >
        {isLoading && <span className={styles.spinner} />}
        {props.children}
      </button>
    );
  }
);

Button.displayName = 'Button';
```

---

## Feature-Specific Components

Feature components live in `src/features/{featureName}/components/` and follow two primary patterns:

### Container + Presentational Pattern

**Container components** (suffixed with nothing or "Container"):
- Fetch data via hooks or props
- Manage local state (filters, pagination, sorting)
- Connect to global state (Zustand store)
- Handle side effects (API calls, logging)
- Pass data and callbacks to presentational components

**Presentational components** (no suffix):
- Pure functions that render UI based on props
- No data fetching or async logic
- Easy to test: pass in props, check output
- Reusable across features if generic enough

```tsx
// Container: CollectionList.tsx
import { useEffect, useState } from 'react';
import { useCollections } from '../hooks/useCollections';
import { CollectionListFilters } from './CollectionListFilters';
import { CollectionCard } from './CollectionCard';

export function CollectionList() {
  const { collections, loading, error } = useCollections();
  const [filters, setFilters] = useState({ rarity: null, set: null });

  const filtered = collections.filter(c => {
    if (filters.rarity && c.rarity !== filters.rarity) return false;
    if (filters.set && c.setCode !== filters.set) return false;
    return true;
  });

  if (loading) return <Spinner />;
  if (error) return <div>Error: {error.message}</div>;

  return (
    <div>
      <CollectionListFilters filters={filters} onChange={setFilters} />
      <div className="grid">
        {filtered.map(card => (
          <CollectionCard key={card.id} card={card} />
        ))}
      </div>
    </div>
  );
}

// Presentational: CollectionCard.tsx
export function CollectionCard({ card }) {
  return (
    <div className="card">
      <img src={card.imageUrl} alt={card.name} />
      <h3>{card.name}</h3>
      <p>{card.rarity} • {card.set}</p>
      <p className="price">${card.currentPrice}</p>
    </div>
  );
}
```

### Custom Hook Pattern

Complex state logic is extracted into custom hooks, keeping components lean and testable.

```tsx
// hooks/useCollections.ts
import { useEffect, useState } from 'react';
import { useCollectionsStore } from '../store/collections';
import { collectionApi } from '../services/collectionApi';

export function useCollections() {
  const { collections, setCollections, error, setError } = useCollectionsStore();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchCollections = async () => {
      try {
        setLoading(true);
        const data = await collectionApi.list();
        setCollections(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    if (collections.length === 0) {
      fetchCollections();
    }
  }, []);

  return { collections, loading, error };
}
```

---

## Design System & Tokens

### Color Palette

| Token | Value | Usage |
|-------|-------|-------|
| `--color-primary` | `#2563eb` (blue-600) | CTAs, active states, links |
| `--color-secondary` | `#64748b` (slate-500) | Secondary buttons, labels |
| `--color-success` | `#10b981` (emerald-500) | Success messages, positive actions |
| `--color-danger` | `#ef4444` (red-500) | Errors, delete actions |
| `--color-warning` | `#f59e0b` (amber-500) | Warnings, alerts |
| `--color-neutral-bg` | `#ffffff` | Page background |
| `--color-neutral-surface` | `#f8fafc` (slate-50) | Cards, panels |
| `--color-neutral-border` | `#e2e8f0` (slate-200) | Dividers, outlines |
| `--color-text-primary` | `#1e293b` (slate-800) | Body text |
| `--color-text-secondary` | `#64748b` (slate-500) | Helper text, captions |

**Rationale**: Neutral tones reduce cognitive load; primary blue matches MTG brand colors; semantic colors (success, danger) are familiar to users.

### Typography Scale

```css
--font-size-xs: 0.75rem;     /* 12px */
--font-size-sm: 0.875rem;    /* 14px */
--font-size-base: 1rem;      /* 16px */
--font-size-lg: 1.125rem;    /* 18px */
--font-size-xl: 1.25rem;     /* 20px */
--font-size-2xl: 1.5rem;     /* 24px */
--font-size-3xl: 1.875rem;   /* 30px */

--font-weight-regular: 400;
--font-weight-medium: 500;
--font-weight-semibold: 600;
--font-weight-bold: 700;
```

**Line height**: 1.5 for body text, 1.2 for headings. Line length: max 65ch for readability.

### Spacing Grid

Based on 4px base unit:

```css
--space-1: 0.25rem;   /* 4px */
--space-2: 0.5rem;    /* 8px */
--space-3: 0.75rem;   /* 12px */
--space-4: 1rem;      /* 16px */
--space-6: 1.5rem;    /* 24px */
--space-8: 2rem;      /* 32px */
--space-12: 3rem;     /* 48px */
```

Use consistently for padding, margins, gaps. Example: card padding is `--space-6`, button padding is `--space-3 --space-4`.

### CSS-in-JS vs CSS Modules Approach

**AutoMana uses CSS Modules** for two reasons:

1. **No runtime overhead**: CSS is extracted at build time, resulting in faster hydration
2. **Type safety** (optional): Tools like `typed-css-modules` provide autocomplete
3. **Colocation**: Each component's styles live in `.module.css` next to the component

**Example**:

```tsx
// Button.tsx
import styles from './Button.module.css';

<button className={styles.primary}>Click me</button>
```

```css
/* Button.module.css */
.primary {
  background-color: var(--color-primary);
  color: white;
  padding: var(--space-3) var(--space-4);
  border-radius: 0.375rem;
}

.primary:hover {
  filter: brightness(1.1);
}
```

**When to break the rule**: Heavy dynamic styling (theming, real-time computed values) may use CSS-in-JS libraries like `styled-components` or `Tailwind`, but prefer CSS variables first.

---

## Component Testing Patterns

### Unit Testing with React Testing Library

Test **behavior**, not implementation. Query elements by role, label, or text, not by CSS class.

```tsx
// Button.test.tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button } from './Button';

describe('Button', () => {
  it('renders with text', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole('button', { name: /click me/i })).toBeInTheDocument();
  });

  it('calls onClick handler when clicked', async () => {
    const handleClick = jest.fn();
    render(<Button onClick={handleClick}>Click me</Button>);
    await userEvent.click(screen.getByRole('button'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('disables button when loading', () => {
    render(<Button isLoading>Click me</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });
});
```

### Component Composition Testing

Test container + presentational pairs together to ensure data flows correctly:

```tsx
// CollectionList.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import { CollectionList } from './CollectionList';
import * as collectionApi from '../services/collectionApi';

jest.mock('../services/collectionApi');

describe('CollectionList', () => {
  it('renders collections after loading', async () => {
    collectionApi.list.mockResolvedValue([
      { id: 1, name: 'Black Lotus', price: 1000 }
    ]);

    render(<CollectionList />);
    
    expect(screen.getByRole('status', { hidden: true })).toBeInTheDocument();
    
    await waitFor(() => {
      expect(screen.getByText('Black Lotus')).toBeInTheDocument();
    });
  });
});
```

### Snapshot Testing (Sparing Use)

Use snapshots only for complex, stable components (charts, layouts). Update snapshots deliberately, not reflexively.

```tsx
it('renders the pricing table', () => {
  const { container } = render(<PricingTable data={mockData} />);
  expect(container).toMatchSnapshot();
});
```

---

## Performance Considerations

### React.memo() Strategy

Use `React.memo()` only when:
- Component is **expensive to render** (complex DOM, expensive computations)
- **Props rarely change** (stable parent)
- **Props are primitive or stable objects** (not inline objects/functions)

```tsx
// DO: Memoize expensive list item
const PricingRow = React.memo(({ price, cardName, lastUpdate }) => (
  <tr>
    <td>{cardName}</td>
    <td>${price}</td>
    <td>{lastUpdate}</td>
  </tr>
));

// DON'T: Memoize trivial component
const Badge = React.memo(({ label }) => <span>{label}</span>);
```

**Correct memoization**:
```tsx
// Parent passes stable callback via useCallback
const CollectionList = () => {
  const handleCardClick = useCallback((id) => {
    navigate(`/collections/${id}`);
  }, [navigate]);

  return cards.map(card => (
    <CollectionCard key={card.id} card={card} onClick={handleCardClick} />
  ));
};

const CollectionCard = React.memo(({ card, onClick }) => (
  <div onClick={() => onClick(card.id)}>{card.name}</div>
));
```

### Code Splitting for Large Components

Use `React.lazy()` with `Suspense` for route-level and heavy feature components:

```tsx
// App.tsx
import { Suspense, lazy } from 'react';
import { Spinner } from './components/ui/Spinner';

const PricingPage = lazy(() => import('./features/pricing/PricingPage'));
const CollectionsPage = lazy(() => import('./features/collections/CollectionsPage'));

export function App() {
  return (
    <Routes>
      <Route
        path="/pricing"
        element={
          <Suspense fallback={<Spinner />}>
            <PricingPage />
          </Suspense>
        }
      />
    </Routes>
  );
}
```

### Image Optimization

- Use `<img>` with `srcSet` for responsive images
- Lazy load images below the fold with `loading="lazy"`
- Serve images in modern formats (WebP with JPEG fallback)

```tsx
<img
  src="card.jpeg"
  srcSet="card-sm.jpeg 500w, card-lg.jpeg 1000w"
  sizes="(max-width: 600px) 500px, 1000px"
  alt="Card name"
  loading="lazy"
/>
```

---

## Summary

AutoMana's component architecture prioritizes **clarity over cleverness**: feature-based organization, thin presentational components, and minimal abstraction. The shared UI library provides a consistent, accessible foundation. Design tokens ensure visual consistency without runtime overhead. Testing focuses on behavior and composition, not implementation details.
