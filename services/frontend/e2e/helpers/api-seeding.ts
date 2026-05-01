/**
 * API seeding helper for E2E tests
 * Creates test data via API calls for isolated, reproducible test scenarios
 *
 * IMPORTANT: All API calls target the ephemeral test environment, never dev.
 * Tests must be run via `make test-e2e` which sets up isolated containers.
 */
import { Page } from '@playwright/test'

// Test data types
export interface SeededTask {
  id: string
  data: Record<string, unknown>
}

export interface SeededGeneration {
  id: string
  task_id: string
  model_id: string
  output: Record<string, unknown>
}

export interface SeededEvaluationResult {
  generation_id: string
  metrics: Record<string, number>
}

export interface SeededEvaluation {
  id: string
  project_id: string
  status: string
}

export interface EvaluationTestData {
  projectId: string
  tasks: SeededTask[]
  generations: SeededGeneration[]
  evaluation: SeededEvaluation
  expectedStats: {
    models: string[]
    modelMeans: Record<string, number>
    overallMean: number
    taskCount: number
  }
}

/**
 * API Seeding Helper for creating test data via API
 */
export class APISeedingHelper {
  private page: Page

  constructor(page: Page) {
    this.page = page
  }

  /**
   * Create a project via API. Retries once on transient network errors
   * (502/503/504 or `TypeError: Failed to fetch`) — these surface
   * sporadically on saturated CI runners. 4xx responses are NOT retried;
   * those are real failures.
   */
  async createProject(name: string, description?: string): Promise<string> {
    const attempt = async () =>
      this.page.evaluate(
        async ({ name, description }) => {
          try {
            const response = await fetch('/api/projects', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              credentials: 'include',
              body: JSON.stringify({
                title: name,
                description: description || `Test project: ${name}`,
              }),
            })
            if (!response.ok) {
              const errorText = await response.text()
              return {
                success: false,
                status: response.status,
                error: `${response.status}: ${errorText}`,
              }
            }
            const data = await response.json()
            return { success: true, status: response.status, projectId: data.id }
          } catch (e) {
            return { success: false, status: 0, error: String(e) }
          }
        },
        { name, description }
      )

    let result = await attempt()
    const transient =
      !result.success &&
      (result.status === 0 || // network error / fetch threw
        result.status === 502 ||
        result.status === 503 ||
        result.status === 504)
    if (transient) {
      console.warn(
        `[APISeedingHelper.createProject] transient failure (${result.error}), retrying once`
      )
      await new Promise((r) => setTimeout(r, 500))
      result = await attempt()
    }

    if (!result.success || !result.projectId) {
      throw new Error(`Failed to create project: ${result.error}`)
    }

