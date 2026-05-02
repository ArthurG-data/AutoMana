# Build, Deployment & Performance

This guide covers Vite configuration, Docker setup, performance optimization, CI/CD pipeline, and production monitoring for the AutoMana React frontend.

## Vite Configuration

### Decision Rationale

**Why Vite over Webpack/CRA?**
- **Fast HMR**: Hot Module Replacement in <100ms (vs. seconds with Webpack).
- **Fast builds**: Optimized production bundles in 10-15 seconds.
- **ES modules**: Native ES imports; no compile step for dev.
- **Plugins**: Rich ecosystem; easy to extend.
- **Dev server**: Built-in, no separate dev server needed.

### vite.config.ts

```typescript
// vite.config.ts

import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import compression from 'vite-plugin-compression';
import visualizer from 'rollup-plugin-visualizer';
import path from 'path';

export default defineConfig({
  plugins: [
    react({
      // Use react-jsx runtime (no need to import React)
      jsxImportSource: 'react',
    }),
    // Gzip compression for production
    compression({
      algorithm: 'gzip',
      ext: '.gz',
      threshold: 10240, // Only compress files > 10KB
    }),
    // Bundle analyzer (run with --open)
    visualizer({
      open: false,
      brotliSize: true,
    }),
  ],

  server: {
    port: 5173,
    proxy: {
      // Proxy API requests to backend during dev
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '/api'),
      },
    },
  },

  build: {
    // Output directory
    outDir: 'dist',
    // Clear dist on build
    emptyOutDir: true,
    // Asset file size limit (inline <4KB as base64)
    assetsInlineLimit: 4096,
    // Source maps for production error tracking
    sourcemap: true,
    // Code splitting configuration
    rollupOptions: {
      output: {
        manualChunks: {
          // Split vendor libraries
          'react-libs': ['react', 'react-dom', 'react-router-dom'],
          'ui-libs': ['@radix-ui/react-dialog', '@radix-ui/react-select'],
          'data-libs': ['@tanstack/react-query', 'zustand', 'zod'],
        },
        // Hash chunk names for cache busting
        entryFileNames: '[name].[hash].js',
        chunkFileNames: '[name].[hash].js',
        assetFileNames: 'assets/[name].[hash][extname]',
      },
    },
    // Minification
    minify: 'terser',
    terserOptions: {
      compress: {
        // Remove console.log in production
        drop_console: true,
      },
    },
    // Report compressed size
    reportCompressedSize: true,
    // Chunk size warning
    chunkSizeWarningLimit: 1000, // KB
  },

  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },

  define: {
    // Replace process.env.NODE_ENV
    'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV),
  },
});
```

---

## Build Output Structure

### Hashing & Cache Busting

Hash values change only when content changes:

```
dist/
├── index.html                           # Entry point (not hashed)
├── assets/
│   ├── react-libs.a1b2c3d4.js          # Hashed vendor chunk
│   ├── ui-libs.e5f6g7h8.js             # Hashed vendor chunk
│   ├── data-libs.i9j0k1l2.js           # Hashed vendor chunk
│   ├── index.a1b2c3d4.js               # Hashed main bundle
│   ├── Cards.e5f6g7h8.js               # Lazy-loaded route chunk
│   ├── Dashboard.i9j0k1l2.js           # Lazy-loaded route chunk
│   ├── style.m3n4o5p6.css              # Hashed CSS
│   ├── style.m3n4o5p6.css.gz           # Gzip compressed
│   ├── card-image.q7r8s9t0.jpg         # Hashed assets
│   └── manifest.json                   # Preload hints
└── .vite/manifest.json                 # Asset manifest (for SSR or preload)
```

**Benefits:**
- Browsers cache files by hash; old hashes are never reused.
- Only changed chunks are re-downloaded on update.
- `index.html` is never cached; it pulls latest chunks via hash.

### Manifest.json (Optional)

For smart preloading of critical chunks:

