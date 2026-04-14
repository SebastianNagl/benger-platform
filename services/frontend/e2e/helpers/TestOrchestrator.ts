/**
 * TestOrchestrator - Advanced E2E Test Infrastructure
 *
 * Manages multi-user scenarios, parallel execution, and data consistency
 * for comprehensive end-to-end testing
 *
 * Part of Issue #471 Implementation
 */

import {
  Browser,
  BrowserContext,
  Page,
  chromium,
  devices,
} from '@playwright/test'

export interface UserConfig {
  email: string
  password?: string
  role:
    | 'superadmin'
    | 'org_admin'
    | 'contributor'
    | 'annotator'
    | 'user'
    | 'project_manager'
    | 'reviewer'
  organization?: string
  device?: string
  locale?: string
  timezone?: string
  permissions?: string[]
}

export interface UserAction {
  execute: (page: Page) => Promise<any>
}

export interface DataSnapshot {
  userId: string
  timestamp: number
  data: any
}

export class TestOrchestrator {
  private browsers: Map<string, Browser> = new Map()
  private contexts: Map<string, BrowserContext> = new Map()
  private pages: Map<string, Page> = new Map()
  private baseUrl: string
  private sharedBrowser: Browser | null = null

  constructor(baseUrl: string = '/') {
    // Use PLAYWRIGHT_BASE_URL if available, otherwise construct from baseUrl
    const envBaseUrl = process.env.PLAYWRIGHT_BASE_URL
    if (envBaseUrl) {
      this.baseUrl = envBaseUrl
    } else if (baseUrl === '/') {
      this.baseUrl = 'http://localhost:3000'
    } else {
      this.baseUrl = baseUrl
    }
  }

  /**
   * Setup multi-user scenario with browser contexts
   * Uses a shared browser instance to reduce resource usage
   */
  async setupMultiUserScenario(users: UserConfig[]): Promise<void> {
    // Launch single shared browser instance for all users (reduces resource usage)
    if (!this.sharedBrowser) {
      this.sharedBrowser = await chromium.launch({ headless: true })
    }

    for (const user of users) {
      // Create context with device emulation if specified
      const contextOptions: any = {
        locale: user.locale || 'en-US',
        timezoneId: user.timezone || 'UTC',
        permissions: user.permissions || [],
      }

      // Add device emulation if specified
      if (user.device && devices[user.device]) {
        Object.assign(contextOptions, devices[user.device])
      }

      // Use shared browser, create new context per user for isolation
      const context = await this.sharedBrowser.newContext(contextOptions)
      const page = await context.newPage()

      // Login the user
      await this.loginUser(page, user)

      // Store references
      this.contexts.set(user.email, context)
      this.pages.set(user.email, page)
    }
  }

  /**
   * Login a user with given credentials
   * Uses data-testid selectors that match the login form implementation
   * Includes retry logic for infrastructure flakiness (traefik 404s, slow loads)
   */
  private async loginUser(page: Page, user: UserConfig): Promise<void> {
    // Navigate to login page with retry logic for traefik's intermittent 404s
    let navigationSuccess = false
    for (let navAttempt = 1; navAttempt <= 5; navAttempt++) {
      try {
        if (navAttempt > 1) {
          const delay = 500 * navAttempt
          console.log(`⏳ Navigation retry ${navAttempt}/5 for /login after ${delay}ms delay...`)
          await page.waitForTimeout(delay)
        }

        const response = await page.goto(`${this.baseUrl}/login`, {
          waitUntil: 'domcontentloaded',
          timeout: 15000,
        })

        // Check for 404 or other error response
        if (response && response.status() >= 400) {
          console.log(`⚠️  Navigation returned ${response.status()}, retrying...`)
          continue
        }

        navigationSuccess = true
        break
      } catch (error) {
        if (navAttempt === 5) {
          throw new Error(`Navigation to /login failed after 5 attempts: ${error}`)
        }
        console.log(`⚠️  Navigation error, retrying: ${error}`)
      }
    }

    if (!navigationSuccess) {
      throw new Error('Failed to navigate to login page after 5 attempts')
    }

    // Wait a bit for potential auto-login redirect
    await page.waitForTimeout(2000)

    // Check if already logged in (auto-login redirected away from login page)
    if (!page.url().includes('/login')) {
      console.log(`User ${user.email} already logged in via auto-login`)
      return
    }

    // Wait for login form using data-testid selectors with retry logic
    const emailInput = page.locator('[data-testid="auth-login-email-input"]')
    const passwordInput = page.locator('[data-testid="auth-login-password-input"]')
    const submitButton = page.locator('[data-testid="auth-login-submit-button"]')

    // Wait for form to be visible with retry logic for slow page rendering
    let formVisible = false
    for (let formAttempt = 1; formAttempt <= 5; formAttempt++) {
      try {
        if (formAttempt > 1) {
          console.log(`⏳ Form load retry ${formAttempt}/5 for ${user.email}...`)
          await page.waitForTimeout(1000)
        }
        await emailInput.waitFor({ state: 'visible', timeout: 5000 })
        formVisible = true
        break
      } catch (error) {
        if (formAttempt === 5) {
          throw new Error(`Login form not visible after 5 attempts for ${user.email}`)
        }
      }
    }

    if (!formVisible) {
      throw new Error(`Login form never became visible for ${user.email}`)
    }

    // Fill login form
    const username = user.email.includes('@') ? user.email.split('@')[0] : user.email
    await emailInput.fill(username)
    await passwordInput.fill(user.password || 'admin')
    await submitButton.click()

    // Wait for successful login - either redirect or user indicator appearing
    await Promise.race([
      page.waitForURL(/\/(dashboard|tasks|projects)/, { timeout: 30000 }),
      page.waitForSelector(`button:has-text("${username}")`, { timeout: 30000 }),
      page.waitForSelector('[class*="sidebar"]', { timeout: 30000 }),
    ]).catch(() => {
      console.log(`Login wait completed for ${user.email}`)
    })

    // Final check - ensure not on login page
    await page.waitForTimeout(1000)
    if (page.url().includes('/login')) {
      throw new Error(`Login failed for user ${user.email} - still on login page`)
    }

    console.log(`User ${user.email} logged in successfully`)
  }

