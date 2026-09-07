/** @type {import('next').NextConfig} */

// Environment detection
const isDevelopment = process.env.NODE_ENV === 'development'
const isProduction = process.env.NODE_ENV === 'production'
const isTesting = process.env.NODE_ENV === 'test'

// Feature flag for new configurations (Trunk-Based Development pattern)
const useNewConfig = process.env.FEATURE_FLAG_NEW_CONFIG !== 'false'

/**
 * Unified Next.js Configuration
 * Consolidated from 8 scattered config files with environment-aware configuration
 * Follows 2025 industry standards with feature flag support
 * NOTE: This is a copy of config/next/next.config.js for Docker build compatibility
 */
// Extended edition support
const isExtended = process.env.NEXT_PUBLIC_BENGER_EDITION === 'extended'

const nextConfig = {
  // Core Next.js settings
  pageExtensions: ['js', 'jsx', 'ts', 'tsx'],
  poweredByHeader: false,
  compress: true,

  // Transpile extended package when running in extended edition
  transpilePackages: isExtended ? ['@benger/extended'] : [],

  // Use standalone output for smaller deployments
  output: 'standalone',

  // Image optimization settings
  images: {
    unoptimized: isDevelopment || isTesting,
  },

  // TypeScript and ESLint handling based on environment
  typescript: {
    // Temporarily ignore TypeScript errors to fix CI/CD
    // TODO: Re-enable once Next.js type generation bug is fixed
    ignoreBuildErrors: true,
  },

  // Environment-specific optimizations
  ...(isDevelopment && {
    // Development optimizations
    devIndicators: {
      position: 'bottom-right',
    },
    productionBrowserSourceMaps: false,
    reactStrictMode: false, // Reduce double renders in dev
    experimental: {
      optimizeCss: false,
      optimizePackageImports: [],
      webVitalsAttribution: [],
    },
  }),

  ...(isProduction && {
    // Production optimizations
    reactStrictMode: true,
    experimental: {
      optimizeCss: true,
      optimizePackageImports: ['@headlessui/react', 'lucide-react'],
    },
  }),

  ...(isTesting && {
    // Testing optimizations
    reactStrictMode: false, // Faster test execution
    productionBrowserSourceMaps: false,
    experimental: {
      optimizeCss: false,
    },
  }),

  // Turbopack is the only bundler since Next 16 (a custom `webpack()` makes
  // `next build` refuse to run). The @benger/extended alias lives here for
  // both editions:
  //   extended, Docker build:  /app/benger-extended-frontend (copied into the
  //                            build context by CI)
  //   extended, dev:           the same path, bind-mounted so Turbopack
  //                            watches it for HMR
  //   community:               a no-op stub — the import in
  //                            src/lib/extensions/index.ts must still resolve
  //                            at build time even though it is never called
  // Paths are relative to next.config.js (which lives at /app in Docker).
  turbopack: {
    resolveExtensions: ['.tsx', '.ts', '.jsx', '.js', '.json'],
    resolveAlias: {
      '@benger/extended':
        isExtended && require('fs').existsSync('./benger-extended-frontend/index.ts')
          ? './benger-extended-frontend'
          : isExtended
            ? './node_modules/@benger/extended'
            : './src/lib/extensions/community-stub.ts',
    },
  },

  // Redirects and rewrites (environment-aware)
  async redirects() {
    const redirects = []

    // Add environment-specific redirects here if needed
    if (isDevelopment) {
      // Development-specific redirects
    }

    return redirects
  },

  // API Proxy configuration - REMOVED to use custom route handlers
  // We handle API proxying through custom route handlers in app/api/* instead
  // This gives us better control over cookie handling and SSE streams
  async rewrites() {
    // No rewrites - all API calls go through our custom route handlers
    return []
  },

  // Headers configuration
  async headers() {
    const headers = []

    if (isProduction) {
      headers.push({
        source: '/:path*',
        headers: [
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'X-XSS-Protection',
            value: '1; mode=block',
          },
        ],
      })
    }

    return headers
  },
}

// Feature flag support for gradual rollout
if (useNewConfig) {
  // New configuration features can be added here
  console.log('✨ Using new unified configuration system')
} else {
  console.log('⚠️  Using legacy configuration compatibility mode')
}

// Environment logging
if (isDevelopment) {
  console.log('🛠️  Next.js running in development mode')
} else if (isTesting) {
  console.log('🧪 Next.js running in testing mode')
} else if (isProduction) {
  console.log('🚀 Next.js running in production mode')
}

module.exports = nextConfig
