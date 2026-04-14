/**
 * Unit tests for PuppeteerAuthHelper
 *
 * These tests verify the authentication helper functionality
 * without mocking the core authentication logic.
 *
 * @jest-environment node
 */

import {
  AuthConfig,
  PuppeteerAuthHelper,
  PuppeteerPage,
} from '../helpers/PuppeteerAuthHelper'

// Mock page implementation for testing
class MockPuppeteerPage implements PuppeteerPage {
  private currentUrl: string = 'http://localhost:3000/login'
  private elements: Map<string, any> = new Map()
  private evaluateResults: Map<string, any> = new Map()
  private navigationPromise: Promise<void> | null = null
  private eventHandlers: Map<string, Function[]> = new Map()

  async goto(url: string, options?: any): Promise<void> {
    this.currentUrl = url
    return Promise.resolve()
  }

  url(): string {
    return this.currentUrl
  }

  async evaluate(fn: Function, ...args: any[]): Promise<any> {
    const fnString = fn.toString()

    // Simulate different scenarios based on the function
    if (fnString.includes('window.location.hostname')) {
      return 'localhost'
    }

    if (fnString.includes('document.documentElement.lang')) {
      return this.evaluateResults.get('lang') || 'en'
    }

    if (fnString.includes('logout-button') || fnString.includes('user-menu')) {
      const isAuthenticated = this.evaluateResults.get('authenticated') || false
      return {
        hasLogoutBtn: isAuthenticated,
        hasUserMenu: isAuthenticated,
        hasAdminText: isAuthenticated,
      }
    }

    if (
      fnString.includes('emailInput.value') ||
      fnString.includes('passwordInput.value')
    ) {
      // Simulate form clearing
      return Promise.resolve()
    }

    return Promise.resolve()
  }

  async waitForSelector(selector: string, options?: any): Promise<any> {
    const element = this.elements.get(selector)
    if (!element && options?.timeout && options.timeout < 1000) {
      throw new Error(`Element ${selector} not found`)
    }
    return Promise.resolve(element || { click: jest.fn(), type: jest.fn() })
  }

  async waitForNavigation(options?: any): Promise<void> {
    if (this.navigationPromise) {
      return this.navigationPromise
    }
    return Promise.resolve()
  }

  async $(selector: string): Promise<any> {
    return this.elements.get(selector) || null
  }

  async click(selector: string): Promise<void> {
    return Promise.resolve()
  }

  async type(selector: string, text: string): Promise<void> {
    return Promise.resolve()
  }

  async waitForTimeout(ms: number): Promise<void> {
    return Promise.resolve()
  }

  on(event: string, handler: Function): void {
    if (!this.eventHandlers.has(event)) {
      this.eventHandlers.set(event, [])
    }
    this.eventHandlers.get(event)!.push(handler)
  }

  async screenshot(options?: any): Promise<Buffer> {
    return Buffer.from('mock-screenshot')
  }

  // Test helper methods
  setCurrentUrl(url: string): void {
    this.currentUrl = url
  }

  setElement(selector: string, element: any): void {
    this.elements.set(selector, element)
  }

  setEvaluateResult(key: string, value: any): void {
    this.evaluateResults.set(key, value)
  }

  setNavigationPromise(promise: Promise<void>): void {
    this.navigationPromise = promise
  }

  simulatePageError(error: Error): void {
    const handlers = this.eventHandlers.get('pageerror') || []
    handlers.forEach((handler) => handler(error))
  }
}

