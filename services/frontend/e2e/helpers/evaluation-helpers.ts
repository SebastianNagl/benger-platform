/**
 * Evaluation test helper class for E2E tests
 * Provides shared navigation and setup functions for evaluation wizard tests
 */
import { expect, Page } from '@playwright/test'
import { TestFixtures } from './test-fixtures'
import { TestHelpers } from './test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost'

export class EvaluationHelpers {
  readonly page: Page
  private helpers: TestHelpers | null = null
  private fixtures: TestFixtures | null = null

  constructor(page: Page, helpers?: TestHelpers) {
    this.page = page
    if (helpers) {
      this.helpers = helpers
      this.fixtures = new TestFixtures(page, helpers)
    }
  }

  /**
   * Initialize helpers if not provided in constructor
   */
  initHelpers(helpers: TestHelpers): void {
    this.helpers = helpers
    this.fixtures = new TestFixtures(this.page, helpers)
  }

  /**
   * Create a project with a specific label config for testing auto-detection
   */
  async createProjectWithConfig(
    config: string,
    taskCount: number = 3
  ): Promise<string> {
    if (!this.fixtures) {
      throw new Error(
        'TestFixtures not initialized. Call initHelpers() first or pass helpers to constructor.'
      )
    }
    return await this.fixtures.createAnnotationTestProject(config, taskCount)
  }