  /**
   * Get page for a specific user
   */
  getPage(userEmail: string): Page {
    const page = this.pages.get(userEmail)
    if (!page) {
      throw new Error(`No page found for user: ${userEmail}`)
    }
    return page
  }

  /**
   * Execute action for a specific user
   */
  async executeForUser(
    userEmail: string,
    action: (page: Page) => Promise<any>
  ): Promise<any> {
    const page = this.getPage(userEmail)
    return await action(page)
  }

  /**
   * Execute actions in parallel across multiple users
   */
  async executeParallel(
    actions: Array<{ user: string; action: (page: Page) => Promise<any> }>
  ): Promise<any[]> {
    const promises = actions.map(async ({ user, action }) => {
      const page = this.getPage(user)
      return await action(page)
    })

    return await Promise.all(promises)
  }

  /**
   * Capture data snapshot for a context
   */
  private async captureDataSnapshot(userEmail: string): Promise<DataSnapshot> {
    const page = this.getPage(userEmail)

    // Capture various data points
    const snapshot = await page.evaluate(() => {
      return {
        localStorage: { ...localStorage },
        sessionStorage: { ...sessionStorage },
        cookies: document.cookie,
        url: window.location.href,
        // Add custom app state if available
        appState: (window as any).__APP_STATE__ || null,
      }
    })

    return {
      userId: userEmail,
      timestamp: Date.now(),
      data: snapshot,
    }
  }

  /**
   * Compare snapshots for consistency
   */
  private compareSnapshots(snapshots: DataSnapshot[]): {
    allConsistent: boolean
    differences: any[]
  } {
    const differences: any[] = []
    let allConsistent = true

    // Compare each snapshot with the first one as reference
    const reference = snapshots[0]

    for (let i = 1; i < snapshots.length; i++) {
      const current = snapshots[i]

      // Compare URLs (accounting for user-specific paths)
      const refUrl = new URL(reference.data.url)
      const currUrl = new URL(current.data.url)

      if (
        refUrl.pathname !== currUrl.pathname &&
        !this.isUserSpecificPath(refUrl.pathname) &&
        !this.isUserSpecificPath(currUrl.pathname)
      ) {
        differences.push({
          type: 'url',
          user1: reference.userId,
          user2: current.userId,
          value1: refUrl.pathname,
          value2: currUrl.pathname,
        })
        allConsistent = false
      }

      // Compare app state if available
      if (reference.data.appState && current.data.appState) {
        const stateDiff = this.compareObjects(
          reference.data.appState,
          current.data.appState
        )
        if (stateDiff.length > 0) {
          differences.push({
            type: 'appState',
            user1: reference.userId,
            user2: current.userId,
            differences: stateDiff,
          })
          allConsistent = false
        }
      }
    }

    return { allConsistent, differences }
  }

  /**
   * Check if a path is user-specific
   */
  private isUserSpecificPath(path: string): boolean {
    const userSpecificPatterns = [
      /\/users\/[^\/]+/,
      /\/profile/,
      /\/settings/,
      /\/dashboard/,
    ]

    return userSpecificPatterns.some((pattern) => pattern.test(path))
  }

