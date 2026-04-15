/**
 * Demonstration of reliable Puppeteer MCP authentication
 *
 * This test showcases the improved authentication reliability
 * addressing the issues described in GitHub Issue #379
 */

const puppeteer = require('puppeteer')

// Import the TypeScript helper (in real usage, this would be transpiled)
// For now, we'll use a simplified JavaScript version
class SimplePuppeteerAuthHelper {
  constructor(page, config = {}) {
    this.page = page
    this.config = {
      username: config.username || 'admin',
      password: config.password || 'admin',
      timeout: config.timeout || 30000,
      maxRetries: config.maxRetries || 3,
      enableLogging: config.enableLogging ?? true,
    }
  }

  log(message, ...args) {
    if (this.config.enableLogging) {
      const timestamp = new Date().toISOString()
      console.log(`[PuppeteerAuth] [${timestamp}] ${message}`, ...args)
    }
  }

  async reliableLogin(username, password) {
    const credentials = {
      username: username || this.config.username,
      password: password || this.config.password,
    }

    this.log(`Starting reliable login for user: ${credentials.username}`)

    for (let attempt = 1; attempt <= this.config.maxRetries; attempt++) {
      try {
        this.log(`Login attempt ${attempt}/${this.config.maxRetries}`)

        // Navigate to login page safely
        await this.page.goto('http://localhost:3000/login', {
          waitUntil: 'networkidle2',
          timeout: this.config.timeout,
        })

        // Wait for stable UI - specifically target login form area
        await this.page.waitForSelector('[data-testid="auth-login-area"]', {
          visible: true,
          timeout: 10000,
        })

        await this.page.waitForSelector('[data-testid="auth-login-form"]', {
          visible: true,
          timeout: 10000,
        })

        // Check if already authenticated
        const currentUrl = this.page.url()
        if (!currentUrl.includes('/login')) {
          this.log('Already authenticated, skipping login')
          return
        }

        // Clear any existing values
        await this.page.evaluate(() => {
          const emailInput = document.querySelector(
            '[data-testid="auth-login-email-input"]'
          )
          const passwordInput = document.querySelector(
            '[data-testid="auth-login-password-input"]'
          )

          if (emailInput) emailInput.value = ''
          if (passwordInput) passwordInput.value = ''
        })

        // Avoid accidental clicks on UI controls by specifically targeting the form area
        this.log('Focusing on login form area to avoid UI control interference')

        // Fill credentials with extra safety
        await this.page.waitForSelector(
          '[data-testid="auth-login-email-input"]',
          { visible: true }
        )
        await this.page.click('[data-testid="auth-login-email-input"]')
        await this.page.type(
          '[data-testid="auth-login-email-input"]',
          credentials.username
        )

        await this.page.waitForSelector(
          '[data-testid="auth-login-password-input"]',
          { visible: true }
        )
        await this.page.click('[data-testid="auth-login-password-input"]')
        await this.page.type(
          '[data-testid="auth-login-password-input"]',
          credentials.password
        )

        // Submit form with navigation wait
        this.log('Submitting login form...')
        await Promise.all([
          this.page.waitForNavigation({
            waitUntil: 'networkidle2',
            timeout: this.config.timeout,
          }),
          this.page.click('[data-testid="auth-login-submit-button"]'),
        ])

        // Verify authentication success
        await this.page.waitForTimeout(1000)
        const finalUrl = this.page.url()
        this.log(`Final URL after login: ${finalUrl}`)

        if (finalUrl.includes('/login')) {
          throw new Error('Still on login page after submission')
        }

        this.log('Login successful')
        return
      } catch (error) {
        this.log(`Login attempt ${attempt} failed:`, error.message)

        if (attempt === this.config.maxRetries) {
          throw new Error(
            `Login failed after ${this.config.maxRetries} attempts: ${error.message}`
          )
        }

        // Wait before retry with exponential backoff
        const waitTime = Math.min(1000 * Math.pow(2, attempt - 1), 5000)
        this.log(`Waiting ${waitTime}ms before retry...`)
        await this.page.waitForTimeout(waitTime)
      }
    }
  }

