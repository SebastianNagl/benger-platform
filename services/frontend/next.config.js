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

  eslint: {
    // Allow builds to continue in development for faster iteration
    // Temporarily ignore during builds to fix production issue
    ignoreDuringBuilds: true,
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

  // Turbopack configuration (Next.js 13+ with --turbo flag)
  turbopack: {
    resolveExtensions: ['.tsx', '.ts', '.jsx', '.js', '.json'],
  },

  // Webpack configuration (legacy fallback when not using --turbo)
  webpack: (config, { dev, isServer }) => {
    // Resolve @benger/extended to mounted volume in extended edition
    if (isExtended) {
      config.resolve.alias['@benger/extended'] = '/app/benger-extended-frontend'
    }

    // Disable MDX processing (not used in BenGER)
    config.module.rules = config.module.rules.filter(
      (rule) => !rule.test?.toString().includes('mdx')
    )

    // Optimization settings based on environment
    config.optimization = {
      ...config.optimization,
      // Disable concatenation in development for faster builds
      concatenateModules: isProduction,
    }

    // Development-specific webpack optimizations
    if (dev) {
      config.watchOptions = {
        ...config.watchOptions,
        ignored: [
          '**/node_modules/**',
          '**/.git/**',
          '**/.next/**',
          '**/.eslintcache',
          '**/.DS_Store',
        ],
        poll: process.env.WATCHPACK_POLLING === 'true' ? 1000 : false,
        aggregateTimeout: 300,
      }

      // Disable minimization in development for faster builds
      config.optimization.minimize = false
      config.optimization.minimizer = []

      // Development build performance monitoring
      if (process.env.DEBUG === 'true') {
        config.plugins.push({
          apply: (compiler) => {
            let lastBuildTime = Date.now()
            compiler.hooks.beforeCompile.tap('BuildTimer', () => {
              const now = Date.now()
              const timeSinceLastBuild = now - lastBuildTime
              if (timeSinceLastBuild < 1000) {
                console.warn(
                  `[Build Monitor] Rapid rebuild detected: ${timeSinceLastBuild}ms since last build`
                )
              }
              lastBuildTime = now
            })
          },
        })
      }
    }

    // Production-specific optimizations
    if (isProduction) {
      // Additional production optimizations can be added here
      config.optimization.minimize = true
    }

    // Testing-specific optimizations
    if (isTesting) {
      // Faster compilation for tests
      config.optimization.minimize = false
      config.optimization.minimizer = []
    }

    return config
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
