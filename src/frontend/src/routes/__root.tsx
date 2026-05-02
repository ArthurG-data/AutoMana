// src/frontend/src/routes/__root.tsx
import { createRootRouteWithContext, Outlet, redirect } from '@tanstack/react-router'
import type { QueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../store/auth'

interface RouterContext {
  queryClient: QueryClient
}

const PUBLIC_PATHS = ['/', '/login']

export const Route = createRootRouteWithContext<RouterContext>()({
  beforeLoad: ({ location }) => {
    const token = useAuthStore.getState().token
    if (!token && !PUBLIC_PATHS.includes(location.pathname)) {
      throw redirect({ to: '/login' })
    }
  },
  component: () => <Outlet />,
})
