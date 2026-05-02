# API Integration and Data Fetching

This guide covers HTTP client setup, request/response handling, error management, and data fetching patterns used in the AutoMana React frontend.

## HTTP Client Architecture

### Axios Configuration

The frontend uses **Axios** as the HTTP client for all API communication. A centralized client instance is initialized with sensible defaults:

**File:** `src/utils/api-client.ts`

```typescript
import axios, { AxiosInstance, InternalAxiosRequestConfig, AxiosResponse, AxiosError } from 'axios';

export const createApiClient = (): AxiosInstance => {
  const client = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
    timeout: 30000,
    headers: {
      'Content-Type': 'application/json',
    },
    withCredentials: true, // Include cookies in requests
  });

  return client;
};

export const apiClient = createApiClient();
```

**Configuration Details:**
- **baseURL**: Pulled from environment variables (`VITE_API_BASE_URL`). Defaults to dev server if not set.
- **timeout**: 30 seconds. Requests exceeding this are aborted and trigger error handling.
- **withCredentials**: `true` to automatically include cookies (for session management).
- **Content-Type**: JSON by default for request bodies.

### Dynamic Base URL

For different deployment environments:

```typescript
// .env.development
VITE_API_BASE_URL=http://localhost:8000/api

// .env.production
VITE_API_BASE_URL=https://api.automana.app/api
```

---

## Request/Response Interceptors

Interceptors handle authentication, error categorization, and request logging without repeating code in every component.

### Request Interceptor (Authorization)

```typescript
// src/utils/api-interceptors.ts

import { apiClient } from './api-client';
import { getAuthToken, isTokenExpired } from './auth-storage';

export const setupRequestInterceptor = () => {
  apiClient.interceptors.request.use(
    async (config: InternalAxiosRequestConfig) => {
      const token = getAuthToken();

      if (token) {
        if (isTokenExpired(token)) {
          // Token is stale; trigger refresh
          // (See AUTHENTICATION.md for refresh flow)
          await refreshToken();
        }

        // Attach JWT to Authorization header
        config.headers.Authorization = `Bearer ${getAuthToken()}`;
      }

      // Log request in dev mode
      if (import.meta.env.DEV) {
        console.debug('[API Request]', config.method?.toUpperCase(), config.url, config.data);
      }

      return config;
    },
    (error) => Promise.reject(error)
  );
};
```

### Response Interceptor (Error Handling)

```typescript
export const setupResponseInterceptor = () => {
  apiClient.interceptors.response.use(
    (response: AxiosResponse) => {
      if (import.meta.env.DEV) {
        console.debug('[API Response]', response.status, response.data);
      }
      return response;
    },
    async (error: AxiosError) => {
      // Distinguish between network, client, and server errors
      const categorizedError = categorizeError(error);

      // 401 Unauthorized: token invalid or expired
      if (error.response?.status === 401) {
        // Clear auth state and redirect to login (handled by auth store)
        clearAuthToken();
        window.location.href = '/login';
      }

      // 403 Forbidden: user lacks permission
      if (error.response?.status === 403) {
        console.warn('[API] Access forbidden', error.config?.url);
      }

      // 5xx Server errors: log for monitoring
      if (error.response?.status && error.response.status >= 500) {
        console.error('[API Server Error]', error.response.status, error.response.data);
      }

      return Promise.reject(categorizedError);
    }
  );
};
```

---

## Error Handling Strategy

### Error Categorization

Errors are categorized by type so UI can display appropriate messages and recovery options.

```typescript
// src/utils/error-handler.ts

export enum ErrorCategory {
  NETWORK = 'network',           // No internet, timeout, DNS failure
  CLIENT = 'client',             // 4xx (bad request, auth, validation)
  SERVER = 'server',             // 5xx (internal server error)
  UNKNOWN = 'unknown',           // Parse error, uncaught exception
}

export interface ApiError {
  category: ErrorCategory;
  code: string;                  // e.g. 'VALIDATION_ERROR', 'NOT_FOUND'
  message: string;               // User-friendly message
  details?: Record<string, any>; // Field validation errors, etc.
  statusCode?: number;
  originalError: any;
}

export const categorizeError = (error: any): ApiError => {
  // Timeout or no response (network issue)
  if (error.code === 'ECONNABORTED' || !error.response) {
    return {
      category: ErrorCategory.NETWORK,
      code: 'NETWORK_ERROR',
      message: 'Unable to reach the server. Check your connection and try again.',
      originalError: error,
    };
  }

  // HTTP error response
  if (error.response) {
    const status = error.response.status;
    const data = error.response.data as any;

    if (status >= 400 && status < 500) {
      return {
        category: ErrorCategory.CLIENT,
        code: data?.error_code || `HTTP_${status}`,
        message: data?.message || getClientErrorMessage(status),
        details: data?.details,
        statusCode: status,
        originalError: error,
      };
    }

    if (status >= 500) {
      return {
        category: ErrorCategory.SERVER,
        code: `HTTP_${status}`,
        message: 'Server error. Please try again later.',
        statusCode: status,
        originalError: error,
      };
    }
  }

  // Fallback
  return {
    category: ErrorCategory.UNKNOWN,
    code: 'UNKNOWN_ERROR',
    message: 'An unexpected error occurred.',
    originalError: error,
  };
};

const getClientErrorMessage = (status: number): string => {
  const messages: Record<number, string> = {
    400: 'Invalid request. Please check your input.',
    401: 'Your session has expired. Please log in again.',
    403: 'You do not have permission to perform this action.',
    404: 'The requested resource was not found.',
    409: 'This resource already exists.',
    422: 'Validation failed. Please check your input.',
  };
  return messages[status] || 'Request failed. Please try again.';
};
```

