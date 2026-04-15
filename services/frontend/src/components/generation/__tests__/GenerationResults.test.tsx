import '@testing-library/jest-dom'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { GenerationResults } from '../GenerationResults'

// Mock date-fns
jest.mock('date-fns', () => ({
  formatDistanceToNow: jest.fn((date) => '2 hours ago'),
}))

// Mock project store
const mockFetchProjectTasks = jest.fn()
jest.mock('@/stores/projectStore', () => ({
  useProjectStore: () => ({
    fetchProjectTasks: mockFetchProjectTasks,
  }),
}))

// Mock i18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(() => ({
    t: (key: string, params?: any) => {
      if (key === 'toasts.generation.exported' && params?.count !== undefined) {
        return `Exported ${params.count} results`
      }
      const translations: Record<string, string> = {
        'toasts.generation.resultsFailed': 'Failed to load generation results',
        'toasts.clipboard.copied': 'Copied to clipboard',
        'toasts.clipboard.copyFailed': 'Failed to copy to clipboard',
        'toasts.generation.exportFailed': 'Failed to export results',
        'generation.results.searchPlaceholder': 'Search tasks and responses...',
        'generation.results.allModels': 'All Models',
        'generation.results.exportResults': 'Export Results',
        'generation.results.tasksWithResponses': 'tasks with responses',
        'generation.results.modelsUsed': 'models used',
        'generation.results.taskPrefix': 'Task',
        'generation.results.response': 'response',
        'generation.results.responses': 'responses',
        'generation.results.taskData': 'Task Data',
        'generation.results.modelResponses': 'Model Responses',
        'generation.results.generated': 'Generated',
        'generation.results.noMatchingResults': 'No results match your filters',
        'generation.results.noResultsYet': 'No generation results available yet',
        'generation.results.generateFirst': 'Generate responses first to see them here',
      }
      return translations[key] || key
    },
    locale: 'en',
  })),
}))

// Mock Toast
jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(() => ({
    addToast: jest.fn(),
    showToast: jest.fn(),
    removeToast: jest.fn(),
  })),
}))

// Mock clipboard API
Object.assign(navigator, {
  clipboard: {
    writeText: jest.fn(() => Promise.resolve()),
  },
})

// Mock window methods
const mockCreateObjectURL = jest.fn(() => 'blob:mock-url')
const mockRevokeObjectURL = jest.fn()
global.URL.createObjectURL = mockCreateObjectURL
global.URL.revokeObjectURL = mockRevokeObjectURL