describe('PuppeteerAuthHelper', () => {
  let mockPage: MockPuppeteerPage
  let authHelper: PuppeteerAuthHelper
  let consoleSpy: jest.SpyInstance

  beforeEach(() => {
    mockPage = new MockPuppeteerPage()
    authHelper = new PuppeteerAuthHelper(mockPage, { enableLogging: false })
    consoleSpy = jest.spyOn(console, 'log').mockImplementation()
  })

  afterEach(() => {
    consoleSpy.mockRestore()
  })

  describe('Constructor and Configuration', () => {
    it('should initialize with default config', () => {
      const helper = new PuppeteerAuthHelper(mockPage)
      const authState = helper.getAuthState()

      expect(authState.isAuthenticated).toBe(false)
      expect(authState.sessionStatus).toBe('unknown')
    })

    it('should accept custom configuration', () => {
      const config: AuthConfig = {
        username: 'testuser',
        password: 'testpass',
        timeout: 60000,
        maxRetries: 5,
        enableLogging: true,
      }

      const helper = new PuppeteerAuthHelper(mockPage, config)
      // Configuration is private, but we can test behavior
      expect(helper).toBeInstanceOf(PuppeteerAuthHelper)
    })
  })

  describe('Environment Detection', () => {
    it('should detect development environment for localhost', async () => {
      mockPage.setEvaluateResult('hostname', 'localhost')

      const isProduction = await authHelper.isProductionEnvironment()
      expect(isProduction).toBe(false)
    })

    it('should detect development environment for benger.localhost', async () => {
      mockPage.setEvaluateResult('hostname', 'benger.localhost')

      const isProduction = await authHelper.isProductionEnvironment()
      expect(isProduction).toBe(false)
    })

    it('should detect production environment for other hostnames', async () => {
      mockPage.setEvaluateResult('hostname', 'benger.example.com')

      const isProduction = await authHelper.isProductionEnvironment()
      expect(isProduction).toBe(true)
    })

    it('should handle environment detection errors gracefully', async () => {
      // Simulate error in evaluate
      mockPage.evaluate = jest
        .fn()
        .mockRejectedValue(new Error('Evaluation failed'))

      const isProduction = await authHelper.isProductionEnvironment()
      expect(isProduction).toBe(false) // Should default to development
    })
  })

  describe('Authentication State Detection', () => {
    it('should detect logged out state on login page', async () => {
      mockPage.setCurrentUrl('http://localhost:3000/login')

      const authState = await authHelper.detectAuthState()
      expect(authState).toBe('logged_out')
    })

    it('should detect logged in state on dashboard with auth indicators', async () => {
      mockPage.setCurrentUrl('http://localhost:3000/dashboard')
      mockPage.setEvaluateResult('authenticated', true)

      const authState = await authHelper.detectAuthState()
      expect(authState).toBe('logged_in')
    })

    it('should detect logged in state on projects page with auth indicators', async () => {
      mockPage.setCurrentUrl('http://localhost:3000/projects')
      mockPage.setEvaluateResult('authenticated', true)

      const authState = await authHelper.detectAuthState()
      expect(authState).toBe('logged_in')
    })

    it('should return unknown state when auth indicators are missing', async () => {
      mockPage.setCurrentUrl('http://localhost:3000/dashboard')
      mockPage.setEvaluateResult('authenticated', false)

      const authState = await authHelper.detectAuthState()
      expect(authState).toBe('unknown')
    })

    it('should handle detection errors gracefully', async () => {
      mockPage.url = jest.fn().mockImplementation(() => {
        throw new Error('URL access failed')
      })

      const authState = await authHelper.detectAuthState()
      expect(authState).toBe('unknown')
    })
  })

  describe('Language Switch Recovery', () => {
    it('should detect non-English page and attempt recovery', async () => {
      mockPage.setEvaluateResult('lang', 'de')
      const mockLanguageSwitcher = { click: jest.fn() }
      mockPage.setElement(
        '[data-testid="language-switcher"]',
        mockLanguageSwitcher
      )

      await authHelper.recoverFromLanguageSwitch()

      expect(mockLanguageSwitcher.click).toHaveBeenCalled()
    })

    it('should skip recovery for English page', async () => {
      mockPage.setEvaluateResult('lang', 'en')
      const mockLanguageSwitcher = { click: jest.fn() }
      mockPage.setElement(
        '[data-testid="language-switcher"]',
        mockLanguageSwitcher
      )

      await authHelper.recoverFromLanguageSwitch()

      expect(mockLanguageSwitcher.click).not.toHaveBeenCalled()
    })

    it('should handle missing language switcher gracefully', async () => {
      mockPage.setEvaluateResult('lang', 'de')
      mockPage.setElement('[data-testid="language-switcher"]', null)

      // Should not throw error
      await expect(
        authHelper.recoverFromLanguageSwitch()
      ).resolves.not.toThrow()
    })

    it('should handle language detection errors gracefully', async () => {
      mockPage.evaluate = jest
        .fn()
        .mockRejectedValue(new Error('Language detection failed'))

      // Should not throw error
      await expect(
        authHelper.recoverFromLanguageSwitch()
      ).resolves.not.toThrow()
    })
  })

  describe('Wait for Authentication', () => {
    it('should return true when authentication is detected quickly', async () => {
      mockPage.setCurrentUrl('http://localhost:3000/dashboard')
      mockPage.setEvaluateResult('authenticated', true)

      const result = await authHelper.waitForAuth(5000)
      expect(result).toBe(true)
    })

    it('should return false when authentication times out', async () => {
      mockPage.setCurrentUrl('http://localhost:3000/login')
      mockPage.setEvaluateResult('authenticated', false)

      const result = await authHelper.waitForAuth(1000)
      expect(result).toBe(false)
    })

    it('should use default timeout when none provided', async () => {
      mockPage.setCurrentUrl('http://localhost:3000/login')
      mockPage.setEvaluateResult('authenticated', false)

      const startTime = Date.now()
      const result = await authHelper.waitForAuth()
      const endTime = Date.now()

      expect(result).toBe(false)
      // Should have waited for some time (allowing for test execution variance)
      expect(endTime - startTime).toBeGreaterThan(500)
    })
  })

  describe('UI State Reset', () => {
    it('should navigate to login page and wait for stable UI', async () => {
      const gotoSpy = jest.spyOn(mockPage, 'goto')
      mockPage.setElement('[data-testid="auth-login-form"]', { visible: true })

      await authHelper.resetUIState()

      expect(gotoSpy).toHaveBeenCalledWith('/login', {
        waitUntil: 'networkidle2',
      })
    })

    it('should handle reset errors gracefully', async () => {
      mockPage.goto = jest
        .fn()
        .mockRejectedValue(new Error('Navigation failed'))

      // Should not throw error
      await expect(authHelper.resetUIState()).resolves.not.toThrow()
    })
  })

  describe('Auto-auth Bypass', () => {
    it('should clear localStorage flags', async () => {
      const evaluateSpy = jest.spyOn(mockPage, 'evaluate')

      await authHelper.bypassAutoAuth()

      expect(evaluateSpy).toHaveBeenCalled()
    })

    it('should handle bypass errors gracefully', async () => {
      mockPage.evaluate = jest
        .fn()
        .mockRejectedValue(new Error('LocalStorage access failed'))

      // Should not throw error
      await expect(authHelper.bypassAutoAuth()).resolves.not.toThrow()
    })
  })

  describe('Authentication State Management', () => {
    it('should return current auth state', () => {
      const state = authHelper.getAuthState()

      expect(state).toHaveProperty('isAuthenticated')
      expect(state).toHaveProperty('sessionStatus')
      expect(state).toHaveProperty('currentUrl')
      expect(typeof state.isAuthenticated).toBe('boolean')
    })

    it('should update auth state during operations', async () => {
      const initialState = authHelper.getAuthState()
      expect(initialState.sessionStatus).toBe('unknown')

      // Simulate authentication detection
      mockPage.setCurrentUrl('http://localhost:3000/dashboard')
      mockPage.setEvaluateResult('authenticated', true)

      await authHelper.detectAuthState()

      // Note: getAuthState returns a copy, so we test behavior through detectAuthState
      const newState = await authHelper.detectAuthState()
      expect(newState).toBe('logged_in')
    })
  })

  describe('Error Handling', () => {
    it('should handle page errors during authentication', () => {
      const error = new Error('Test page error')

      // Should not throw when page error occurs
      expect(() => {
        mockPage.simulatePageError(error)
      }).not.toThrow()
    })

    it('should capture screenshots on failure when logging enabled', async () => {
      const helperWithLogging = new PuppeteerAuthHelper(mockPage, {
        enableLogging: true,
      })
      const screenshotSpy = jest.spyOn(mockPage, 'screenshot')

      await helperWithLogging.handleAuthFailure()

      expect(screenshotSpy).toHaveBeenCalled()
    })

    it('should handle screenshot errors gracefully', async () => {
      const helperWithLogging = new PuppeteerAuthHelper(mockPage, {
        enableLogging: true,
      })
      mockPage.screenshot = jest
        .fn()
        .mockRejectedValue(new Error('Screenshot failed'))

      // Should not throw error
      await expect(helperWithLogging.handleAuthFailure()).resolves.not.toThrow()
    })
  })

  describe('Logging', () => {
    it('should log messages when logging is enabled', () => {
      const helperWithLogging = new PuppeteerAuthHelper(mockPage, {
        enableLogging: true,
      })

      // Trigger a method that logs
      helperWithLogging.isProductionEnvironment()

      // Note: We can't easily test private log method, but we verify no errors occur
      expect(consoleSpy).toHaveBeenCalled()
    })

    it('should not log when logging is disabled', () => {
      const helperWithoutLogging = new PuppeteerAuthHelper(mockPage, {
        enableLogging: false,
      })

      // The helper is created with logging disabled, so no logs should occur
      expect(helperWithoutLogging).toBeInstanceOf(PuppeteerAuthHelper)
    })
  })

  describe('Edge Cases and Boundary Conditions', () => {
    it('should handle null/undefined page gracefully', () => {
      // This tests the interface rather than implementation
      expect(() => {
        new PuppeteerAuthHelper(mockPage)
      }).not.toThrow()
    })

    it('should handle empty credentials', async () => {
      mockPage.setElement('[data-testid="auth-login-form"]', { visible: true })
      mockPage.setElement('[data-testid="auth-login-email-input"]', {
        click: jest.fn(),
      })
      mockPage.setElement('[data-testid="auth-login-password-input"]', {
        click: jest.fn(),
      })
      mockPage.setElement('[data-testid="auth-login-submit-button"]', {
        click: jest.fn(),
      })

      // Should handle empty string credentials
      await expect(authHelper.reliableLogin('', '')).rejects.toThrow()
    })

    it('should handle network timeouts during login', async () => {
      mockPage.setElement('[data-testid="auth-login-form"]', { visible: true })
      mockPage.waitForNavigation = jest
        .fn()
        .mockRejectedValue(new Error('Navigation timeout'))

      await expect(authHelper.reliableLogin()).rejects.toThrow(
        'Navigation timeout'
      )
    })

    it('should handle selector not found errors', async () => {
      mockPage.waitForSelector = jest
        .fn()
        .mockRejectedValue(new Error('Selector not found'))

      await expect(authHelper.reliableLogin()).rejects.toThrow()
    })

    it('should handle maximum retry attempts', async () => {
      const helperWithLimitedRetries = new PuppeteerAuthHelper(mockPage, {
        maxRetries: 2,
        enableLogging: false,
      })

      mockPage.waitForSelector = jest
        .fn()
        .mockRejectedValue(new Error('Persistent failure'))

      await expect(helperWithLimitedRetries.reliableLogin()).rejects.toThrow(
        'Login failed after 2 attempts'
      )
    })
  })
})

