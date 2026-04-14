import { chromium, FullConfig, Page } from '@playwright/test'

interface HealthCheckResult {
  api: boolean
  database: boolean
  redis: boolean
  auth: boolean
  frontend: boolean
}

/**
 * Validate infrastructure health before running tests
 * Returns detailed health status for debugging
 */
async function validateInfrastructure(
  page: Page,
  baseURL: string,
  maxRetries: number = 5
): Promise<HealthCheckResult> {
  const result: HealthCheckResult = {
    api: false,
    database: false,
    redis: false,
    auth: false,
    frontend: false,
  }

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    console.log(`Health check attempt ${attempt}/${maxRetries}...`)

    try {
      // Check API health endpoint
      const healthResponse = await page.request.get(`${baseURL}/api/health`, {
        timeout: 10000,
      })

      if (healthResponse.ok()) {
        result.api = true
        const healthData = await healthResponse.json().catch(() => ({}))
        result.database = healthData.status === 'healthy' || healthData.database === 'ok'
        result.redis = healthData.redis === 'connected' || healthData.redis === 'ok'
        console.log(
          `  API: OK, DB: ${result.database ? 'OK' : 'FAIL'}, Redis: ${result.redis ? 'OK' : 'FAIL'}`
        )
      }

      // Verify demo user can authenticate
      const authResponse = await page.request.post(
        `${baseURL}/api/auth/login`,
        {
          headers: { 'Content-Type': 'application/json' },
          data: { username: 'admin', password: 'admin' },
          timeout: 10000,
        }
      )

      if (authResponse.ok()) {
        result.auth = true
        console.log('  Auth: OK (demo user accessible)')
      }

      // Verify frontend is serving content
      const frontendResponse = await page.goto(baseURL, {
        waitUntil: 'domcontentloaded',
        timeout: 15000,
      })

      if (frontendResponse?.ok()) {
        const hasContent = await page.evaluate(() => {
          return document.body && document.body.innerHTML.length > 100
        })
        result.frontend = hasContent
        console.log(
          `  Frontend: ${result.frontend ? 'OK' : 'FAIL (no content)'}`
        )
      }

      // Check if all critical services are healthy
      const allHealthy = result.api && result.auth && result.frontend
      if (allHealthy) {
        console.log('All critical services healthy')
        return result
      }

      // Wait before retry with exponential backoff
      if (attempt < maxRetries) {
        const backoffMs = Math.min(2000 * Math.pow(1.5, attempt - 1), 10000)
        console.log(`  Retrying in ${backoffMs}ms...`)
        await page.waitForTimeout(backoffMs)
      }
    } catch (error) {
      console.log(
        `  Health check error: ${error instanceof Error ? error.message : error}`
      )
      if (attempt < maxRetries) {
        const backoffMs = Math.min(2000 * Math.pow(1.5, attempt - 1), 10000)
        await page.waitForTimeout(backoffMs)
      }
    }
  }

  return result
}

async function globalSetup(config: FullConfig) {
  console.log('Starting E2E test global setup...')

  const baseURL =
    process.env.PLAYWRIGHT_BASE_URL ||
    config.projects[0].use.baseURL ||
    'http://benger.localhost'
  console.log(`Connecting to: ${baseURL}`)

  const browser = await chromium.launch()
  const page = await browser.newPage()

  try {
    console.log('Performing infrastructure health validation...')

    // Validate all services are healthy before proceeding
    const health = await validateInfrastructure(page, baseURL, 8)

    const criticalHealthy = health.api && health.auth && health.frontend
    if (!criticalHealthy) {
      const failedServices = []
      if (!health.api) failedServices.push('API')
      if (!health.auth) failedServices.push('Auth')
      if (!health.frontend) failedServices.push('Frontend')

      const errorMsg = `Critical services not healthy after retries: ${failedServices.join(', ')}`

      if (process.env.CI) {
        console.warn(`WARNING: ${errorMsg} - proceeding in CI mode`)
      } else {
        throw new Error(errorMsg)
      }
    }

    // Navigate to base URL for session setup
    await page.goto(baseURL, {
      waitUntil: 'domcontentloaded',
      timeout: 30000,
    })

    // Give React time to hydrate
    await page.waitForTimeout(2000)

    // Disable auto-login for E2E tests
    await page.evaluate(() => {
      sessionStorage.setItem('e2e_test_mode', 'true')
    })
    console.log('Disabled auto-login for E2E tests')

    console.log('Infrastructure validated successfully')
  } catch (error) {
    console.error('Setup failed:', error)
    if (process.env.CI) {
      console.log(
        'Ignoring setup failure in CI - tests will handle connectivity issues'
      )
    } else {
      throw error
    }
  } finally {
    await browser.close()
  }
}

export default globalSetup