```json
{
  "src/main.tsx": {
    "file": "assets/index.a1b2c3d4.js",
    "src": "src/main.tsx",
    "isEntry": true,
    "imports": ["_react-libs.e5f6g7h8.js"]
  },
  "src/pages/Cards.tsx": {
    "file": "assets/Cards.e5f6g7h8.js",
    "src": "src/pages/Cards.tsx",
    "isDynamicEntry": true
  }
}
```

---

## Environment Configuration

### .env Files

**File structure:**

```
.env                    # Shared (committed)
.env.local              # Local overrides (gitignored)
.env.development        # Dev-specific (committed)
.env.production         # Production-specific (committed)
```

**File:** `.env`

```
VITE_APP_NAME=AutoMana
VITE_APP_VERSION=1.0.0
```

**File:** `.env.development`

```
VITE_API_BASE_URL=http://localhost:8000/api
VITE_LOG_LEVEL=debug
VITE_FEATURE_FLAGS=cards,collection,import
```

**File:** `.env.production`

```
VITE_API_BASE_URL=https://api.automana.app/api
VITE_LOG_LEVEL=warn
VITE_FEATURE_FLAGS=cards,collection,import,analytics
```

**File:** `.env.local` (gitignored)

```
# Local dev secrets (never commit)
VITE_DEV_AUTH_TOKEN=mock-token-for-testing
```

### Using Environment Variables

```typescript
// src/config/env.ts

export const config = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
  appName: import.meta.env.VITE_APP_NAME,
  logLevel: (import.meta.env.VITE_LOG_LEVEL || 'info') as 'debug' | 'info' | 'warn' | 'error',
  featureFlags: (import.meta.env.VITE_FEATURE_FLAGS || '').split(',').filter(Boolean),
  isDev: import.meta.env.DEV,
  isProd: import.meta.env.PROD,
};

// Usage:
if (config.featureFlags.includes('analytics')) {
  // Enable analytics
}
```

### Feature Flags

```typescript
// src/utils/feature-flags.ts

export const isFeatureEnabled = (flag: string): boolean => {
  if (import.meta.env.DEV) {
    // In dev, allow runtime override via localStorage
    const override = localStorage.getItem(`feature_${flag}`);
    if (override !== null) {
      return override === 'true';
    }
  }
  return config.featureFlags.includes(flag);
};

// Component usage:
function AnalyticsWidget() {
  if (!isFeatureEnabled('analytics')) return null;
  return <AnalyticsDashboard />;
}
```

---

## Docker Integration

### Multi-Stage Dockerfile

**File:** `Dockerfile`

```dockerfile
# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build the app
RUN npm run build

# Stage 2: Runtime (nginx)
FROM nginx:1.27-alpine

# Copy nginx config
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/default.conf /etc/nginx/conf.d/default.conf

# Copy built app from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Create a non-root user for security
RUN addgroup -g 101 -S nginx && \
    adduser -S -D -H -u 101 -h /var/cache/nginx -s /sbin/nologin -G nginx -g nginx nginx

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://localhost:80/ || exit 1

# Expose port
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
```

### Nginx Configuration

**File:** `docker/default.conf`

```nginx
server {
    listen 80;
    server_name _;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css text/javascript application/javascript application/json;
    gzip_min_length 1024;

    root /usr/share/nginx/html;
    index index.html;

    # Cache assets with hash (long expiry)
    location ~* /assets/.*\.[a-f0-9]{8}\.(js|css|woff2|png|jpg|svg)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Don't cache index.html (always check for updates)
    location = /index.html {
        expires -1;
        add_header Cache-Control "public, must-revalidate, max-age=0";
    }

    # SPA routing: fallback to index.html for 404s
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API proxy (if needed for development)
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;

    # CSP header
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; font-src 'self' data:;" always;
}
```

### Building Docker Image

```bash
# Build
docker build -t automana-frontend:latest -f Dockerfile .

# Run
docker run -p 80:3000 automana-frontend:latest

# Tag and push
docker tag automana-frontend:latest ghcr.io/ArthurG-data/automana-frontend:latest
docker push ghcr.io/ArthurG-data/automana-frontend:latest
```

---

## Performance Optimization

### Code Splitting (Route-Based)

