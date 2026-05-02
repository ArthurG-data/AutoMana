# automana Frontend Design Spec

_Date: 2026-05-02_

## Overview

A single-page React application (SPA) that provides the automana MTG finance dashboard. The backend is the existing FastAPI service. The frontend is greenfield — no existing React code in the repo.

---

## Tech Stack

| Concern | Choice | Rationale |
|---|---|---|
| Build tool | Vite 5 | Fast HMR, native ESM |
| Framework | React 18 + TypeScript | |
| Routing | TanStack Router (file-based) | Type-safe route params and loaders |
| Server state | TanStack Query v5 | Caching, background refetch, optimistic updates |
| Tables | TanStack Table v8 + `@tanstack/react-virtual` | 8–9 column tables with sort/filter; virtualize when >200 rows |
| Client state | Zustand | Thin store: auth token, theme, UI state |
| Styling | CSS Modules + CSS custom properties | Zero runtime overhead; 2-theme switching via `data-theme` attribute |
| Charts | Hand-rolled SVG | `Sparkline` (~40 lines) and `AreaChart` (~60 lines) — no charting library |

---

## Folder Structure

```
automana-frontend/
└── src/
    ├── features/
    │   ├── cards/
    │   │   ├── api.ts           # useCardSearch, useCard (TQ hooks)
    │   │   ├── components/      # CardDetail, SearchResults, SearchFilters
    │   │   └── types.ts
    │   ├── collection/
    │   │   ├── api.ts           # useCollection, useCollectionHoldings
    │   │   ├── components/      # CollectionTable, ListingStatusSidebar
    │   │   └── types.ts
    │   └── listings/
    │       ├── api.ts           # useListings, useListing, useCreateListing, useApplyStrategy
    │       ├── components/      # ListingsTable, ListingDetail, NewListingFlow, StrategyTable
    │       └── types.ts
    ├── components/
    │   ├── design-system/       # Icon, Pip, Sparkline, AreaChart, CardArt, AIBadge, PriceBand
    │   ├── layout/              # AppShell, Sidebar, TopBar, AttentionChip
    │   └── ui/                  # Panel, Button, Chip, Toggle, Step, Sep
    ├── lib/
    │   ├── apiClient.ts         # base fetch wrapper — injects auth token, handles 401
    │   └── queryClient.ts       # TanStack Query client with global retry/error config
    ├── routes/
    │   ├── __root.tsx           # root layout: public shell or authed app shell
    │   ├── index.tsx            # Landing
    │   ├── login.tsx            # Login (auth stubbed)
    │   ├── search.tsx           # Search
    │   ├── cards.$id.tsx        # Card Detail
    │   ├── collection.tsx       # Collection vault
    │   └── listings/
    │       ├── index.tsx        # Listings Overview
    │       ├── $id.tsx          # Listing Detail + strategy advisor
    │       └── new.tsx          # New Listing stepper
    ├── store/
    │   ├── auth.ts              # token, currentUser, login, logout
    │   └── ui.ts                # theme ("dark" | "light")
    └── styles/
        ├── tokens.css           # :root dark tokens + [data-theme="light"] overrides
        └── global.css           # @fontsource imports, CSS reset
```

Routes are thin shells: they wire loaders and call `queryClient.ensureQueryData`; all logic lives in `features/`. Features never import from each other.

---

## Design System

### Themes

Two themes: **Deep Sea** (dark, default) and **Arctic** (light). Switching writes `document.documentElement.dataset.theme`; Zustand persists to `localStorage` and initialises from `matchMedia('(prefers-color-scheme: light)')`.

**Dark tokens (`:root`):**

```css
--hd-bg: #080f1e;
--hd-surface: #0f1830;
--hd-surface-alt: #152040;
--hd-border: rgba(150, 200, 255, 0.14);
--hd-text: #e8efff;
--hd-muted: #8e9fc4;
--hd-sub: #4d5b80;
--hd-accent: #3de8d2;        /* nudged from #34d8c4 for WCAG AA compliance */
--hd-blue: #7aa6ff;
--hd-red: #e35e6c;
--hd-amber: #e0a96a;
--hd-shadow: 0 20px 60px rgba(0, 0, 0, 0.45);
```

**Light overrides (`[data-theme="light"]`):**

