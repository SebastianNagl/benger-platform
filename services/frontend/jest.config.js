/** @type {import('jest').Config} */
const config = {
  // DUAL PROJECT CONFIGURATION: Separate environments for client code vs API routes
  projects: [
    {
      displayName: 'client',
      // ESM-only packages that babel-jest must transpile for the CJS test runtime.
      transformIgnorePatterns: [
        '/node_modules/(?!(@tanstack|@faker-js|@sindresorhus)/)',
        '^.+\\.module\\.(css|sass|scss)$',
      ],
      testEnvironment: 'jsdom',
      setupFilesAfterEnv: [
        '<rootDir>/jest.setup.js',
        '<rootDir>/src/test-utils/setupTests.ts',
      ],
      testMatch: [
        '<rootDir>/src/**/__tests__/**/*.{ts,tsx}',
        '<rootDir>/src/**/*.{test,spec}.{ts,tsx}',
        '<rootDir>/tests/**/*.{test,spec}.{ts,tsx}',
      ],
      // API route tests belong to the api-routes project only. A negated
      // testMatch entry never excluded them: Jest replaces <rootDir> only at
      // the start of a pattern, and '!<rootDir>/...' does not start with it,
      // so every route test ran twice, once per environment.
      testPathIgnorePatterns: [
        '<rootDir>/.next/',
        '<rootDir>/node_modules/',
        '<rootDir>/e2e/',
        '<rootDir>/src/app/api/',
      ],
      moduleNameMapper: {
        '^@/components/shared/Select$':
          '<rootDir>/src/components/shared/__mocks__/Select.tsx',
        '^@/(.*)$': '<rootDir>/src/$1',
        '^@/components/(.*)$': '<rootDir>/src/components/$1',
        '^@/lib/(.*)$': '<rootDir>/src/lib/$1',
        '^@/hooks/(.*)$': '<rootDir>/src/hooks/$1',
        '^@/types/(.*)$': '<rootDir>/src/types/$1',
        '\\.(css|less|scss|sass)$': 'identity-obj-proxy',
        '\\.(jpg|jpeg|png|gif|eot|otf|webp|svg|ttf|woff|woff2|mp4|webm|wav|mp3|m4a|aac|oga)$':
          '<rootDir>/__mocks__/fileMock.js',
      },
      transform: {
        '^.+\\.(js|jsx|ts|tsx)$': [
          'babel-jest',
          {
            presets: ['next/babel'],
            babelrc: false,
            configFile: false,
            compact: false,
          },
        ],
      },
      moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json', 'node'],
    },
    {
      displayName: 'api-routes',
      // ESM-only packages that babel-jest must transpile for the CJS test runtime.
      transformIgnorePatterns: [
        '/node_modules/(?!(@tanstack|@faker-js|@sindresorhus)/)',
        '^.+\\.module\\.(css|sass|scss)$',
      ],
      testEnvironment: 'node', // Node environment for API routes
      setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
      testMatch: [
        '<rootDir>/src/app/api/**/__tests__/**/*.{ts,tsx}',
        '<rootDir>/src/app/api/**/*.{test,spec}.{ts,tsx}',
      ],
      moduleNameMapper: {
        '^@/(.*)$': '<rootDir>/src/$1',
        '^@/components/(.*)$': '<rootDir>/src/components/$1',
        '^@/lib/(.*)$': '<rootDir>/src/lib/$1',
        '^@/hooks/(.*)$': '<rootDir>/src/hooks/$1',
        '^@/types/(.*)$': '<rootDir>/src/types/$1',
      },
      transform: {
        '^.+\\.(js|jsx|ts|tsx)$': [
          'babel-jest',
          {
            presets: ['next/babel'],
            babelrc: false,
            configFile: false,
            compact: false,
          },
        ],
      },
      moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json', 'node'],
    },
  ],

  // Performance optimizations
  maxWorkers: process.env.CI ? 4 : '50%',
  testTimeout: 30000,
  cache: true,
  cacheDirectory: '<rootDir>/.jest-cache',
  workerIdleMemoryLimit: '512MB',

  // CI optimizations
  detectOpenHandles: process.env.CI === 'true',
  forceExit: process.env.CI === 'true',
  bail: process.env.CI ? 10 : 0,

  // Coverage settings
  collectCoverage: true,
  coverageDirectory: 'coverage',
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    '!src/**/*.d.ts',
    '!src/**/*.stories.{ts,tsx}',
    '!src/**/__tests__/**',
    '!src/**/__mocks__/**',
    '!src/test-utils/**',
    '!src/**/*.config.{ts,tsx}',
    // Untestable shells (issue #33, "optimal solution" decision): extended-slot
    // dispatcher pages (useSlot(...) + community fallback; the real behavior is
    // tested in benger-extended) and a pure <ProtectedRoute><LabelingInterface/>
    // composition shell. No isolated logic; not renderable under jsdom.
    '!src/app/projects/[id]/korrektur/page.tsx',
    '!src/app/projects/[id]/my-korrektur/[taskId]/page.tsx',
    '!src/app/projects/[id]/review/page.tsx',
    '!src/app/projects/[id]/label/page.tsx',
  ],

  // UPDATED COVERAGE THRESHOLDS (Issue #764)
  // Target: 75% global coverage for production-ready legal tech application
  // Progressive implementation: 60% → 75% → 85% → 89%
  // Recalibrated after the Korrektur Rework (4-card project detail page):
  // the old 5,614-line page.test/page.mega/page.branch trio was deleted in
  // favor of 25 focused contract tests on ConfigCard/SubSection/page.cards.
  // Real coverage of production code is unchanged; the headline % dropped
  // because the deleted tests were exercising the same lines repeatedly.
  coverageThreshold: {
    global: {
      // Ratcheted 2026-06-15 (issue #33) after the project-page + evaluation +
      // labeling + pages/auth/search backfill. Measured (non-grouped "rest"):
      // 90.54/83.63/85.40/91.94. Stmts/lines clear 90; funcs/branches climbing.
      // Ratcheted again 2026-09-14 to floor(CI-measured): the coverage gate of
      // PR #370 (run 34843964926) measured 92.23/85.95/90.35/93.20.
      statements: 92,
      branches: 85,
      functions: 90,
      lines: 93,
    },
    // Per-dir floors ratcheted 2026-06-15 (issue #33) to floor(measured)
    // after the project-page/evaluation/labeling/data backfill, and again on
    // 2026-09-14 to floor(CI-measured) from the coverage gate of PR #370 (run
    // 34843964926). Never lower without a comment on issue #33. Target: 90.
    // Critical business logic - higher standards
    'src/lib/api/': {
      statements: 94, // measured 94.04
      branches: 86, // measured 86.66
      functions: 93, // measured 93.17
      lines: 94, // measured 94.29
    },
    // API routes (the old "~0%" note was stale; really ~96%)
    'src/app/api/': {
      statements: 97, // measured 97.31
      branches: 93, // measured 93.50
      functions: 92, // measured 92.30
      lines: 97, // measured 97.29
    },
    // Utilities - should be thoroughly tested
    'src/utils/': {
      statements: 99, // measured 99.11
      branches: 97, // measured 97.32
      functions: 100, // measured 100
      lines: 99, // measured 99.15
    },
    // State management - critical
    'src/stores/': {
      statements: 99, // measured 99.41
      branches: 87, // measured 87.04
      functions: 100, // measured 100
      lines: 99, // measured 99.39
    },
    // Components - RESTORED 2026-06-24 to the pre-decomposition ratchet. The
    // Tier-2 decomposition had extracted ~5 cards/hooks (AdvancedSettingsCard,
    // ModelSelectionSection, Evaluation/GenerationDefaultsCard, usePermissions)
    // without tests, which forced a temporary floor relax to 91/85/88/92. Those
    // components now have dedicated tests (all ~100%), so the floors are back up.
    // 2026-09-14 CI measured 92.34/85.82/90.55/93.39: same integers, unchanged.
    'src/components/': {
      statements: 92,
      branches: 85,
      functions: 90,
      lines: 93,
    },
  },

  // Coverage reporters
  coverageReporters: [
    'text',
    'lcov',
    'html',
    'json',
    'json-summary',
    'text-summary',
  ],

  // Ignore patterns
  testPathIgnorePatterns: [
    '<rootDir>/.next/',
    '<rootDir>/node_modules/',
    '<rootDir>/e2e/',
  ],

  transformIgnorePatterns: [
    // ESM-only packages that babel-jest must transpile for the CJS test runtime.
    '/node_modules/(?!(@tanstack|@faker-js|@sindresorhus)/)',
    '^.+\\.module\\.(css|sass|scss)$',
  ],

  globals: {
    'ts-jest': {
      tsconfig: 'tsconfig.test.json',
    },
  },
}

module.exports = config
