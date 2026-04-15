/**
 * Example usage of PuppeteerAuthHelper for reliable MCP authentication
 *
 * This example demonstrates how to use the PuppeteerAuthHelper class
 * for production-ready authentication in Puppeteer MCP workflows.
 */

const puppeteer = require('puppeteer')
const { PuppeteerAuthHelper } = require('../helpers/PuppeteerAuthHelper')

async function demonstrateReliableAuth() {
  console.log('🔄 Demonstrating reliable Puppeteer MCP authentication...')

  let browser = null
  try {
    // Launch browser with appropriate settings for production testing
    browser = await puppeteer.launch({
      headless: false, // Set to true for CI/CD environments
      defaultViewport: { width: 1280, height: 720 },
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage', // Overcome limited resource problems
        '--disable-extensions',
        '--no-first-run',
        '--disable-default-apps',
      ],
    })

    const page = await browser.newPage()

    // Create the authentication helper
    const authHelper = new PuppeteerAuthHelper(page, {
      username: 'admin',
      password: 'admin',
      timeout: 30000,
      maxRetries: 3,
      enableLogging: true,
    })

    console.log('📱 Testing reliable authentication...')

    // Example 1: Basic reliable login
    await authHelper.reliableLogin()
    console.log('✅ Basic login successful')

    // Example 2: Check authentication state
    const authState = authHelper.getAuthState()
    console.log('📊 Auth state:', authState)

    // Example 3: Environment detection
    const isProduction = await authHelper.isProductionEnvironment()
    console.log('🌍 Environment - Production:', isProduction)

    // Example 4: Explicit authentication verification
    const isAuthenticated = await authHelper.waitForAuth(10000)
    console.log('🔐 Authentication verified:', isAuthenticated)

    // Example 5: Navigate to protected resource
    await page.goto('http://localhost:3000/projects', {
      waitUntil: 'networkidle2',
      timeout: 30000,
    })

    // Verify we can access protected content
    await page.waitForSelector('[data-testid="projects-table"]', {
      timeout: 10000,
    })
    console.log('✅ Successfully accessed protected resource')

    // Example 6: Handle logout and re-authentication
    const logoutButton = await page.$('[data-testid="logout-button"]')
    if (logoutButton) {
      await logoutButton.click()
      console.log('🚪 Logged out successfully')

      // Re-authenticate
      await authHelper.reliableLogin()
      console.log('✅ Re-authentication successful')
    }

    console.log('🎉 All authentication tests passed!')
  } catch (error) {
    console.error('❌ Authentication test failed:', error.message)

    // Example of error recovery
    try {
      console.log('🔄 Attempting error recovery...')
      await authHelper.handleAuthFailure()
    } catch (recoveryError) {
      console.error('❌ Error recovery failed:', recoveryError.message)
    }

    throw error
  } finally {
    if (browser) {
      await browser.close()
    }
  }
}

// Example of integration with existing test suite
async function integrationExample() {
  console.log('🔄 Integration example with existing test patterns...')

  let browser = null
  try {
    browser = await puppeteer.launch({
      headless: false,
      defaultViewport: { width: 1280, height: 720 },
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    })

    const page = await browser.newPage()
    const authHelper = new PuppeteerAuthHelper(page)

    // Step 1: Authenticate
    await authHelper.reliableLogin()

    // Step 2: Navigate to specific functionality
    await page.goto('http://localhost:3000/projects', {
      waitUntil: 'networkidle2',
      timeout: 30000,
    })

    // Step 3: Verify authentication is maintained
    const authState = await authHelper.detectAuthState()
    if (authState !== 'logged_in') {
      throw new Error('Authentication lost during navigation')
    }

    // Step 4: Perform test actions
    // (Your existing test logic here)
    console.log('✅ Integration test completed successfully')
  } catch (error) {
    console.error('❌ Integration test failed:', error.message)
    throw error
  } finally {
    if (browser) {
      await browser.close()
    }
  }
}

// Run examples if called directly
if (require.main === module) {
  demonstrateReliableAuth()
    .then(() => {
      console.log('🎉 All examples completed successfully!')
      process.exit(0)
    })
    .catch((error) => {
      console.error('💥 Example execution failed:', error)
      process.exit(1)
    })
}

module.exports = {
  demonstrateReliableAuth,
  integrationExample,
}
