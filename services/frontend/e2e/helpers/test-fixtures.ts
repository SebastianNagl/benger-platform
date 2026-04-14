/**
 * Test fixtures helper for E2E tests
 * Creates projects with specific configurations for testing
 */
import { Page } from '@playwright/test'
import { TestHelpers } from './test-helpers'

// Label config templates
export const SIMPLE_TEXT_CONFIG = `<View>
  <Text name="text" value="$text"/>
  <TextArea name="answer" toName="text" placeholder="Enter your answer" required="true"/>
</View>`

export const CHOICE_CONFIG = `<View>
  <Text name="text" value="$text"/>
  <Choices name="sentiment" toName="text" choice="single" required="true">
    <Choice value="positive"/>
    <Choice value="negative"/>
    <Choice value="neutral"/>
  </Choices>
</View>`

export const MULTI_CHOICE_CONFIG = `<View>
  <Text name="text" value="$text"/>
  <Choices name="categories" toName="text" choice="multiple" required="true">
    <Choice value="legal"/>
    <Choice value="business"/>
    <Choice value="technical"/>
    <Choice value="other"/>
  </Choices>
</View>`

export const COMBINED_CONFIG = `<View>
  <Text name="text" value="$text"/>
  <TextArea name="summary" toName="text" placeholder="Enter summary" required="true"/>
  <Choices name="quality" toName="text" choice="single" required="true">
    <Choice value="good"/>
    <Choice value="fair"/>
    <Choice value="poor"/>
  </Choices>
</View>`

// NER/Span Selection config (span_selection type)
export const NER_CONFIG = `<View>
  <Text name="text" value="$text"/>
  <Labels name="entities" toName="text">
    <Label value="Person"/>
    <Label value="Organization"/>
    <Label value="Location"/>
  </Labels>
</View>`

// Rating Scale config (rating type)
export const RATING_CONFIG = `<View>
  <Text name="text" value="$text"/>
  <Rating name="quality" toName="text" maxRating="5" required="true"/>
</View>`

// Numeric Value config (numeric type)
export const NUMERIC_CONFIG = `<View>
  <Text name="text" value="$text"/>
  <Number name="score" toName="text" min="0" max="100" required="true"/>
</View>`

export class TestFixtures {
  private page: Page
  private helpers: TestHelpers

  constructor(page: Page, helpers: TestHelpers) {
    this.page = page
    this.helpers = helpers
  }

  /**
   * Wait for tasks to be indexed and queryable
   * Polls the API until the expected number of tasks are returned
   */
  async waitForTasksIndexed(
    projectId: string,
    expectedCount: number,
    timeout: number = 10000
  ): Promise<boolean> {
    const startTime = Date.now()
    const pollInterval = 500

    while (Date.now() - startTime < timeout) {
      const result = await this.page.evaluate(async (id) => {
        try {
          const response = await fetch(`/api/projects/${id}/tasks?limit=1`, {
            credentials: 'include',
          })
          if (!response.ok) return { total: 0 }
          const data = await response.json()
          return { total: data.total || data.tasks?.length || 0 }
        } catch {
          return { total: 0 }
        }
      }, projectId)

      if (result.total >= expectedCount) {
        return true
      }

      await this.page.waitForTimeout(pollInterval)
    }

    console.warn(
      `Tasks not fully indexed within ${timeout}ms (got ${expectedCount} expected)`
    )
    return false
  }

  /**
   * Validate clean test state before starting tests
   * Checks for orphaned test projects from previous runs
   */
  async validateCleanState(): Promise<{
    clean: boolean
    orphanedProjects: string[]
  }> {
    const result = await this.page.evaluate(async () => {
      try {
        const response = await fetch('/api/projects?search=E2E_', {
          credentials: 'include',
        })
        if (!response.ok) return { projects: [] }
        const data = await response.json()
        const projects = data.projects || data || []
        return {
          projects: projects
            .filter((p: { title: string }) => p.title?.includes('E2E'))
            .map((p: { id: string; title: string }) => ({
              id: p.id,
              title: p.title,
            })),
        }
      } catch {
        return { projects: [] }
      }
    })

    const orphanedProjects = result.projects.map((p: { id: string }) => p.id)

    if (orphanedProjects.length > 0) {
      console.warn(
        `Found ${orphanedProjects.length} orphaned E2E test projects`
      )
    }

    return {
      clean: orphanedProjects.length === 0,
      orphanedProjects,
    }
  }