  /**
   * Navigate to a specific project by ID
   * Uses retry logic to handle slow infrastructure and 404 errors during E2E tests
   */
  async navigateToProject(projectId: string): Promise<void> {
    const maxRetries = 3
    let lastError: Error | null = null

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const response = await this.page.goto(
          `${BASE_URL}/projects/${projectId}`,
          {
            waitUntil: 'domcontentloaded',
            timeout: 30000,
          }
        )

        // Check for 404 or other error responses
        if (response && response.status() >= 400) {
          console.warn(
            `Navigation attempt ${attempt} returned ${response.status()}, retrying...`
          )
          await this.page.waitForTimeout(1000 * attempt)
          continue
        }

        // Wait for project content to load with longer timeout for E2E environment
        // Try multiple selectors that indicate the page is ready
        const selectors = [
          'text=Evaluierungskonfiguration',
          'text=Evaluation Configuration',
          '[data-testid="project-settings"]',
          'h1', // Fallback to any heading
        ]

        let found = false
        for (const selector of selectors) {
          try {
            await this.page.waitForSelector(selector, { timeout: 10000 })
            found = true
            break
          } catch {
            // Try next selector
          }
        }

        if (!found) {
          // If no specific selector found, just wait for the page to stabilize
          await this.page.waitForTimeout(2000)
        }

        await this.page.waitForTimeout(500)
        // After all the soft waits the page may have client-side
        // redirected (e.g. to /projects when project not found). Verify
        // and surface a clear error if so.
        const finalUrl = this.page.url()
        if (!finalUrl.includes(`/projects/${projectId}`)) {
          throw new Error(
            `Navigation to /projects/${projectId} ended up at ${finalUrl} ` +
              `— project may not exist or user lacks access`
          )
        }
        console.log(`[navigateToProject] landed at ${finalUrl}`)
        return
      } catch (error) {
        lastError = error as Error
        console.warn(
          `Navigation attempt ${attempt}/${maxRetries} failed: ${lastError.message}`
        )
        if (attempt < maxRetries) {
          await this.page.waitForTimeout(1000 * attempt)
        }
      }
    }

    throw (
      lastError ||
      new Error(
        `Failed to navigate to project ${projectId} after ${maxRetries} attempts`
      )
    )
  }

  /**
   * Delete a test project (cleanup)
   */
  async cleanupProject(projectId: string): Promise<void> {
    if (!this.fixtures) {
      throw new Error('TestFixtures not initialized.')
    }
    await this.fixtures.cleanup(projectId)
  }

  /**
   * Ensure a project with evaluation-compatible config exists
   * Creates one if fixtures are available, otherwise throws
   * Returns the project ID
   */
  async ensureProjectExists(): Promise<string> {
    if (!this.fixtures) {
      throw new Error(
        'TestFixtures not initialized. Call initHelpers() first or pass helpers to constructor.'
      )
    }

    // Create a project with a label config suitable for evaluation tests
    const labelConfig = `<View>
      <Text name="text" value="$text"/>
      <TextArea name="answer" toName="text" required="true"/>
    </View>`

    const projectId = await this.fixtures.createAnnotationTestProject(
      labelConfig,
      3
    )
    return projectId
  }

  /**
   * Navigate to a project with tasks
   * Returns true if a project was found and navigated to
   * @deprecated Use ensureProjectExists() + navigateToProject() for guaranteed test data
   */
  async navigateToProjectWithTasks(): Promise<boolean> {
    await this.page.goto(`${BASE_URL}/projects`)
    await this.page.waitForLoadState('domcontentloaded')
    await this.page.waitForTimeout(2000)

    // Look for any project link we can click
    const projectLink = this.page.locator('a[href^="/projects/"]').first()
    if (await projectLink.isVisible({ timeout: 3000 }).catch(() => false)) {
      await projectLink.click()
      await this.page.waitForTimeout(2000)
      return true
    }

    // Fallback: try clicking project name text
    const projectNames = ['Test AGG', 'Auto-Redirect Test', 'NER Span Test']
    for (const name of projectNames) {
      const nameLink = this.page.locator(`text="${name}"`).first()
      if (await nameLink.isVisible({ timeout: 1000 }).catch(() => false)) {
        await nameLink.click()
        await this.page.waitForTimeout(2000)
        return true
      }
    }

    return false
  }

  /**
   * Open the Evaluierungskonfiguration section in project settings
   * Supports both German and English labels, with retry logic for slow infrastructure
   */
  async openEvaluationConfigSection(): Promise<void> {
    // Wait for project page to be ready
    await this.page.waitForTimeout(1000)
    console.log(`[openEvaluationConfigSection] starting at URL: ${this.page.url()}`)

    // Fail fast if we're not on a project detail page — the rest of the
    // helper otherwise scrolls a wrong page silently and confuses later
    // failures (e.g. clickNext throwing "button not found" when really
    // the wizard never opened).
    if (!/\/projects\/[0-9a-f-]{8,}/.test(this.page.url())) {
      throw new Error(
        `openEvaluationConfigSection called from ${this.page.url()}, ` +
          `expected /projects/{id} — earlier setup step likely failed silently`
      )
    }

    const sectionLabels = [
      'Evaluierungskonfiguration',
      'Evaluation Configuration',
      'Evaluation Config',
    ]

    const maxScrollAttempts = 5
    for (
      let scrollAttempt = 0;
      scrollAttempt <= maxScrollAttempts;
      scrollAttempt++
    ) {
      for (const label of sectionLabels) {
        const section = this.page.locator(`text=${label}`).first()

        if (await section.isVisible({ timeout: 2000 }).catch(() => false)) {
          await section.click()
          await this.page.waitForTimeout(1000)
          return
        }
      }

      const partialMatch = this.page.locator('text=/Evaluierung/i').first()
      if (await partialMatch.isVisible({ timeout: 1000 }).catch(() => false)) {
        await partialMatch.click()
        await this.page.waitForTimeout(1000)
        return
      }

      if (scrollAttempt < maxScrollAttempts) {
        await this.page.evaluate(() => window.scrollBy(0, 300))
        await this.page.waitForTimeout(500)
      }
    }

    throw new Error(
      `Evaluation config section not found after scrolling at ${this.page.url()}`
    )
  }

  /**
   * Click "Add Evaluation" button to open the wizard
   * Throws if button cannot be found
   */
  async openAddEvaluationWizard(): Promise<void> {
    console.log(`[openAddEvaluationWizard] starting at URL: ${this.page.url()}`)
    const testIdButton = this.page.locator('[data-testid="add-evaluation-button"]')
    if (await testIdButton.isVisible({ timeout: 3000 }).catch(() => false)) {
      await testIdButton.click()
      // Confirm the wizard actually rendered before continuing — without this
      // a misclick or stale state silently passes through and surfaces as a
      // mysterious "Next button not found" three steps later.
      const wizardHeader = this.page.locator(
        '[data-testid="evaluation-wizard-header"]'
      )
      try {
        await wizardHeader.waitFor({ state: 'visible', timeout: 5000 })
      } catch {
        throw new Error(
          'Clicked add-evaluation-button but wizard header never appeared'
        )
      }
      await this.page.waitForTimeout(500)
      return
    }

    // Fallback: Support both English and German translations
    const buttonTexts = ['Add Evaluation', 'Evaluierung hinzufügen']

    for (const buttonText of buttonTexts) {
      const addButton = this.page
        .locator('button')
        .filter({ hasText: new RegExp(buttonText, 'i') })
        .first()

      if (await addButton.isVisible({ timeout: 3000 }).catch(() => false)) {
        await addButton.click()
        await this.page.waitForTimeout(1000)
        return
      }
    }

    throw new Error('Add Evaluation button not found')
  }

  /**
   * Select LLM-as-Judge metric in Step 1
   * Throws if metric cannot be found
   */
  async selectLLMJudgeMetric(): Promise<void> {
    // The metrics are displayed in a scrollable list inside the wizard dialog
    // We need to scroll within the dialog, not the window
    const scrollContainer = this.page.locator('.overflow-y-auto').first()

    // Try scrolling the container to find LLM Judge
    for (let scrollAttempt = 0; scrollAttempt < 5; scrollAttempt++) {
      // Try data-testid first (most reliable)
      const metricByTestId = this.page.locator('[data-testid^="metric-button-llm_judge"]')
      if (await metricByTestId.first().isVisible({ timeout: 1000 }).catch(() => false)) {
        await metricByTestId.first().click()
        await this.page.waitForTimeout(500)
        return
      }

      // Try clicking text "Classic LLM Judge" or "Custom LLM Judge" (list items, not buttons)
      const llmJudgeText = this.page.locator('text=Classic LLM Judge').first()
      if (await llmJudgeText.isVisible({ timeout: 1000 }).catch(() => false)) {
        await llmJudgeText.click()
        await this.page.waitForTimeout(500)
        return
      }

      // Fallback: look for any element containing "LLM Judge"
      const llmJudgeAny = this.page.locator('text=/LLM.*Judge/i').first()
      if (await llmJudgeAny.isVisible({ timeout: 1000 }).catch(() => false)) {
        await llmJudgeAny.click()
        await this.page.waitForTimeout(500)
        return
      }

      // Scroll within the container
      if (await scrollContainer.isVisible({ timeout: 500 }).catch(() => false)) {
        await scrollContainer.evaluate((el) => (el.scrollTop += 300))
      } else {
        // Fallback to window scroll
        await this.page.evaluate(() => window.scrollBy(0, 300))
      }
      await this.page.waitForTimeout(300)
    }

    throw new Error(
      'LLM Judge metric not found - check if wizard is open and metrics are loaded'
    )
  }

  /**
   * Check if LLM Judge feature is available (API keys configured)
   * This checks if the evaluation wizard has the LLM-as-Judge option
   */
  async isLLMJudgeAvailable(): Promise<boolean> {
    // Scroll to find LLM-as-Judge section
    await this.page.evaluate(() => window.scrollBy(0, 600))
    await this.page.waitForTimeout(500)

    // Try data-testid first (most reliable)
    const metricByTestId = this.page.locator('[data-testid^="metric-button-llm_judge"]')
    if (await metricByTestId.first().isVisible({ timeout: 2000 }).catch(() => false)) {
      return true
    }

    // Fallback: look for button containing LLM Judge text
    const llmJudgeButton = this.page.locator('button').filter({ hasText: /LLM Judge/i }).first()
    return await llmJudgeButton.isVisible({ timeout: 2000 }).catch(() => false)
  }

  /**
   * Click Next button in the wizard (supports English and German)
   * Throws if button cannot be found
   */
  async clickNext(): Promise<void> {
    const testIdButton = this.page.locator('[data-testid="wizard-next-button"]')
    if (await testIdButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      const isDisabled = await testIdButton.isDisabled().catch(() => false)
      if (isDisabled) {
        const stepIndicator = await this.page
          .locator('[data-testid="wizard-step-indicator"]')
          .textContent()
          .catch(() => '?')
        throw new Error(
          `wizard-next-button is disabled at step "${stepIndicator}" ` +
            `at URL ${this.page.url()} — current step's canProceed() is false ` +
            `(likely a previous helper clicked the wrong element)`
        )
      }
      await testIdButton.click()
      await this.page.waitForTimeout(1000)
      return
    }

    const selectors = [
      'button:has-text("Next")',
      'button:has-text("Weiter")',
      'button:text-is("Next")',
      'button:text-is("Weiter")',
    ]

    for (const selector of selectors) {
      const btn = this.page.locator(selector).first()
      if (await btn.isVisible({ timeout: 1000 }).catch(() => false)) {
        await btn.click()
        await this.page.waitForTimeout(1000)
        return
      }
    }

    const wizardOpen = await this.page
      .locator('[data-testid="evaluation-wizard-header"]')
      .isVisible({ timeout: 500 })
      .catch(() => false)
    const allButtons = await this.page.locator('button').allTextContents()
    console.log('Available buttons:', allButtons.slice(0, 10))
    throw new Error(
      `Next/Weiter button not found in wizard ` +
        `(wizard header visible: ${wizardOpen}, URL: ${this.page.url()})`
    )
  }

  /**
   * Click Back button in the wizard (supports English and German)
   * Throws if button cannot be found
   */
  async clickBack(): Promise<void> {
    // First try data-testid selector (most reliable)
    const testIdButton = this.page.locator('[data-testid="wizard-back-button"]')
    if (await testIdButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await testIdButton.click()
      await this.page.waitForTimeout(1000)
      return
    }

    // Fallback: Try multiple selectors for Back/Zurück button
    const selectors = [
      'button:has-text("Back")',
      'button:has-text("Zurück")',
      'button:text-is("Back")',
      'button:text-is("Zurück")',
    ]

    for (const selector of selectors) {
      const btn = this.page.locator(selector).first()
      if (await btn.isVisible({ timeout: 1000 }).catch(() => false)) {
        await btn.click()
        await this.page.waitForTimeout(1000)
        return
      }
    }

    throw new Error('Back/Zurück button not found in wizard')
  }

  /**
   * Click Cancel button to close wizard (supports English and German)
   */
  async clickCancel(): Promise<void> {
    // Support both English and German: Cancel / Abbrechen
    const cancelBtn = this.page
      .locator('button')
      .filter({ hasText: /^(Cancel|Abbrechen)$/i })
      .first()

    if (await cancelBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await cancelBtn.click()
      await this.page.waitForTimeout(500)
    }
    // Cancel is optional, don't throw if not found
  }

  /**
   * Select first available prediction field in Step 2
   * Throws if no checkbox found
   */
  async selectFirstPredictionField(): Promise<void> {
    // Scope to the wizard body via its semantic testid so an unrelated
    // checkbox elsewhere on the page can't be picked up.
    const wizard = this.page.locator('[data-testid="evaluation-wizard-body"]')
    const checkbox = wizard.locator('input[type="checkbox"]').first()

    if (await checkbox.isVisible({ timeout: 3000 }).catch(() => false)) {
      await checkbox.click()
      await this.page.waitForTimeout(500)
      return
    }

    throw new Error(
      `No prediction field checkbox found inside wizard at ${this.page.url()}`
    )
  }

  /**
   * Select first available reference field in Step 3
   * Throws if no checkbox found
   */
  async selectFirstReferenceField(): Promise<void> {
    const wizard = this.page.locator('[data-testid="evaluation-wizard-body"]')
    const checkbox = wizard.locator('input[type="checkbox"]').first()

    if (await checkbox.isVisible({ timeout: 3000 }).catch(() => false)) {
      await checkbox.click()
      await this.page.waitForTimeout(500)
      return
    }

    throw new Error(
      `No reference field checkbox found inside wizard at ${this.page.url()}`
    )
  }

  /**
   * Get current wizard step number (1-5)
   * Supports both English and German: "Step X of 5" / "Schritt X von 5"
   */
  async getCurrentStep(): Promise<number> {
    // First try data-testid selector (most reliable)
    const stepIndicator = this.page.locator('[data-testid="wizard-step-indicator"]')
    if (await stepIndicator.isVisible({ timeout: 3000 }).catch(() => false)) {
      const text = await stepIndicator.textContent().catch(() => '')
      // Match both English and German formats
      const match = text?.match(/(?:Step|Schritt)\s*(\d)/)
      if (match) {
        return parseInt(match[1])
      }
    }

    // Fallback: Look for the wizard header which contains the step indicator
    const wizardHeader = this.page.locator('[data-testid="evaluation-wizard-header"]')
    if (await wizardHeader.isVisible({ timeout: 2000 }).catch(() => false)) {
      const headerText = await wizardHeader.textContent().catch(() => '')

      // Try English format: "Step X of 5"
      let match = headerText?.match(/Step (\d) of 5/)
      if (match) {
        return parseInt(match[1])
      }

      // Try German format: "Schritt X von 5"
      match = headerText?.match(/Schritt (\d) von 5/)
      if (match) {
        return parseInt(match[1])
      }
    }

    // Last resort: search page text for step indicator patterns
    const pageText = await this.page.textContent('body').catch(() => '')

    // Try English
    let match = pageText?.match(/Step (\d) of 5/)
    if (match) {
      return parseInt(match[1])
    }

    // Try German
    match = pageText?.match(/Schritt (\d) von 5/)
    if (match) {
      return parseInt(match[1])
    }

    console.log('Could not find step indicator. Wizard may not be open.')
    return 0
  }

  /**
   * Get all options from the Answer Type dropdown (HeadlessUI Listbox)
   */
  async getAnswerTypeOptions(): Promise<string[]> {
    // Try native <select> first (backwards compat), then HeadlessUI Listbox
    const nativeSelect = this.page.locator('select').first()
    if (await nativeSelect.isVisible({ timeout: 2000 }).catch(() => false)) {
      return await nativeSelect.locator('option').allTextContents()
    }

    // HeadlessUI: use the shared button locator
    const answerTypeButton = this.answerTypeButton()

    if (!(await answerTypeButton.isVisible({ timeout: 5000 }).catch(() => false))) {
      return []
    }

    await answerTypeButton.click()
    await this.page.waitForTimeout(300)

    const listbox = this.page.getByRole('listbox')
    if (!(await listbox.isVisible({ timeout: 3000 }).catch(() => false))) {
      return []
    }

    const options = await listbox.getByRole('option').allTextContents()
    await this.page.keyboard.press('Escape')
    await this.page.waitForTimeout(200)

    return options.map(o => o.trim())
  }

  /**
   * Select an answer type from the dropdown (HeadlessUI Listbox)
   */
  async selectAnswerType(value: string): Promise<void> {
    // Try native <select> first
    const nativeSelect = this.page.locator('select').first()
    if (await nativeSelect.isVisible({ timeout: 2000 }).catch(() => false)) {
      await nativeSelect.selectOption(value)
      await this.page.waitForTimeout(500)
      return
    }

    // HeadlessUI: find the answer type button by its current displayed value
    const answerTypeButton = this.answerTypeButton()

    await expect(answerTypeButton).toBeVisible({ timeout: 5000 })

    await answerTypeButton.click()
    await this.page.waitForTimeout(300)

    // Use data-value attribute for reliable value-based selection
    const option = this.page.locator(`[role="option"][data-value="${value}"]`)
    if (await option.isVisible({ timeout: 3000 }).catch(() => false)) {
      await option.click()
    } else {
      // Fallback: match by visible text
      const textOption = this.page.getByRole('option', { name: new RegExp(value, 'i') })
      if (await textOption.isVisible({ timeout: 1000 }).catch(() => false)) {
        await textOption.click()
      } else {
        await this.page.keyboard.press('Escape')
        throw new Error(`Could not find answer type option: ${value}`)
      }
    }
    await this.page.waitForTimeout(300)
  }

  /**
   * Get the currently selected answer type value from the dropdown.
   * Reads the data-value from the HeadlessUI button or falls back to native <select>.
   */
  async getSelectedAnswerType(): Promise<string> {
    // Try native <select> first
    const nativeSelect = this.page.locator('select').first()
    if (await nativeSelect.isVisible({ timeout: 1000 }).catch(() => false)) {
      return await nativeSelect.inputValue()
    }

    // HeadlessUI: read the button text (shows the display name, not the value)
    const button = this.answerTypeButton()
    await expect(button).toBeVisible({ timeout: 5000 })
    const text = await button.textContent()
    return text?.trim() || ''
  }

  /**
   * Locator for the answer type HeadlessUI button
   */
  private answerTypeButton() {
    return this.page.locator('button').filter({
      hasText: /Free.form|Short Text|Long Text|NER|Named Entity|Span|Freitext|Kurztext|Langtext|Rating|Binary|Choice|Classification/i
    }).first()
  }

  /**
   * Get visible criteria checkboxes labels
   */
  async getVisibleCriteria(): Promise<string[]> {
    const labels: string[] = []
    const checkboxes = this.page.locator('input[type="checkbox"]')
    const count = await checkboxes.count()

    for (let i = 0; i < count; i++) {
      const checkbox = checkboxes.nth(i)
      const label = await checkbox
        .locator('..')
        .locator('..')
        .textContent()
        .catch(() => '')

      if (label) {
        labels.push(label.trim())
      }
    }

    return labels
  }

  /**
   * Check if detected type banner is visible
   * Supports both English and German: "Detected:" / "erkannt"
   */
  async isDetectedTypeBannerVisible(): Promise<boolean> {
    // Try English first
    const bannerEn = this.page.locator('text=/Detected:/').first()
    if (await bannerEn.isVisible({ timeout: 1000 }).catch(() => false)) {
      return true
    }

    // Try German (e.g., "Automatisch erkannte Felder")
    const bannerDe = this.page.locator('text=/erkannt/i').first()
    return await bannerDe.isVisible({ timeout: 1000 }).catch(() => false)
  }

  /**
   * Navigate through wizard to Step 4 (Parameters)
   * Throws if any step fails
   */
  async navigateToParametersStep(): Promise<void> {
    // Open wizard
    await this.openAddEvaluationWizard()

    // Step 1: Select LLM-as-Judge
    await this.selectLLMJudgeMetric()
    await this.clickNext()

    // Step 2: Select prediction field
    await this.selectFirstPredictionField()
    await this.clickNext()

    // Step 3: Select reference field
    await this.selectFirstReferenceField()
    await this.clickNext()

    // Now on Step 4
  }
}
