import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'

export default defineConfig({
  plugins: [
    TanStackRouterVite({
      routesDirectory: './src/routes',
      generatedRouteTree: './src/routeTree.gen.ts',
    }),
    react(),
  ],
  server: {
    allowedHosts: ['automana.duckdns.org'],
    proxy: {
      '/api': 'http://backend:8000',
    },
    hmr: process.env.VITE_HMR_HOST
      ? {
          host: process.env.VITE_HMR_HOST,
          protocol: 'wss',
        }
      : undefined,
    middlewares: [
      (req, res, next) => {
        const originalSetHeader = res.setHeader
        res.setHeader = function(name, value) {
          if (name.toLowerCase() === 'x-content-type-options') {
            return res
          }
          return originalSetHeader.call(this, name, value)
        }
        next()
      },
    ],
  },
})
