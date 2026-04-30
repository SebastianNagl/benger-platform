/**
 * Test helper class for E2E tests
 */
import { Page } from '@playwright/test'
import { APISeedingHelper } from './api-seeding'

// Simple request throttle to prevent API overload
let lastRequestTime = 0
const MIN_REQUEST_INTERVAL = 50 // ms between API calls

async function throttledRequest<T>(fn: () => Promise<T>): Promise<T> {
  const now = Date.now()
  const timeSinceLastRequest = now - lastRequestTime
  if (timeSinceLastRequest < MIN_REQUEST_INTERVAL) {
    await new Promise((resolve) =>
      setTimeout(resolve, MIN_REQUEST_INTERVAL - timeSinceLastRequest)
    )
  }
  lastRequestTime = Date.now()
  return fn()
}

export class TestHelpers {
  readonly page: Page

  constructor(page: Page) {
    this.page = page
  }

  /**
   * Login as test user
   * Handles auto-login in development environment
   * In dev mode, auto-login often redirects before form is needed
   * Includes retry logic for infrastructure flakiness (traefik 404s, slow loads)
   */
  async login(email: string = 'admin', password: string = 'admin') {
    // Navigate to login page with retry logic for traefik's intermittent 404s
    const maxAttempts = 8
    let navigationSuccess = false
    for (let navAttempt = 1; navAttempt <= maxAttempts; navAttempt++) {
      try {
        if (navAttempt > 1) {
          const delay = 500 * navAttempt
          console.log(`⏳ Navigation retry ${navAttempt}/${maxAttempts} for /login after ${delay}ms delay...`)
          await this.page.waitForTimeout(delay)
        }

        const response = await this.page.goto('/login', {
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
        if (navAttempt === maxAttempts) {
          throw new Error(`Navigation to /login failed after ${maxAttempts} attempts: ${error}`)
        }
        console.log(`⚠️  Navigation error, retrying: ${error}`)
      }
    }

    if (!navigationSuccess) {
      throw new Error(`Failed to navigate to login page after ${maxAttempts} attempts`)
    }

    // Wait a bit for auto-login to potentially redirect
    await this.page.waitForTimeout(2000)

    // Check if already logged in (redirected away from login)
    if (!this.page.url().includes('/login')) {
      console.log('Already logged in (redirected)')
      return
    }

    // Check for user indicator in header (already logged in but on login page)
    const userIndicator = this.page
      .locator('button')
      .filter({ hasText: /admin|user/i })
      .first()
    if (await userIndicator.isVisible({ timeout: 1000 }).catch(() => false)) {
      console.log('Already logged in (user button visible)')
      return
    }

    // At this point, we're on login page - fill the form
    try {
      const emailInput = this.page.locator(
        '[data-testid="auth-login-email-input"]'
      )
      const passwordInput = this.page.locator(
        '[data-testid="auth-login-password-input"]'
      )
      const submitButton = this.page.locator(
        '[data-testid="auth-login-submit-button"]'
      )

      // Wait for form to be visible with retry logic for slow page rendering
      let formVisible = false
      for (let formAttempt = 1; formAttempt <= 5; formAttempt++) {
        try {
          if (formAttempt > 1) {
            console.log(`⏳ Form load retry ${formAttempt}/5...`)
            await this.page.waitForTimeout(1000)
          }
          await emailInput.waitFor({ state: 'visible', timeout: 5000 })
          formVisible = true
          break
        } catch (error) {
          if (formAttempt === 5) {
            throw new Error(`Login form not visible after 5 attempts`)
          }
        }
      }

      if (!formVisible) {
        throw new Error('Login form never became visible')
      }

      await emailInput.fill(email)
      await passwordInput.fill(password)
      await submitButton.click()

      // Wait for successful login - either redirect or user indicator appearing
      await Promise.race([
        this.page.waitForURL(/\/(dashboard|tasks|projects)/, { timeout: 30000 }),
        this.page.waitForSelector('button:has-text("admin")', { timeout: 30000 }),
        this.page.waitForSelector('[class*="sidebar"]', { timeout: 30000 }),
      ]).catch(() => {
        console.log('Login wait timeout, checking current state...')
      })

      // Verify we're logged in
      await this.page.waitForTimeout(1000)
      if (this.page.url().includes('/login')) {
        // Still on login page - check for error
        const errorMessage = this.page.locator('[data-testid="auth-error"]')
        if (await errorMessage.isVisible({ timeout: 1000 }).catch(() => false)) {
          const errorText = await errorMessage.textContent()
          throw new Error(`Login failed: ${errorText}`)
        }
        throw new Error('Login failed: still on login page after submit')
      }

      console.log('Login successful, redirected to:', this.page.url())
    } catch (error) {
      // If any error occurs, check if we're actually logged in
      if (!this.page.url().includes('/login')) {
        console.log('Login completed despite error')
        return
      }
      console.error('Login failed:', error)
      throw error
    }
  }

  /**
   * Create unique task name with timestamp
   */
  createUniqueTaskName(prefix: string): string {
    const timestamp = new Date().getTime()
    return `${prefix} ${timestamp}`
  }

  /**
   * Wait for toast message
   */
  async waitForToast(message: string) {
    await this.page.locator(`text=${message}`).waitFor({ state: 'visible' })
  }

  /**
   * Upload file to file input
   */
  async uploadFile(
    selector: string,
    fileName: string,
    content: string,
    mimeType: string
  ) {
    const buffer = Buffer.from(content)
    await this.page.setInputFiles(selector, {
      name: fileName,
      mimeType: mimeType,
      buffer: buffer,
    })
  }

  /**
   * Navigate to task and wait for it to load
   */
  async navigateToTask(taskId: string) {
    await this.page.goto(`/tasks/${taskId}`)
    await this.page.waitForSelector('h1', { state: 'visible' })
  }

  /**
   * Navigate to annotation page for a task
   */
  async navigateToAnnotation(taskId: string, itemIndex: number = 0) {
    await this.page.goto(`/tasks/${taskId}/annotate?item=${itemIndex}`)
    await this.page.waitForSelector('[data-testid="annotation-form"]', {
      state: 'visible',
    })
  }

  /**
   * Create a project for testing
   */
  async setupProject(projectData: { title: string; description?: string }) {
    // Navigate to projects page
    await this.page.goto('/projects')

    // Click create project button
    await this.page.click('button:has-text("Create Project")')

    // Fill project form
    await this.page.fill('input[name="title"]', projectData.title)
    if (projectData.description) {
      await this.page.fill(
        'textarea[name="description"]',
        projectData.description
      )
    }

    // Submit form
    await this.page.click('button[type="submit"]:has-text("Create")')

    // Wait for redirect to project detail page
    await this.page.waitForURL(/\/projects\/[a-zA-Z0-9-]+$/)

    // Extract project ID from URL
    const url = this.page.url()
    const projectId = url.split('/').pop() || ''

    return {
      id: projectId,
      title: projectData.title,
      description: projectData.description,
    }
  }

  // Create a test project via POST /api/projects. Default for any spec
  // that needs a project as setup; use createTestProjectViaWizard only when
  // you're explicitly asserting on the wizard UX.
  async createTestProject(name: string): Promise<string | null> {
    try {
      const seeder = new APISeedingHelper(this.page)
      return await seeder.createProject(name)
    } catch (err) {
      console.error('createTestProject (API) failed:', err)
      return null
    }
  }

  // Walks the project-creation wizard step-by-step. Use only in specs that
  // explicitly test the wizard UX; everything else should call the API-
  // driven createTestProject above.
  async createTestProjectViaWizard(name: string): Promise<string | null> {
    const currentUrl = this.page.url()

    try {
      // Navigate to create project page
      await this.page.goto('/projects/create')

      // Step 1: Project Info
      // Wait for form to be ready with fallback selectors
      const nameInputSelector =
        '[data-testid="project-create-name-input"], input[name="name"], input[placeholder*="German Legal"], input[placeholder*="Name"]'
      await this.page
        .waitForSelector(nameInputSelector, { timeout: 5000 })
        .catch(() => {
          console.log('Name input not found with primary selectors')
        })

      // Fill in project details using fallback selectors
      const nameInput = this.page.locator(nameInputSelector).first()
      if (await nameInput.isVisible().catch(() => false)) {
        await nameInput.fill(name)
      } else {
        console.log('Could not find name input field')
        return null
      }

      const descriptionTextarea = this.page
        .locator(
          '[data-testid="project-create-description-textarea"], textarea[name="description"], textarea[placeholder*="Describe"]'
        )
        .first()
      if (await descriptionTextarea.isVisible().catch(() => false)) {
        await descriptionTextarea.fill(`Test project for ${name}`)
      }

      // Click Next button with fallback selectors (including German locale)
      const nextButton = this.page
        .locator(
          '[data-testid="project-create-next-button"], button:has-text("Next"), button:has-text("Weiter"), button:has-text("Nächster")'
        )
        .first()
      await nextButton.click()

      // Step 2: Data Import - Skip this step
      // Wait for the data import step to be visible
      await this.page
        .waitForSelector('text=/Daten importieren|Import Data|Data Import/i', {
          timeout: 10000,
        })
        .catch(() => console.log('Data import heading not found'))

      // Look for "Skip Data Import" button with fallbacks (including German locale)
      const skipButton = this.page
        .locator(
          '[data-testid="project-create-skip-data-button"], button:has-text("Skip Data Import"), button:has-text("Datenimport überspringen"), button:has-text("Skip")'
        )
        .first()

      // Wait for the button to be visible and stable
      await skipButton.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {
        console.log('Skip button not visible')
      })

      if (await skipButton.isVisible().catch(() => false)) {
        // Use force: true to bypass the file dropzone overlay that intercepts pointer events on mobile
        await skipButton.click({ force: true })
        // Wait for navigation to step 3
        await this.page.waitForTimeout(500)
      } else {
        // If no skip button, try clicking Next again (including German locale)
        const nextButton2 = this.page
          .locator(
            '[data-testid="project-create-next-button"], button:has-text("Next"), button:has-text("Weiter"), button:has-text("Nächster")'
          )
          .first()
        await nextButton2.click()
      }

      // Step 3: Labeling Setup - Just create the project
      // Wait for the annotation setup step to be visible
      await this.page
        .waitForSelector('text=/Annotation einrichten|Annotation Setup|Labeling/i', {
          timeout: 10000,
        })
        .catch(() => console.log('Annotation setup heading not found'))

      // Click "Create Project" button with fallback selectors (including German locale)
      const createButton = this.page
        .locator(
          '[data-testid="project-create-submit-button"], button:has-text("Create Project"), button:has-text("Create"), button:has-text("Projekt erstellen"), button:has-text("Erstellen")'
        )
        .first()
      await createButton.click()

      // Wait for success toast
      await this.page.waitForTimeout(1000) // Give time for the request to complete

      // Wait for redirect to project page with UUID pattern
      await this.page.waitForURL(
        /\/projects\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
        { timeout: 10000 }
      )
      const projectUrl = this.page.url()
      console.log('Project URL after creation:', projectUrl)

      // Extract project ID from URL (handle both /projects/id and /projects/id/something patterns)
      const urlParts = projectUrl.split('/')
      const projectsIndex = urlParts.findIndex((part) => part === 'projects')
      const projectId =
        projectsIndex >= 0 && projectsIndex + 1 < urlParts.length
          ? urlParts[projectsIndex + 1].split('?')[0] // Remove any query params
          : null

      console.log('Extracted project ID:', projectId)

      // Navigate back to original page
      await this.page.goto(currentUrl)

      return projectId
    } catch (error) {
      console.error('Failed to create test project:', error)
      // Navigate back to original page on failure
      await this.page.goto(currentUrl).catch(() => {})
      return null
    }
  }

  /**
   * Delete a test project with verification
   * Returns true if deletion was successful, false otherwise
   */
  async deleteTestProject(projectId: string): Promise<boolean> {
    try {
      // Navigate to projects page first to ensure we're in the right context
      await this.page.goto('/projects')

      // Use API directly to delete project with throttling
      const deleteResult = await throttledRequest(() =>
        this.page.evaluate(async (id) => {
          const response = await fetch(`/api/projects/${id}`, {
            method: 'DELETE',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${localStorage.getItem('access_token')}`,
            },
          })
          return { status: response.status, ok: response.ok }
        }, projectId)
      )

      // 200 = deleted, 404 = already deleted (both acceptable)
      if (deleteResult.status !== 200 && deleteResult.status !== 404) {
        console.warn(
          `Delete returned status ${deleteResult.status} for project ${projectId}`
        )
        return false
      }

      // Verify deletion by checking project no longer exists
      const verifyResult = await throttledRequest(() =>
        this.page.evaluate(async (id) => {
          const response = await fetch(`/api/projects/${id}`, {
            headers: {
              Authorization: `Bearer ${localStorage.getItem('access_token')}`,
            },
          })
          return response.status
        }, projectId)
      )

      if (verifyResult !== 404) {
        console.warn(
          `Project ${projectId} still exists after deletion (status: ${verifyResult})`
        )
        return false
      }

      return true
    } catch (error) {
      console.warn(`Failed to delete test project ${projectId}:`, error)
      return false
    }
  }

  /**
   * Make a throttled API request to prevent overwhelming the backend
   */
  async throttledApiCall<T>(fn: () => Promise<T>): Promise<T> {
    return throttledRequest(fn)
  }
}
