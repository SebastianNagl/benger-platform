/**
 * Tests for TaskGenerationComparisonModal — the per-task "all generations"
 * modal that shows one tab per model.
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'

const mockGet = jest.fn()
jest.mock('@/lib/api/client', () => ({
  apiClient: { get: (...args: any[]) => mockGet(...args) },
}))

import { TaskGenerationComparisonModal } from '../TaskGenerationComparisonModal'

const baseTask: any = {
  id: 'task-1',
  project_id: 'project-1',
  data: { text: 'Sample task text' },
  meta: {},
  is_labeled: false,
  total_annotations: 0,
  cancelled_annotations: 0,
  total_generations: 2,
  created_at: '2024-01-01T00:00:00Z',
}

describe('TaskGenerationComparisonModal', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGet.mockResolvedValue({
      task_id: 'task-1',
      model_id: 'model-a',
      results: [
        {
          task_id: 'task-1',
          model_id: 'model-a',
          generation_id: 'g1',
          status: 'completed',
          result: { generated_text: 'Hello from model A' },
        },
      ],
    })
  })

  it('does not render when closed', () => {
    const { container } = render(
      <TaskGenerationComparisonModal
        task={baseTask}
        isOpen={false}
        onClose={() => {}}
        projectId="project-1"
      />
    )
    expect(container.querySelector('[role="dialog"]')).not.toBeInTheDocument()
  })

  it('renders a tab per model and loads the selected model with include_history', async () => {
    render(
      <TaskGenerationComparisonModal
        task={{ ...baseTask, generation_models: ['model-a', 'model-b'] }}
        isOpen
        onClose={() => {}}
        projectId="project-1"
      />
    )

    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())

    // One tab per model.
    expect(screen.getByText('model-a')).toBeInTheDocument()
    expect(screen.getByText('model-b')).toBeInTheDocument()

    // The first model's results are fetched and rendered.
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    await waitFor(() =>
      expect(screen.getByText('Hello from model A')).toBeInTheDocument()
    )

    // Fetch uses include_history so per-model totals reconcile with the count.
    const firstUrl = mockGet.mock.calls[0][0] as string
    expect(firstUrl).toContain('model_id=model-a')
    expect(firstUrl).toContain('include_history=true')
  })

  it('shows the empty state and fetches nothing when there are no models', async () => {
    render(
      <TaskGenerationComparisonModal
        task={{ ...baseTask, generation_models: [] }}
        isOpen
        onClose={() => {}}
        projectId="project-1"
      />
    )

    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
    expect(
      screen.getByText(/generation\.comparison\.modal\.noGenerations/i)
    ).toBeInTheDocument()
    expect(mockGet).not.toHaveBeenCalled()
  })
})
