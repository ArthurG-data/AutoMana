// src/frontend/src/routes/__root.tsx
import { createRootRouteWithContext, Outlet, redirect, useNavigate } from '@tanstack/react-router'
import { useEffect, useRef } from 'react'
import type { QueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../store/auth'

interface RouterContext {
  queryClient: QueryClient
}

// Paths accessible without a token
const PUBLIC_PATHS = ['/login', '/search']

function RootComponent() {
  const navigate = useNavigate()
  const token = useAuthStore((s) => s.token)
  const prevTokenRef = useRef(token)

  useEffect(() => {
    const wasAuthenticated = prevTokenRef.current !== null
    const isNowUnauthenticated = token === null
    if (wasAuthenticated && isNowUnauthenticated) {
      // Token was cleared (logout or 401) — send the user to the public search page
      navigate({ to: '/search' })
    }
    prevTokenRef.current = token
  }, [token, navigate])

  return <Outlet />
}

export const Route = createRootRouteWithContext<RouterContext>()({
  beforeLoad: ({ location }) => {
    const token = useAuthStore.getState().token
    const { pathname } = location

    // Unauthenticated: public paths are always allowed; / redirects to /search (marketing page is for guests, app shell is not)
    if (!token) {
      if (PUBLIC_PATHS.includes(pathname)) return
      if (pathname === '/') throw redirect({ to: '/search' })
      throw redirect({ to: '/login' })
    }
  },
  component: RootComponent,
})
