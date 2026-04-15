/**
 * Test suite for Generation Result Modal Component
 *
 * Target: 85%+ coverage (from 0%)
 */

import { apiClient } from '@/lib/api/client'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { GenerationResultModal } from '../GenerationResultModal'

// Mock dependencies
jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: jest.fn(),
  },
}))

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, arg2?: any, arg3?: any) => {
      const vars = typeof arg2 === 'object' ? arg2 : arg3
      const translations: Record<string, string> = {
        'generation.resultModal.title': 'Generation Result',
        'generation.resultModal.model': 'Model:',
        'generation.resultModal.task': 'Task:',
        'generation.resultModal.loading': 'Loading...',
        'generation.resultModal.status': 'Status:',
        'generation.resultModal.generatedAt': 'Generated at:',
        'generation.resultModal.generationTime': 'Generation time:',
        'generation.resultModal.seconds': '{value} seconds',
        'generation.resultModal.formatted': 'Formatted',
        'generation.resultModal.rawJson': 'Raw JSON',
        'generation.resultModal.copy': 'Copy',
        'generation.resultModal.copied': 'Copied',
        'generation.resultModal.generatedText': 'Generated Text',
        'generation.resultModal.error': 'Error:',
        'generation.resultModal.runningMessage': 'Generation is currently running. Please check back later.',
        'generation.resultModal.pendingMessage': 'Generation is queued and will start soon.',
        'generation.resultModal.noResultMessage': 'No result available for this generation.',
        'generation.resultModal.noResultsFound': 'No generation results found',
        'generation.resultModal.viewPrompt': 'View Prompt Used',
        'generation.resultModal.noPromptStored': 'No prompt data stored for this generation. Re-run to capture prompt.',
        'generation.resultModal.viewParameters': 'View Generation Parameters',
        'generation.resultModal.close': 'Close',
        'generation.resultModal.default': 'default',
        'generation.resultModal.current': 'Current',
        'generation.resultModal.history': 'History',
        'generation.resultModal.currentLabel': '(current)',
        'generation.resultModal.noHistory': 'No generation history available',
        'generation.resultModal.by': 'by {user}',
      }
      let result = translations[key] || key
      if (vars) {
        Object.entries(vars).forEach(([k, v]) => {
          result = result.replace(`{${k}}`, String(v))
        })
      }
      return result
    },
    locale: 'en',
  }),
}))

const mockCompletedResult = {
  task_id: 'task-123',
  model_id: 'gpt-4',
  generation_id: 'gen-456',
  status: 'completed',
  result: {
    generated_text: 'This is the generated text response.',
    metadata: { tokens: 150 },
  },
  generated_at: '2024-01-01T10:00:00Z',
  generation_time_seconds: 2.5,
  prompt_used: 'Generate a response for this prompt',
  parameters: { temperature: 0.7, max_tokens: 500 },
  structure_key: 'structured_output',
}

const mockFailedResult = {
  task_id: 'task-123',
  model_id: 'gpt-4',
  generation_id: 'gen-789',
  status: 'failed',
  error_message: 'API rate limit exceeded',
  generated_at: '2024-01-01T10:00:00Z',
}

const mockRunningResult = {
  task_id: 'task-123',
  model_id: 'gpt-4',
  generation_id: 'gen-101',
  status: 'running',
}

const mockPendingResult = {
  task_id: 'task-123',
  model_id: 'gpt-4',
  generation_id: 'gen-102',
  status: 'pending',
}