  /**
   * Clean up orphaned test projects from previous runs
   */
  async cleanupOrphanedProjects(): Promise<number> {
    const { orphanedProjects } = await this.validateCleanState()
    let cleanedCount = 0

    for (const projectId of orphanedProjects) {
      const success = await this.helpers.deleteTestProject(projectId)
      if (success) {
        cleanedCount++
      }
    }

    if (cleanedCount > 0) {
      console.log(`Cleaned up ${cleanedCount} orphaned test projects`)
    }

    return cleanedCount
  }

  /**
   * Create a project with label config and tasks for annotation testing
   * Includes retry logic for resilience against flaky infrastructure
   */
  async createAnnotationTestProject(
    labelConfig: string = SIMPLE_TEXT_CONFIG,
    taskCount: number = 5
  ): Promise<string> {
    const maxRetries = 3
    let lastError: Error | null = null

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const projectName = `E2E Annotation ${Date.now()}`
        const projectId = await this.helpers.createTestProject(projectName)

        if (!projectId) {
          throw new Error('Project creation returned null')
        }

        // Set label config via API
        await this.setLabelConfig(projectId, labelConfig)

        // Create test tasks
        await this.createTasks(projectId, taskCount)

        return projectId
      } catch (error) {
        lastError = error as Error
        console.warn(`Project creation attempt ${attempt}/${maxRetries} failed:`, error)
        if (attempt < maxRetries) {
          // Wait before retry with exponential backoff
          await this.page.waitForTimeout(1000 * attempt)
        }
      }
    }

    throw new Error(`Failed to create test project after ${maxRetries} attempts: ${lastError?.message}`)
  }

  /**
   * Create a project configured for generation testing (UI only)
   */
  async createGenerationTestProject(taskCount: number = 5): Promise<string> {
    const projectName = `E2E Generation ${Date.now()}`
    const projectId = await this.helpers.createTestProject(projectName)

    if (!projectId) {
      throw new Error('Failed to create test project')
    }

    // Set label config
    await this.setLabelConfig(projectId, SIMPLE_TEXT_CONFIG)

    // Create test tasks
    await this.createTasks(projectId, taskCount)

    // Configure generation settings
    await this.setGenerationConfig(projectId, {
      selected_models: ['gpt-4o-mini'],
      prompt_structures: [
        {
          name: 'default',
          template: 'Answer the following: {{text}}',
          is_active: true,
        },
      ],
    })

    return projectId
  }

  /**
   * Create tasks with sample data using the import endpoint
   */
  async createTasks(projectId: string, count: number): Promise<void> {
    const sampleQuestions = [
      'What are the key legal implications of this contract clause?',
      'Summarize the main findings of this legal document.',
      'Identify the parties involved in this agreement.',
      'What are the termination conditions specified?',
      'Explain the liability limitations mentioned.',
      'What jurisdiction governs this contract?',
      'Describe the payment terms outlined.',
      'What are the confidentiality requirements?',
      'List the warranties provided in this agreement.',
      'What dispute resolution mechanism is specified?',
    ]

    // Build tasks array in Label Studio format
    const tasks = []
    for (let i = 0; i < count; i++) {
      const questionIndex = i % sampleQuestions.length
      tasks.push({
        id: i + 1,
        data: { text: sampleQuestions[questionIndex] },
      })
    }

    // Import all tasks at once using the import endpoint
    const result = await this.page.evaluate(
      async ({ projectId, tasks }) => {
        try {
          const response = await fetch(`/api/projects/${projectId}/import`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            credentials: 'include',
            body: JSON.stringify({ data: tasks }),
          })
          if (!response.ok) {
            const errorText = await response.text()
            return {
              success: false,
              error: `${response.status}: ${errorText}`,
            }
          }
          return { success: true }
        } catch (e) {
          return { success: false, error: String(e) }
        }
      },
      { projectId, tasks }
    )

    if (!result.success) {
      console.error(`Failed to import tasks:`, result.error)
      return
    }

    // Wait for tasks to be indexed and queryable
    await this.waitForTasksIndexed(projectId, count, 10000)
  }

  /**
   * Set label configuration for a project
   */
  async setLabelConfig(projectId: string, config: string): Promise<void> {
    // Cookies are already set from login - no navigation needed
    const result = await this.page.evaluate(
      async ({ projectId, config }) => {
        try {
          // Use credentials: 'include' to send cookies for auth
          const response = await fetch(`/api/projects/${projectId}`, {
            method: 'PATCH',
            headers: {
              'Content-Type': 'application/json',
            },
            credentials: 'include',
            body: JSON.stringify({ label_config: config }),
          })
          if (!response.ok) {
            const errorText = await response.text()
            return { success: false, error: `${response.status}: ${errorText}` }
          }
          return { success: true }
        } catch (e) {
          return { success: false, error: String(e) }
        }
      },
      { projectId, config }
    )
    if (!result.success) {
      console.error('Failed to set label config:', result.error)
    }
  }

  /**
   * Set generation configuration for a project
   */
  async setGenerationConfig(
    projectId: string,
    config: {
      selected_models?: string[]
      prompt_structures?: Array<{
        name: string
        template: string
        is_active?: boolean
      }>
    }
  ): Promise<void> {
    const result = await this.page.evaluate(
      async ({ projectId, config }) => {
        try {
          const response = await fetch(`/api/projects/${projectId}`, {
            method: 'PATCH',
            headers: {
              'Content-Type': 'application/json',
            },
            credentials: 'include',
            body: JSON.stringify({ generation_config: config }),
          })
          if (!response.ok) {
            const errorText = await response.text()
            return { success: false, error: `${response.status}: ${errorText}` }
          }
          return { success: true }
        } catch (e) {
          return { success: false, error: String(e) }
        }
      },
      { projectId, config }
    )
    if (!result.success) {
      console.error('Failed to set generation config:', result.error)
    }
  }

  /**
   * Create an annotation for a task
   */
  async createAnnotation(
    taskId: string,
    annotationResult: Array<{
      from_name: string
      to_name: string
      type: string
      value: { text?: string; choices?: string[] }
    }>
  ): Promise<void> {
    const result = await this.page.evaluate(
      async ({ taskId, annotationResult }) => {
        try {
          const response = await fetch(
            `/api/projects/tasks/${taskId}/annotations`,
            {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              credentials: 'include',
              body: JSON.stringify({ result: annotationResult }),
            }
          )
          if (!response.ok) {
            const errorText = await response.text()
            return { success: false, error: `${response.status}: ${errorText}` }
          }
          return { success: true }
        } catch (e) {
          return { success: false, error: String(e) }
        }
      },
      { taskId, annotationResult }
    )
    if (!result.success) {
      console.error('Failed to create annotation:', result.error)
    }
  }

  /**
   * Get tasks for a project
   */
  async getTasks(
    projectId: string
  ): Promise<Array<{ id: string; data: Record<string, unknown> }>> {
    return await this.page.evaluate(async (projectId) => {
      try {
        const response = await fetch(`/api/projects/${projectId}/tasks`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
          credentials: 'include',
        })
        if (!response.ok) {
          console.error('Failed to get tasks:', await response.text())
          return []
        }
        const data = await response.json()
        return data.items || data.tasks || (Array.isArray(data) ? data : [])
      } catch (e) {
        console.error('Failed to get tasks:', e)
        return []
      }
    }, projectId)
  }

  /**
   * Delete a test project and all its data
   */
  async cleanup(projectId: string): Promise<void> {
    await this.helpers.deleteTestProject(projectId)
  }
}
