# syntax=docker/dockerfile:1

# Development Dockerfile: Runs Vite dev server with hot-reload
FROM node:20-alpine

WORKDIR /app

# Copy package manifests for dependency installation
COPY src/frontend/package.json src/frontend/package-lock.json ./

# Install dependencies (including devDependencies)
RUN npm ci

# Copy source code (will be volume-mounted in dev, overriding this)
COPY src/frontend/ ./

EXPOSE 5173

# Run Vite dev server on 0.0.0.0 so it's accessible from host
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
