# Authentication & Authorization

This guide covers session/token management, protected routes, role-based access control, and security considerations in the AutoMana frontend.

## Authentication Flow

### Sequence Diagram: Login → Token Refresh → Logout

```
User                    Frontend              Backend
  │                        │                     │
  ├─ Enter credentials ────→│                     │
  │                        │─ POST /auth/login ──→│
  │                        │                   (bcrypt verify)
  │                        │←─ {access, refresh} ─│
  │                        │ (store in localStorage)
  │                        │                     │
  ├─ Request protected ──→ │                     │
  │   resource             │─ GET /cards ────────→│
  │                        │ (+ Bearer access)   │
  │                        │← {cards} ────────────│
  │                        │                     │
  │                    [5 min later]            │
  │                        │                     │
  ├─ Request protected ──→ │                     │
  │   resource             │─ GET /dashboard ───→│
  │                        │ (+ Bearer access)   │
  │                        │← 401 Unauthorized ──│
  │                        │ (token expired)     │
  │                        │                     │
  │                        │─ POST /auth/refresh─→│
  │                        │ (+ refresh token)   │
  │                        │← {new access} ──────│
  │                        │ (update store)      │
  │                        │                     │
  │                        │─ GET /dashboard ───→│
  │                        │ (+ new Bearer)      │
  │                        │← {dashboard} ───────│
  │                        │                     │
  ├─ Click logout ────────→│                     │
  │                        │─ POST /auth/logout ─→│
  │                        │ (+ refresh token)   │
  │                        │← 200 OK ────────────│
  │                        │ (clear storage)     │
  │                        │                     │
```

---

## Session/Token Management

### Token Storage Strategy

Tokens are stored in **localStorage** for persistence across page reloads, with in-memory backup for security.

```typescript
// src/utils/auth-storage.ts

export interface StoredTokens {
  access_token: string;
  refresh_token: string;
  expires_in: number;        // Seconds until access_token expires
  token_type: 'Bearer';
}

interface TokenPayload {
  sub: string;               // User ID
  exp: number;               // Expiration (Unix timestamp)
  iat: number;               // Issued at
  roles: string[];           // User roles
}

const TOKEN_STORAGE_KEY = 'automana_auth_tokens';
const STORAGE_EXPIRY_PADDING = 60; // Refresh 60s before actual expiry

/**
 * Store tokens in localStorage and memory.
 * On app reload, tokens are restored from localStorage.
 */
export const setAuthTokens = (tokens: StoredTokens) => {
  localStorage.setItem(TOKEN_STORAGE_KEY, JSON.stringify(tokens));
  // Memory cache for fast access
  (window as any).__authTokens = tokens;
  (window as any).__tokenExpiry = Date.now() + tokens.expires_in * 1000;
};

/**
 * Retrieve the current access token.
 * Returns null if token is missing or expired.
 */
export const getAuthToken = (): string | null => {
  const tokens = getStoredTokens();
  if (!tokens) return null;

  // Check if token is expired (with padding)
  if (isTokenExpired(tokens.access_token)) {
    return null;
  }

  return tokens.access_token;
};

/**
 * Get the refresh token (should only be used for refresh requests).
 */
export const getRefreshToken = (): string | null => {
  const tokens = getStoredTokens();
  return tokens?.refresh_token || null;
};

/**
 * Check if a JWT token is expired.
 * Decoded without verification (for UX timing only).
 */
export const isTokenExpired = (token: string): boolean => {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    const expiresAt = payload.exp * 1000; // Convert to milliseconds
    return Date.now() > expiresAt - STORAGE_EXPIRY_PADDING * 1000;
  } catch {
    return true; // Treat as expired if we can't parse
  }
};

/**
 * Decode token to extract claims (user ID, roles, etc.).
 */
export const decodeToken = (token: string): TokenPayload | null => {
  try {
    return JSON.parse(atob(token.split('.')[1]));
  } catch {
    return null;
  }
};

/**
 * Retrieve tokens from localStorage.
 */
const getStoredTokens = (): StoredTokens | null => {
  const cached = (window as any).__authTokens;
  if (cached) return cached;

  const stored = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (stored) {
    return JSON.parse(stored);
  }
  return null;
};

/**
 * Clear all tokens and auth state.
 */
export const clearAuthTokens = () => {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
  (window as any).__authTokens = null;
  (window as any).__tokenExpiry = null;
};

/**
 * Get user info from stored token (e.g., user ID, roles).
 */
export const getAuthUser = () => {
  const token = getAuthToken();
  if (!token) return null;
  return decodeToken(token);
};
```

### Token Refresh Mechanism

Refresh is triggered proactively (before expiry) or reactively (on 401):

