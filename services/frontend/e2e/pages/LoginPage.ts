import { Locator, Page } from '@playwright/test'

export class LoginPage {
  readonly page: Page
  readonly emailInput: Locator
  readonly passwordInput: Locator
  readonly loginButton: Locator
  readonly authForm: Locator

  constructor(page: Page) {
    this.page = page
    this.emailInput = page.locator('[data-testid="auth-login-email-input"]')
    this.passwordInput = page.locator(
      '[data-testid="auth-login-password-input"]'
    )
    this.loginButton = page.locator('[data-testid="auth-login-submit-button"]')
    this.authForm = page.locator('[data-testid="auth-login-form"]')
  }

  async goto() {
    await this.page.goto('/login')
  }

  async login(email: string = 'admin', password: string = 'admin') {
    await this.goto()

    // Wait for login form to be visible
    await this.authForm.waitFor({ state: 'visible', timeout: 5000 })

    // Fill login form
    await this.emailInput.fill(email)
    await this.passwordInput.fill(password)

    // Click login button
    await this.loginButton.click()

    // Wait for redirect
    try {
      await this.page.waitForURL(/\/(dashboard|tasks|projects)/, {
        timeout: 10000,
      })
    } catch (error) {
      // Check if already logged in
      const adminText = this.page.locator('text=admin (TUM)')
      const isLoggedIn = await adminText.isVisible()
      if (!isLoggedIn) {
        await this.page.waitForTimeout(2000)
        const currentUrl = this.page.url()
        if (currentUrl.includes('/login')) {
          throw new Error('Login failed - still on login page')
        }
      }
    }
  }
}
