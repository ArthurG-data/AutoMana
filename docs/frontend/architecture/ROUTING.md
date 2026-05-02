# Routing & Navigation

## Route Structure Overview

AutoMana uses **React Router v6** with a hierarchical route structure. All routes are defined in a central router configuration, with nested routes creating layout nesting and preserving breadcrumb context.

### Route Tree Diagram

```
/                              (RootLayout)
├── /login                     (LoginPage)
├── /signup                    (SignupPage)
├── /dashboard                 (DashboardLayout)
│   ├── /                      (DashboardHome)
│   ├── /collections           (CollectionsPage)
│   │   ├── /:id               (CollectionDetailPage)
│   │   └── /new               (CollectionFormPage - create)
│   ├── /pricing               (PricingPage)
│   │   ├── /:id/history       (PriceHistoryPage)
│   │   └── /bulk              (BulkPricingPage)
│   ├── /portfolio             (PortfolioPage)
│   │   └── /summary           (PortfolioSummaryPage)
│   ├── /integrations          (IntegrationsPage)
│   │   ├── /ebay              (EbayIntegrationPage)
│   │   ├── /shopify           (ShopifyIntegrationPage)
│   │   └── /settings          (IntegrationSettingsPage)
│   ├── /sync                  (SyncPage)
│   │   └── /history           (SyncHistoryPage)
│   └── /settings              (SettingsPage)
├── /oauth/callback/:provider  (OAuthCallbackPage)
└── *                          (NotFoundPage)
```

### Nesting Hierarchy

**Root Level** (`/`): Authentication gates, error boundaries, global layout
- Routes: `/login`, `/signup`, `/oauth/callback/:provider`

**Dashboard Level** (`/dashboard`): Authenticated user routes with sidebar + header
- Routes: All feature pages under `/dashboard/*`
- Layout: Persistent sidebar, top header, breadcrumbs

**Feature Level** (`/dashboard/collections`, `/dashboard/pricing`): Feature-specific routes
- Routes: List view, detail view, form, sub-features
- Layout: Feature-specific sidebar or tabs (optional)

---

## URL Schema Design

### Route Naming Conventions

1. **Collections/Lists**: Plural nouns (e.g., `/collections`, `/pricing`)
2. **Detail Pages**: `/:id` suffix (e.g., `/collections/42`, `/pricing/mtg-stock-001`)
3. **Forms**: `/new` for create, `/:id/edit` for update
4. **Sub-resources**: `/parent/:parentId/child` (e.g., `/collections/42/cards`)
5. **Actions**: `/bulk` for batch operations, `/history` for audit trails

### Query Parameters Table

| Parameter | Type | Usage | Example |
|-----------|------|-------|---------|
| `sort` | string | Sort field name | `?sort=price` or `?sort=-createdAt` (minus = desc) |
| `order` | `asc` \| `desc` | Sort direction (legacy; prefer `-` prefix) | `?order=desc` |
| `page` | number | Pagination page (1-indexed) | `?page=2` |
| `limit` | number | Results per page | `?limit=25` |
| `search` | string | Full-text search query | `?search=black+lotus` |
| `filter` | string (JSON) | Complex filters (URL-encoded JSON) | `?filter={"rarity":"M","set":"NEO"}` |
| `rarity` | string | Card rarity (chainable filter) | `?rarity=M&rarity=R` |
| `set` | string | Set code (chainable filter) | `?set=NEO&set=MH2` |
| `min-price` | number | Price range lower bound | `?min-price=10.00` |
| `max-price` | number | Price range upper bound | `?max-price=100.00` |
| `tab` | string | Active tab ID | `?tab=details` |
| `view` | string | View mode (grid/list) | `?view=grid` |

### Bookmarkable States

All filterable/sortable views encode state in the URL query string so users can:
- Bookmark filtered views
- Share URLs with others
- Use browser back/forward to navigate filter history

```
/collections?search=lotus&rarity=M&sort=-price&page=1
/pricing?min-price=100&max-price=500&sort=price&view=chart
```

---

## Protected Routes & Auth Guards

### ProtectedRoute Component

Wraps routes that require authentication. Redirects unauthenticated users to `/login` with a `returnTo` param for post-login redirect.

```tsx
// src/features/auth/components/ProtectedRoute.tsx
import { Navigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRole?: string[];
}

export function ProtectedRoute({ children, requiredRole }: ProtectedRouteProps) {
  const { user, loading } = useAuth();

  if (loading) {
    return <Spinner />;
  }

  if (!user) {
    return <Navigate to={`/login?returnTo=${window.location.pathname}`} replace />;
  }

  if (requiredRole && !requiredRole.includes(user.role)) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
}
```