describe('GenerationResults', () => {
  const mockProjectId = 'test-project-123'

  const mockTasks = [
    {
      id: 'task-1',
      data: {
        text: 'Legal case about contract law',
        question: 'What is the ruling?',
      },
      created_at: '2025-01-15T10:00:00Z',
      llm_responses: {
        'gpt-4': 'Response from GPT-4 about contract law',
        'claude-3': 'Response from Claude-3 about contract law',
      },
    },
    {
      id: 'task-2',
      data: { prompt: 'Criminal case analysis', text: 'Case details here' },
      created_at: '2025-01-15T11:00:00Z',
      llm_responses: {
        'gpt-4': 'GPT-4 criminal case analysis',
      },
    },
    {
      id: 'task-3',
      data: { text: 'Administrative law case' },
      created_at: '2025-01-15T12:00:00Z',
      llm_responses: {
        'claude-3': 'Claude-3 administrative analysis',
        'gemini-pro': 'Gemini Pro administrative analysis',
      },
    },
  ]

  const mockAddToast = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    mockFetchProjectTasks.mockResolvedValue(mockTasks)

    // Mock useToast
    const { useToast } = require('@/components/shared/Toast')
    useToast.mockReturnValue({ addToast: mockAddToast })
  })

  describe('Loading State', () => {
    it('should show loading spinner while fetching data', () => {
      mockFetchProjectTasks.mockImplementation(() => new Promise(() => {}))

      render(<GenerationResults projectId={mockProjectId} />)

      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
    })

    it('should hide loading spinner after data loads', async () => {
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.queryByTestId('loading-spinner')).not.toBeInTheDocument()
      })
    })
  })

  describe('Results Display', () => {
    it('should display all tasks with responses', async () => {
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getByText(/Task #task-1/)).toBeInTheDocument()
        expect(screen.getByText(/Task #task-2/)).toBeInTheDocument()
        expect(screen.getByText(/Task #task-3/)).toBeInTheDocument()
      })
    })

    it('should show task preview text', async () => {
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.getByText('Legal case about contract law')
        ).toBeInTheDocument()
        // Task 2 shows "Case details here" because text field takes precedence
        expect(screen.getByText('Case details here')).toBeInTheDocument()
        expect(screen.getByText('Administrative law case')).toBeInTheDocument()
      })
    })

    it('should display response count for each task', async () => {
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        // Should show response count badges - use getAllByText since we have multiple "2 responses"
        const twoResponses = screen.getAllByText('2 responses')
        expect(twoResponses.length).toBeGreaterThan(0)
        expect(screen.getByText('1 response')).toBeInTheDocument()
      })

      // Verify we have 3 tasks total
      expect(screen.getAllByText(/Task #/).length).toBe(3)
    })

    it('should show correct stats in header', async () => {
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getByText('3 tasks with responses')).toBeInTheDocument()
        expect(screen.getByText('3 models used')).toBeInTheDocument()
      })
    })

    it('should use correct task preview fallbacks', async () => {
      const tasksWithDifferentData = [
        {
          id: 'task-no-text',
          data: { question: 'What is the verdict?' },
          created_at: '2025-01-15T10:00:00Z',
          llm_responses: { 'gpt-4': 'Response' },
        },
        {
          id: 'task-with-prompt',
          data: { prompt: 'Analyze this' },
          created_at: '2025-01-15T11:00:00Z',
          llm_responses: { 'gpt-4': 'Response' },
        },
        {
          id: 'task-with-other',
          data: { customField: 'Custom value', id: 'custom-id' },
          created_at: '2025-01-15T12:00:00Z',
          llm_responses: { 'gpt-4': 'Response' },
        },
      ]

      mockFetchProjectTasks.mockResolvedValue(tasksWithDifferentData)
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getByText('What is the verdict?')).toBeInTheDocument()
        expect(screen.getByText('Analyze this')).toBeInTheDocument()
        expect(screen.getByText('Custom value')).toBeInTheDocument()
      })
    })
  })

  describe('Task Expansion', () => {
    it('should expand task when clicked', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getByText(/Task #task-1/)).toBeInTheDocument()
      })

      // Before expansion, model responses should not be visible
      expect(
        screen.queryByText('Response from GPT-4 about contract law')
      ).not.toBeInTheDocument()

      const taskHeader = screen
        .getByText('Legal case about contract law')
        .closest('div[class*="cursor-pointer"]')
      await user.click(taskHeader!)

      await waitFor(
        () => {
          expect(
            screen.getByText('Response from GPT-4 about contract law')
          ).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      // Verify both model responses are visible (use getAllByText since multiple tasks may have these models)
      const gpt4Elements = screen.getAllByText('gpt-4')
      expect(gpt4Elements.length).toBeGreaterThan(0)
      const claude3Elements = screen.getAllByText('claude-3')
      expect(claude3Elements.length).toBeGreaterThan(0)
    })

    it('should collapse task when clicked again', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getByText(/Task #task-1/)).toBeInTheDocument()
      })

      const taskHeader = screen.getByText(/Task #task-1/).closest('div')

      // Expand
      await user.click(taskHeader!)
      await waitFor(() => {
        expect(
          screen.getByText('Response from GPT-4 about contract law')
        ).toBeInTheDocument()
      })

      // Collapse
      await user.click(taskHeader!)
      await waitFor(() => {
        expect(
          screen.queryByText('Response from GPT-4 about contract law')
        ).not.toBeInTheDocument()
      })
    })

    it('should show task data when expanded', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getByText(/Task #task-1/)).toBeInTheDocument()
      })

      const taskHeader = screen.getByText(/Task #task-1/).closest('div')
      await user.click(taskHeader!)

      await waitFor(() => {
        expect(screen.getByText('Task Data')).toBeInTheDocument()
        expect(screen.getByText('Model Responses')).toBeInTheDocument()
      })
    })

    it('should show timestamp for each response', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getByText(/Task #task-1/)).toBeInTheDocument()
      })

      const taskHeader = screen.getByText(/Task #task-1/).closest('div')
      await user.click(taskHeader!)

      await waitFor(() => {
        const timestamps = screen.getAllByText(/Generated 2 hours ago/)
        expect(timestamps.length).toBeGreaterThan(0)
      })
    })
  })

  describe('Search Filtering', () => {
    it('should filter results by search query', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.getByText('Legal case about contract law')
        ).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText(
        'Search tasks and responses...'
      )
      await user.type(searchInput, 'criminal')

      await waitFor(() => {
        // Should find task with "criminal" in prompt field or text
        expect(screen.getByText('Case details here')).toBeInTheDocument()
        expect(
          screen.queryByText('Legal case about contract law')
        ).not.toBeInTheDocument()
        expect(
          screen.queryByText('Administrative law case')
        ).not.toBeInTheDocument()
      })
    })

    it('should filter by response content', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(3)
      })

      const searchInput = screen.getByPlaceholderText(
        'Search tasks and responses...'
      )
      await user.type(searchInput, 'administrative')

      await waitFor(() => {
        expect(screen.getByText('Administrative law case')).toBeInTheDocument()
        expect(
          screen.queryByText('Legal case about contract law')
        ).not.toBeInTheDocument()
      })
    })

    it('should be case insensitive', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(3)
      })

      const searchInput = screen.getByPlaceholderText(
        'Search tasks and responses...'
      )
      await user.type(searchInput, 'CRIMINAL')

      await waitFor(() => {
        // Should filter to 1 task (case insensitive)
        expect(screen.getAllByText(/Task #/).length).toBe(1)
        expect(screen.getByText('Case details here')).toBeInTheDocument()
      })
    })

    it('should clear filter when search is cleared', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(3)
      })

      const searchInput = screen.getByPlaceholderText(
        'Search tasks and responses...'
      )
      await user.type(searchInput, 'criminal')

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(1)
      })

      await user.clear(searchInput)

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(3)
      })
    })
  })

  describe('Model Filtering', () => {
    it('should show all models in filter dropdown', async () => {
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        const modelSelect = screen.getByRole('combobox')
        expect(modelSelect).toBeInTheDocument()
      })

      const modelSelect = screen.getByRole('combobox')
      expect(within(modelSelect).getByText('All Models')).toBeInTheDocument()

      const options = within(modelSelect).getAllByRole('option')
      expect(options).toHaveLength(4) // All Models + 3 unique models
    })

    it('should filter results by selected model', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(3)
      })

      const modelSelect = screen.getByRole('combobox')
      await user.selectOptions(modelSelect, 'gpt-4')

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(2)
        expect(
          screen.getByText('Legal case about contract law')
        ).toBeInTheDocument()
        expect(screen.getByText('Case details here')).toBeInTheDocument()
        expect(
          screen.queryByText('Administrative law case')
        ).not.toBeInTheDocument()
      })
    })

    it('should filter to tasks with claude-3', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(3)
      })

      const modelSelect = screen.getByRole('combobox')
      await user.selectOptions(modelSelect, 'claude-3')

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(2)
        expect(
          screen.getByText('Legal case about contract law')
        ).toBeInTheDocument()
        expect(screen.getByText('Administrative law case')).toBeInTheDocument()
      })
    })

    it('should reset filter when "All Models" is selected', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(3)
      })

      const modelSelect = screen.getByRole('combobox')
      await user.selectOptions(modelSelect, 'gpt-4')

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(2)
      })

      await user.selectOptions(modelSelect, 'all')

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(3)
      })
    })
  })

  describe('Combined Filtering', () => {
    it('should apply both search and model filters together', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(3)
      })

      // Apply model filter
      const modelSelect = screen.getByRole('combobox')
      await user.selectOptions(modelSelect, 'claude-3')

      // Apply search filter
      const searchInput = screen.getByPlaceholderText(
        'Search tasks and responses...'
      )
      await user.type(searchInput, 'administrative')

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(1)
        expect(screen.getByText('Administrative law case')).toBeInTheDocument()
      })
    })
  })

  describe('Copy to Clipboard', () => {
    it('should copy task data to clipboard when clicking copy button', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getByText(/Task #task-1/)).toBeInTheDocument()
      })

      // Expand task
      const taskHeader = screen
        .getByText('Legal case about contract law')
        .closest('div[class*="cursor-pointer"]')
      await user.click(taskHeader!)

      await waitFor(() => {
        expect(screen.getByText('Task Data')).toBeInTheDocument()
      })

      // Find all ClipboardDocumentIcon SVGs
      const clipboardIcons = Array.from(
        document.querySelectorAll('svg')
      ).filter((svg) => {
        const path = svg.querySelector('path')
        return path
          ?.getAttribute('d')
          ?.includes(
            'M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3'
          )
      })

      // Click the first copy button (for task data)
      if (clipboardIcons.length > 0) {
        const copyButton = clipboardIcons[0].closest('button')
        if (copyButton) {
          await user.click(copyButton)

          await waitFor(() => {
            expect(navigator.clipboard.writeText).toHaveBeenCalled()
            expect(mockAddToast).toHaveBeenCalledWith(
              'Copied to clipboard',
              'success'
            )
          })
        }
      }
    })

    it('should have copy buttons in expanded view', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getByText(/Task #task-1/)).toBeInTheDocument()
      })

      // Expand task
      const taskHeader = screen
        .getByText('Legal case about contract law')
        .closest('div[class*="cursor-pointer"]')
      await user.click(taskHeader!)

      await waitFor(() => {
        expect(screen.getByText('Task Data')).toBeInTheDocument()
        expect(screen.getByText('Model Responses')).toBeInTheDocument()
      })

      // Verify clipboard icon SVGs are present
      const svgs = document.querySelectorAll('svg')
      expect(svgs.length).toBeGreaterThan(0)
    })

    it('should handle clipboard error gracefully', async () => {
      const user = userEvent.setup()

      // Override clipboard mock to fail
      const originalWriteText = navigator.clipboard.writeText
      navigator.clipboard.writeText = jest
        .fn()
        .mockRejectedValue(new Error('Clipboard error'))

      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getByText(/Task #task-1/)).toBeInTheDocument()
      })

      // Expand task
      const taskHeader = screen
        .getByText('Legal case about contract law')
        .closest('div[class*="cursor-pointer"]')
      await user.click(taskHeader!)

      await waitFor(() => {
        expect(screen.getByText('Task Data')).toBeInTheDocument()
      })

      // Try to trigger copy which should fail
      const clipboardIcons = Array.from(
        document.querySelectorAll('svg')
      ).filter((svg) => {
        const path = svg.querySelector('path')
        return path
          ?.getAttribute('d')
          ?.includes(
            'M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3'
          )
      })

      if (clipboardIcons.length > 0) {
        const copyButton = clipboardIcons[0].closest('button')
        if (copyButton) {
          await user.click(copyButton)

          await waitFor(() => {
            expect(mockAddToast).toHaveBeenCalledWith(
              'Failed to copy to clipboard',
              'error'
            )
          })
        }
      }

      // Restore original
      navigator.clipboard.writeText = originalWriteText
    })
  })

  describe('Export Results', () => {
    it('should export results as JSON file', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getByText('Export Results')).toBeInTheDocument()
      })

      const exportButton = screen.getByText('Export Results')
      await user.click(exportButton)

      await waitFor(() => {
        expect(mockCreateObjectURL).toHaveBeenCalled()
        expect(mockRevokeObjectURL).toHaveBeenCalled()
        expect(mockAddToast).toHaveBeenCalledWith(
          'Exported 3 results',
          'success'
        )
      })
    })

    it('should export with correct data structure', async () => {
      const user = userEvent.setup()
      let blobData: string = ''

      // Capture blob data when created
      const originalBlob = global.Blob
      global.Blob = jest.fn(function (parts: any[], options: any) {
        blobData = parts[0]
        return new originalBlob(parts, options)
      }) as any

      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getByText('Export Results')).toBeInTheDocument()
      })

      const exportButton = screen.getByText('Export Results')
      await user.click(exportButton)

      await waitFor(
        () => {
          expect(mockCreateObjectURL).toHaveBeenCalled()
          expect(blobData).not.toBe('')
        },
        { timeout: 5000 }
      )

      // Validate structure
      const parsedData = JSON.parse(blobData)
      expect(parsedData).toHaveProperty('project_id', mockProjectId)
      expect(parsedData).toHaveProperty('exported_at')
      expect(parsedData).toHaveProperty('total_tasks', 3)
      expect(parsedData).toHaveProperty('models')
      expect(parsedData.models).toContain('gpt-4')
      expect(parsedData.results).toHaveLength(3)

      // Restore original Blob
      global.Blob = originalBlob
    })

    it('should export only filtered results', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(3)
      })

      // Apply filter
      const searchInput = screen.getByPlaceholderText(
        'Search tasks and responses...'
      )
      await user.type(searchInput, 'criminal')

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(1)
      })

      const exportButton = screen.getByText('Export Results')
      await user.click(exportButton)

      await waitFor(() => {
        expect(mockCreateObjectURL).toHaveBeenCalled()
        expect(mockAddToast).toHaveBeenCalledWith(
          'Exported 1 results',
          'success'
        )
      })
    })

    it('should disable export when no results', async () => {
      mockFetchProjectTasks.mockResolvedValue([])
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        const exportButton = screen.getByText('Export Results')
        expect(exportButton).toBeDisabled()
      })
    })

    it('should handle export error', async () => {
      const user = userEvent.setup()
      mockCreateObjectURL.mockImplementation(() => {
        throw new Error('Export error')
      })

      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getByText('Export Results')).toBeInTheDocument()
      })

      const exportButton = screen.getByText('Export Results')
      await user.click(exportButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to export results',
          'error'
        )
      })
    })
  })

  describe('Empty States', () => {
    it('should show empty state when no results', async () => {
      mockFetchProjectTasks.mockResolvedValue([])
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.getByText('No generation results available yet')
        ).toBeInTheDocument()
        expect(
          screen.getByText('Generate responses first to see them here')
        ).toBeInTheDocument()
      })
    })

    it('should show empty state when tasks have no responses', async () => {
      const tasksWithoutResponses = [
        {
          id: 'task-1',
          data: { text: 'Some task' },
          created_at: '2025-01-15T10:00:00Z',
          llm_responses: {},
        },
      ]
      mockFetchProjectTasks.mockResolvedValue(tasksWithoutResponses)
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.getByText('No generation results available yet')
        ).toBeInTheDocument()
      })
    })

    it('should show filtered empty state', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(3)
      })

      const searchInput = screen.getByPlaceholderText(
        'Search tasks and responses...'
      )
      await user.type(searchInput, 'nonexistent query')

      await waitFor(() => {
        expect(
          screen.getByText('No results match your filters')
        ).toBeInTheDocument()
        expect(
          screen.getByText('Generate responses first to see them here')
        ).toBeInTheDocument()
      })
    })

    it('should show filtered empty state for model filter', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(3)
      })

      const modelSelect = screen.getByRole('combobox')
      await user.selectOptions(modelSelect, 'gemini-pro')

      await waitFor(() => {
        expect(screen.getAllByText(/Task #/).length).toBe(1)
      })

      const searchInput = screen.getByPlaceholderText(
        'Search tasks and responses...'
      )
      await user.type(searchInput, 'criminal')

      await waitFor(() => {
        expect(
          screen.getByText('No results match your filters')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Error Handling', () => {
    it('should handle fetch error', async () => {
      const consoleError = jest.spyOn(console, 'error').mockImplementation()
      mockFetchProjectTasks.mockRejectedValue(new Error('Fetch failed'))

      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to load generation results',
          'error'
        )
        expect(consoleError).toHaveBeenCalledWith(
          'Failed to load results:',
          expect.any(Error)
        )
      })

      consoleError.mockRestore()
    })

    it('should handle string responses in llm_responses', async () => {
      const tasksWithStringResponses = [
        {
          id: 'task-1',
          data: { text: 'Test task' },
          created_at: '2025-01-15T10:00:00Z',
          llm_responses: {
            'gpt-4': 'Simple string response',
          },
        },
      ]
      mockFetchProjectTasks.mockResolvedValue(tasksWithStringResponses)

      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getByText('Test task')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      const taskHeader = screen.getByText(/Task #task-1/).closest('div')
      await user.click(taskHeader!)

      await waitFor(() => {
        expect(screen.getByText('Simple string response')).toBeInTheDocument()
      })
    })

    it('should handle object responses in llm_responses', async () => {
      const tasksWithObjectResponses = [
        {
          id: 'task-1',
          data: { text: 'Test task' },
          created_at: '2025-01-15T10:00:00Z',
          llm_responses: {
            'gpt-4': { content: 'Object response', metadata: 'extra' },
          },
        },
      ]
      mockFetchProjectTasks.mockResolvedValue(tasksWithObjectResponses)

      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getByText('Test task')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      const taskHeader = screen.getByText(/Task #task-1/).closest('div')
      await user.click(taskHeader!)

      await waitFor(() => {
        expect(screen.getByText(/"content":/)).toBeInTheDocument()
      })
    })
  })

  describe('Stats Display', () => {
    it('should update stats when filtering', async () => {
      const user = userEvent.setup()
      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getByText('3 tasks with responses')).toBeInTheDocument()
        expect(screen.getByText('3 models used')).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText(
        'Search tasks and responses...'
      )
      await user.type(searchInput, 'criminal')

      await waitFor(() => {
        expect(screen.getByText('1 tasks with responses')).toBeInTheDocument()
      })
    })

    it('should show singular "task" when count is 1', async () => {
      const singleTask = [mockTasks[0]]
      mockFetchProjectTasks.mockResolvedValue(singleTask)

      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getByText('1 tasks with responses')).toBeInTheDocument()
      })
    })
  })

  describe('JSON Stringification', () => {
    it('should handle task data with circular references gracefully', async () => {
      const taskWithCircular: any = {
        id: 'task-circular',
        data: { text: 'Test' },
        created_at: '2025-01-15T10:00:00Z',
        llm_responses: { 'gpt-4': 'Response' },
      }
      // Create circular reference
      taskWithCircular.data.self = taskWithCircular.data

      mockFetchProjectTasks.mockResolvedValue([taskWithCircular])

      render(<GenerationResults projectId={mockProjectId} />)

      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument()
      })
    })
  })
})
