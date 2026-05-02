# syntax=docker/dockerfile:1

# ──────────────────────────────────────────────────────────────────────────────
# Stage 1: Build the React app with Vite
# ──────────────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package manifests first for better layer caching.
# If only source code changes (not dependencies), npm ci is skipped from cache.
COPY src/frontend/package.json src/frontend/package-lock.json ./

# Install all dependencies (including devDependencies for Vite and TypeScript).
# npm ci (not npm install) ensures reproducible builds using package-lock.json.
RUN npm ci

# Copy application source after dependencies.
# This way, source-only changes don't bust the npm ci layer.
COPY src/frontend/ ./

# Compile TypeScript and bundle with Vite.
# Output goes to dist/ (Vite's default).
RUN npm run build

# ──────────────────────────────────────────────────────────────────────────────
# Stage 2: Serve with nginx
# ──────────────────────────────────────────────────────────────────────────────
FROM nginx:alpine AS runner

# Copy the SPA-specific nginx config.
# This config handles:
# - Cache headers for hashed assets (cache forever)
# - Cache headers for index.html (never cache — enables new deploys)
# - SPA fallback: unmapped URLs serve index.html for client-side routing
COPY deploy/docker/frontend/nginx.spa.conf /etc/nginx/conf.d/default.conf

# Copy compiled assets from builder stage into nginx's document root.
# This is the ONLY application code in the final image.
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port 80 (the proxy routes HTTPS traffic to this HTTP port via Docker DNS).
EXPOSE 80

# Health check: nginx responds with index.html on GET /.
# Used by docker-compose to wait until container is ready.
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD wget -qO- http://localhost/ > /dev/null || exit 1

# Start nginx in foreground (standard in Docker).
CMD ["nginx", "-g", "daemon off;"]