  /**
   * Compare two objects and return differences
   */
  private compareObjects(obj1: any, obj2: any, path: string = ''): any[] {
    const differences: any[] = []

    // Get all keys from both objects
    const keys = new Set([
      ...Object.keys(obj1 || {}),
      ...Object.keys(obj2 || {}),
    ])

    for (const key of keys) {
      const currentPath = path ? `${path}.${key}` : key

      if (!(key in obj1)) {
        differences.push({
          path: currentPath,
          type: 'missing_in_first',
          value: obj2[key],
        })
      } else if (!(key in obj2)) {
        differences.push({
          path: currentPath,
          type: 'missing_in_second',
          value: obj1[key],
        })
      } else if (typeof obj1[key] !== typeof obj2[key]) {
        differences.push({
          path: currentPath,
          type: 'type_mismatch',
          value1: obj1[key],
          value2: obj2[key],
        })
      } else if (typeof obj1[key] === 'object' && obj1[key] !== null) {
        // Recursively compare nested objects
        const nestedDiff = this.compareObjects(
          obj1[key],
          obj2[key],
          currentPath
        )
        differences.push(...nestedDiff)
      } else if (obj1[key] !== obj2[key]) {
        // Skip certain fields that are expected to be different
        const skipFields = ['timestamp', 'lastUpdated', 'sessionId', 'userId']
        if (!skipFields.includes(key)) {
          differences.push({
            path: currentPath,
            type: 'value_mismatch',
            value1: obj1[key],
            value2: obj2[key],
          })
        }
      }
    }

    return differences
  }

  /**
   * Verify data consistency across all contexts
   */
  async verifyDataConsistency(): Promise<{
    allConsistent: boolean
    differences: any[]
  }> {
    const snapshots: DataSnapshot[] = []

    for (const [userEmail, _] of this.contexts) {
      const snapshot = await this.captureDataSnapshot(userEmail)
      snapshots.push(snapshot)
    }

    return this.compareSnapshots(snapshots)
  }

  /**
   * Simulate network conditions for a user
   */
  async simulateNetworkCondition(
    userEmail: string,
    condition: 'offline' | 'slow' | 'fast'
  ): Promise<void> {
    const context = this.contexts.get(userEmail)
    if (!context) {
      throw new Error(`No context found for user: ${userEmail}`)
    }

    switch (condition) {
      case 'offline':
        await context.setOffline(true)
        break
      case 'slow':
        // Simulate slow 3G
        await context.setOffline(false)
        // Note: Playwright doesn't have built-in network throttling,
        // but we can add delays through route interception
        await context.route('**/*', async (route) => {
          await new Promise((resolve) => setTimeout(resolve, 1000)) // 1s delay
          await route.continue()
        })
        break
      case 'fast':
        await context.setOffline(false)
        await context.unroute('**/*')
        break
    }
  }

  /**
   * Cleanup all browsers and contexts
   */
  async cleanup(): Promise<void> {
    // Close all pages
    for (const page of this.pages.values()) {
      await page.close()
    }

    // Close all contexts
    for (const context of this.contexts.values()) {
      await context.close()
    }

    // Close legacy individual browsers (for backwards compatibility)
    for (const browser of this.browsers.values()) {
      await browser.close()
    }

    // Close shared browser if it exists
    if (this.sharedBrowser) {
      await this.sharedBrowser.close()
      this.sharedBrowser = null
    }

    // Clear maps
    this.pages.clear()
    this.contexts.clear()
    this.browsers.clear()
  }

  /**
   * Take screenshots for all users
   */
  async takeScreenshots(namePrefix: string): Promise<Map<string, Buffer>> {
    const screenshots = new Map<string, Buffer>()

    for (const [userEmail, page] of this.pages) {
      const screenshot = await page.screenshot({
        fullPage: true,
      })
      screenshots.set(`${namePrefix}_${userEmail}.png`, screenshot)
    }

    return screenshots
  }

  /**
   * Wait for all users to reach a certain state
   */
  async waitForAllUsers(
    condition: (page: Page) => Promise<boolean>,
    timeout: number = 30000
  ): Promise<boolean> {
    const startTime = Date.now()

    while (Date.now() - startTime < timeout) {
      const results = await Promise.all(
        Array.from(this.pages.values()).map((page) => condition(page))
      )

      if (results.every((result) => result === true)) {
        return true
      }

      await new Promise((resolve) => setTimeout(resolve, 1000))
    }

    return false
  }
}