### Using Categorized Errors in Components

```typescript
// src/features/cards/hooks/useSearchCards.ts

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/utils/api-client';
import { categorizeError, ApiError } from '@/utils/error-handler';

export const useSearchCards = (query: string) => {
  const [error, setError] = useState<ApiError | null>(null);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['cards', 'search', query],
    queryFn: async () => {
      try {
        const response = await apiClient.get('/cards/search', {
          params: { q: query },
        });
        setError(null);
        return response.data;
      } catch (err) {
        const apiError = categorizeError(err);
        setError(apiError);
        throw apiError;
      }
    },
    enabled: query.length > 2,
  });

  return { data, isLoading, error, refetch };
};
```

---

## Data Fetching Patterns

### Component-Level Fetching with React Query

For simple, component-specific data:

```typescript
// src/features/dashboard/Dashboard.tsx

import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/utils/api-client';

function Dashboard() {
  const { data: stats, isLoading, error } = useQuery({
    queryKey: ['dashboard', 'stats'],
    queryFn: async () => {
      const res = await apiClient.get('/dashboard/stats');
      return res.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  if (isLoading) return <DashboardSkeleton />;
  if (error) return <ErrorBanner error={error} />;

  return <DashboardContent stats={stats} />;
}
```

### Store-Level Fetching (Zustand)

For global state that multiple components consume:

```typescript
// src/stores/collectionStore.ts

import { create } from 'zustand';
import { apiClient } from '@/utils/api-client';

interface CollectionStore {
  cards: Card[];
  isLoading: boolean;
  error: ApiError | null;
  fetchCards: () => Promise<void>;
}

export const useCollectionStore = create<CollectionStore>((set) => ({
  cards: [],
  isLoading: false,
  error: null,

  fetchCards: async () => {
    set({ isLoading: true, error: null });
    try {
      const res = await apiClient.get('/collections/my-cards');
      set({ cards: res.data.cards, isLoading: false });
    } catch (err) {
      const apiError = categorizeError(err);
      set({ error: apiError, isLoading: false });
    }
  },
}));
```

---

## Caching & Cache Invalidation

React Query manages request caching and deduplication automatically.

### Cache Configuration

```typescript
// src/utils/react-query-config.ts

import { DefaultOptions, QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,      // Data is fresh for 5 minutes
      gcTime: 10 * 60 * 1000,        // Keep in cache for 10 minutes (was cacheTime in v4)
      retry: 1,                       // Retry failed requests once
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
    },
    mutations: {
      retry: 0,                       // Don't retry mutations
    },
  } as DefaultOptions,
});
```

### Manual Cache Invalidation

After mutations (POST/PUT/DELETE), invalidate affected queries:

```typescript
// src/features/cards/hooks/useUpdateCard.ts

import { useMutation } from '@tanstack/react-query';
import { queryClient } from '@/utils/react-query-config';
import { apiClient } from '@/utils/api-client';

export const useUpdateCard = () => {
  return useMutation({
    mutationFn: async (cardData: UpdateCardRequest) => {
      const res = await apiClient.put(`/cards/${cardData.id}`, cardData);
      return res.data;
    },
    onSuccess: (data) => {
      // Invalidate the specific card
      queryClient.invalidateQueries({
        queryKey: ['cards', data.id],
      });

      // Invalidate the collection list (to update counts)
      queryClient.invalidateQueries({
        queryKey: ['collections'],
      });

      // Show success toast
      toast.success('Card updated successfully');
    },
    onError: (error) => {
      const apiError = categorizeError(error);
      toast.error(apiError.message);
    },
  });
};
```

---

## Loading States & Skeletons

Use skeleton screens during data fetch to provide visual continuity:

```typescript
// src/components/CardListSkeleton.tsx

export function CardListSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="space-y-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="flex gap-4 animate-pulse">
          <div className="w-16 h-24 bg-gray-300 rounded" />
          <div className="flex-1 space-y-2">
            <div className="h-4 bg-gray-300 rounded w-3/4" />
            <div className="h-3 bg-gray-300 rounded w-1/2" />
          </div>
        </div>
      ))}
    </div>
  );
}
```

