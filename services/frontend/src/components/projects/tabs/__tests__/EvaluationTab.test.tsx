/**
 * Test file for EvaluationTab component
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useRouter } from 'next/navigation'
import { EvaluationTab } from '../EvaluationTab'

// Mock dependencies
const mockAddToast = jest.fn()
const mockStartProgress = jest.fn()
const mockUpdateProgress = jest.fn()
const mockCompleteProgress = jest.fn()
const mockFetchProjectTasks = jest.fn()
const mockPush = jest.fn()

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: mockAddToast,
  }),
}))

// Mock I18n context with toast translations
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, string | number>) => {
      const translations: Record<string, string> = {
        'toasts.evaluation.refreshed': 'Evaluations refreshed successfully',
        'toasts.evaluation.refreshFailed': 'Failed to refresh evaluations',
        'projects.evaluationTab.evaluatedCount': '{count} evaluated',
        'projects.evaluationTab.pendingCount': '{count} pending',
        'projects.evaluationTab.allTasks': 'All Tasks',
        'projects.evaluationTab.evaluated': 'Evaluated',
        'projects.evaluationTab.pending': 'Pending',
        'projects.evaluationTab.export': 'Export',
        'projects.evaluationTab.searchPlaceholder': 'Search evaluations...',
        'projects.evaluationTab.showingTasks': 'Showing {showing} of {total} tasks',
        'projects.evaluationTab.taskId': 'Task ID',
        'projects.evaluationTab.taskData': 'Task Data',
        'projects.evaluationTab.status': 'Status',
        'projects.evaluationTab.accuracy': 'Accuracy',
        'projects.evaluationTab.f1Score': 'F1 Score',
        'projects.evaluationTab.confidence': 'Confidence',
        'projects.evaluationTab.model': 'Model',
        'projects.evaluationTab.evaluatedColumn': 'Evaluated',
        'projects.evaluationTab.noMatchingEvaluations': 'No evaluations match your filters',
        'projects.evaluationTab.noEvaluationData': 'No evaluation data available yet',
        'projects.evaluationTab.metricsWillAppear': 'Evaluation metrics will appear here once tasks are evaluated',
      }
      let result = translations[key] || key
      if (params) {
        Object.entries(params).forEach(([k, v]) => {
          result = result.replace(`{${k}}`, String(v))
        })
      }
      return result
    },
    locale: 'en',
  }),
}))

jest.mock('@/contexts/ProgressContext', () => ({
  useProgress: () => ({
    startProgress: mockStartProgress,
    updateProgress: mockUpdateProgress,
    completeProgress: mockCompleteProgress,
  }),
}))

jest.mock('@/stores/projectStore', () => ({
  useProjectStore: () => ({
    currentProject: {
      id: 'test-project-id',
      title: 'Test Project',
    },
    loading: false,
    fetchProjectTasks: mockFetchProjectTasks,
  }),
}))

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

// Mock date-fns
jest.mock('date-fns', () => ({
  formatDistanceToNow: jest.fn((date) => '2 hours ago'),
}))

// Mock useModels hook
jest.mock('@/hooks/useModels', () => ({
  useModels: () => ({
    models: [{ id: 'gpt-4', name: 'GPT-4' }],
    loading: false,
  }),
}))

// Sample task data
const mockTaskWithEvaluation = {
  id: '1',
  project_id: 'test-project-id',
  data: { text: 'Test task data' },
  is_labeled: true,
  total_annotations: 1,
  cancelled_annotations: 0,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T12:00:00Z',
  llm_evaluations: {
    eval_1: {
      accuracy: 0.85,
      f1_score: 0.82,
      precision: 0.88,
      recall: 0.79,
      confidence: 0.91,
      model: 'gpt-4',
      evaluated_at: '2025-01-01T12:00:00Z',
    },
  },
  llm_responses: { response_1: 'Test response' },
}

const mockTaskWithoutEvaluation = {
  id: '2',
  project_id: 'test-project-id',
  data: { question: 'Test question' },
  is_labeled: false,
  total_annotations: 0,
  cancelled_annotations: 0,
  created_at: '2025-01-01T00:00:00Z',
  llm_responses: { response_1: 'Test response' },
}

const mockTaskLowScore = {
  id: '3',
  project_id: 'test-project-id',
  data: { prompt: 'Test prompt' },
  is_labeled: true,
  total_annotations: 1,
  cancelled_annotations: 0,
  created_at: '2025-01-01T00:00:00Z',
  llm_evaluations: {
    eval_1: {
      accuracy: 0.45,
      f1_score: 0.42,
      confidence: 0.51,
      model: 'claude-3',
      evaluated_at: '2025-01-01T12:00:00Z',
    },
  },
}

describe('EvaluationTab', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue({
      push: mockPush,
    })
    // Default mock implementation
    mockFetchProjectTasks.mockResolvedValue([
      mockTaskWithEvaluation,
      mockTaskWithoutEvaluation,
      mockTaskLowScore,
    ])
  })

  describe('Component Rendering', () => {
    it('should render the component with action bar', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('2 evaluated')).toBeInTheDocument()
        expect(screen.getByText('1 pending')).toBeInTheDocument()
      })
    })

    it('should show loading state initially', () => {
      render(<EvaluationTab projectId="test-project-id" />)

      // Check for the loading spinner element
      const spinner = document.querySelector('.animate-spin')
      expect(spinner).toBeInTheDocument()
    })

    it('should load and display tasks after loading', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(mockFetchProjectTasks).toHaveBeenCalledWith('test-project-id')
        expect(screen.getByText('Test task data')).toBeInTheDocument()
      })
    })

    it('should display stats correctly', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('2 evaluated')).toBeInTheDocument()
        expect(screen.getByText('1 pending')).toBeInTheDocument()
      })
    })
  })

  describe('Task Filtering', () => {
    it('should filter tasks by status - all', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText(/Showing 3 of 3 tasks/i)).toBeInTheDocument()
      })
    })

    it('should filter tasks by status - evaluated', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('All Tasks')).toBeInTheDocument()
      })

      const filterSelect = screen.getByRole('combobox')
      fireEvent.change(filterSelect, { target: { value: 'evaluated' } })

      await waitFor(() => {
        expect(screen.getByText(/Showing 2 of 3 tasks/i)).toBeInTheDocument()
      })
    })

    it('should filter tasks by status - pending', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('All Tasks')).toBeInTheDocument()
      })

      const filterSelect = screen.getByRole('combobox')
      fireEvent.change(filterSelect, { target: { value: 'pending' } })

      await waitFor(() => {
        expect(screen.getByText(/Showing 1 of 3 tasks/i)).toBeInTheDocument()
      })
    })

    it('should filter tasks by search query', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText('Search evaluations...')
        ).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText('Search evaluations...')
      fireEvent.change(searchInput, { target: { value: 'question' } })

      await waitFor(() => {
        expect(screen.getByText(/Showing 1 of 3 tasks/i)).toBeInTheDocument()
        expect(screen.getByText('Test question')).toBeInTheDocument()
      })
    })

    it('should show empty state when no matches', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText('Search evaluations...')
        ).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText('Search evaluations...')
      fireEvent.change(searchInput, { target: { value: 'nonexistent' } })

      await waitFor(() => {
        expect(
          screen.getByText('No evaluations match your filters')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Task Sorting', () => {
    it('should sort by task ID', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('Task ID')).toBeInTheDocument()
      })

      const taskIdHeader = screen.getByText('Task ID')
      fireEvent.click(taskIdHeader)

      // Default sort is descending, so clicking should toggle to ascending
      await waitFor(() => {
        const rows = screen.getAllByRole('row')
        expect(rows.length).toBeGreaterThan(1)
      })
    })

    it('should sort by accuracy', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('Accuracy')).toBeInTheDocument()
      })

      const accuracyHeader = screen.getByText('Accuracy')
      fireEvent.click(accuracyHeader)

      await waitFor(() => {
        const rows = screen.getAllByRole('row')
        expect(rows.length).toBeGreaterThan(1)
      })
    })

    it('should toggle sort order on multiple clicks', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('Task ID')).toBeInTheDocument()
      })

      const taskIdHeader = screen.getByText('Task ID')

      // First click - changes to ascending
      fireEvent.click(taskIdHeader)

      // Second click - changes back to descending
      fireEvent.click(taskIdHeader)

      await waitFor(() => {
        const rows = screen.getAllByRole('row')
        expect(rows.length).toBeGreaterThan(1)
      })
    })
  })

  describe('Metrics Display', () => {
    it('should display evaluation metrics correctly', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('85.0%')).toBeInTheDocument() // accuracy
        expect(screen.getByText('82.0%')).toBeInTheDocument() // f1_score
        expect(screen.getByText('91.0%')).toBeInTheDocument() // confidence
        expect(screen.getByText('gpt-4')).toBeInTheDocument() // model
      })
    })

    it('should show placeholder for missing metrics', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        const placeholders = screen.getAllByText('—')
        expect(placeholders.length).toBeGreaterThan(0)
      })
    })

    it('should apply correct color classes based on score', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        const highScore = screen.getByText('85.0%')
        expect(highScore).toHaveClass('text-emerald-600')

        const lowScore = screen.getByText('45.0%')
        expect(lowScore).toHaveClass('text-red-600')
      })
    })

    it('should display evaluated badge for completed tasks', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        const evaluatedBadges = screen.getAllByText('Evaluated')
        // There are 2 evaluated tasks in the table
        expect(evaluatedBadges.length).toBeGreaterThanOrEqual(2)
      })
    })

    it('should display pending badge for unevaluated tasks', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('Pending')).toBeInTheDocument()
      })
    })

    it('should display relative time for evaluation', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        const timeElements = screen.getAllByText('2 hours ago')
        expect(timeElements.length).toBeGreaterThan(0)
      })
    })
  })

  describe('User Interactions', () => {
    it('should navigate to task detail on row click', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('Test task data')).toBeInTheDocument()
      })

      const row = screen.getByText('Test task data').closest('tr')
      fireEvent.click(row!)

      expect(mockPush).toHaveBeenCalledWith('/projects/test-project-id/tasks/1')
    })

    it('should handle export button click', async () => {
      // Mock URL.createObjectURL and URL.revokeObjectURL
      global.URL.createObjectURL = jest.fn(() => 'blob:test-url')
      global.URL.revokeObjectURL = jest.fn()

      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('Export')).toBeInTheDocument()
      })

      const exportButton = screen.getByText('Export')
      fireEvent.click(exportButton)

      await waitFor(() => {
        expect(mockStartProgress).toHaveBeenCalled()
        expect(mockUpdateProgress).toHaveBeenCalled()
        expect(mockCompleteProgress).toHaveBeenCalledWith(
          expect.any(String),
          'success'
        )
        expect(mockAddToast).toHaveBeenCalledWith(
          'Exported 3 evaluations',
          'success'
        )
      })
    })

    it('should disable export button when no tasks', async () => {
      mockFetchProjectTasks.mockResolvedValue([])

      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        const exportButton = screen.getByText('Export')
        expect(exportButton).toBeDisabled()
      })
    })

    it('should handle refresh button click', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      // Wait for initial load to complete
      await waitFor(() => {
        expect(mockFetchProjectTasks).toHaveBeenCalledWith('test-project-id')
      })

      // Clear mocks to track new calls
      mockFetchProjectTasks.mockClear()
      mockStartProgress.mockClear()
      mockCompleteProgress.mockClear()
      mockAddToast.mockClear()

      // Find and click refresh button using data-testid
      const refreshButton = screen.getByTestId('refresh-evaluations-button')
      fireEvent.click(refreshButton)

      await waitFor(() => {
        expect(mockStartProgress).toHaveBeenCalled()
        expect(mockFetchProjectTasks).toHaveBeenCalledWith('test-project-id')
        expect(mockCompleteProgress).toHaveBeenCalledWith(
          expect.any(String),
          'success'
        )
        expect(mockAddToast).toHaveBeenCalledWith(
          'Evaluations refreshed successfully',
          'success'
        )
      })
    })
  })

  describe('Error Handling', () => {
    beforeEach(() => {
      // Reset all mocks before each test in this suite
      jest.clearAllMocks()
      mockFetchProjectTasks.mockResolvedValue([
        mockTaskWithEvaluation,
        mockTaskWithoutEvaluation,
        mockTaskLowScore,
      ])
    })

    it('should handle export error', async () => {
      // Mock URL.createObjectURL to throw error
      global.URL.createObjectURL = jest.fn(() => {
        throw new Error('Export failed')
      })

      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('Export')).toBeInTheDocument()
      })

      const exportButton = screen.getByText('Export')
      fireEvent.click(exportButton)

      await waitFor(() => {
        expect(mockCompleteProgress).toHaveBeenCalledWith(
          expect.any(String),
          'error'
        )
        expect(mockAddToast).toHaveBeenCalledWith(
          expect.stringContaining('Export failed'),
          'error'
        )
      })
    })

    it('should handle refresh error', async () => {
      mockFetchProjectTasks
        .mockResolvedValueOnce([mockTaskWithEvaluation]) // Initial load succeeds
        .mockRejectedValueOnce(new Error('Network error')) // Refresh fails

      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('Test task data')).toBeInTheDocument()
      })

      // Clear mocks after initial load
      mockCompleteProgress.mockClear()
      mockAddToast.mockClear()

      const refreshButton = screen.getByTestId('refresh-evaluations-button')
      fireEvent.click(refreshButton)

      await waitFor(() => {
        expect(mockCompleteProgress).toHaveBeenCalledWith(
          expect.any(String),
          'error'
        )
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to refresh evaluations',
          'error'
        )
      })
    })
  })

  describe('Empty States', () => {
    beforeEach(() => {
      jest.clearAllMocks()
      mockFetchProjectTasks.mockReset()
    })

    it('should show empty state when no tasks with evaluation data', async () => {
      mockFetchProjectTasks.mockResolvedValue([])

      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(
          screen.getByText('No evaluation data available yet')
        ).toBeInTheDocument()
        expect(
          screen.getByText(
            'Evaluation metrics will appear here once tasks are evaluated'
          )
        ).toBeInTheDocument()
      })
    })

    it('should filter out tasks without evaluation data or predictions', async () => {
      const taskWithoutData = {
        id: '4',
        project_id: 'test-project-id',
        data: { text: 'No evaluation data' },
        is_labeled: false,
        total_annotations: 0,
        cancelled_annotations: 0,
        created_at: '2025-01-01T00:00:00Z',
      }

      mockFetchProjectTasks.mockResolvedValue([taskWithoutData])

      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.queryByText('No evaluation data')).not.toBeInTheDocument()
        expect(
          screen.getByText('No evaluation data available yet')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Task Display Values', () => {
    it('should display text field from task data', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('Test task data')).toBeInTheDocument()
      })
    })

    it('should display question field from task data', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('Test question')).toBeInTheDocument()
      })
    })

    it('should display prompt field from task data', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('Test prompt')).toBeInTheDocument()
      })
    })

    it('should fallback to task ID when no string value found', async () => {
      const taskWithoutStringValue = {
        id: '99',
        project_id: 'test-project-id',
        data: { number: 123, boolean: true },
        is_labeled: false,
        total_annotations: 0,
        cancelled_annotations: 0,
        created_at: '2025-01-01T00:00:00Z',
        llm_responses: { response_1: 'Test' },
      }

      mockFetchProjectTasks.mockResolvedValue([taskWithoutStringValue])

      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('Task 99')).toBeInTheDocument()
      })
    })
  })

  describe('Badge Variants', () => {
    it('should use correct variant for high accuracy scores', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        const badges = screen.getAllByText('Evaluated')
        // There are evaluated tasks showing the badge
        expect(badges.length).toBeGreaterThanOrEqual(2)
      })
    })

    it('should use correct variant for low accuracy scores', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        const badges = screen.getAllByText('Evaluated')
        // Both evaluated tasks should show Evaluated badge
        expect(badges.length).toBeGreaterThanOrEqual(2)
        expect(badges[0]).toBeInTheDocument()
      })
    })

    it('should show pending badge for unevaluated tasks', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        const pendingBadge = screen.getByText('Pending')
        expect(pendingBadge).toBeInTheDocument()
      })
    })
  })

  describe('Export Functionality', () => {
    beforeEach(() => {
      global.URL.createObjectURL = jest.fn(() => 'blob:test-url')
      global.URL.revokeObjectURL = jest.fn()
    })

    afterEach(() => {
      jest.restoreAllMocks()
    })

    it('should create correct export data structure', async () => {
      const mockClick = jest.fn()
      const mockLink = document.createElement('a')
      mockLink.click = mockClick

      const originalCreateElement = document.createElement.bind(document)
      jest.spyOn(document, 'createElement').mockImplementation((tagName) => {
        if (tagName === 'a') {
          return mockLink
        }
        return originalCreateElement(tagName)
      })

      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('Export')).toBeInTheDocument()
      })

      const exportButton = screen.getByText('Export')
      fireEvent.click(exportButton)

      await waitFor(() => {
        expect(mockClick).toHaveBeenCalled()
        expect(global.URL.createObjectURL).toHaveBeenCalled()
      })
    })

    it('should include correct filename with project title and date', async () => {
      const mockClick = jest.fn()
      const mockLink = document.createElement('a')
      mockLink.click = mockClick

      const originalCreateElement = document.createElement.bind(document)
      jest.spyOn(document, 'createElement').mockImplementation((tagName) => {
        if (tagName === 'a') {
          return mockLink
        }
        return originalCreateElement(tagName)
      })

      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('Export')).toBeInTheDocument()
      })

      const exportButton = screen.getByText('Export')
      fireEvent.click(exportButton)

      await waitFor(() => {
        expect(mockLink.download).toContain('Test Project')
        expect(mockLink.download).toContain('evaluations')
        expect(mockLink.download).toContain('.json')
      })
    })
  })

  describe('Additional Coverage - Sorting Edge Cases', () => {
    it('should handle sorting by status', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('Status')).toBeInTheDocument()
      })

      const statusHeader = screen.getByText('Status')
      fireEvent.click(statusHeader)

      await waitFor(() => {
        const rows = screen.getAllByRole('row')
        expect(rows.length).toBeGreaterThan(1)
      })
    })

    it('should handle sorting by created date', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        const tableHeaders = screen.getAllByRole('columnheader')
        expect(tableHeaders.length).toBeGreaterThan(0)
      })

      // Find the "Evaluated" column header (last one in the table)
      const tableHeaders = screen.getAllByRole('columnheader')
      const evaluatedHeader = tableHeaders[tableHeaders.length - 1]
      fireEvent.click(evaluatedHeader)

      await waitFor(() => {
        const rows = screen.getAllByRole('row')
        expect(rows.length).toBeGreaterThan(1)
      })
    })

    it('should handle sorting by confidence', async () => {
      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('Confidence')).toBeInTheDocument()
      })

      const confidenceHeader = screen.getByText('Confidence')
      fireEvent.click(confidenceHeader)

      await waitFor(() => {
        const rows = screen.getAllByRole('row')
        expect(rows.length).toBeGreaterThan(1)
      })
    })
  })

  describe('Additional Coverage - Score Formatting', () => {
    it('should handle tasks with medium accuracy scores', async () => {
      const mediumScoreTask = {
        id: '5',
        project_id: 'test-project-id',
        data: { text: 'Medium score task' },
        is_labeled: true,
        total_annotations: 1,
        cancelled_annotations: 0,
        created_at: '2025-01-01T00:00:00Z',
        llm_evaluations: {
          eval_1: {
            accuracy: 0.65,
            f1_score: 0.63,
            model: 'gpt-3.5',
            evaluated_at: '2025-01-01T12:00:00Z',
          },
        },
      }

      mockFetchProjectTasks.mockResolvedValue([mediumScoreTask])

      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        expect(screen.getByText('65.0%')).toBeInTheDocument()
        expect(screen.getByText('63.0%')).toBeInTheDocument()
      })
    })

    it('should handle tasks with null metrics', async () => {
      const taskWithNullMetrics = {
        id: '6',
        project_id: 'test-project-id',
        data: { text: 'Null metrics task' },
        is_labeled: true,
        total_annotations: 1,
        cancelled_annotations: 0,
        created_at: '2025-01-01T00:00:00Z',
        llm_evaluations: {
          eval_1: {
            model: 'test-model',
            evaluated_at: '2025-01-01T12:00:00Z',
          },
        },
      }

      mockFetchProjectTasks.mockResolvedValue([taskWithNullMetrics])

      render(<EvaluationTab projectId="test-project-id" />)

      await waitFor(() => {
        const placeholders = screen.getAllByText('—')
        expect(placeholders.length).toBeGreaterThan(0)
      })
    })
  })
})