```typescript
// src/utils/token-refresh.ts

import { apiClient } from './api-client';
import { getRefreshToken, setAuthTokens, clearAuthTokens } from './auth-storage';
import { useAuthStore } from '@/stores/authStore';

let refreshPromise: Promise<string | null> | null = null;

/**
 * Refresh the access token using the refresh token.
 * Multiple concurrent refresh requests are batched into one.
 */
export const refreshToken = async (): Promise<string | null> => {
  // If a refresh is already in flight, wait for it
  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = (async () => {
    try {
      const refreshToken = getRefreshToken();
      if (!refreshToken) {
        clearAuthTokens();
        useAuthStore.setState({ isAuthenticated: false });
        return null;
      }

      const response = await apiClient.post('/auth/refresh', {
        refresh_token: refreshToken,
      });

      const newTokens = response.data;
      setAuthTokens(newTokens);

      return newTokens.access_token;
    } catch (error) {
      // Refresh failed: force logout
      clearAuthTokens();
      useAuthStore.setState({ isAuthenticated: false });
      window.location.href = '/login';
      return null;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
};
```

---

## Protected Components & Routes

### ProtectedRoute (Higher-Order Component)

```typescript
// src/components/auth/ProtectedRoute.tsx

import { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { LoginPage } from '@/pages/LoginPage';

interface ProtectedRouteProps {
  children: ReactNode;
  requiredRoles?: string[];
}

/**
 * Wrapper component that checks authentication and authorization.
 * Redirects unauthenticated users to /login.
 * Renders AccessDenied if user lacks required roles.
 */
export function ProtectedRoute({
  children,
  requiredRoles = [],
}: ProtectedRouteProps) {
  const { isAuthenticated, user } = useAuthStore();

  // Not authenticated: show login page
  if (!isAuthenticated || !user) {
    return <LoginPage />;
  }

  // Check role-based access
  if (requiredRoles.length > 0) {
    const hasRole = requiredRoles.some(role =>
      user.roles?.includes(role)
    );

    if (!hasRole) {
      return (
        <div className="p-8 text-center">
          <h1 className="text-2xl font-bold text-red-600 mb-2">
            Access Denied
          </h1>
          <p>You do not have permission to view this page.</p>
          <p className="text-sm text-gray-500 mt-4">
            Required roles: {requiredRoles.join(', ')}
          </p>
        </div>
      );
    }
  }

  return <>{children}</>;
}
```

### useAuth Hook

```typescript
// src/hooks/useAuth.ts

import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '@/utils/api-client';
import { setAuthTokens, clearAuthTokens, getAuthUser } from '@/utils/auth-storage';
import { useAuthStore } from '@/stores/authStore';

export const useAuth = () => {
  const navigate = useNavigate();
  const { setUser, setAuthenticated } = useAuthStore();

  /**
   * Log in with email and password.
   */
  const login = useCallback(async (email: string, password: string) => {
    try {
      const response = await apiClient.post('/auth/login', {
        email,
        password,
      });

      const tokens = response.data;
      setAuthTokens(tokens);

      // Decode token to get user info
      const user = getAuthUser();
      setUser(user);
      setAuthenticated(true);

      navigate('/dashboard');
    } catch (error) {
      throw error;
    }
  }, [navigate, setUser, setAuthenticated]);

  /**
   * Log out and clear tokens.
   */
  const logout = useCallback(async () => {
    try {
      // Notify backend (optional, for audit logging)
      await apiClient.post('/auth/logout', {});
    } catch (error) {
      console.error('Logout API call failed (continuing anyway):', error);
    } finally {
      clearAuthTokens();
      setUser(null);
      setAuthenticated(false);
      navigate('/login');
    }
  }, [navigate, setUser, setAuthenticated]);

  /**
   * Check if user is authenticated.
   */
  const isAuthenticated = useCallback(() => {
    return useAuthStore.getState().isAuthenticated;
  }, []);

  return {
    login,
    logout,
    isAuthenticated,
    user: useAuthStore((state) => state.user),
  };
};
```

### Router Setup with Protected Routes

```typescript
// src/router/routes.tsx

import { createBrowserRouter } from 'react-router-dom';
import { LoginPage } from '@/pages/LoginPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { CardsPage } from '@/pages/CardsPage';
import { AdminPage } from '@/pages/AdminPage';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/dashboard',
    element: (
      <ProtectedRoute>
        <DashboardPage />
      </ProtectedRoute>
    ),
  },
  {
    path: '/cards',
    element: (
      <ProtectedRoute>
        <CardsPage />
      </ProtectedRoute>
    ),
  },
  {
    path: '/admin',
    element: (
      <ProtectedRoute requiredRoles={['admin']}>
        <AdminPage />
      </ProtectedRoute>
    ),
  },
]);
```

---

## Authorization & Permissions

### Permission Checking Hook

