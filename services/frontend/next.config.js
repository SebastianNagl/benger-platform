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
// Extension overlays. NEXT_PUBLIC_BENGER_EXTENSIONS lists the enabled overlay
// names in load order (e.g. "extended,compliance"); when it is unset or blank
// the legacy NEXT_PUBLIC_BENGER_EDITION=extended still enables the extended
// overlay alone. Unknown names are ignored with a warning. This mirrors
// src/lib/extensions/enabled.ts, which applies the same rule at runtime;
// keep the two in sync. Each name maps to the directory CI copies (or dev
// bind-mounts) the overlay's frontend tree into, relative to this file.
const OVERLAY_DIRS = {
  extended: 'benger-extended-frontend',
  compliance: 'benger-compliance-frontend',
}

function parseEnabledExtensions(env) {
  const raw = env.NEXT_PUBLIC_BENGER_EXTENSIONS
  if (raw === undefined || raw.trim() === '') {
    return env.NEXT_PUBLIC_BENGER_EDITION === 'extended' ? ['extended'] : []
  }
  const enabled = []
  for (const part of raw.split(',')) {
    const name = part.trim()
    if (name === '') continue
    if (!Object.prototype.hasOwnProperty.call(OVERLAY_DIRS, name)) {
      console.warn(
        `[extensions] unknown extension "${name}" in NEXT_PUBLIC_BENGER_EXTENSIONS ignored`,
      )
      continue
    }
    if (!enabled.includes(name)) enabled.push(name)
  }
  return enabled
}

const enabledExtensions = parseEnabledExtensions(process.env)
const isExtended = enabledExtensions.includes('extended')

// Where `@benger/<name>` resolves, in order of preference:
//   enabled, overlay tree present:  ./benger-<name>-frontend (copied into the
//                                   Docker build context by CI, or bind-mounted
//                                   in dev so Turbopack watches it for HMR)
//   enabled, tree absent:           ./node_modules/@benger/<name> (the dev
//                                   compose overlay mounts the tree there)
//   disabled:                       the no-op stub, because the import in
//                                   src/lib/extensions/index.ts must still
//                                   resolve at build time even though it is
//                                   never called
function overlayAlias(name) {
  if (!enabledExtensions.includes(name)) {
    return './src/lib/extensions/community-stub.ts'
  }
  const dir = `./${OVERLAY_DIRS[name]}`
  return require('fs').existsSync(`${dir}/index.ts`)
    ? dir
    : `./node_modules/@benger/${name}`
}

// The only path another site may frame (IMS LTI Dynamic Registration). The
// ingress (infra/helm/benger/templates/ingress.yaml) exempts the same path
// from its frameDeny header.
const FRAMEABLE_PATH = '/api/lti/register/init'

const nextConfig = {
  // Core Next.js settings
  pageExtensions: ['js', 'jsx', 'ts', 'tsx'],
  poweredByHeader: false,
  compress: true,

  // Transpile the enabled overlay packages (TypeScript, imported via alias)
  transpilePackages: enabledExtensions.map((name) => `@benger/${name}`),

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
  // `next build` refuse to run). Every overlay gets an alias in every build
  // (see overlayAlias above); paths are relative to next.config.js (which
  // lives at /app in Docker).
  turbopack: {
    resolveExtensions: ['.tsx', '.ts', '.jsx', '.js', '.json'],
    resolveAlias: Object.fromEntries(
      Object.keys(OVERLAY_DIRS).map((name) => [
        `@benger/${name}`,
        overlayAlias(name),
      ]),
    ),
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
      const baseHeaders = [
        {
          key: 'X-Content-Type-Options',
          value: 'nosniff',
        },
        {
          key: 'X-XSS-Protection',
          value: '1; mode=block',
        },
      ]
      headers.push({
        // Every path except the LTI Dynamic Registration page. The negative
        // lookahead is path-to-regexp syntax that Next documents for
        // headers(); see src/__tests__/nextConfigHeaders.test.ts.
        source: `/:path((?!${FRAMEABLE_PATH.slice(1)}$).*)`,
        headers: [
          ...baseHeaders,
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
        ],
      })
      headers.push({
        // An LMS (Moodle "Add LTI Advantage") loads this page in an iframe.
        // No X-Frame-Options here: the API answer carries a
        // Content-Security-Policy frame-ancestors limited to the LMS origin.
        source: FRAMEABLE_PATH,
        headers: baseHeaders,
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