### Auth State Handling

Auth state is managed in Zustand. The `useAuth()` hook exposes `user`, `loading`, and `error`:

```tsx
// src/features/auth/store/auth.ts
import { create } from 'zustand';

interface AuthStore {
  user: User | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  loading: true,
  error: null,

  login: async (email, password) => {
    set({ loading: true });
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      const { user, token } = await response.json();
      localStorage.setItem('authToken', token);
      set({ user, loading: false });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  logout: () => {
    localStorage.removeItem('authToken');
    set({ user: null });
  },
}));

export function useAuth() {
  return useAuthStore((state) => ({
    user: state.user,
    loading: state.loading,
    error: state.error,
  }));
}
```

### Redirect Logic

On app mount, check localStorage for auth token and restore user session:

```tsx
// src/App.tsx
useEffect(() => {
  const restoreSession = async () => {
    const token = localStorage.getItem('authToken');
    if (token) {
      try {
        const response = await fetch('/api/auth/me', {
          headers: { Authorization: `Bearer ${token}` },
        });
        const user = await response.json();
        setUser(user);
      } catch (err) {
        localStorage.removeItem('authToken');
      }
    }
    setLoading(false);
  };

  restoreSession();
}, []);
```

---

## Navigation Patterns

### Link vs useNavigate() Decision Matrix

| Scenario | Tool | Reason |
|----------|------|--------|
| Regular navigation (user clicks) | `<Link>` | Semantic HTML, prefetch hints, accessible |
| Programmatic nav after action | `useNavigate()` | No re-render cycle needed |
| Conditional redirect | `<Navigate>` | Declarative, works in render |
| External URL | `<a href="">` | Browser handles it |
| Deep linking with state | `useNavigate()` + state param | Preserve data without URL |

### Example: Link Component

```tsx
import { Link } from 'react-router-dom';

export function CollectionCard({ card }) {
  return (
    <Link to={`/dashboard/collections/${card.id}`}>
      <div className="card">
        <img src={card.imageUrl} alt={card.name} />
        <h3>{card.name}</h3>
      </div>
    </Link>
  );
}
```

### Example: Programmatic Navigation

```tsx
import { useNavigate } from 'react-router-dom';

export function CollectionForm() {
  const navigate = useNavigate();

  const handleSubmit = async (formData) => {
    const { id } = await api.createCollection(formData);
    navigate(`/dashboard/collections/${id}`);
  };

  return <form onSubmit={handleSubmit}>{/* ... */}</form>;
}
```

### Active Route Styling

Use `useLocation()` to highlight the current nav item:

```tsx
import { useLocation, Link } from 'react-router-dom';

export function Sidebar() {
  const location = useLocation();
  const isActive = (path) => location.pathname.startsWith(path);

  return (
    <nav>
      <Link
        to="/dashboard/collections"
        className={isActive('/dashboard/collections') ? 'active' : ''}
      >
        Collections
      </Link>
      <Link
        to="/dashboard/pricing"
        className={isActive('/dashboard/pricing') ? 'active' : ''}
      >
        Pricing
      </Link>
    </nav>
  );
}
```

### Breadcrumb Patterns

Build breadcrumbs from the current pathname:

```tsx
// src/components/ui/Breadcrumbs.tsx
import { useLocation, Link } from 'react-router-dom';

const routeNames = {
  dashboard: 'Dashboard',
  collections: 'Collections',
  pricing: 'Pricing',
  settings: 'Settings',
};

export function Breadcrumbs() {
  const location = useLocation();
  const segments = location.pathname.split('/').filter(Boolean);

  return (
    <nav className="breadcrumbs">
      <Link to="/dashboard">Home</Link>
      {segments.map((segment, i) => {
        const path = '/' + segments.slice(0, i + 1).join('/');
        const label = routeNames[segment] || segment;
        const isLast = i === segments.length - 1;

        return (
          <span key={segment}>
            <span className="separator">/</span>
            {isLast ? (
              <span>{label}</span>
            ) : (
              <Link to={path}>{label}</Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}
```

---

## Code Splitting & Lazy Loading

### React.lazy() with Suspense

Heavy route components are lazy-loaded to reduce initial bundle size. Each major feature is a separate chunk:

