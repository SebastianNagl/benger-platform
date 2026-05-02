/**
 * Test helper utilities for E2E tests
 */

import { Page } from '@playwright/test'

/**
 * Login as test user
 */
export async function loginAsTestUser(page: Page) {
  await page.goto('/login')

  // Wait for login form to be visible
  await page.waitForSelector('[data-testid="auth-login-form"]', {
    timeout: 5000,
  })

  // Fill login form using test IDs
  const emailInput = await page.locator(
    '[data-testid="auth-login-email-input"]'
  )
  await emailInput.fill('admin')

  const passwordInput = await page.locator(
    '[data-testid="auth-login-password-input"]'
  )
  await passwordInput.fill('admin')

  // Click login button
  const loginButton = await page.locator(
    '[data-testid="auth-login-submit-button"]'
  )
  await loginButton.click()

  // Wait for redirect to dashboard or projects page
  try {
    await page.waitForURL(/\/(dashboard|tasks|projects)/, { timeout: 10000 })
  } catch (error) {
    // If redirect doesn't happen, check if we're already logged in by looking for admin text
    const adminText = page.locator('text=admin (TUM)')
    const isLoggedIn = await adminText.isVisible()
    if (!isLoggedIn) {
      // Try waiting a bit more and check current URL
      await page.waitForTimeout(2000)
      const currentUrl = page.url()
      console.log('Current URL after login attempt:', currentUrl)
      if (currentUrl.includes('/login')) {
        throw new Error('Login failed - still on login page')
      }
    }
    console.log('Login successful but no redirect detected')
  }
}

/**
 * Create unique task name with timestamp
 */
export function createUniqueTaskName(prefix: string): string {
  const timestamp = new Date().getTime()
  return `${prefix} ${timestamp}`
}

/**
 * Wait for toast message
 */
export async function waitForToast(page: Page, message: string) {
  await page.locator(`text=${message}`).waitFor({ state: 'visible' })
}

/**
 * Upload file to file input
 */
export async function uploadFile(
  page: Page,
  selector: string,
  fileName: string,
  content: string,
  mimeType: string
) {
  const buffer = Buffer.from(content)
  await page.setInputFiles(selector, {
    name: fileName,
    mimeType: mimeType,
    buffer: buffer,
  })
}

/**
 * Create sample CSV data for QA tasks
 */
export function createQACSVData(numRows: number = 3): string {
  const questions = [
    { q: 'What is the capital of France?', a: 'Paris', s: 'Geography' },
    { q: 'Who painted the Mona Lisa?', a: 'Leonardo da Vinci', s: 'Art' },
    { q: 'What is 2 + 2?', a: '4', s: 'Mathematics' },
    { q: 'What is the largest planet?', a: 'Jupiter', s: 'Astronomy' },
    { q: 'Who wrote Hamlet?', a: 'William Shakespeare', s: 'Literature' },
  ]

  let csv = 'question,reference_answer,source\n'
  for (let i = 0; i < Math.min(numRows, questions.length); i++) {
    const { q, a, s } = questions[i]
    csv += `"${q}","${a}","${s}"\n`
  }

  return csv
}

/**
 * Create sample JSON data for QA tasks
 */
export function createQAJSONData(numItems: number = 3): string {
  const items = []
  const questions = [
    {
      question: 'What is the capital of France?',
      reference_answer: 'Paris',
      source: 'Geography',
    },
    {
      question: 'Who painted the Mona Lisa?',
      reference_answer: 'Leonardo da Vinci',
      source: 'Art',
    },
    {
      question: 'What is 2 + 2?',
      reference_answer: '4',
      source: 'Mathematics',
    },
  ]

  for (let i = 0; i < Math.min(numItems, questions.length); i++) {
    items.push(questions[i])
  }

  return JSON.stringify(items, null, 2)
}

/**
 * Navigate to task and wait for it to load
 * @deprecated Tasks are now accessed through projects
 */
export async function navigateToTask(
  page: Page,
  taskId: string,
  projectId?: string
) {
  if (!projectId) {
    throw new Error(
      'Project ID is required to navigate to tasks. Tasks are now accessed through projects.'
    )
  }
  await page.goto(`/projects/${projectId}/tasks/${taskId}`)
  await page.waitForSelector('h1', { state: 'visible' })
}

/**
 * Navigate to annotation page for a task
 * @deprecated Tasks are now accessed through projects
 */
export async function navigateToAnnotation(
  page: Page,
  taskId: string,
  itemIndex: number = 0,
  projectId?: string
) {
  if (!projectId) {
    throw new Error(
      'Project ID is required to navigate to task annotations. Tasks are now accessed through projects.'
    )
  }
  await page.goto(`/projects/${projectId}/tasks/${taskId}?item=${itemIndex}`)
  await page.waitForSelector('[data-testid="annotation-form"]', {
    state: 'visible',
  })
}