```typescript
// src/hooks/usePermission.ts

import { useAuthStore } from '@/stores/authStore';

/**
 * Permissions are role-based.
 * Map roles to capabilities for fine-grained control.
 */
const ROLE_PERMISSIONS: Record<string, string[]> = {
  user: ['read:cards', 'write:own-cards'],
  moderator: ['read:cards', 'write:cards', 'delete:cards'],
  admin: ['*'], // All permissions
};

export const usePermission = () => {
  const user = useAuthStore((state) => state.user);

  /**
   * Check if user has a specific permission.
   */
  const hasPermission = (permission: string): boolean => {
    if (!user?.roles) return false;

    return user.roles.some(role => {
      const perms = ROLE_PERMISSIONS[role] || [];
      return perms.includes('*') || perms.includes(permission);
    });
  };

  /**
   * Check if user has any of the given roles.
   */
  const hasRole = (roles: string | string[]): boolean => {
    if (!user?.roles) return false;
    const roleList = Array.isArray(roles) ? roles : [roles];
    return roleList.some(role => user.roles?.includes(role));
  };

  return { hasPermission, hasRole };
};
```

### Using Permissions in Components

```typescript
// src/features/cards/CardActions.tsx

import { usePermission } from '@/hooks/usePermission';

function CardActions({ cardId }: { cardId: string }) {
  const { hasPermission } = usePermission();
  const canDelete = hasPermission('delete:cards');
  const canEdit = hasPermission('write:cards');

  return (
    <div className="flex gap-2">
      {canEdit && (
        <button className="px-3 py-1 bg-blue-500 text-white rounded">
          Edit
        </button>
      )}
      {canDelete && (
        <button className="px-3 py-1 bg-red-500 text-white rounded">
          Delete
        </button>
      )}
    </div>
  );
}
```

---

## Error States

### 401 Unauthorized (Expired Token)

When the server returns 401:
1. Response interceptor detects it.
2. Trigger token refresh.
3. Retry the original request.
4. If refresh fails, redirect to login.

```typescript
// In API interceptor (see API_INTEGRATION.md)

if (error.response?.status === 401) {
  const token = getRefreshToken();
  if (token) {
    // Try to refresh
    const newAccessToken = await refreshToken();
    if (newAccessToken) {
      // Retry original request with new token
      error.config!.headers.Authorization = `Bearer ${newAccessToken}`;
      return apiClient(error.config!);
    }
  }
  // Refresh failed, logout
  clearAuthTokens();
  window.location.href = '/login';
}
```

### 403 Forbidden (Insufficient Permissions)

```typescript
function CardDeleteButton({ cardId }: { cardId: string }) {
  const { hasPermission } = usePermission();
  const mutation = useDeleteCard();

  if (!hasPermission('delete:cards')) {
    return (
      <button disabled className="opacity-50 cursor-not-allowed">
        Delete (Insufficient Permissions)
      </button>
    );
  }

  return (
    <button
      onClick={() => mutation.mutate(cardId)}
      className="px-3 py-1 bg-red-500 text-white rounded"
    >
      Delete
    </button>
  );
}
```

---

## CORS, CSRF, and Security Considerations

### CORS Headers

The backend sets appropriate CORS headers for the frontend domain:

**Backend (`src/automana/core/settings.py`):**

```python
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",   # Vite dev server
    "http://localhost:3000",   # Fallback
    "https://automana.app",    # Production
]

CORS_ALLOW_CREDENTIALS = True  # Allow cookies
```

**Frontend:**

```typescript
// src/utils/api-client.ts
const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  withCredentials: true, // Include cookies
});
```

### CSRF Protection

Use SameSite cookies and CSRF tokens for state-changing requests:

```typescript
// Backend sets: Set-Cookie: sessionid=...; SameSite=Strict

// If backend uses X-CSRF-Token header:
const getCsrfToken = () => {
  const token = document.querySelector('meta[name="csrf-token"]');
  return token ? token.getAttribute('content') : null;
};

// Add to all non-GET requests
apiClient.interceptors.request.use((config) => {
  if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(config.method?.toUpperCase() || '')) {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      config.headers['X-CSRF-Token'] = csrfToken;
    }
  }
  return config;
});
```

### Token Security Best Practices

1. **HttpOnly Cookies (Recommended)**: Store refresh token in an HttpOnly cookie (cannot be accessed by JS, safer against XSS).
   - Requires backend support: `Set-Cookie: refresh_token=...; HttpOnly; SameSite=Strict`
   - Frontend only needs to send the cookie automatically.

2. **localStorage (Current Approach)**: Store tokens in localStorage for SPA use.
   - Vulnerable to XSS attacks; keep Content-Security-Policy strict.
   - Never expose tokens in URLs or logs.

3. **Never Log Tokens**: Exclude tokens from logs, error messages, and monitoring tools.

4. **Token Expiry**: Set reasonable expiration times:
   - Access token: 15 minutes
   - Refresh token: 7 days

---

## Summary

- **Tokens**: JWT stored in localStorage with in-memory cache.
- **Refresh**: Proactive (before expiry) or reactive (on 401), with batching for concurrent requests.
- **Protected Routes**: ProtectedRoute HOC with role-based access checks.
- **Permissions**: Fine-grained permissions mapped to roles, checked with usePermission hook.
- **Error Handling**: 401 triggers refresh; 403 shows access denied; network errors retry.
- **Security**: CORS configured, CSRF protected, tokens never logged, SameSite cookies.
