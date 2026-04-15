/**
 * Evaluation test fixture for E2E tests
 * Creates a project with tasks and annotations ready for evaluation
 *
 * NOTE: Full generation/evaluation seeding requires either:
 * 1. Running actual LLM generations (requires API keys, slow)
 * 2. Database seeding (not pure API approach)
 * 3. Test seeding API endpoints (not currently available)
 *
 * This fixture creates the foundation (project, tasks, annotations) via API.
 * For tests requiring evaluation results, use existing projects with data
 * or run manual evaluations before testing.
 *
 * IMPORTANT: All data is created via API in the ephemeral test environment.
 * Tests must be run via `make test-e2e` which sets up isolated containers.
 */
import { Page } from '@playwright/test'
import { APISeedingHelper } from '../helpers/api-seeding'
import { TestHelpers } from '../helpers/test-helpers'

// Expected model scores when evaluation data is present
// These are reference values for verification when tests run on seeded data
export const TEST_MODEL_SCORES = {
  'test-model-alpha': {
    scores: [0.8, 0.9, 0.7, 0.85, 0.75],
    expectedMean: 0.8,
    displayName: 'Test Model Alpha',
  },
  'test-model-beta': {
    scores: [0.6, 0.7, 0.5, 0.65, 0.55],
    expectedMean: 0.6,
    displayName: 'Test Model Beta',
  },
  'test-model-gamma': {
    scores: [0.9, 0.95, 0.85, 0.9, 0.8],
    expectedMean: 0.88,
    displayName: 'Test Model Gamma',
  },
}

export const EXPECTED_OVERALL_MEAN = 0.76

export const TEST_TASKS = [
  { text: 'What are the key elements of a valid contract under German law?' },
  { text: 'Explain the concept of Treu und Glauben in German civil law.' },
  { text: 'What is the difference between BGB and HGB?' },
  { text: 'Describe the German court system hierarchy.' },
  { text: 'What are the requirements for a legally binding will in Germany?' },
]

export const LABEL_CONFIG = `<View>
  <Text name="text" value="$text"/>
  <TextArea name="answer" toName="text" placeholder="Enter your legal analysis" required="true"/>
</View>`

export interface EvaluationFixtureResult {
  projectId: string
  projectName: string
  taskIds: string[]
  generationIds: string[]
  evaluationId: string
  expectedStats: {
    models: string[]
    modelMeans: Record<string, number>
    overallMean: number
    taskCount: number
    sampleCount: number
  }
}

/**
 * Seed a basic evaluation test project
 * Creates project, tasks, and annotations via API.
 *
 * Note: Full generation/evaluation seeding is not available via API alone.
 * For tests requiring evaluation results, either:
 * 1. Use an existing project with evaluation data
 * 2. Run manual evaluations before testing
 * 3. Add test seeding endpoints to the API
 */