```css
--hd-bg: #eef4f8;
--hd-surface: #ffffff;
--hd-surface-alt: #f5f9fc;
--hd-border: rgba(20, 50, 80, 0.12);
--hd-text: #0c1a25;
--hd-muted: #506576;
--hd-sub: #8898a6;
--hd-accent: #00b380;
--hd-blue: #2b80c8;
```

### Typography

```css
--font-serif: 'Fraunces', serif;         /* headlines, large numbers */
--font-sans:  'Space Grotesk', 'Inter', sans-serif;  /* body, labels */
--font-mono:  'JetBrains Mono', monospace;           /* prices, IDs, metadata */
```

Loaded via `@fontsource/fraunces`, `@fontsource/space-grotesk`, `@fontsource/jetbrains-mono`.

### AIBadge — 3-group model (UX revision)

The original 9 states are preserved internally but exposed to the user in 3 groups. The table row shows only the group icon; hovering/focusing expands to the specific state label.

| Group | States | Color token |
|---|---|---|
| Needs action | `over`, `under`, `stale`, `revised` | `--hd-red` / `--hd-amber` / `--hd-blue` |
| Monitoring | `watching`, `ready` | `--hd-blue` / `--hd-accent` |
| Settled | `ok`, `listed`, `vault` | `--hd-accent` / `--hd-amber` / `--hd-sub` |

TypeScript type:
```ts
type AIStatus = 'ok' | 'over' | 'under' | 'revised' | 'stale'
              | 'ready' | 'watching' | 'listed' | 'vault';
```

All rendering logic (icon, color, label) lives in an exhaustive `switch` — compile-time coverage guarantee.

### PriceBand (UX revision)

Shows p25 / median / p75 by default. Low and high markers are rendered in the DOM but visually hidden; they appear on `hover` / `focus-within` via CSS. The "your price" dot and label always show.

### Other design-system components

| Component | Source file | Notes |
|---|---|---|
| `Icon` | `shared.jsx` | Port as-is; 20+ SVG glyphs keyed by `kind` string |
| `Pip` | `shared.jsx` | WUBRG mana pips — W/U/B/R/G/C |
| `Sparkline` | `shared.jsx` | Pure SVG path; props: `points`, `color`, `fill` |
| `AreaChart` | `shared.jsx` | Larger area chart for card detail and portfolio |
| `CardArt` | `shared.jsx` | Deterministic striped placeholder |
| `Toggle` | `page-listings-wf.jsx` | Simple CSS toggle |
| `Step` / `Sep` | `page-listings-wf.jsx` | Stepper indicators for New Listing flow |

---

## Pages

### Phase 1 — Core shell

**Landing** (`/`): Public. Hero search bar, "Track every card. Price the market." headline, 3 feature tiles. No auth required.

**Login** (`/login`): Split layout — marketing left panel, form right. Google / Apple / Discord social buttons + email+password form. Auth calls are **stubbed**: `useAuthStore.getState().login(hardcodedToken)` until the backend ships endpoints.

**Search** (`/search?q=`): Filter sidebar (set, rarity, finish, artist, price range) + card grid. Calls `GET /api/v1/cards/search`. TanStack Router search param schema validates `q`, `set`, `rarity`, `finish`, `minPrice`, `maxPrice`.

**Card Detail** (`/cards/:id`): Card art + price history area chart + print/finish selector chips + add to collection / watch / set alert CTAs. Calls `GET /api/v1/cards/:id`.

### Phase 2 — Portfolio

**Collection** (`/collection`): 5 metric tiles + **attention chip** in TopBar ("N cards ready to list" → highlights rows) + table with AI listing-status icons per row (grouped AIBadge). Sidebar: listing-status legend, ready-to-list panel (List now / Snooze per card), WUBRG color split. Calls `GET /api/v1/collection`.

The banner-style AI advisor is **removed** (UX revision). Replaced by:
- `AttentionChip` in the TopBar: compact chip showing count of actionable items
- Highlighted table rows for `ready` and `needs-action` groups

### Phase 3 — eBay Manager

**Listings Overview** (`/listings`): 5 metric tiles + attention chip + TanStack Table with Active / Sold / Saved / Drafts tabs. Columns: status bar, card + thumbnail, strategy pill, listed price, market price, watchers/days, AIBadge. Calls `GET /api/v1/listings`.

**Listing Detail** (`/listings/:id`): 3-column layout — card identity + metadata (left), strategy advisor (centre), payout projection + auto-revise rules (right). Strategy advisor uses a **comparison table** (UX revision): strategies as columns (Quick sale, Balanced, Max return, Auction 7d, Auction + reserve), attributes as rows (recommended price, delta from market, estimated days, payout after fees). Calls `GET /api/v1/listings/:id`.

