/** @type {import('jest').Config} */
const config = {
  // DUAL PROJECT CONFIGURATION: Separate environments for client code vs API routes
  projects: [
    {
      displayName: 'client',
      testEnvironment: 'jsdom',
      setupFilesAfterEnv: [
        '<rootDir>/jest.setup.js',
        '<rootDir>/src/test-utils/setupTests.ts',
      ],
      testMatch: [
        '<rootDir>/src/**/__tests__/**/*.{ts,tsx}',
        '<rootDir>/src/**/*.{test,spec}.{ts,tsx}',
        '<rootDir>/tests/**/*.{test,spec}.{ts,tsx}',
        '!<rootDir>/src/app/api/**', // Exclude API routes from client project
      ],
      moduleNameMapper: {
        '^@/components/shared/Select$': '<rootDir>/src/components/shared/__mocks__/Select.tsx',
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
  ],

  // UPDATED COVERAGE THRESHOLDS (Issue #764)
  // Target: 75% global coverage for production-ready legal tech application
  // Progressive implementation: 60% → 75% → 85% → 89%
  // Thresholds adjusted after removing duplicate/low-quality AI-generated test files
  coverageThreshold: {
    global: {
      statements: 86,
      branches: 82,
      functions: 82,
      lines: 88,
    },
    // Critical business logic - higher standards
    'src/lib/api/': {
      statements: 70, // Target: 85%
      branches: 64, // Target: 80%
      functions: 70, // Target: 85%
      lines: 70, // Target: 85%
    },
    // API routes - essential coverage
    'src/app/api/': {
      statements: 60, // Target: 80% (currently ~0%)
      branches: 54, // Target: 75%
      functions: 60, // Target: 80%
      lines: 60, // Target: 80%
    },
    // Utilities - should be thoroughly tested
    'src/utils/': {
      statements: 85, // Already at 93.78%, maintain high standard
      branches: 80,
      functions: 85,
      lines: 85,
    },
    // State management - critical
    'src/stores/': {
      statements: 80,
      branches: 68,
      functions: 90,
      lines: 85,
    },
    // Components - raised after Phase 4 coverage improvement
    'src/components/': {
      statements: 60,
      branches: 50,
      functions: 55,
      lines: 60,
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
    '/node_modules/',
    '^.+\\.module\\.(css|sass|scss)$',
  ],

  globals: {
    'ts-jest': {
      tsconfig: 'tsconfig.test.json',
    },
  },
}

module.exports = config