```tsx
// src/App.tsx
import { Suspense, lazy } from 'react';
import { Routes, Route } from 'react-router-dom';
import { Spinner } from './components/ui/Spinner';

// Lazy-loaded route components
const LoginPage = lazy(() => import('./pages/LoginPage'));
const DashboardLayout = lazy(() => import('./layouts/DashboardLayout'));
const CollectionsPage = lazy(() => import('./features/collections/pages/CollectionsPage'));
const PricingPage = lazy(() => import('./features/pricing/pages/PricingPage'));
const SettingsPage = lazy(() => import('./features/settings/pages/SettingsPage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));

export function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/dashboard/*"
          element={
            <ProtectedRoute>
              <DashboardLayout />
            </ProtectedRoute>
          }
        >
          <Route path="collections" element={<CollectionsPage />} />
          <Route path="pricing" element={<PricingPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
```

### Which Routes Are Lazy Loaded and Why

| Route | Lazy | Reason |
|-------|------|--------|
| `/login` | Yes | Only loaded once per session; not on dashboard |
| `/dashboard/*` | Yes | Entire authenticated section; users stay here long |
| `/collections` | Yes | Large feature with charts, forms |
| `/pricing` | Yes | Heavy data visualization components |
| `/settings` | Yes | Low-traffic feature |
| `/not-found` | Yes | Rarely visited |

**Layout components** (`DashboardLayout`, `RootLayout`) are **not lazy** because they load on every dashboard navigation.

### Bundle Analysis

Use `source-map-explorer` to audit bundle size:

```bash
npm run build
npx source-map-explorer 'dist/**/*.js'
```

Target: Keep initial bundle < 100KB (gzipped). Lazy-loaded routes should be < 50KB each.

---

## Deep Linking & State Restoration

### Preserving State Across Refresh

Transient UI state (open modals, active tabs, scroll position) is stored in query params or a Ref; permanent state (filters, search queries) is in the URL.

```tsx
// Good: Filter state in URL
const [filters, setFilters] = useState(() => {
  const params = new URLSearchParams(location.search);
  return {
    rarity: params.get('rarity'),
    minPrice: parseInt(params.get('min-price') || '0'),
  };
});

useEffect(() => {
  const params = new URLSearchParams();
  if (filters.rarity) params.set('rarity', filters.rarity);
  params.set('min-price', filters.minPrice);
  navigate(`?${params.toString()}`, { replace: true });
}, [filters]);

// Bad: Filter state in local state only (lost on refresh)
const [filters, setFilters] = useState({ rarity: null, minPrice: 0 });
```

### Browser History Management

Never manually manipulate `window.history`. React Router handles back/forward correctly via `useNavigate()`:

```tsx
const navigate = useNavigate();

// Go back one page
navigate(-1);

// Go forward one page
navigate(1);

// Navigate with history push (can use back button)
navigate('/path');

// Navigate with history replace (cannot use back button, e.g., redirects)
navigate('/path', { replace: true });
```

### Scroll Position Restoration

By default, React Router does not restore scroll position. Implement a `ScrollToTop` component:

```tsx
// src/components/ScrollToTop.tsx
import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

export function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return null;
}

// In App.tsx
<BrowserRouter>
  <ScrollToTop />
  <Routes>{/* ... */}</Routes>
</BrowserRouter>
```

### Restoring List Scroll Position

For long lists with pagination, save scroll position per route before navigation and restore on return:

```tsx
// src/hooks/useScrollRestoration.ts
import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

const scrollPositions = new Map<string, number>();

export function useScrollRestoration() {
  const location = useLocation();

  useEffect(() => {
    // Restore scroll position on mount
    const savedPosition = scrollPositions.get(location.pathname);
    if (savedPosition !== undefined) {
      window.scrollTo(0, savedPosition);
    }
  }, [location.pathname]);

  return () => {
    // Save scroll position on unmount
    scrollPositions.set(location.pathname, window.scrollY);
  };
}
```

---

## Summary

AutoMana's routing architecture emphasizes:

1. **Clarity**: Nested routes create intuitive URL hierarchies
2. **Performance**: Lazy loading splits code by feature
3. **User Experience**: Query params enable bookmarking and sharing
4. **Accessibility**: Semantic HTML (`<Link>`) and ARIA landmarks
5. **Maintainability**: Centralized route definitions and consistent naming

The URL is the single source of truth for UI state; the store holds domain state. This separation keeps routing concerns separate from data management.