**New Listing** (`/listings/new`): 4-step stepper (Card → Condition → Strategy → Review & post). Step 3 uses the same strategy comparison table. Sticky market context sidebar (median sold, PriceBand, live competition, reprint risk). Calls `POST /api/v1/listings`.

---

## Data Flow

```
React Route (loader)
  └─ queryClient.ensureQueryData(featureQuery)
       └─ feature api.ts (TQ hook)
            └─ lib/apiClient.ts
                 ├─ reads useAuthStore.getState().token (sync)
                 ├─ injects Authorization: Bearer <token>
                 └─ fetch → FastAPI :8000/api/v1/...
```

`queryClient` global config (TQ v5 — global error handling via `MutationCache` and `QueryCache`):
```ts
new QueryClient({
  queryCache: new QueryCache({
    onError: (err) => {
      if ((err as ApiError).status === 401) useAuthStore.getState().logout();
    },
  }),
  mutationCache: new MutationCache({
    onError: (err) => {
      if ((err as ApiError).status === 401) useAuthStore.getState().logout();
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (count, err) => (err as ApiError).status !== 401 && count < 2,
    },
  },
})
```

### FastAPI endpoints consumed (Phase 1–3)

| Method | Path | Feature |
|---|---|---|
| GET | `/api/v1/cards/search` | Search |
| GET | `/api/v1/cards/:id` | Card Detail |
| GET | `/api/v1/collection` | Collection |
| GET | `/api/v1/listings` | Listings Overview |
| GET | `/api/v1/listings/:id` | Listing Detail |
| POST | `/api/v1/listings` | New Listing |
| PATCH | `/api/v1/listings/:id` | Apply strategy / auto-revise |
| POST | `/api/v1/auth/login` | Login (**stubbed until backend ships**) |

---

## Auth Stub Contract

Until the backend team ships auth, the following stub is used:

```ts
// store/auth.ts
const STUB_TOKEN = 'dev-stub-token';

export const useAuthStore = create()(persist((set) => ({
  token: STUB_TOKEN,
  currentUser: { id: 'dev', email: 'dev@automana.local' },
  login: (token: string) => set({ token }),
  logout: () => set({ token: null, currentUser: null }),
}), { name: 'automana-auth' }));
```

When real auth lands: replace `STUB_TOKEN` with the actual login flow in `login.tsx`. `apiClient.ts` and all TQ hooks require zero changes.

---

## Error Handling

- Network / 5xx errors: TQ retries twice, then surfaces an inline error state per query (not a global toast, so the rest of the page stays usable).
- 401: global `onError` fires `logout()` → TanStack Router redirects to `/login`.
- 404 on card/listing: route loader throws, caught by TanStack Router error boundary, renders a "not found" panel.
- Empty states: each table/list has a defined empty state component (not a blank div).

---

## Testing

- **Component tests**: Vitest + React Testing Library. Design-system primitives (`Icon`, `Pip`, `AIBadge`) get unit tests; exhaustive `switch` coverage verified at the type level.
- **Feature tests**: mock `apiClient` at the module boundary (not `fetch`). Test TQ hooks with `renderHook` + `QueryClientProvider`.
- **E2E**: Playwright for the 3 critical flows: Search → Card Detail, Add to Collection, Create Listing with strategy.

---

## Implementation Phases

| Phase | Pages | Key dependencies |
|---|---|---|
| 1 | Landing, Login (stub), Search, Card Detail | Design system, `apiClient`, `GET /cards/*` |
| 2 | Collection | `GET /collection`, AIBadge 3-group model, TanStack Table |
| 3 | Listings Overview, Listing Detail, New Listing Flow | `GET/POST/PATCH /listings`, StrategyTable, PriceBand, stepper |

Each phase ships as a PR. Phase 1 can be built without a running FastAPI instance (MSW for mocks).

---

## Open Dependencies

- **Auth endpoints** — design owned by backend team. Frontend ships stub in Phase 1; wires real endpoints when available.
- **AI advisor API** — the `ai.kind` field on listings and collection holdings must be returned by FastAPI. Frontend consumes it; backend computes it.
- **Card art** — `CardArt` currently renders a striped placeholder. Replace with Scryfall image URLs once `GET /api/v1/cards/:id` returns `image_uri`.
