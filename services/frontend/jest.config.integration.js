/** @type {import('jest').Config} */
const baseConfig = require('./jest.config.js')

module.exports = {
  ...baseConfig,
  // Integration test configuration
  testMatch: ['<rootDir>/src/**/*.integration.{test,spec}.{ts,tsx}'],
  // Longer timeout for integration tests
  testTimeout: 60000,
  // Enable coverage for integration tests
  collectCoverage: true,
  // Less parallelization for integration tests
  maxWorkers: 2,
}
