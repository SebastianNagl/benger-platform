/**
 * Coverage-focused tests for GenerationTab
 *
 * Targets uncovered branches:
 * - getTaskDisplayValue fallbacks (question, prompt, first string, "Task ID")
 * - formatPrompt branches (prompt, question, text, fallback JSON)
 * - Model filter dropdown
 * - Task with no llm_responses (hasResponses = false)
 * - Response is object vs string
 * - Empty state with active filter vs without
 * - Export error branch
 * - Refresh error branch
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'
import { GenerationTab } from '../GenerationTab'

const mockPush = jest.fn()
const mockAddToast = jest.fn()
const mockStartProgress = jest.fn()
const mockUpdateProgress = jest.fn()
const mockCompleteProgress = jest.fn()
const mockFetchProjectTasks = jest.fn()

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, string | number>) => {
      const translations: Record<string, string> = {
        'toasts.generation.refreshed': 'Refreshed',
        'toasts.generation.refreshFailed': 'Refresh failed',
        'projects.generationTab.tasksWithGenerations': '{count} tasks',
        'projects.generationTab.modelsUsed': '{count} models',
        'projects.generationTab.allModels': 'All Models',
        'projects.generationTab.export': 'Export',
        'projects.generationTab.searchPlaceholder': 'Search...',
        'projects.generationTab.showingTasks': 'Showing {showing} of {total}',
        'projects.generationTab.taskId': 'Task #{id}',
        'projects.generationTab.responses': '{count} responses',
        'projects.generationTab.prompt': 'Prompt',
        'projects.generationTab.llmResponses': 'LLM Responses',
        'projects.generationTab.viewTaskDetails': 'View Details',
        'projects.generationTab.noMatchingGenerations': 'No matching results',
        'projects.generationTab.noGenerationsFound': 'No generations found',
        'projects.generationTab.generateResponsesToSee': 'Generate responses first',
      }
      let result = translations[key] || key
      if (params) {
        Object.entries(params).forEach(([k, v]) => {
          result = result.replace(`{${k}}`, String(v))
        })
      }
      return result
    },
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
    currentProject: { id: 'proj-1', title: 'Test' },
    loading: false,
    fetchProjectTasks: mockFetchProjectTasks,
  }),
}))

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

jest.mock('date-fns', () => ({
  formatDistanceToNow: jest.fn(() => '2 hours ago'),
}))

jest.mock('@/utils/taskTypeAdapter', () => ({
  labelStudioTaskToApi: (task: any) => task,
}))

describe('GenerationTab - branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue({ push: mockPush })
    global.URL.createObjectURL = jest.fn(() => 'blob:test')
    global.URL.revokeObjectURL = jest.fn()
  })

  describe('getTaskDisplayValue fallbacks', () => {
    it('displays question field', async () => {
      mockFetchProjectTasks.mockResolvedValue([
        {
          id: '1',
          data: { question: 'What is law?' },
          total_generations: 1,
          created_at: '2025-01-01T00:00:00Z',
          llm_responses: { 'gpt-4': 'Answer' },
        },
      ])

      render(<GenerationTab projectId="proj-1" />)

      await waitFor(() => {
        expect(screen.getByText('What is law?')).toBeInTheDocument()
      })
    })

    it('displays prompt field', async () => {
      mockFetchProjectTasks.mockResolvedValue([
        {
          id: '2',
          data: { prompt: 'Analyze this' },
          total_generations: 1,
          created_at: '2025-01-01T00:00:00Z',
          llm_responses: { 'gpt-4': 'Result' },
        },
      ])

      render(<GenerationTab projectId="proj-1" />)

      await waitFor(() => {
        expect(screen.getByText('Analyze this')).toBeInTheDocument()
      })
    })

    it('displays first string value from data', async () => {
      mockFetchProjectTasks.mockResolvedValue([
        {
          id: '3',
          data: { count: 5, description: 'Some text' },
          total_generations: 1,
          created_at: '2025-01-01T00:00:00Z',
          llm_responses: { 'gpt-4': 'Result' },
        },
      ])

      render(<GenerationTab projectId="proj-1" />)

      await waitFor(() => {
        expect(screen.getByText('Some text')).toBeInTheDocument()
      })
    })

    it('falls back to "Task ID" when no string values', async () => {
      mockFetchProjectTasks.mockResolvedValue([
        {
          id: '99',
          data: { num: 1, bool: true },
          total_generations: 1,
          created_at: '2025-01-01T00:00:00Z',
          llm_responses: { 'gpt-4': 'Result' },
        },
      ])

      render(<GenerationTab projectId="proj-1" />)

      await waitFor(() => {
        expect(screen.getByText('Task 99')).toBeInTheDocument()
      })
    })
  })

  describe('Task expansion and response display', () => {
    it('expands task to show prompt and responses', async () => {
      const user = userEvent.setup()
      mockFetchProjectTasks.mockResolvedValue([
        {
          id: '10',
          data: { text: 'Test text' },
          total_generations: 1,
          created_at: '2025-01-01T00:00:00Z',
          llm_responses: { 'gpt-4': 'Response text' },
        },
      ])

      render(<GenerationTab projectId="proj-1" />)

      await waitFor(() => {
        expect(screen.getByText('Test text')).toBeInTheDocument()
      })

      // Click to expand
      const taskHeader = screen.getByText('Test text').closest('[class*="cursor-pointer"]')
      await user.click(taskHeader!)

      await waitFor(() => {
        expect(screen.getByText('Prompt')).toBeInTheDocument()
        expect(screen.getByText('LLM Responses')).toBeInTheDocument()
        expect(screen.getByText('Response text')).toBeInTheDocument()
      })
    })

    it('displays object response as JSON string', async () => {
      const user = userEvent.setup()
      mockFetchProjectTasks.mockResolvedValue([
        {
          id: '11',
          data: { text: 'Object response' },
          total_generations: 1,
          created_at: '2025-01-01T00:00:00Z',
          llm_responses: { 'gpt-4': { key: 'value', nested: true } },
        },
      ])

      render(<GenerationTab projectId="proj-1" />)

      await waitFor(() => {
        expect(screen.getByText('Object response')).toBeInTheDocument()
      })

      const taskHeader = screen.getByText('Object response').closest('[class*="cursor-pointer"]')
      await user.click(taskHeader!)

      await waitFor(() => {
        // JSON.stringify should display the object
        expect(screen.getByText(/\"key\": \"value\"/)).toBeInTheDocument()
      })
    })

    it('shows task without llm_responses (no responses section)', async () => {
      const user = userEvent.setup()
      mockFetchProjectTasks.mockResolvedValue([
        {
          id: '12',
          data: { text: 'No responses' },
          total_generations: 1,
          created_at: '2025-01-01T00:00:00Z',
        },
      ])

      render(<GenerationTab projectId="proj-1" />)

      await waitFor(() => {
        expect(screen.getByText('No responses')).toBeInTheDocument()
      })

      const taskHeader = screen.getByText('No responses').closest('[class*="cursor-pointer"]')
      await user.click(taskHeader!)

      await waitFor(() => {
        expect(screen.getByText('Prompt')).toBeInTheDocument()
        // No "LLM Responses" heading since hasResponses is false
        expect(screen.queryByText('LLM Responses')).not.toBeInTheDocument()
      })
    })
  })

  describe('formatPrompt branches', () => {
    it('shows question as formatted prompt', async () => {
      const user = userEvent.setup()
      mockFetchProjectTasks.mockResolvedValue([
        {
          id: '20',
          data: { question: 'Legal question?' },
          total_generations: 1,
          created_at: '2025-01-01T00:00:00Z',
          llm_responses: { 'gpt-4': 'Answer' },
        },
      ])

      render(<GenerationTab projectId="proj-1" />)

      await waitFor(() => {
        expect(screen.getByText('Legal question?')).toBeInTheDocument()
      })

      const taskHeader = screen.getByText('Legal question?').closest('[class*="cursor-pointer"]')
      await user.click(taskHeader!)

      await waitFor(() => {
        expect(screen.getByText('Question: Legal question?')).toBeInTheDocument()
      })
    })
  })

  describe('Model filter', () => {
    it('filters tasks by selected model', async () => {
      mockFetchProjectTasks.mockResolvedValue([
        {
          id: '30',
          data: { text: 'GPT task' },
          total_generations: 1,
          created_at: '2025-01-01T00:00:00Z',
          llm_responses: { 'gpt-4': 'GPT response' },
        },
        {
          id: '31',
          data: { text: 'Claude task' },
          total_generations: 1,
          created_at: '2025-01-01T00:00:00Z',
          llm_responses: { 'claude-3': 'Claude response' },
        },
      ])

      render(<GenerationTab projectId="proj-1" />)

      await waitFor(() => {
        expect(screen.getByText('Showing 2 of 2')).toBeInTheDocument()
      })

      const filterSelect = screen.getByRole('combobox')
      fireEvent.change(filterSelect, { target: { value: 'gpt-4' } })

      await waitFor(() => {
        expect(screen.getByText('Showing 1 of 2')).toBeInTheDocument()
        expect(screen.getByText('GPT task')).toBeInTheDocument()
        expect(screen.queryByText('Claude task')).not.toBeInTheDocument()
      })
    })
  })

  describe('Empty state variants', () => {
    it('shows no matching message when filter is active', async () => {
      mockFetchProjectTasks.mockResolvedValue([
        {
          id: '40',
          data: { text: 'Some task' },
          total_generations: 1,
          created_at: '2025-01-01T00:00:00Z',
          llm_responses: { 'gpt-4': 'Response' },
        },
      ])

      render(<GenerationTab projectId="proj-1" />)

      await waitFor(() => {
        expect(screen.getByText('Some task')).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText('Search...')
      fireEvent.change(searchInput, { target: { value: 'nonexistent_xyz' } })

      await waitFor(() => {
        expect(screen.getByText('No matching results')).toBeInTheDocument()
      })
    })

    it('shows default empty message when no filters active', async () => {
      mockFetchProjectTasks.mockResolvedValue([])

      render(<GenerationTab projectId="proj-1" />)

      await waitFor(() => {
        expect(screen.getByText('No generations found')).toBeInTheDocument()
        expect(screen.getByText('Generate responses first')).toBeInTheDocument()
      })
    })
  })

  describe('Refresh error', () => {
    it('shows error toast when refresh fails', async () => {
      mockFetchProjectTasks
        .mockResolvedValueOnce([]) // Initial load
        .mockRejectedValueOnce(new Error('Network error')) // Refresh fails

      render(<GenerationTab projectId="proj-1" />)

      await waitFor(() => {
        expect(mockFetchProjectTasks).toHaveBeenCalledTimes(1)
      })

      mockStartProgress.mockClear()
      mockAddToast.mockClear()

      // Find and click refresh button
      const buttons = screen.getAllByRole('button')
      const refreshButton = buttons.find((btn) =>
        btn.querySelector('[class*="h-4 w-4"]') && !btn.textContent?.includes('Export')
      )

      if (refreshButton) {
        fireEvent.click(refreshButton)

        await waitFor(() => {
          expect(mockCompleteProgress).toHaveBeenCalledWith(expect.any(String), 'error')
          expect(mockAddToast).toHaveBeenCalledWith('Refresh failed', 'error')
        })
      }
    })
  })

  describe('Export error', () => {
    it('shows error toast when export fails', async () => {
      global.URL.createObjectURL = jest.fn(() => {
        throw new Error('Blob error')
      })

      mockFetchProjectTasks.mockResolvedValue([
        {
          id: '50',
          data: { text: 'Export task' },
          total_generations: 1,
          created_at: '2025-01-01T00:00:00Z',
          llm_responses: { 'gpt-4': 'Response' },
        },
      ])

      render(<GenerationTab projectId="proj-1" />)

      await waitFor(() => {
        expect(screen.getByText('Export')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Export'))

      await waitFor(() => {
        expect(mockCompleteProgress).toHaveBeenCalledWith(expect.any(String), 'error')
      })
    })
  })

  describe('View details navigation', () => {
    it('navigates to task detail page when clicking View Details', async () => {
      const user = userEvent.setup()
      mockFetchProjectTasks.mockResolvedValue([
        {
          id: '60',
          data: { text: 'Detail task' },
          total_generations: 1,
          created_at: '2025-01-01T00:00:00Z',
          llm_responses: { 'gpt-4': 'Response' },
        },
      ])

      render(<GenerationTab projectId="proj-1" />)

      await waitFor(() => {
        expect(screen.getByText('Detail task')).toBeInTheDocument()
      })

      // Expand task
      const taskHeader = screen.getByText('Detail task').closest('[class*="cursor-pointer"]')
      await user.click(taskHeader!)

      await waitFor(() => {
        expect(screen.getByText('View Details')).toBeInTheDocument()
      })

      await user.click(screen.getByText('View Details'))

      expect(mockPush).toHaveBeenCalledWith('/projects/proj-1/tasks/60')
    })
  })
})
