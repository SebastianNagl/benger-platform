# Optimized multi-stage Dockerfile for Next.js
FROM node:18-alpine AS base

# Install dependencies only when needed
FROM base AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

# Copy package files and install dependencies
COPY package.json package-lock.json* ./
COPY .npmrc* ./

# Install all dependencies (including dev for build)
# Use cache mount for faster installs
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund --prefer-offline

# Build stage
FROM base AS builder
WORKDIR /app

# Copy dependencies
COPY --from=deps /app/node_modules ./node_modules

# Copy source code
COPY . .

# Build configuration
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

# Accept build arguments for public environment variables
ARG NEXT_PUBLIC_DISABLE_AUTO_LOGIN
ENV NEXT_PUBLIC_DISABLE_AUTO_LOGIN=${NEXT_PUBLIC_DISABLE_AUTO_LOGIN}
ARG NEXT_PUBLIC_BENGER_EDITION
ENV NEXT_PUBLIC_BENGER_EDITION=${NEXT_PUBLIC_BENGER_EDITION}

# Copy production config if it exists, otherwise use default
RUN if [ -f "next.config.production.js" ]; then \
      mv next.config.production.js next.config.js; \
    fi

# Build the application with optimized memory usage
# Use standalone output for smaller deployment size
# Increase memory limit and optimize build
RUN NODE_OPTIONS="--max-old-space-size=4096" \
    NEXT_TELEMETRY_DISABLED=1 \
    npm run build

# Production stage
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
# Set API URL for production container
ENV INTERNAL_API_URL=http://api:8000

# Install curl for health checks
RUN apk add --no-cache curl

# Create user
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copy standalone output for optimized deployment
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Add tini for proper signal handling (before switching user)
RUN apk add --no-cache tini

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Use tini as PID 1
ENTRYPOINT ["/sbin/tini", "--"]

# Start the application with our custom entrypoint
CMD ["/usr/local/bin/docker-entrypoint.sh"]