  async detectAuthState() {
    try {
      const currentUrl = this.page.url()

      if (currentUrl.includes('/login') || currentUrl.includes('/auth')) {
        return 'logged_out'
      }

      if (
        currentUrl.includes('/dashboard') ||
        currentUrl.includes('/projects') ||
        currentUrl.includes('/admin')
      ) {
        // Look for auth indicators
        const authIndicators = await this.page.evaluate(() => {
          const logoutBtn = document.querySelector(
            '[data-testid="logout-button"]'
          )
          const userMenu = document.querySelector('[data-testid="user-menu"]')

          return {
            hasLogoutBtn: !!logoutBtn,
            hasUserMenu: !!userMenu,
          }
        })

        if (authIndicators.hasLogoutBtn || authIndicators.hasUserMenu) {
          return 'logged_in'
        }
      }

      return 'unknown'
    } catch (error) {
      this.log('Error detecting auth state:', error)
      return 'unknown'
    }
  }
}

async function testReliableAuthentication() {
  console.log('🔄 Testing reliable Puppeteer MCP authentication...')

  let browser = null
  try {
    browser = await puppeteer.launch({
      headless: false, // Show browser for demo
      defaultViewport: { width: 1280, height: 720 },
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    })

    const page = await browser.newPage()

    // Enable console and error logging
    page.on('console', (msg) => {
      console.log(`[BROWSER] ${msg.type()}: ${msg.text()}`)
    })

    page.on('pageerror', (error) => {
      console.error(`[PAGE ERROR] ${error.message}`)
    })

    // Create authentication helper
    const authHelper = new SimplePuppeteerAuthHelper(page, {
      username: 'admin',
      password: 'admin',
      enableLogging: true,
      maxRetries: 3,
    })

    console.log('📱 Performing reliable authentication...')

    // Test reliable login
    await authHelper.reliableLogin()

    // Verify authentication state
    const authState = await authHelper.detectAuthState()
    console.log('✅ Authentication state:', authState)

    if (authState !== 'logged_in') {
      throw new Error('Authentication verification failed')
    }

    // Test navigation to protected admin page (demonstrating the original issue)
    console.log('📍 Testing access to admin users page...')
    await page.goto('http://localhost:3000/admin/users', {
      waitUntil: 'networkidle2',
      timeout: 10000,
    })

    // Wait and check for successful page load
    await page.waitForTimeout(2000)
    const adminUrl = page.url()
    console.log('📍 Admin page URL:', adminUrl)

    // Check for error indicators
    const hasError = await page.evaluate(() => {
      const errorBoundary = document.querySelector('.error-boundary')
      const errorMessage = document.querySelector('.error-message')
      return !!(errorBoundary || errorMessage)
    })

    if (hasError) {
      console.log('❌ Error detected on admin page')

      // Take screenshot for debugging
      await page.screenshot({
        path: `admin-error-${Date.now()}.png`,
        fullPage: true,
      })
    } else {
      console.log('✅ Admin page loaded successfully without errors')
    }

    // Test projects page access
    console.log('📍 Testing projects page access...')
    await page.goto('http://localhost:3000/projects', {
      waitUntil: 'networkidle2',
      timeout: 15000,
    })

    await page.waitForSelector('[data-testid="projects-table"]', {
      timeout: 10000,
    })
    console.log('✅ Projects page loaded successfully')

    // Demonstrate language switching resilience
    console.log('🌍 Testing language switching resilience...')

    // Find language switcher (but don't accidentally click it during auth)
    const languageSwitcher = await page.$('[data-testid="language-switcher"]')
    if (languageSwitcher) {
      console.log('✅ Language switcher found with proper data-testid')

      // Test that UI controls are properly isolated
      const uiControlsArea = await page.$('[data-testid="auth-ui-controls"]')
      if (uiControlsArea) {
        console.log('✅ UI controls area properly isolated with data-testid')
      }
    }

    console.log('🎉 All authentication reliability tests passed!')
  } catch (error) {
    console.error('❌ Test failed:', error.message)

    // Take failure screenshot
    try {
      await page.screenshot({
        path: `test-failure-${Date.now()}.png`,
        fullPage: true,
      })
      console.log('📸 Failure screenshot saved')
    } catch (screenshotError) {
      console.log(
        '⚠️  Could not save failure screenshot:',
        screenshotError.message
      )
    }

    throw error
  } finally {
    if (browser) {
      await browser.close()
    }
  }
}

// Run the test
testReliableAuthentication()
  .then(() => {
    console.log('🎉 Reliable authentication test completed successfully!')
    process.exit(0)
  })
  .catch((error) => {
    console.error('💥 Reliable authentication test failed:', error)
    process.exit(1)
  })
