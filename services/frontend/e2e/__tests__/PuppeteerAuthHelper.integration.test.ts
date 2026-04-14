/**
 * Integration tests for PuppeteerAuthHelper
 *
 * These tests verify the authentication helper functionality
 * with real Puppeteer browser instances to ensure actual reliability.
 *
 * @jest-environment node
 */

import puppeteer, { Browser, Page } from 'puppeteer'
import { PuppeteerAuthHelper } from '../helpers/PuppeteerAuthHelper'

// Test configuration
const TEST_CONFIG = {
  baseUrl: process.env.TEST_BASE_URL || 'http://localhost:3000',
  username: process.env.TEST_USERNAME || 'admin',
  password: process.env.TEST_PASSWORD || 'admin',
  timeout: 30000,
  browserOptions: {
    headless: process.env.CI === 'true', // Show browser locally, hide in CI
    defaultViewport: { width: 1280, height: 720 },
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-extensions',
      '--no-first-run',
      '--disable-default-apps',
    ],
  },
}

describe('PuppeteerAuthHelper Integration Tests', () => {
  let browser: Browser
  let page: Page
  let authHelper: PuppeteerAuthHelper

  beforeAll(async () => {
    browser = await puppeteer.launch(TEST_CONFIG.browserOptions)
  })

  afterAll(async () => {
    if (browser) {
      await browser.close()
    }
  })

  beforeEach(async () => {
    page = await browser.newPage()
    authHelper = new PuppeteerAuthHelper(page, {
      username: TEST_CONFIG.username,
      password: TEST_CONFIG.password,
      timeout: TEST_CONFIG.timeout,
      enableLogging: false, // Disable logging in tests
    })

    // Set up error tracking
    page.on('pageerror', (error) => {
      console.error('Page error during test:', error.message)
    })
  })

  afterEach(async () => {
    if (page) {
      await page.close()
    }
  })

  describe('Environment Detection', () => {
    it('should correctly detect localhost as development environment', async () => {
      await page.goto(`${TEST_CONFIG.baseUrl}/login`)

      const isProduction = await authHelper.isProductionEnvironment()
      expect(isProduction).toBe(false)
    })

    it('should handle environment detection with different hostnames', async () => {
      // Navigate to localhost first to ensure page is loaded
      await page.goto(`${TEST_CONFIG.baseUrl}/login`)

      // Mock hostname change
      await page.evaluate(() => {
        Object.defineProperty(window.location, 'hostname', {
          value: 'production.example.com',
          writable: true,
        })
      })

      const isProduction = await authHelper.isProductionEnvironment()
      expect(isProduction).toBe(true)
    })
  })

  describe('Authentication State Detection', () => {
    it('should detect logged out state on login page', async () => {
      await page.goto(`${TEST_CONFIG.baseUrl}/login`)

      const authState = await authHelper.detectAuthState()
      expect(authState).toBe('logged_out')
    })

    it('should detect logged in state after successful authentication', async () => {
      // Perform actual login
      await authHelper.reliableLogin()

      // Wait for authentication to complete
      await authHelper.waitForAuth(10000)

      const authState = await authHelper.detectAuthState()
      expect(authState).toBe('logged_in')
    })

    it('should detect unknown state on ambiguous pages', async () => {
      await page.goto(`${TEST_CONFIG.baseUrl}/about`)

      const authState = await authHelper.detectAuthState()
      expect(['logged_out', 'unknown']).toContain(authState)
    })
  })

  describe('Reliable Login Functionality', () => {
    it('should successfully log in with correct credentials', async () => {
      const loginResult = await authHelper.reliableLogin()

      // Should complete without throwing
      expect(loginResult).toBeUndefined()

      // Verify we're no longer on login page
      const currentUrl = page.url()
      expect(currentUrl).not.toContain('/login')

      // Verify authentication state
      const authState = await authHelper.detectAuthState()
      expect(authState).toBe('logged_in')
    })

    it('should handle already authenticated state gracefully', async () => {
      // First login
      await authHelper.reliableLogin()

      // Second login attempt should skip actual login
      const startTime = Date.now()
      await authHelper.reliableLogin()
      const endTime = Date.now()

      // Should complete quickly (less than 5 seconds) if already authenticated
      expect(endTime - startTime).toBeLessThan(5000)

      const authState = await authHelper.detectAuthState()
      expect(authState).toBe('logged_in')
    })

    it('should retry login on transient failures', async () => {
      // Create helper with limited retries for faster test
      const limitedHelper = new PuppeteerAuthHelper(page, {
        username: TEST_CONFIG.username,
        password: TEST_CONFIG.password,
        maxRetries: 2,
        enableLogging: false,
      })

      // Mock a transient failure by briefly making selectors unavailable
      const originalWaitForSelector = page.waitForSelector
      let callCount = 0

      page.waitForSelector = jest
        .fn()
        .mockImplementation(async (selector, options) => {
          callCount++
          if (
            callCount <= 2 &&
            selector === '[data-testid="auth-login-form"]'
          ) {
            throw new Error('Transient failure')
          }
          return originalWaitForSelector.call(page, selector, options)
        })

      // Should succeed despite initial failures
      await limitedHelper.reliableLogin()

      const authState = await limitedHelper.detectAuthState()
      expect(authState).toBe('logged_in')

      // Restore original method
      page.waitForSelector = originalWaitForSelector
    })

    it('should fail gracefully with invalid credentials', async () => {
      const invalidHelper = new PuppeteerAuthHelper(page, {
        username: 'invalid_user',
        password: 'invalid_password',
        maxRetries: 1, // Limit retries for faster test
        enableLogging: false,
      })

      await expect(invalidHelper.reliableLogin()).rejects.toThrow()
    })
  })

  describe('UI Element Isolation', () => {
    it('should find auth-ui-controls area without accidentally clicking', async () => {
      await page.goto(`${TEST_CONFIG.baseUrl}/login`)

      // Wait for page to load
      await page.waitForSelector('[data-testid="auth-login-area"]', {
        timeout: 10000,
      })

      // Verify UI controls area exists and has proper isolation attributes
      const uiControlsArea = await page.$('[data-testid="auth-ui-controls"]')
      expect(uiControlsArea).toBeTruthy()

      // Verify automation ignore attribute
      const automationIgnore = await page.$('[data-automation="ignore"]')
      expect(automationIgnore).toBeTruthy()

      // Verify login area is separate and accessible
      const loginArea = await page.$('[data-testid="auth-login-area"]')
      expect(loginArea).toBeTruthy()
    })

    it('should access language switcher and theme toggle without interference', async () => {
      await page.goto(`${TEST_CONFIG.baseUrl}/login`)

      // Wait for UI to load
      await page.waitForSelector('[data-testid="language-switcher"]', {
        timeout: 10000,
      })

      // Verify elements exist with proper test IDs
      const languageSwitcher = await page.$('[data-testid="language-switcher"]')
      expect(languageSwitcher).toBeTruthy()

      const themeToggle = await page.$('[data-testid="theme-toggle"]')
      expect(themeToggle).toBeTruthy()

      // Test that clicking these elements doesn't interfere with subsequent auth
      await languageSwitcher!.click()
      await page.waitForTimeout(500)

      // Should still be able to authenticate successfully
      await authHelper.reliableLogin()
      const authState = await authHelper.detectAuthState()
      expect(authState).toBe('logged_in')
    })
  })

  describe('Language Switch Recovery', () => {
    it('should recover from language switch during authentication flow', async () => {
      await page.goto(`${TEST_CONFIG.baseUrl}/login`)

      // Wait for page to load
      await page.waitForSelector('[data-testid="language-switcher"]', {
        timeout: 10000,
      })

      // Click language switcher to change language
      const languageSwitcher = await page.$('[data-testid="language-switcher"]')
      if (languageSwitcher) {
        await languageSwitcher.click()
        await page.waitForTimeout(1000)
      }

      // Attempt recovery
      await authHelper.recoverFromLanguageSwitch()

      // Should still be able to authenticate after recovery
      await authHelper.reliableLogin()
      const authState = await authHelper.detectAuthState()
      expect(authState).toBe('logged_in')
    })

    it('should handle missing language switcher gracefully', async () => {
      await page.goto(`${TEST_CONFIG.baseUrl}/login`)

      // Hide language switcher with CSS
      await page.addStyleTag({
        content:
          '[data-testid="language-switcher"] { display: none !important; }',
      })

      // Should not throw error even when switcher is not available
      await expect(
        authHelper.recoverFromLanguageSwitch()
      ).resolves.not.toThrow()
    })
  })

  describe('Authentication Persistence', () => {
    it('should maintain authentication across page navigation', async () => {
      // Login first
      await authHelper.reliableLogin()

      // Navigate to different pages
      await page.goto(`${TEST_CONFIG.baseUrl}/projects`)
      await page.waitForSelector('body', { timeout: 10000 })

      let authState = await authHelper.detectAuthState()
      expect(authState).toBe('logged_in')

      // Navigate to admin page if user has access
      try {
        await page.goto(`${TEST_CONFIG.baseUrl}/admin/users`)
        await page.waitForSelector('body', { timeout: 5000 })

        authState = await authHelper.detectAuthState()
        expect(['logged_in', 'unknown']).toContain(authState) // May vary based on permissions
      } catch (error) {
        // Admin page may not be accessible for test user, that's okay
        console.log('Admin page not accessible for test user:', error.message)
      }
    })

    it('should detect session expiration', async () => {
      // Login first
      await authHelper.reliableLogin()

      // Clear authentication cookies/localStorage to simulate session expiration
      await page.evaluate(() => {
        localStorage.clear()
        sessionStorage.clear()
      })

      await page.deleteCookie()

      // Navigate to protected page
      await page.goto(`${TEST_CONFIG.baseUrl}/projects`)
      await page.waitForTimeout(2000)

      const authState = await authHelper.detectAuthState()
      expect(authState).toBe('logged_out')
    })
  })

  describe('Error Handling and Recovery', () => {
    it('should handle network timeouts gracefully', async () => {
      // Create helper with very short timeout to force timeout
      const timeoutHelper = new PuppeteerAuthHelper(page, {
        username: TEST_CONFIG.username,
        password: TEST_CONFIG.password,
        timeout: 100, // Very short timeout
        maxRetries: 1,
        enableLogging: false,
      })

      await expect(timeoutHelper.reliableLogin()).rejects.toThrow()
    })

    it('should reset UI state after failures', async () => {
      // Navigate to a non-login page first
      await page.goto(`${TEST_CONFIG.baseUrl}/about`)

      // Attempt to reset UI state
      await authHelper.resetUIState()

      // Should be on login page after reset
      const currentUrl = page.url()
      expect(currentUrl).toContain('/login')

      // Should be able to authenticate after reset
      await authHelper.reliableLogin()
      const authState = await authHelper.detectAuthState()
      expect(authState).toBe('logged_in')
    })

    it('should bypass auto-authentication when requested', async () => {
      await page.goto(`${TEST_CONFIG.baseUrl}/login`)

      // Bypass auto-auth
      await authHelper.bypassAutoAuth()

      // Should still be able to perform manual authentication
      await authHelper.reliableLogin()
      const authState = await authHelper.detectAuthState()
      expect(authState).toBe('logged_in')
    })
  })

  describe('Wait for Authentication', () => {
    it('should wait for authentication with reasonable timeout', async () => {
      // Start login process
      const loginPromise = authHelper.reliableLogin()

      // Wait for authentication in parallel
      const waitPromise = authHelper.waitForAuth(30000)

      const [loginResult, waitResult] = await Promise.all([
        loginPromise,
        waitPromise,
      ])

      expect(waitResult).toBe(true)
    })

    it('should timeout when authentication never occurs', async () => {
      await page.goto(`${TEST_CONFIG.baseUrl}/login`)

      // Don't perform login, just wait
      const result = await authHelper.waitForAuth(2000)
      expect(result).toBe(false)
    })
  })

  describe('Real-world Scenarios', () => {
    it('should handle complete workflow from login to protected resource access', async () => {
      // 1. Start from login page
      await page.goto(`${TEST_CONFIG.baseUrl}/login`)

      // 2. Verify initial state
      let authState = await authHelper.detectAuthState()
      expect(authState).toBe('logged_out')

      // 3. Perform authentication
      await authHelper.reliableLogin()

      // 4. Verify authentication
      authState = await authHelper.detectAuthState()
      expect(authState).toBe('logged_in')

      // 5. Access protected resource
      await page.goto(`${TEST_CONFIG.baseUrl}/projects`)
      await page.waitForSelector('[data-testid="projects-table"]', {
        timeout: 15000,
      })

      // 6. Verify still authenticated
      authState = await authHelper.detectAuthState()
      expect(authState).toBe('logged_in')

      // 7. Verify page content loaded correctly
      const projectsTable = await page.$('[data-testid="projects-table"]')
      expect(projectsTable).toBeTruthy()
    })

    it('should handle rapid successive login attempts', async () => {
      const attempts = 3
      const results = []

      for (let i = 0; i < attempts; i++) {
        try {
          await authHelper.reliableLogin()
          const authState = await authHelper.detectAuthState()
          results.push(authState === 'logged_in')
        } catch (error) {
          results.push(false)
        }
      }

      // At least the first attempt should succeed
      expect(results[0]).toBe(true)

      // Subsequent attempts should either succeed or skip (already authenticated)
      const allSuccessful = results.every((result) => result === true)
      expect(allSuccessful).toBe(true)
    })

    it('should maintain performance within acceptable limits', async () => {
      const startTime = Date.now()

      await authHelper.reliableLogin()

      const endTime = Date.now()
      const duration = endTime - startTime

      // Authentication should complete within 30 seconds
      expect(duration).toBeLessThan(30000)

      // Log performance for monitoring
      console.log(`Authentication completed in ${duration}ms`)
    })
  })
})
