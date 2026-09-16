# ============================================================
# WattPilot AI - Frontend Dockerfile
# Multi-stage build: Vite dev/build → Nginx production serve.
# ============================================================

# --------------------------------------------------
# Stage 1: Install dependencies & build the React app
# --------------------------------------------------
FROM node:20-alpine AS builder

# Set working directory inside the container
WORKDIR /app

# Copy dependency manifests first to leverage Docker layer caching.
# Changes to source code won't trigger a full npm install.
# (Paths are relative to the build context = project root.)
COPY Frontend/package.json Frontend/package-lock.json* ./

# Install npm dependencies
# - --frozen-lockfile: ensure reproducible builds from lockfile
RUN npm ci --frozen-lockfile 2>/dev/null || npm install

# Copy the rest of the frontend source code
COPY Frontend/ ./

# Build the production bundle
# - Vite outputs an optimized static build to Frontend/dist
RUN npm run build

# --------------------------------------------------
# Stage 2: Production image with Nginx
# Serve the static build and proxy API calls to the backend.
# --------------------------------------------------
FROM nginx:stable-alpine AS runtime

# Remove the default Nginx configuration
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom Nginx config for the SPA routing & API proxy
COPY Frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copy the production build from the builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port 80 for HTTP traffic
EXPOSE 80

# Nginx runs in the foreground by default in the official image
CMD ["nginx", "-g", "daemon off;"]