    return result.projectId
  }

  /**
   * Set label config for a project via API
   */
  async setLabelConfig(projectId: string, labelConfig: string): Promise<void> {
    const result = await this.page.evaluate(
      async ({ projectId, labelConfig }) => {
        try {
          const response = await fetch(`/api/projects/${projectId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ label_config: labelConfig }),
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
      { projectId, labelConfig }
    )

    if (!result.success) {
      throw new Error(`Failed to set label config: ${result.error}`)
    }
  }

  /**
   * Import tasks to a project via API
   */
  async importTasks(
    projectId: string,
    tasks: Array<{ data: Record<string, unknown> }>
  ): Promise<SeededTask[]> {
    // Step 1: Import tasks via the import endpoint
    const importResult = await this.page.evaluate(
      async ({ projectId, tasks }) => {
        try {
          const response = await fetch(`/api/projects/${projectId}/import`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ data: tasks }),
          })
          if (!response.ok) {
            const errorText = await response.text()
            return { success: false, error: `${response.status}: ${errorText}` }
          }
          const data = await response.json()
          return { success: true, created: data.created_tasks || 0 }
        } catch (e) {
          return { success: false, error: String(e) }
        }
      },
      { projectId, tasks }
    )

    if (!importResult.success) {
      throw new Error(`Failed to import tasks: ${importResult.error}`)
    }

    // Step 2: Fetch the actual task objects from the project
    return this.getTasks(projectId)
  }

  /**
   * Get tasks for a project via API
   */
  async getTasks(projectId: string): Promise<SeededTask[]> {
    const result = await this.page.evaluate(async (projectId) => {
      try {
        const response = await fetch(`/api/projects/${projectId}/tasks`, {
          credentials: 'include',
        })
        if (!response.ok) {
          const errorText = await response.text()
          return { success: false, error: `${response.status}: ${errorText}` }
        }
        const data = await response.json()
        // API returns paginated response with 'items' key
        return { success: true, tasks: data.items || data.tasks || data || [] }
      } catch (e) {
        return { success: false, error: String(e) }
      }
    }, projectId)

    if (!result.success) {
      throw new Error(`Failed to get tasks: ${result.error}`)
    }

    return result.tasks || []
  }

  /**
   * Assign tasks to users via API
   */
  async assignTasks(
    projectId: string,
    taskIds: string[],
    userIds: string[],
    distribution: 'manual' | 'round_robin' | 'random' | 'load_balanced' = 'manual'
  ): Promise<{ assignments_created: number }> {
    const result = await this.page.evaluate(
      async ({ projectId, taskIds, userIds, distribution }) => {
        try {
          const response = await fetch(
            `/api/projects/${projectId}/tasks/assign`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              credentials: 'include',
              body: JSON.stringify({
                task_ids: taskIds,
                user_ids: userIds,
                distribution,
              }),
            }
          )
          if (!response.ok) {
            const errorText = await response.text()
            return { success: false, error: `${response.status}: ${errorText}` }
          }
          const data = await response.json()
          return {
            success: true,
            assignments_created: data.assignments_created,
          }
        } catch (e) {
          return { success: false, error: String(e) }
        }
      },
      { projectId, taskIds, userIds, distribution }
    )

    if (!result.success) {
      throw new Error(`Failed to assign tasks: ${result.error}`)
    }

    return { assignments_created: result.assignments_created || 0 }
  }

  /**
   * Get tasks assigned to current user via API
   */
  async getMyTasks(
    projectId: string
  ): Promise<{ tasks: SeededTask[]; total: number }> {
    const result = await this.page.evaluate(async (projectId) => {
      try {
        const response = await fetch(
          `/api/projects/${projectId}/my-tasks`,
          { credentials: 'include' }
        )
        if (!response.ok) {
          const errorText = await response.text()
          return { success: false, error: `${response.status}: ${errorText}` }
        }
        const data = await response.json()
        return { success: true, tasks: data.tasks || [], total: data.total || 0 }
      } catch (e) {
        return { success: false, error: String(e) }
      }
    }, projectId)

    if (!result.success) {
      throw new Error(`Failed to get my tasks: ${result.error}`)
    }

    return { tasks: result.tasks || [], total: result.total || 0 }
  }

  /**
   * Create an annotation for a task via API
   */
  async createAnnotation(
    taskId: string,
    result: Array<{
      from_name: string
      to_name: string
      type: string
      value: Record<string, unknown>
    }>
  ): Promise<string> {
    const apiResult = await this.page.evaluate(
      async ({ taskId, result }) => {
        try {
          const response = await fetch(
            `/api/projects/tasks/${taskId}/annotations`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              credentials: 'include',
              body: JSON.stringify({ result }),
            }
          )
          if (!response.ok) {
            const errorText = await response.text()
            return { success: false, error: `${response.status}: ${errorText}` }
          }
          const data = await response.json()
          return { success: true, annotationId: data.id }
        } catch (e) {
          return { success: false, error: String(e) }
        }
      },
      { taskId, result }
    )

    if (!apiResult.success || !apiResult.annotationId) {
      throw new Error(`Failed to create annotation: ${apiResult.error}`)
    }

    return apiResult.annotationId
  }

  /**
   * Create a generation for a task via API
   * This seeds mock LLM outputs without actually calling LLM APIs
   */
  async createGeneration(
    projectId: string,
    taskId: string,
    modelId: string,
    output: Record<string, unknown>
  ): Promise<string> {
    const result = await this.page.evaluate(
      async ({ projectId, taskId, modelId, output }) => {
        try {
          const response = await fetch(`/api/generations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
              project_id: projectId,
              task_id: taskId,
              model_id: modelId,
              output,
              status: 'completed',
            }),
          })
          if (!response.ok) {
            const errorText = await response.text()
            return { success: false, error: `${response.status}: ${errorText}` }
          }
          const data = await response.json()
          return { success: true, generationId: data.id }
        } catch (e) {
          return { success: false, error: String(e) }
        }
      },
      { projectId, taskId, modelId, output }
    )

    if (!result.success || !result.generationId) {
      throw new Error(`Failed to create generation: ${result.error}`)
    }

    return result.generationId
  }

  /**
   * Create an evaluation for a project via API
   */
  async createEvaluation(
    projectId: string,
    evaluationType: string = 'multi_field'
  ): Promise<string> {
    const result = await this.page.evaluate(
      async ({ projectId, evaluationType }) => {
        try {
          const response = await fetch(`/api/evaluations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
              project_id: projectId,
              evaluation_type: evaluationType,
              status: 'completed',
            }),
          })
          if (!response.ok) {
            const errorText = await response.text()
            return { success: false, error: `${response.status}: ${errorText}` }
          }
          const data = await response.json()
          return { success: true, evaluationId: data.id }
        } catch (e) {
          return { success: false, error: String(e) }
        }
      },
      { projectId, evaluationType }
    )

    if (!result.success || !result.evaluationId) {
      throw new Error(`Failed to create evaluation: ${result.error}`)
    }

    return result.evaluationId
  }

  /**
   * Create evaluation sample results via API
   * This seeds predetermined scores for verification
   */
  async createEvaluationResults(
    evaluationId: string,
    results: Array<{
      generation_id: string
      task_id: string
      metrics: Record<string, number>
    }>
  ): Promise<void> {
    const result = await this.page.evaluate(
      async ({ evaluationId, results }) => {
        try {
          const response = await fetch(
            `/api/evaluations/${evaluationId}/results`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              credentials: 'include',
              body: JSON.stringify({ results }),
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
      { evaluationId, results }
    )

    if (!result.success) {
      throw new Error(`Failed to create evaluation results: ${result.error}`)
    }
  }

  /**
   * Update evaluation status via API
   */
  async updateEvaluationStatus(
    evaluationId: string,
    status: string
  ): Promise<void> {
    const result = await this.page.evaluate(
      async ({ evaluationId, status }) => {
        try {
          const response = await fetch(`/api/evaluations/${evaluationId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ status }),
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
      { evaluationId, status }
    )

    if (!result.success) {
      throw new Error(`Failed to update evaluation status: ${result.error}`)
    }
  }

  /**
   * Seed mock generations via test seeding API
   * Creates ResponseGeneration + Generation records without calling LLMs
   */
  async seedGenerations(
    projectId: string,
    generations: Array<{ task_id: string; model_id: string; output: string }>
  ): Promise<string[]> {
    const result = await this.page.evaluate(
      async ({ projectId, generations }) => {
        try {
          const response = await fetch('/api/test/seed/generations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ project_id: projectId, generations }),
          })
          if (!response.ok) {
            const errorText = await response.text()
            return { success: false, error: `${response.status}: ${errorText}` }
          }
          const data = await response.json()
          return { success: true, ids: data.ids || [] }
        } catch (e) {
          return { success: false, error: String(e) }
        }
      },
      { projectId, generations }
    )

    if (!result.success) {
      throw new Error(`Failed to seed generations: ${result.error}`)
    }

    return result.ids || []
  }

  /**
   * Seed mock evaluation via test seeding API
   * Creates Evaluation + EvaluationSampleResult records without running metrics
   */
  async seedEvaluation(
    projectId: string,
    results: Array<{ generation_id: string; metric: string; score: number }>,
    evaluationName?: string
  ): Promise<string[]> {
    const result = await this.page.evaluate(
      async ({ projectId, results, evaluationName }) => {
        try {
          const response = await fetch('/api/test/seed/evaluation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
              project_id: projectId,
              evaluation_name: evaluationName || 'E2E Test Evaluation',
              results,
            }),
          })
          if (!response.ok) {
            const errorText = await response.text()
            return { success: false, error: `${response.status}: ${errorText}` }
          }
          const data = await response.json()
          return { success: true, ids: data.ids || [] }
        } catch (e) {
          return { success: false, error: String(e) }
        }
      },
      { projectId, results, evaluationName }
    )

    if (!result.success) {
      throw new Error(`Failed to seed evaluation: ${result.error}`)
    }

    return result.ids || []
  }

  /**
   * Cleanup test project via test seeding API (more thorough than deleteProject)
   * Deletes project + all related data (tasks, annotations, generations, evaluations)
   */
  async cleanupTestProject(projectId: string): Promise<void> {
    await this.page.evaluate(async (projectId) => {
      try {
        await fetch(`/api/test/cleanup/${projectId}`, {
          method: 'DELETE',
          credentials: 'include',
        })
      } catch {
        // Cleanup failure is non-fatal
      }
    }, projectId)
  }

  /**
   * Delete a project via API (cleanup)
   */
  async deleteProject(projectId: string): Promise<boolean> {
    const result = await this.page.evaluate(async (projectId) => {
      try {
        const response = await fetch(`/api/projects/${projectId}`, {
          method: 'DELETE',
          credentials: 'include',
        })
        // 200 = deleted, 404 = already deleted (both acceptable)
        return {
          success: response.status === 200 || response.status === 404,
        }
      } catch (e) {
        return { success: false, error: String(e) }
      }
    }, projectId)

    return result.success
  }

  /**
   * Wait for a condition with polling
   */
  async waitFor(
    condition: () => Promise<boolean>,
    timeout: number = 10000,
    interval: number = 500
  ): Promise<boolean> {
    const startTime = Date.now()
    while (Date.now() - startTime < timeout) {
      if (await condition()) {
        return true
      }
      await this.page.waitForTimeout(interval)
    }
    return false
  }
}