```typescript
// src/router/routes.tsx

import { lazy, Suspense } from 'react';
import { LoadingSpinner } from '@/components/LoadingSpinner';

// Lazy load route components
const DashboardPage = lazy(() => import('@/pages/DashboardPage'));
const CardsPage = lazy(() => import('@/pages/CardsPage'));
const CollectionPage = lazy(() => import('@/pages/CollectionPage'));

export const routes = [
  {
    path: '/dashboard',
    element: (
      <Suspense fallback={<LoadingSpinner />}>
        <DashboardPage />
      </Suspense>
    ),
  },
  {
    path: '/cards',
    element: (
      <Suspense fallback={<LoadingSpinner />}>
        <CardsPage />
      </Suspense>
    ),
  },
  {
    path: '/collection',
    element: (
      <Suspense fallback={<LoadingSpinner />}>
        <CollectionPage />
      </Suspense>
    ),
  },
];
```

### Lazy Loading Components

```typescript
// Lazy load heavy components
const CardGallery = lazy(() => import('@/features/cards/components/CardGallery'));
const ChartWidget = lazy(() => import('@/features/dashboard/components/ChartWidget'));

export function Dashboard() {
  const [showGallery, setShowGallery] = useState(false);

  return (
    <div>
      <button onClick={() => setShowGallery(true)}>Show Gallery</button>

      {showGallery && (
        <Suspense fallback={<div>Loading gallery...</div>}>
          <CardGallery />
        </Suspense>
      )}
    </div>
  );
}
```

### Image Optimization

```typescript
// src/components/OptimizedImage.tsx

import { useState } from 'react';

interface OptimizedImageProps {
  src: string;
  alt: string;
  width?: number;
  height?: number;
}

export function OptimizedImage({
  src,
  alt,
  width = 300,
  height = 400,
}: OptimizedImageProps) {
  const [isLoaded, setIsLoaded] = useState(false);

  // Generate responsive image URLs (using image CDN)
  const srcSet = `
    ${src}?w=300&q=80 300w,
    ${src}?w=600&q=80 600w,
    ${src}?w=900&q=80 900w
  `;

  return (
    <img
      src={`${src}?w=${width}&q=80`}
      srcSet={srcSet}
      alt={alt}
      width={width}
      height={height}
      loading="lazy"
      onLoad={() => setIsLoaded(true)}
      className={`transition-opacity ${isLoaded ? 'opacity-100' : 'opacity-0'}`}
    />
  );
}
```

### Web Vitals Monitoring

```typescript
// src/utils/web-vitals.ts

import { getCLS, getFID, getFCP, getLCP, getTTFB } from 'web-vitals';

export const reportWebVitals = () => {
  getCLS(console.log);  // Cumulative Layout Shift
  getFID(console.log);  // First Input Delay
  getFCP(console.log);  // First Contentful Paint
  getLCP(console.log);  // Largest Contentful Paint
  getTTFB(console.log); // Time to First Byte
};

// Call in main.tsx
reportWebVitals();
```

### Bundle Analysis

```bash
# Generate visualization
npm run build && npm run build -- --visualize

# Opens an HTML file showing chunk breakdown
# Identifies large dependencies for potential optimization
```

---

## Deployment Pipeline (CI/CD)

### GitHub Actions Workflow

**File:** `.github/workflows/deploy.yml`

```yaml
name: Build & Deploy Frontend

on:
  push:
    branches: [main]
    paths:
      - 'frontend/**'
      - '.github/workflows/deploy.yml'
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Run tests
        run: npm run test -- run

      - name: Build
        run: npm run build
        env:
          VITE_API_BASE_URL: https://api.automana.app/api

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage/coverage-final.json

      - name: Build Docker image
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        run: |
          docker build -t automana-frontend:${{ github.sha }} .
          docker tag automana-frontend:${{ github.sha }} automana-frontend:latest

      - name: Push to registry
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        run: |
          echo ${{ secrets.GHCR_TOKEN }} | docker login ghcr.io -u ${{ secrets.GHCR_USER }} --password-stdin
          docker push ghcr.io/ArthurG-data/automana-frontend:${{ github.sha }}
          docker push ghcr.io/ArthurG-data/automana-frontend:latest

      - name: Deploy to production
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        run: |
          # Example: trigger deployment webhook
          curl -X POST ${{ secrets.DEPLOY_WEBHOOK }} \
            -H "Authorization: Bearer ${{ secrets.DEPLOY_TOKEN }}" \
            -d '{"image": "automana-frontend:${{ github.sha }}"}'
```