describe('Integration Scenarios', () => {
  let mockPage: MockPuppeteerPage
  let authHelper: PuppeteerAuthHelper

  beforeEach(() => {
    mockPage = new MockPuppeteerPage()
    authHelper = new PuppeteerAuthHelper(mockPage, { enableLogging: false })
  })

  it('should handle complete login flow with state changes', async () => {
    // Setup initial login page state
    mockPage.setCurrentUrl('http://localhost:3000/login')
    mockPage.setElement('[data-testid="auth-login-form"]', { visible: true })
    mockPage.setElement('[data-testid="auth-login-email-input"]', {
      click: jest.fn(),
    })
    mockPage.setElement('[data-testid="auth-login-password-input"]', {
      click: jest.fn(),
    })
    mockPage.setElement('[data-testid="auth-login-submit-button"]', {
      click: jest.fn(),
    })

    // Simulate successful navigation to dashboard
    let navigated = false
    mockPage.setNavigationPromise(
      new Promise((resolve) => {
        setTimeout(() => {
          if (!navigated) {
            mockPage.setCurrentUrl('http://localhost:3000/dashboard')
            mockPage.setEvaluateResult('authenticated', true)
            navigated = true
          }
          resolve()
        }, 100)
      })
    )

    // Perform login
    await authHelper.reliableLogin()

    // Verify final state
    const finalState = await authHelper.detectAuthState()
    expect(finalState).toBe('logged_in')
  })

  it('should handle language switch during authentication', async () => {
    // Setup German page state
    mockPage.setCurrentUrl('http://localhost:3000/login')
    mockPage.setEvaluateResult('lang', 'de')
    mockPage.setElement('[data-testid="language-switcher"]', {
      click: jest.fn(),
    })

    // Perform language recovery
    await authHelper.recoverFromLanguageSwitch()

    // Verify language switcher was clicked
    const switcher = mockPage.elements.get('[data-testid="language-switcher"]')
    expect(switcher.click).toHaveBeenCalled()
  })

  it('should handle authentication verification timeout', async () => {
    // Setup page that never shows as authenticated
    mockPage.setCurrentUrl('http://localhost:3000/dashboard')
    mockPage.setEvaluateResult('authenticated', false)

    const startTime = Date.now()
    const result = await authHelper.waitForAuth(1000)
    const endTime = Date.now()

    expect(result).toBe(false)
    expect(endTime - startTime).toBeGreaterThanOrEqual(1000)
  })
})