Use skeletons while `isLoading` is true:

```typescript
function CardList() {
  const { data: cards, isLoading } = useQuery({
    queryKey: ['cards'],
    queryFn: () => apiClient.get('/cards').then(r => r.data),
  });

  if (isLoading) return <CardListSkeleton count={10} />;

  return (
    <div>
      {cards.map(card => (
        <CardItem key={card.id} card={card} />
      ))}
    </div>
  );
}
```

---

## Optimistic Updates

Show local changes immediately while the server request is in flight:

```typescript
// src/features/cards/hooks/useToggleFavorite.ts

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/utils/api-client';

export const useToggleFavorite = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (cardId: string) =>
      apiClient.post(`/cards/${cardId}/favorite`),

    // Update UI before server responds
    onMutate: async (cardId) => {
      // Cancel ongoing queries for this card
      await queryClient.cancelQueries({ queryKey: ['cards', cardId] });

      // Get current data
      const previousData = queryClient.getQueryData(['cards', cardId]);

      // Optimistically update
      queryClient.setQueryData(['cards', cardId], (old: any) => ({
        ...old,
        is_favorited: !old.is_favorited,
      }));

      // Return a context to rollback if mutation fails
      return { previousData };
    },

    onError: (err, cardId, context) => {
      // Rollback on error
      if (context?.previousData) {
        queryClient.setQueryData(['cards', cardId], context.previousData);
      }
    },

    onSuccess: (data, cardId) => {
      // Optionally refetch to ensure consistency
      queryClient.setQueryData(['cards', cardId], data);
    },
  });
};
```

Usage in component:

```typescript
function CardFavoriteButton({ cardId, isFavorited }: Props) {
  const mutation = useToggleFavorite();
  const optimisticFavorited = !isFavorited; // Assume local state

  return (
    <button
      onClick={() => mutation.mutate(cardId)}
      disabled={mutation.isPending}
      className={optimisticFavorited ? 'text-red-500' : 'text-gray-400'}
    >
      ♥ {mutation.isPending ? 'Saving...' : 'Favorite'}
    </button>
  );
}
```

---

## Mock Data & MSW Setup

For testing and local development without a real server, use **Mock Service Worker (MSW)**.

### MSW Handler Definition

**File:** `src/mocks/handlers.ts`

```typescript
import { http, HttpResponse } from 'msw';

export const handlers = [
  // GET /api/cards/search?q=...
  http.get('http://localhost:8000/api/cards/search', ({ request }) => {
    const url = new URL(request.url);
    const query = url.searchParams.get('q') || '';

    return HttpResponse.json({
      cards: [
        {
          id: '1',
          name: `Card matching "${query}"`,
          mana_cost: '{2}{U}',
          rarity: 'rare',
        },
      ],
    });
  }),

  // POST /api/cards/:id/favorite
  http.post('http://localhost:8000/api/cards/:id/favorite', async ({ params }) => {
    return HttpResponse.json({
      id: params.id,
      is_favorited: true,
    });
  }),

  // Catch-all for unmatched requests (log and pass through in dev)
  http.all('*', ({ request }) => {
    console.warn('[MSW] Unmatched request:', request.method, request.url);
    return HttpResponse.json({ error: 'Not mocked' }, { status: 501 });
  }),
];
```

### MSW Server Setup (Browser)

```typescript
// src/mocks/browser.ts

import { setupWorker } from 'msw/browser';
import { handlers } from './handlers';

export const worker = setupWorker(...handlers);
```

### Initialize in Dev

```typescript
// src/main.tsx

import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

// Only enable MSW in development
if (import.meta.env.DEV) {
  const { worker } = await import('./mocks/browser');
  await worker.start();
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

### Using Mock Data in Tests

```typescript
// src/features/cards/__tests__/CardSearch.test.tsx

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { setupServer } from 'msw/node';
import { handlers } from '@/mocks/handlers';
import { CardSearch } from '../CardSearch';

const server = setupServer(...handlers);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

test('searches cards by name', async () => {
  const user = userEvent.setup();
  render(<CardSearch />);

  const input = screen.getByPlaceholderText(/search cards/i);
  await user.type(input, 'Blue{Backspace}Print');

  await waitFor(() => {
    expect(screen.getByText(/card matching "Blue Print"/i)).toBeInTheDocument();
  });
});
```

---

## Summary

- **HTTP Client**: Axios with centralized configuration and interceptors.
- **Error Handling**: Categorize errors by type for appropriate UI feedback.
- **Data Fetching**: Use React Query for component-level, Zustand for global state.
- **Caching**: React Query handles deduplication; manually invalidate after mutations.
- **Optimistic Updates**: Show local changes before server confirmation.
- **Mock Data**: MSW for testing and offline development.
