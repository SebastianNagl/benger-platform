/** @type {import('jest').Config} */
const baseConfig = require('./jest.config.js')

module.exports = {
  ...baseConfig,
  // Fast configuration for unit tests only
  testMatch: ['<rootDir>/src/**/*.{test,spec}.{ts,tsx}'],
  testPathIgnorePatterns: [
    '/node_modules/',
    'integration.test.',
    'e2e.test.',
    'performance.test.',
  ],
  // Disable coverage for faster execution
  collectCoverage: false,
  // More aggressive caching
  cache: true,
  // Reduce output for speed
  verbose: false,
  silent: false,
}