/**
 * Mock authenticated user session for tests
 */
export async function mockUserSession(page: Page) {
  // Set authentication token in localStorage before navigation
  await page.addInitScript(() => {
    window.localStorage.setItem('access_token', 'test-token-123')
    window.localStorage.setItem(
      'user',
      JSON.stringify({
        id: '1',
        email: 'test@example.com',
        name: 'Test User',
        is_superadmin: true,
      })
    )
  })
}

/**
 * Create a project for testing
 */
export async function setupProject(
  page: Page,
  projectData: { title: string; description?: string }
) {
  // Navigate to projects page
  await page.goto('/projects')

  // Click create project button
  await page.click('button:has-text("Create Project")')

  // Fill project form
  await page.fill('input[name="title"]', projectData.title)
  if (projectData.description) {
    await page.fill('textarea[name="description"]', projectData.description)
  }

  // Submit form
  await page.click('button[type="submit"]:has-text("Create")')

  // Wait for redirect to project detail page
  await page.waitForURL(/\/projects\/[a-zA-Z0-9-]+$/)

  // Extract project ID from URL
  const url = page.url()
  const projectId = url.split('/').pop() || ''

  return {
    id: projectId,
    title: projectData.title,
    description: projectData.description,
  }
}

/**
 * Login helper for tests
 */
export async function testLogin(page: Page) {
  await loginAsTestUser(page)
}

/**
 * Create a test project using the 3-step wizard
 */
export async function createTestProject(
  page: Page,
  name: string
): Promise<string | null> {
  const currentUrl = page.url()

  // Navigate to create project page
  await page.goto('/projects/create')

  // Step 1: Project Info
  // Wait for form to be ready
  await page.waitForSelector('[data-testid="project-create-name-input"]', {
    timeout: 5000,
  })

  // Fill in project details
  const nameInput = page.locator('[data-testid="project-create-name-input"]')
  await nameInput.fill(name)

  const descriptionTextarea = page.locator(
    '[data-testid="project-create-description-textarea"]'
  )
  await descriptionTextarea.fill(`Test project for ${name}`)

  // Click Next button
  const nextButton = page.locator('[data-testid="project-create-next-button"]')
  await nextButton.click()

  // Step 2: Data Import - Skip this step
  await page.waitForTimeout(1000)

  // Look for "Skip Data Import" button
  const skipButton = page.locator(
    '[data-testid="project-create-skip-data-button"]'
  )
  if (await skipButton.isVisible()) {
    await skipButton.click()
  } else {
    // If no skip button, try clicking Next again
    const nextButton2 = page.locator(
      '[data-testid="project-create-next-button"]'
    )
    await nextButton2.click()
  }

  // Step 3: Labeling Setup - Just create the project
  await page.waitForTimeout(1000)

  // Click "Create Project" button
  const createButton = page.locator(
    '[data-testid="project-create-submit-button"]'
  )
  await createButton.click()

  // Wait for success toast
  await page.waitForTimeout(1000) // Give time for the request to complete

  // Wait for redirect to project page with UUID pattern
  await page.waitForURL(
    /\/projects\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    { timeout: 10000 }
  )
  const projectUrl = page.url()
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
  await page.goto(currentUrl)

  return projectId
}

/**
 * Delete a test project
 */
export async function deleteTestProject(
  page: Page,
  projectId: string
): Promise<void> {
  try {
    // Navigate to projects page first to ensure we're in the right context
    await page.goto('/projects')

    // Use API directly to delete project
    await page.evaluate(async (id) => {
      const response = await fetch(`/api/projects/${id}`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('access_token')}`,
        },
      })
      if (!response.ok && response.status !== 404) {
        // Ignore 404 errors since the project might already be deleted
        const errorText = await response.text()
        console.warn(`Delete response (${response.status}):`, errorText)
      }
    }, projectId)
  } catch (error) {
    console.warn(`Failed to delete test project ${projectId}:`, error)
  }
}

/**
 * Click the FilterToolbar's collapsed search toggle and return the now-visible
 * <input>. The toolbar (services/frontend/src/components/shared/FilterToolbar.tsx)
 * keeps its search field hidden until the magnifying-glass button is clicked.
 * Button title is set from the searchLabel prop, which on every adopting page
 * resolves to t('common.filters.search') = "Search" (en) / "Suche" (de).
 */
export async function revealFilterToolbarSearch(page: Page) {
  const toggle = page
    .locator('button[title="Search"], button[title="Suche"]')
    .first()
  await toggle.click({ timeout: 10000 })
  return page.locator('input[type="text"], input[type="search"]').first()
}