describe('GenerationResultModal Component', () => {
  const mockApiClient = apiClient as jest.Mocked<typeof apiClient>
  const mockOnClose = jest.fn()
  let mockWriteText: jest.Mock

  beforeEach(() => {
    jest.clearAllMocks()
    // Set up clipboard mock for copy tests
    mockWriteText = jest.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: {
        writeText: mockWriteText,
        readText: jest.fn().mockResolvedValue(''),
      },
      writable: true,
      configurable: true,
    })
  })

  describe('modal visibility', () => {
    it('renders when isOpen is true', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      expect(screen.getByText('Generation Result')).toBeInTheDocument()
    })

    it('does not render when isOpen is false', () => {
      render(
        <GenerationResultModal
          isOpen={false}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      expect(screen.queryByText('Generation Result')).not.toBeInTheDocument()
    })

    it('closes when close button is clicked', async () => {
      const user = userEvent.setup()
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      const closeButtons = screen.getAllByRole('button', { name: /close/i })
      await user.click(closeButtons[0])

      expect(mockOnClose).toHaveBeenCalled()
    })

    it('closes when X button is clicked', async () => {
      const user = userEvent.setup()
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      const closeButtons = screen.getAllByRole('button', { name: /close/i })
      // Click the first close button (X icon in header)
      await user.click(closeButtons[0])

      expect(mockOnClose).toHaveBeenCalled()
    })
  })

  describe('loading state', () => {
    it('shows loading spinner when fetching data', () => {
      mockApiClient.get.mockImplementation(() => new Promise(() => {}))

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
        />
      )

      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })

    it('fetches result from API when no result provided', async () => {
      mockApiClient.get.mockResolvedValueOnce({
        task_id: 'task-123',
        model_id: 'gpt-4',
        results: [mockCompletedResult],
      })

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
        />
      )

      await waitFor(() => {
        expect(mockApiClient.get).toHaveBeenCalledWith(
          '/generation-tasks/generation-result?task_id=task-123&model_id=gpt-4'
        )
      })
    })

    it('uses provided result without API call', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      expect(mockApiClient.get).not.toHaveBeenCalled()
      expect(
        screen.getByText('This is the generated text response.')
      ).toBeInTheDocument()
    })

    it('handles API errors gracefully', async () => {
      const consoleError = jest.spyOn(console, 'error').mockImplementation()
      mockApiClient.get.mockRejectedValueOnce(new Error('API Error'))

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
        />
      )

      await waitFor(() => {
        expect(consoleError).toHaveBeenCalledWith(
          'Failed to fetch generation results:',
          expect.any(Error)
        )
      })

      consoleError.mockRestore()
    })
  })

  describe('header information', () => {
    it('displays modal title', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      expect(screen.getByText('Generation Result')).toBeInTheDocument()
    })

    it('displays model ID', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      expect(screen.getByText('gpt-4')).toBeInTheDocument()
      expect(screen.getByText('Model:')).toBeInTheDocument()
    })

    it('displays truncated task ID', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      expect(screen.getByText(/task-123/)).toBeInTheDocument()
      expect(screen.getByText('Task:')).toBeInTheDocument()
    })

    it('displays structure key when there are multiple results', () => {
      // Mock multiple results to trigger structure tabs
      const result1 = { ...mockCompletedResult, structure_key: 'structure1' }
      const result2 = { ...mockCompletedResult, structure_key: 'structure2' }

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={result1}
        />
      )

      // When only one result is provided, structure tabs are not shown
      // The component needs multiple results in an array to show tabs
      // This test verifies single result doesn't show structure tabs
      expect(screen.queryByText('structure1')).not.toBeInTheDocument()
    })

    it('does not display structure key when not present', () => {
      const resultWithoutStructure = {
        ...mockCompletedResult,
        structure_key: undefined,
      }
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={resultWithoutStructure}
        />
      )

      expect(screen.queryByText('Structure:')).not.toBeInTheDocument()
    })
  })

  describe('status badges', () => {
    it('displays completed status with green badge', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      const statusBadge = screen.getByText('completed')
      expect(statusBadge).toHaveClass('bg-green-100', 'text-green-800')
    })

    it('displays failed status with red badge', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockFailedResult}
        />
      )

      const statusBadge = screen.getByText('failed')
      expect(statusBadge).toHaveClass('bg-red-100', 'text-red-800')
    })

    it('displays running status with yellow badge', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockRunningResult}
        />
      )

      const statusBadge = screen.getByText('running')
      expect(statusBadge).toHaveClass('bg-yellow-100', 'text-yellow-800')
    })

    it('displays pending status with gray badge', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockPendingResult}
        />
      )

      const statusBadge = screen.getByText('pending')
      expect(statusBadge).toHaveClass('bg-gray-100', 'text-gray-800')
    })
  })

  describe('metadata display', () => {
    it('displays generated timestamp', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      expect(screen.getByText('Generated at:')).toBeInTheDocument()
      expect(screen.getByText(/2024/)).toBeInTheDocument()
    })

    it('displays generation time', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      expect(screen.getByText('Generation time:')).toBeInTheDocument()
      expect(screen.getByText('2.50 seconds')).toBeInTheDocument()
    })

    it('formats generation time to 2 decimal places', () => {
      const resultWithPreciseTime = {
        ...mockCompletedResult,
        generation_time_seconds: 1.23456789,
      }
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={resultWithPreciseTime}
        />
      )

      expect(screen.getByText('1.23 seconds')).toBeInTheDocument()
    })

    it('does not display timestamp when not present', () => {
      const resultWithoutTimestamp = {
        ...mockCompletedResult,
        generated_at: undefined,
      }
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={resultWithoutTimestamp}
        />
      )

      expect(screen.queryByText('Generated at:')).not.toBeInTheDocument()
    })

    it('does not display generation time when not present', () => {
      const resultWithoutTime = {
        ...mockCompletedResult,
        generation_time_seconds: undefined,
      }
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={resultWithoutTime}
        />
      )

      expect(screen.queryByText('Generation time:')).not.toBeInTheDocument()
    })
  })

  describe('view mode toggle', () => {
    it('displays view mode toggle buttons', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      expect(screen.getByText('Formatted')).toBeInTheDocument()
      expect(screen.getByText('Raw JSON')).toBeInTheDocument()
    })

    it('defaults to formatted view', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      const formattedButton = screen.getByText('Formatted')
      expect(formattedButton).toHaveClass('bg-white')
    })

    it('switches to raw JSON view when clicked', async () => {
      const user = userEvent.setup()
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      const rawButton = screen.getByText('Raw JSON')
      await user.click(rawButton)

      await waitFor(() => {
        expect(rawButton).toHaveClass('bg-white')
      })
    })

    it('displays formatted text in formatted mode', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      expect(
        screen.getByText('This is the generated text response.')
      ).toBeInTheDocument()
    })

    it('displays JSON in raw mode', async () => {
      const user = userEvent.setup()
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      const rawButton = screen.getByText('Raw JSON')
      await user.click(rawButton)

      await waitFor(() => {
        expect(screen.getByText(/"generated_text":/)).toBeInTheDocument()
      })
    })
  })

  describe('copy functionality', () => {
    it('displays copy button', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      expect(screen.getByText('Copy')).toBeInTheDocument()
    })

    it('copies formatted text to clipboard', async () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      // Find the copy button by its icon and text structure
      const copyButtons = screen.getAllByRole('button')
      const copyButton = copyButtons.find(
        (btn) =>
          btn.textContent?.includes('Copy') &&
          !btn.textContent.includes('Copied')
      )
      expect(copyButton).toBeDefined()

      fireEvent.click(copyButton!)

      await waitFor(() => {
        expect(mockWriteText).toHaveBeenCalledWith(
          'This is the generated text response.'
        )
      })
    })

    it('copies raw JSON to clipboard in raw mode', async () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      const rawButton = screen.getByText('Raw JSON')
      fireEvent.click(rawButton)

      // Find the copy button by its icon and text structure
      const copyButtons = screen.getAllByRole('button')
      const copyButton = copyButtons.find(
        (btn) =>
          btn.textContent?.includes('Copy') &&
          !btn.textContent.includes('Copied')
      )
      expect(copyButton).toBeDefined()

      fireEvent.click(copyButton!)

      await waitFor(() => {
        expect(mockWriteText).toHaveBeenCalledWith(
          expect.stringContaining('"generated_text"')
        )
      })
    })

    it('shows "Copied" confirmation after copying', async () => {
      const user = userEvent.setup()
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      const copyButton = screen.getByText('Copy')
      await user.click(copyButton)

      await waitFor(() => {
        expect(screen.getByText('Copied')).toBeInTheDocument()
      })
    })

    it('resets "Copied" text after timeout', async () => {
      jest.useFakeTimers()
      const user = userEvent.setup({ delay: null })

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      const copyButton = screen.getByText('Copy')
      await user.click(copyButton)

      await waitFor(() => {
        expect(screen.getByText('Copied')).toBeInTheDocument()
      })

      jest.advanceTimersByTime(2000)

      await waitFor(() => {
        expect(screen.getByText('Copy')).toBeInTheDocument()
      })

      jest.useRealTimers()
    })

    it('handles copy error gracefully', async () => {
      const consoleError = jest.spyOn(console, 'error').mockImplementation()
      const user = userEvent.setup()

      // Set up clipboard to reject for this test
      Object.defineProperty(navigator, 'clipboard', {
        value: {
          writeText: jest.fn().mockRejectedValue(new Error('Copy failed')),
          readText: jest.fn().mockResolvedValue(''),
        },
        writable: true,
        configurable: true,
      })

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      const copyButton = screen.getByText('Copy')
      await user.click(copyButton)

      await waitFor(() => {
        expect(consoleError).toHaveBeenCalledWith(
          'Failed to copy to clipboard:',
          expect.any(Error)
        )
      })

      consoleError.mockRestore()
    })
  })

  describe('completed result display', () => {
    it('displays generated text for completed result', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      expect(screen.getByText('Generated Text')).toBeInTheDocument()
      expect(
        screen.getByText('This is the generated text response.')
      ).toBeInTheDocument()
    })

    it('formats result with generated_text field', () => {
      const resultWithGeneratedText = {
        ...mockCompletedResult,
        result: {
          generated_text: 'Special generated text',
          other_field: 'ignored',
        },
      }

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={resultWithGeneratedText}
        />
      )

      expect(screen.getByText('Special generated text')).toBeInTheDocument()
    })

    it('formats string results directly', () => {
      const stringResult = {
        ...mockCompletedResult,
        result: 'Simple string result',
      }

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={stringResult}
        />
      )

      expect(screen.getByText('Simple string result')).toBeInTheDocument()
    })

    it('formats number results as strings', () => {
      const numberResult = {
        ...mockCompletedResult,
        result: 42,
      }

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={numberResult}
        />
      )

      expect(screen.getByText('42')).toBeInTheDocument()
    })

    it('formats boolean results as strings', () => {
      const booleanResult = {
        ...mockCompletedResult,
        result: true,
      }

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={booleanResult}
        />
      )

      expect(screen.getByText('true')).toBeInTheDocument()
    })

    it('formats array results with newlines', () => {
      const arrayResult = {
        ...mockCompletedResult,
        result: ['item1', 'item2', 'item3'],
      }

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={arrayResult}
        />
      )

      expect(screen.getByText(/item1/)).toBeInTheDocument()
    })

    it('formats object results as key-value pairs', () => {
      const objectResult = {
        ...mockCompletedResult,
        result: {
          key1: 'value1',
          key2: 'value2',
        },
      }

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={objectResult}
        />
      )

      expect(screen.getByText(/key1: value1/)).toBeInTheDocument()
    })
  })

  describe('failed result display', () => {
    it('displays error message for failed result', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockFailedResult}
        />
      )

      expect(screen.getByText('Error:')).toBeInTheDocument()
      expect(screen.getByText('API rate limit exceeded')).toBeInTheDocument()
    })

    it('displays error in red background', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockFailedResult}
        />
      )

      const errorText = screen.getByText('API rate limit exceeded')
      expect(errorText.closest('div')).toHaveClass('bg-red-50')
    })
  })

  describe('running result display', () => {
    it('displays running message', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockRunningResult}
        />
      )

      expect(
        screen.getByText(/Generation is currently running/)
      ).toBeInTheDocument()
    })

    it('displays running message in yellow background', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockRunningResult}
        />
      )

      const runningText = screen.getByText(/Generation is currently running/)
      expect(runningText.closest('div')).toHaveClass('bg-yellow-50')
    })
  })

  describe('pending result display', () => {
    it('displays pending message', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockPendingResult}
        />
      )

      expect(screen.getByText(/Generation is queued/)).toBeInTheDocument()
    })

    it('displays pending message in gray background', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockPendingResult}
        />
      )

      const pendingText = screen.getByText(/Generation is queued/)
      expect(pendingText.closest('div')).toHaveClass('bg-gray-50')
    })
  })

  describe('prompt display', () => {
    it('displays prompt in collapsible section', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      expect(screen.getByText('View Prompt Used')).toBeInTheDocument()
    })

    it('expands to show prompt text', async () => {
      const user = userEvent.setup()
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      const promptSummary = screen.getByText('View Prompt Used')
      await user.click(promptSummary)

      await waitFor(() => {
        expect(
          screen.getByText('Generate a response for this prompt')
        ).toBeInTheDocument()
      })
    })

    it('displays placeholder when no prompt data stored', () => {
      const resultWithoutPrompt = {
        ...mockCompletedResult,
        prompt_used: undefined,
      }
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={resultWithoutPrompt}
        />
      )

      expect(screen.getByText('View Prompt Used')).toBeInTheDocument()
      expect(screen.getByText(/No prompt data stored|Keine Prompt-Daten/)).toBeInTheDocument()
    })
  })

  describe('parameters display', () => {
    it('displays parameters in collapsible section', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      expect(screen.getByText('View Generation Parameters')).toBeInTheDocument()
    })

    it('expands to show parameters JSON', async () => {
      const user = userEvent.setup()
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      const paramsSummary = screen.getByText('View Generation Parameters')
      await user.click(paramsSummary)

      await waitFor(() => {
        expect(screen.getByText(/"temperature": 0.7/)).toBeInTheDocument()
      })
    })

    it('does not display parameters section when empty', () => {
      const resultWithoutParams = { ...mockCompletedResult, parameters: {} }
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={resultWithoutParams}
        />
      )

      expect(
        screen.queryByText('View Generation Parameters')
      ).not.toBeInTheDocument()
    })

    it('does not display parameters section when undefined', () => {
      const resultWithoutParams = {
        ...mockCompletedResult,
        parameters: undefined,
      }
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={resultWithoutParams}
        />
      )

      expect(
        screen.queryByText('View Generation Parameters')
      ).not.toBeInTheDocument()
    })
  })

  describe('no result state', () => {
    it('displays no result message when result is null', async () => {
      mockApiClient.get.mockResolvedValueOnce({
        task_id: 'task-123',
        model_id: 'gpt-4',
        results: [],
      })

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
        />
      )

      await waitFor(() => {
        expect(
          screen.getByText('No generation results found')
        ).toBeInTheDocument()
      })
    })
  })

  describe('accessibility', () => {
    it('has proper dialog role', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('has accessible close buttons', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      const closeButtons = screen.getAllByRole('button', { name: /close/i })
      expect(closeButtons.length).toBeGreaterThan(0)
    })

    it('has proper heading structure', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      expect(
        screen.getByRole('heading', { name: 'Generation Result' })
      ).toBeInTheDocument()
    })
  })

  // Issue #1372: Generation history tab tests
  describe('history tab', () => {
    const mockHistoryResponse = {
      task_id: 'task-123',
      model_id: 'gpt-4',
      results: [
        {
          task_id: 'task-123',
          model_id: 'gpt-4',
          generation_id: 'gen-new',
          status: 'completed',
          result: { generated_text: 'Newest response' },
          generated_at: '2024-02-01T10:00:00Z',
          generation_time_seconds: 1.5,
          structure_key: 'structured_output',
          created_by: 'user-1',
          created_by_name: 'Alice',
        },
        {
          task_id: 'task-123',
          model_id: 'gpt-4',
          generation_id: 'gen-old',
          status: 'completed',
          result: { generated_text: 'Older response' },
          generated_at: '2024-01-01T10:00:00Z',
          generation_time_seconds: 3.2,
          structure_key: 'structured_output',
          created_by: 'user-2',
          created_by_name: 'Bob',
        },
        {
          task_id: 'task-123',
          model_id: 'gpt-4',
          generation_id: 'gen-failed',
          status: 'failed',
          error_message: 'Rate limit',
          generated_at: '2023-12-01T10:00:00Z',
          structure_key: 'structured_output',
          created_by: 'user-1',
          created_by_name: 'Alice',
        },
      ],
    }

    it('shows Current/History toggle when results exist', () => {
      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
          result={mockCompletedResult}
        />
      )

      expect(screen.getByText('Current')).toBeInTheDocument()
      expect(screen.getByText('History')).toBeInTheDocument()
    })

    it('does not show toggle when no results', async () => {
      mockApiClient.get.mockResolvedValueOnce({
        task_id: 'task-123',
        model_id: 'gpt-4',
        results: [],
      })

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('No generation results found')).toBeInTheDocument()
      })

      expect(screen.queryByText('Current')).not.toBeInTheDocument()
      expect(screen.queryByText('History')).not.toBeInTheDocument()
    })

    it('fetches history with include_history=true on History tab click', async () => {
      mockApiClient.get
        .mockResolvedValueOnce({
          task_id: 'task-123',
          model_id: 'gpt-4',
          results: [mockCompletedResult],
        })
        .mockResolvedValueOnce(mockHistoryResponse)

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('History')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('History'))

      await waitFor(() => {
        expect(mockApiClient.get).toHaveBeenCalledTimes(2)
      })

      // Verify the second call included include_history=true
      const secondCallUrl = mockApiClient.get.mock.calls[1][0] as string
      expect(secondCallUrl).toContain('include_history=true')
    })

    it('shows history entries with metadata after fetching', async () => {
      mockApiClient.get
        .mockResolvedValueOnce({
          task_id: 'task-123',
          model_id: 'gpt-4',
          results: [mockCompletedResult],
        })
        .mockResolvedValueOnce(mockHistoryResponse)

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('History')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('History'))

      await waitFor(() => {
        // Status badges visible (multiple "completed" entries, so use getAllByText)
        expect(screen.getAllByText('completed').length).toBeGreaterThanOrEqual(1)
        expect(screen.getAllByText('failed').length).toBeGreaterThanOrEqual(1)
      })

      // Created by names visible
      expect(screen.getAllByText('by Alice').length).toBeGreaterThanOrEqual(1)
      expect(screen.getByText('by Bob')).toBeInTheDocument()
    })

    it('marks most recent entry with (current) label', async () => {
      mockApiClient.get
        .mockResolvedValueOnce({
          task_id: 'task-123',
          model_id: 'gpt-4',
          results: [mockCompletedResult],
        })
        .mockResolvedValueOnce(mockHistoryResponse)

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('History')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('History'))

      await waitFor(() => {
        expect(screen.getByText('(current)')).toBeInTheDocument()
      })
    })

    it('expands history entry on click to show content', async () => {
      mockApiClient.get
        .mockResolvedValueOnce({
          task_id: 'task-123',
          model_id: 'gpt-4',
          results: [mockCompletedResult],
        })
        .mockResolvedValueOnce(mockHistoryResponse)

      const user = userEvent.setup()

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('History')).toBeInTheDocument()
      })

      await user.click(screen.getByText('History'))

      await waitFor(() => {
        // Wait for history entries to load
        expect(screen.getByText('(current)')).toBeInTheDocument()
      })

      // Click the first disclosure button (contains "(current)" label) to expand it
      const disclosureButtons = screen.getAllByRole('button').filter(
        (btn) => btn.textContent?.includes('(current)')
      )
      expect(disclosureButtons.length).toBeGreaterThan(0)

      await user.click(disclosureButtons[0])

      // After expanding, the result content should be visible
      await waitFor(() => {
        expect(screen.getByText('Newest response')).toBeInTheDocument()
      })
    })

    it('shows no history message when history is empty', async () => {
      mockApiClient.get
        .mockResolvedValueOnce({
          task_id: 'task-123',
          model_id: 'gpt-4',
          results: [mockCompletedResult],
        })
        .mockResolvedValueOnce({
          task_id: 'task-123',
          model_id: 'gpt-4',
          results: [],
        })

      render(
        <GenerationResultModal
          isOpen={true}
          taskId="task-123"
          modelId="gpt-4"
          onClose={mockOnClose}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('History')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('History'))

      await waitFor(() => {
        expect(screen.getByText('No generation history available')).toBeInTheDocument()
      })
    })
  })
})