export async function seedEvaluationTestData(
  page: Page,
  helpers: TestHelpers
): Promise<EvaluationFixtureResult> {
  const apiSeeder = new APISeedingHelper(page)
  const timestamp = Date.now()
  const projectName = `E2E Evaluation Test ${timestamp}`

  console.log(`[Evaluation Fixture] Creating test project: ${projectName}`)

  // Step 1: Create project
  const projectId = await apiSeeder.createProject(
    projectName,
    'E2E test project for evaluation results verification'
  )
  console.log(`[Evaluation Fixture] Project created: ${projectId}`)

  // Step 2: Set label config
  await apiSeeder.setLabelConfig(projectId, LABEL_CONFIG)
  console.log(`[Evaluation Fixture] Label config set`)

  // Step 3: Import tasks
  const tasksToImport = TEST_TASKS.map((t) => ({ data: t }))
  await apiSeeder.importTasks(projectId, tasksToImport)
  console.log(`[Evaluation Fixture] ${TEST_TASKS.length} tasks imported`)

  // Wait for tasks to be indexed
  await page.waitForTimeout(2000)

  // Step 4: Get task IDs
  const tasks = await apiSeeder.getTasks(projectId)
  const taskIds = tasks.map((t) => t.id)
  console.log(`[Evaluation Fixture] Got ${taskIds.length} task IDs`)

  if (taskIds.length < TEST_TASKS.length) {
    throw new Error(
      `Expected ${TEST_TASKS.length} tasks, got ${taskIds.length}`
    )
  }

  // Step 5: Create annotations (reference answers)
  for (let i = 0; i < taskIds.length; i++) {
    try {
      await apiSeeder.createAnnotation(taskIds[i], [
        {
          from_name: 'answer',
          to_name: 'text',
          type: 'textarea',
          value: { text: [`Reference answer for task ${i + 1}`] },
        },
      ])
    } catch (error) {
      console.warn(`[Evaluation Fixture] Failed to create annotation for task ${i + 1}:`, error)
    }
  }
  console.log(`[Evaluation Fixture] Annotations created`)

  // NOTE: Generation and evaluation seeding would require either:
  // 1. Calling actual LLM APIs (slow, requires keys)
  // 2. Direct database access (not pure API)
  // 3. Test seeding endpoints (not currently available)
  //
  // For now, tests should either:
  // - Test against projects with existing evaluation data
  // - Focus on UI functionality without strict data verification
  // - Use this fixture for basic project setup only

  console.log(`[Evaluation Fixture] Setup complete (project ready for manual evaluation)`)

  // Return partial data - no evaluation results seeded
  return {
    projectId,
    projectName,
    taskIds,
    generationIds: [], // Not seeded
    evaluationId: '', // Not seeded
    expectedStats: {
      models: [],
      modelMeans: {},
      overallMean: 0,
      taskCount: TEST_TASKS.length,
      sampleCount: 0,
    },
  }
}

/**
 * Clean up evaluation test data
 */
export async function cleanupEvaluationTestData(
  page: Page,
  projectId: string
): Promise<void> {
  const apiSeeder = new APISeedingHelper(page)
  const success = await apiSeeder.deleteProject(projectId)
  if (success) {
    console.log(`[Evaluation Fixture] Project ${projectId} deleted`)
  } else {
    console.warn(`[Evaluation Fixture] Failed to delete project ${projectId}`)
  }
}

/**
 * Seed a second evaluation to test aggregation across multiple evaluations
 * This creates new generations for a different model and adds to existing project
 */
export async function seedSecondEvaluation(
  page: Page,
  projectId: string,
  taskIds: string[]
): Promise<{
  evaluationId: string
  generationIds: string[]
  modelId: string
  expectedMean: number
}> {
  const apiSeeder = new APISeedingHelper(page)
  const modelId = 'test-model-delta'
  const scores = [0.7, 0.75, 0.65, 0.7, 0.6] // mean = 0.68

  console.log(`[Evaluation Fixture] Creating second evaluation with ${modelId}`)

  // Create generations
  const generationIds: string[] = []
  for (let i = 0; i < taskIds.length; i++) {
    const generationId = await apiSeeder.createGeneration(
      projectId,
      taskIds[i],
      modelId,
      { answer: `Generated answer from ${modelId} for task ${i + 1}` }
    )
    generationIds.push(generationId)
  }

  // Create evaluation
  const evaluationId = await apiSeeder.createEvaluation(projectId, 'multi_field')

  // Create results
  const results = taskIds.map((taskId, i) => ({
    generation_id: generationIds[i],
    task_id: taskId,
    metrics: {
      llm_judge_custom: scores[i],
      score: scores[i],
    },
  }))

  await apiSeeder.createEvaluationResults(evaluationId, results)
  await apiSeeder.updateEvaluationStatus(evaluationId, 'completed')

  console.log(`[Evaluation Fixture] Second evaluation created: ${evaluationId}`)

  return {
    evaluationId,
    generationIds,
    modelId,
    expectedMean: 0.68,
  }
}
