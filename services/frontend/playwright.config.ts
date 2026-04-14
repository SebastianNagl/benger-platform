import { defineConfig, devices } from '@playwright/test'

/**
 * Isolated E2E mode detection
 * When E2E_ISOLATED=true, tests run against isolated infrastructure with higher parallelism
 */
const isIsolatedE2E = process.env.E2E_ISOLATED === 'true'

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
  testDir: './e2e',
  /* Run tests in files in parallel */
  fullyParallel: true,
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  /* Retry on CI and locally for flaky infrastructure tests */
  retries: 2,
  /* Opt out of parallel tests on CI. Workers optimized for isolated E2E mode */
  // Single worker for E2E isolated to prevent infrastructure overload
  // Multiple parallel logins to shared test accounts cause session conflicts
  workers: isIsolatedE2E ? 1 : process.env.CI ? 2 : 4,
  /* Global timeout for each test */
  timeout: isIsolatedE2E ? 90 * 1000 : process.env.CI ? 90 * 1000 : 30 * 1000,
  /* Global timeout for the entire test run */
  globalTimeout: isIsolatedE2E
    ? 90 * 60 * 1000
    : process.env.CI
      ? 100 * 60 * 1000
      : undefined,
  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: [
    ['html'],
    ['json', { outputFile: 'playwright-report/results.json' }],
    ['junit', { outputFile: 'playwright-report/results.xml' }],
  ],
  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    /* Base URL to use in actions like `await page.goto('/')`. */
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost',

    /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
    trace: 'on-first-retry',

    /* Screenshot on failure */
    screenshot: 'only-on-failure',

    /* Video recording */
    video: 'retain-on-failure',
  },

  /* Configure projects for major browsers */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
      testMatch: ['**/user-journeys/*.spec.ts', '**/error-recovery/*.spec.ts'],
      // Use single worker for user-journeys to prevent session conflicts and race conditions
      workers: 1,
    },
    {
      name: 'visual-regression',
      use: { ...devices['Desktop Chrome'] },
      testMatch: ['**/visual/*.spec.ts'],
    },
    {
      name: 'enhanced-workflows',
      use: { ...devices['Desktop Chrome'] },
      testMatch: ['**/enhanced-workflows/*.spec.ts'],
    },
    {
      name: 'feature-tests',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost',
      },
      testMatch: ['**/user-workflows/annotation-comparison.spec.ts'],
      workers: isIsolatedE2E ? 1 : 1,
    },
    {
      name: 'user-workflows',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost',
        storageState: undefined,
      },
      testMatch: ['**/user-workflows/*.spec.ts'],
      workers: isIsolatedE2E ? 1 : 1,
    },
    {
      name: 'admin',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost',
      },
      testMatch: ['**/admin/*.spec.ts'],
      workers: isIsolatedE2E ? 1 : 1,
    },
    {
      name: 'cross-browser',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost',
      },
      testMatch: ['**/cross-browser/*.spec.ts'],
      workers: isIsolatedE2E ? 1 : 2,
    },
    {
      name: 'integrity',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost',
      },
      testMatch: ['**/integrity/*.spec.ts'],
      workers: isIsolatedE2E ? 1 : 2,
    },
    {
      name: 'mobile',
      use: {
        ...devices['Pixel 5'],
        baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost',
      },
      testMatch: ['**/mobile/*.spec.ts'],
      workers: isIsolatedE2E ? 1 : 2,
    },
    {
      name: 'puppeteer-mcp',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost',
      },
      testMatch: ['**/puppeteer-mcp/*.spec.ts'],
      workers: isIsolatedE2E ? 1 : 2,
    },
    {
      name: 'resilience',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost',
      },
      testMatch: ['**/resilience/*.spec.ts'],
      workers: isIsolatedE2E ? 1 : 2,
    },
    {
      name: 'workflows',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost',
      },
      testMatch: ['**/workflows/*.spec.ts'],
      workers: isIsolatedE2E ? 1 : 2,
    },
    {
      name: 'root-level',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost',
      },
      testMatch: ['issue-*.spec.ts'],
      workers: isIsolatedE2E ? 1 : 2,
    },
    {
      name: 'annotation-types',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost',
      },
      testMatch: ['**/annotation-types/*.spec.ts'],
      workers: isIsolatedE2E ? 1 : 2,
    },
    {
      name: 'settings',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost',
      },
      testMatch: ['**/settings/*.spec.ts'],
      workers: isIsolatedE2E ? 1 : 2,
    },
  ],

  /* Skip webServer since we use Docker environment
  webServer: {
    command: process.env.CI ? 'npm run build && npm run start' : 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 180 * 1000, // Increased timeout for slower CI environments
    stdout: 'pipe',
    stderr: 'pipe',
    // Additional options for better reliability
    cwd: process.cwd(),
    env: {
      ...process.env,
      NODE_ENV: process.env.CI ? 'production' : 'development',
      NEXT_PUBLIC_ENABLE_DEV_AUTH: 'false', // Disable auto-login for tests
    },
  },
  */

  /* Global setup and teardown */
  globalSetup: './e2e/global-setup.ts',
  globalTeardown: './e2e/global-teardown.ts',

  /* Visual comparison settings */
  expect: {
    // Threshold for visual comparisons
    toHaveScreenshot: { threshold: 0.2 },
    toMatchSnapshot: { threshold: 0.2 },
  },
})
