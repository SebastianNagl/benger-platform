import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: 0,
  workers: 1,
  timeout: 60 * 1000, // Longer timeout for comprehensive tests
  use: {
    baseURL: 'http://benger.localhost',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'annotation-tab-real',
      use: {
        ...devices['Desktop Chrome'],
        navigationTimeout: 45000,
      },
      testMatch: ['**/annotation-tab-column-management.spec.ts'],
    },
    {
      name: 'debug',
      use: { ...devices['Desktop Chrome'] },
      testMatch: ['**/debug-navigation.spec.ts'],
    },
  ],
})