### Manual Deployment Steps

```bash
# 1. Verify tests pass
npm run test -- run
npm run test:e2e

# 2. Build for production
npm run build

# 3. Verify bundle size
ls -lh dist/assets/*.js

# 4. Run lighthouse audit (optional)
npm run build && npm install -g @lhci/cli@latest
lhci autorun

# 5. Build and tag Docker image
docker build -t automana-frontend:v1.2.3 .

# 6. Push to registry
docker tag automana-frontend:v1.2.3 ghcr.io/ArthurG-data/automana-frontend:v1.2.3
docker push ghcr.io/ArthurG-data/automana-frontend:v1.2.3

# 7. Update deployment (e.g., Kubernetes)
kubectl set image deployment/automana-frontend \
  automana-frontend=ghcr.io/ArthurG-data/automana-frontend:v1.2.3

# 8. Monitor deployment
kubectl rollout status deployment/automana-frontend
```

### Rollback Procedure

```bash
# List previous deployments
kubectl rollout history deployment/automana-frontend

# Rollback to previous version
kubectl rollout undo deployment/automana-frontend

# Or rollback to specific revision
kubectl rollout undo deployment/automana-frontend --to-revision=2

# Verify rollback
kubectl get pods
kubectl logs <pod-name>
```

---

## Production Monitoring

### Error Tracking (Sentry)

```typescript
// src/main.tsx

import * as Sentry from "@sentry/react";

if (import.meta.env.PROD) {
  Sentry.init({
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: import.meta.env.VITE_ENV || 'production',
    integrations: [
      Sentry.replayIntegration(),
    ],
    tracesSampleRate: 0.1,
    replaysSessionSampleRate: 0.1,
    replaysOnErrorSampleRate: 1.0,
  });
}
```

### Performance Monitoring (DataDog/New Relic)

```typescript
// src/utils/monitoring.ts

export const captureMetric = (name: string, value: number, tags?: Record<string, string>) => {
  if (import.meta.env.PROD && window.datadog) {
    window.datadog.metrics.gauge(name, value, tags);
  }
};

// Usage:
import { getLCP } from 'web-vitals';

getLCP(({ value }) => {
  captureMetric('frontend.web_vitals.lcp', value, {
    page: window.location.pathname,
  });
});
```

### User Analytics

```typescript
// src/utils/analytics.ts

import { config } from '@/config/env';

export const trackEvent = (name: string, props?: Record<string, any>) => {
  if (config.isProd && window.gtag) {
    window.gtag('event', name, props);
  }
};

// Usage:
function CardSearch() {
  const { data, refetch } = useSearchCards();

  const handleSearch = (query: string) => {
    trackEvent('card_search', { query, result_count: data?.length });
    refetch();
  };

  return (
    <input
      placeholder="Search..."
      onChange={(e) => handleSearch(e.target.value)}
    />
  );
}
```

### Uptime Monitoring

```yaml
# Synthetic monitoring (e.g., Datadog or Uptime Robot)
- Monitor root page (/) every 5 minutes
- Monitor API health endpoint (/api/health) every 5 minutes
- Alert if response time > 2s or status != 200
```

---

## Summary

- **Vite**: Fast dev server, fast builds, ES modules, rich plugin ecosystem.
- **Output**: Hashed chunks for cache busting; index.html always fresh.
- **Environment**: .env files per stage; feature flags for runtime control.
- **Docker**: Multi-stage build; nginx serving with SPA routing.
- **Performance**: Code splitting, lazy loading, image optimization, web vitals.
- **CI/CD**: GitHub Actions for test → build → push → deploy.
- **Monitoring**: Error tracking (Sentry), performance (DataDog), analytics (GA).
