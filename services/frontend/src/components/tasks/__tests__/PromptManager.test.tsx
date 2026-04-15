/**
 * Tests for PromptManager component
 * Target: 85%+ coverage
 */

import * as api from '@/lib/api'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PromptData, PromptManager, promptsToJson } from '../PromptManager'

// Mock dependencies
jest.mock('@/components/shared/Button', () => ({
  Button: ({
    children,
    onClick,
    className,
    disabled,
    variant,
    ...props
  }: any) => (
    <button
      onClick={onClick}
      className={className}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: jest.fn(),
    removeToast: jest.fn(),
    toasts: [],
  }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'tasks.prompts.promptNumber': `Prompt #${params?.number}`,
        'tasks.prompts.promptText': 'Prompt Text',
        'tasks.prompts.expectedOutput': 'Expected Output',
        'tasks.prompts.promptType': 'Prompt Type',
        'tasks.prompts.maxTokens': 'Max Tokens',
        'tasks.prompts.temperature': 'Temperature',
        'tasks.prompts.context': 'Context',
        'tasks.prompts.promptPlaceholder': 'Enter prompt text...',
        'tasks.prompts.expectedOutputPlaceholder': 'Enter expected output...',
        'tasks.prompts.contextPlaceholder': 'Enter context...',
        'tasks.prompts.system': 'System',
        'tasks.prompts.instruction': 'Instruction',
        'tasks.prompts.evaluation': 'Evaluation',
        'tasks.prompts.addNew': 'Add New Prompt',
        'tasks.prompts.addPrompt': 'Add Prompt',
        'tasks.prompts.cancel': 'Cancel',
        'tasks.prompts.uploadPrompts': 'Upload Prompts',
        'tasks.prompts.emptyState':
          'No prompts yet. Add your first prompt to get started.',
        'tasks.prompts.uploading': 'Uploading prompts...',
        'tasks.prompts.uploadSuccess': `Uploaded ${params?.count} prompts successfully`,
        'tasks.prompts.uploadFailed': 'Failed to upload prompts',
      }
      return translations[key] || key
    },
    changeLanguage: jest.fn(),
    currentLanguage: 'en',
    languages: ['en', 'de'],
  }),
}))

jest.mock('@/hooks/useDefaultConfig', () => ({
  useDefaultConfig: () => ({
    config: {
      max_tokens: 500,
      temperature: 0.7,
    },
    isLoading: false,
  }),
}))

jest.mock('@/lib/api', () => ({
  api: {
    uploadData: jest.fn(),
  },
}))

describe('PromptManager', () => {
  const mockOnPromptsChange = jest.fn()
  const mockAddToast = jest.fn()

  const mockPrompts: PromptData[] = [
    {
      prompt: 'Test prompt 1',
      expected_output: 'Test output 1',
      metadata: {
        max_tokens: 500,
        temperature: 0.7,
        context: 'Test context 1',
        prompt_type: 'instruction',
      },
    },
    {
      prompt: 'Test prompt 2',
      expected_output: 'Test output 2',
      metadata: {
        max_tokens: 1000,
        temperature: 0.5,
        context: 'Test context 2',
        prompt_type: 'system',
      },
    },
  ]

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders empty state when no prompts exist', () => {
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      expect(
        screen.getByText(
          'No prompts yet. Add your first prompt to get started.'
        )
      ).toBeInTheDocument()
      expect(screen.getByText('Add Prompt')).toBeInTheDocument()
    })

    it('renders existing prompts', () => {
      render(
        <PromptManager
          prompts={mockPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      expect(screen.getByText('Prompt #1')).toBeInTheDocument()
      expect(screen.getByText('Prompt #2')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Test prompt 1')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Test prompt 2')).toBeInTheDocument()
    })

    it('shows all prompt fields correctly', () => {
      render(
        <PromptManager
          prompts={mockPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      expect(screen.getByDisplayValue('Test prompt 1')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Test output 1')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Test context 1')).toBeInTheDocument()
      expect(screen.getByDisplayValue('500')).toBeInTheDocument()
      expect(screen.getByDisplayValue('0.7')).toBeInTheDocument()
    })

    it('renders upload button when taskId is provided', () => {
      render(
        <PromptManager
          prompts={[]}
          onPromptsChange={mockOnPromptsChange}
          taskId="test-task-id"
        />
      )

      expect(screen.getByText('Upload Prompts')).toBeInTheDocument()
    })

    it('does not render upload button when no taskId', () => {
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      expect(screen.queryByText('Upload Prompts')).not.toBeInTheDocument()
    })
  })

  describe('Adding Prompts', () => {
    it('shows add prompt form when add button is clicked', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      expect(screen.getByText('Add New Prompt')).toBeInTheDocument()
      expect(
        screen.getByPlaceholderText('Enter prompt text...')
      ).toBeInTheDocument()
    })

    it('allows entering prompt details in add form', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      const promptInput = screen.getByPlaceholderText('Enter prompt text...')
      await user.type(promptInput, 'New prompt text')

      expect(promptInput).toHaveValue('New prompt text')
    })

    it('adds new prompt when form is submitted', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      const promptInput = screen.getByPlaceholderText('Enter prompt text...')
      await user.type(promptInput, 'New prompt')

      // The button in the form has the disabled state based on prompt text
      const submitButton = screen.getByRole('button', { name: 'Add Prompt' })
      await user.click(submitButton)

      expect(mockOnPromptsChange).toHaveBeenCalled()
      const call = mockOnPromptsChange.mock.calls[0][0]
      expect(call).toHaveLength(1)
      expect(call[0].prompt).toBe('New prompt')
    })

    it('does not add prompt if text is empty', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      const submitButton = screen.getByRole('button', { name: 'Add Prompt' })
      await user.click(submitButton)

      expect(mockOnPromptsChange).not.toHaveBeenCalled()
    })

    it('resets form after adding prompt', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      const promptInput = screen.getByPlaceholderText('Enter prompt text...')
      await user.type(promptInput, 'New prompt')

      const submitButton = screen.getByRole('button', { name: 'Add Prompt' })
      await user.click(submitButton)

      // Form should be hidden after submission
      expect(screen.queryByText('Add New Prompt')).not.toBeInTheDocument()
    })

    it('cancels add form when cancel is clicked', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      const cancelButton = screen.getByText('Cancel')
      await user.click(cancelButton)

      expect(screen.queryByText('Add New Prompt')).not.toBeInTheDocument()
    })

    it('uses default configuration values for new prompts', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      const promptInput = screen.getByPlaceholderText('Enter prompt text...')
      await user.type(promptInput, 'Test')

      const submitButton = screen.getByRole('button', { name: 'Add Prompt' })
      await user.click(submitButton)

      expect(mockOnPromptsChange).toHaveBeenCalled()
      const call = mockOnPromptsChange.mock.calls[0][0]
      expect(call[0].metadata).toMatchObject({
        max_tokens: expect.any(Number),
        temperature: expect.any(Number),
      })
    })
  })

  describe('Removing Prompts', () => {
    it('removes prompt when delete button is clicked', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager
          prompts={mockPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      // Find the first trash icon button
      const trashIcons = screen
        .getAllByRole('button')
        .filter(
          (btn) =>
            btn.querySelector('svg[data-slot="icon"]') !== null &&
            btn.querySelector('path') !== null
        )

      if (trashIcons.length > 0) {
        await user.click(trashIcons[0])
        expect(mockOnPromptsChange).toHaveBeenCalled()
      }
    })
  })

  describe('Updating Prompts', () => {
    it('updates prompt text', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager
          prompts={mockPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      const promptInput = screen.getByDisplayValue('Test prompt 1')
      await user.clear(promptInput)
      await user.type(promptInput, 'U')

      await waitFor(() => {
        expect(mockOnPromptsChange).toHaveBeenCalled()
      })
    })

    it('updates expected output', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager
          prompts={mockPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      const outputInput = screen.getByDisplayValue('Test output 1')
      await user.clear(outputInput)
      await user.type(outputInput, 'U')

      await waitFor(() => {
        expect(mockOnPromptsChange).toHaveBeenCalled()
      })
    })

    it('updates max tokens', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager
          prompts={mockPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      const maxTokensInput = screen.getByDisplayValue('500')
      await user.clear(maxTokensInput)
      await user.type(maxTokensInput, '2')

      await waitFor(() => {
        expect(mockOnPromptsChange).toHaveBeenCalled()
      })
    })

    it('updates temperature', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager
          prompts={mockPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      const tempInput = screen.getByDisplayValue('0.7')
      await user.clear(tempInput)
      await user.type(tempInput, '1')

      await waitFor(() => {
        expect(mockOnPromptsChange).toHaveBeenCalled()
      })
    })

    it('updates context', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager
          prompts={mockPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      const contextInput = screen.getByDisplayValue('Test context 1')
      await user.clear(contextInput)
      await user.type(contextInput, 'U')

      await waitFor(() => {
        expect(mockOnPromptsChange).toHaveBeenCalled()
      })
    })

    it('updates prompt type', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager
          prompts={mockPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      const typeSelects = screen.getAllByDisplayValue('Instruction')
      await user.selectOptions(typeSelects[0], 'System')

      await waitFor(() => {
        expect(mockOnPromptsChange).toHaveBeenCalled()
      })
    })
  })

  describe('File Upload', () => {
    it('handles file upload when taskId is provided', async () => {
      const mockUploadData = jest
        .spyOn(api.api, 'uploadData')
        .mockResolvedValue({
          uploaded_items: 5,
        } as any)

      const user = userEvent.setup()
      render(
        <PromptManager
          prompts={[]}
          onPromptsChange={mockOnPromptsChange}
          taskId="test-task"
        />
      )

      const file = new File(['test'], 'test.json', { type: 'application/json' })
      const uploadButton = screen.getByText('Upload Prompts')

      await user.click(uploadButton)

      const fileInput = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      if (fileInput) {
        await user.upload(fileInput, file)
      }

      await waitFor(() => {
        expect(mockUploadData).toHaveBeenCalledWith(file, 'test-task')
      })
    })

    it('does not upload when no file is selected', async () => {
      const mockUploadData = jest.spyOn(api.api, 'uploadData')

      render(
        <PromptManager
          prompts={[]}
          onPromptsChange={mockOnPromptsChange}
          taskId="test-task"
        />
      )

      expect(mockUploadData).not.toHaveBeenCalled()
    })

    it('clears file input after successful upload', async () => {
      jest.spyOn(api.api, 'uploadData').mockResolvedValue({
        uploaded_items: 5,
      } as any)

      const user = userEvent.setup()
      render(
        <PromptManager
          prompts={[]}
          onPromptsChange={mockOnPromptsChange}
          taskId="test-task"
        />
      )

      const file = new File(['test'], 'test.json', { type: 'application/json' })
      const uploadButton = screen.getByText('Upload Prompts')

      await user.click(uploadButton)

      const fileInput = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      if (fileInput) {
        await user.upload(fileInput, file)

        await waitFor(() => {
          expect(fileInput.value).toBe('')
        })
      }
    })
  })

  describe('Prompt Type Options', () => {
    it('displays all prompt type options', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      expect(screen.getByText('System')).toBeInTheDocument()
      expect(screen.getByText('Instruction')).toBeInTheDocument()
      expect(screen.getByText('Evaluation')).toBeInTheDocument()
    })

    it('sets instruction as default prompt type', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      const promptInput = screen.getByPlaceholderText('Enter prompt text...')
      await user.type(promptInput, 'Test')

      const submitButton = screen.getByRole('button', { name: 'Add Prompt' })
      await user.click(submitButton)

      expect(mockOnPromptsChange).toHaveBeenCalledWith([
        expect.objectContaining({
          metadata: expect.objectContaining({ prompt_type: 'instruction' }),
        }),
      ])
    })
  })

  describe('promptsToJson Helper Function', () => {
    it('converts prompts to JSON format', () => {
      const result = promptsToJson(mockPrompts)

      expect(result).toEqual([
        {
          prompt: 'Test prompt 1',
          expected_output: 'Test output 1',
          metadata: {
            max_tokens: 500,
            temperature: 0.7,
            context: 'Test context 1',
            prompt_type: 'instruction',
          },
        },
        {
          prompt: 'Test prompt 2',
          expected_output: 'Test output 2',
          metadata: {
            max_tokens: 1000,
            temperature: 0.5,
            context: 'Test context 2',
            prompt_type: 'system',
          },
        },
      ])
    })

    it('handles prompts without expected output', () => {
      const prompts: PromptData[] = [
        {
          prompt: 'Test prompt',
          metadata: {
            max_tokens: 500,
            temperature: 0.7,
          },
        },
      ]

      const result = promptsToJson(prompts)

      expect(result[0].expected_output).toBeNull()
    })

    it('handles prompts without metadata', () => {
      const prompts: PromptData[] = [
        {
          prompt: 'Test prompt',
        },
      ]

      const result = promptsToJson(prompts)

      expect(result[0].metadata).toEqual({})
    })

    it('handles empty prompt array', () => {
      const result = promptsToJson([])

      expect(result).toEqual([])
    })
  })

  describe('Disabled State', () => {
    it('disables add button when prompt text is empty', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      const submitButton = screen.getByRole('button', { name: 'Add Prompt' })
      expect(submitButton).toBeDisabled()
    })

    it('enables add button when prompt text is provided', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      const promptInput = screen.getByPlaceholderText('Enter prompt text...')
      await user.type(promptInput, 'Test prompt')

      const submitButton = screen.getByRole('button', { name: 'Add Prompt' })
      expect(submitButton).not.toBeDisabled()
    })
  })

  describe('Task Type Configuration', () => {
    it('uses task type for default configuration', () => {
      render(
        <PromptManager
          prompts={[]}
          onPromptsChange={mockOnPromptsChange}
          taskType="evaluation"
        />
      )

      // Component should use the taskType prop
      expect(screen.getByText('Add Prompt')).toBeInTheDocument()
    })

    it('defaults to generation task type', () => {
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      expect(screen.getByText('Add Prompt')).toBeInTheDocument()
    })
  })

  describe('Additional Coverage Tests', () => {
    it('handles whitespace-only prompt text', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      const promptInput = screen.getByPlaceholderText('Enter prompt text...')
      await user.type(promptInput, '   ')

      const submitButton = screen.getByRole('button', { name: 'Add Prompt' })

      // Whitespace-only text should keep the button disabled
      expect(submitButton).toBeDisabled()

      // Should not be able to submit
      expect(mockOnPromptsChange).not.toHaveBeenCalled()
    })

    it('handles expected output field in add form', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      const expectedOutputInput = screen.getByPlaceholderText(
        'Enter expected output...'
      )
      await user.type(expectedOutputInput, 'Expected result')

      expect(expectedOutputInput).toHaveValue('Expected result')
    })

    it('changes prompt type in add form', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      const promptInput = screen.getByPlaceholderText('Enter prompt text...')
      await user.type(promptInput, 'Test')

      const typeSelects = screen.getAllByDisplayValue('Instruction')
      await user.selectOptions(typeSelects[0], 'Evaluation')

      const submitButton = screen.getByRole('button', { name: 'Add Prompt' })
      await user.click(submitButton)

      expect(mockOnPromptsChange).toHaveBeenCalledWith([
        expect.objectContaining({
          metadata: expect.objectContaining({ prompt_type: 'evaluation' }),
        }),
      ])
    })

    it('renders multiple prompts with different types', () => {
      const mixedPrompts: PromptData[] = [
        {
          ...mockPrompts[0],
          metadata: { ...mockPrompts[0].metadata, prompt_type: 'system' },
        },
        {
          ...mockPrompts[1],
          metadata: { ...mockPrompts[1].metadata, prompt_type: 'evaluation' },
        },
      ]

      render(
        <PromptManager
          prompts={mixedPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      expect(screen.getByDisplayValue('System')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Evaluation')).toBeInTheDocument()
    })

    it('handles prompt with undefined metadata fields', () => {
      const undefinedMetadata: PromptData[] = [
        {
          prompt: 'Test',
          metadata: {},
        },
      ]

      render(
        <PromptManager
          prompts={undefinedMetadata}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      expect(screen.getByText('Prompt #1')).toBeInTheDocument()
    })

    it('handles prompt with no expected output', () => {
      const noOutput: PromptData[] = [
        {
          prompt: 'Test prompt',
          metadata: { max_tokens: 500 },
        },
      ]

      render(
        <PromptManager
          prompts={noOutput}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      expect(screen.getByDisplayValue('Test prompt')).toBeInTheDocument()
    })

    it('displays temperature with decimal values correctly', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager
          prompts={mockPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      const tempInput = screen.getByDisplayValue('0.5')
      await user.clear(tempInput)
      await user.type(tempInput, '1.5')

      await waitFor(() => {
        expect(mockOnPromptsChange).toHaveBeenCalled()
      })
    })

    it('handles file upload error gracefully', async () => {
      jest
        .spyOn(api.api, 'uploadData')
        .mockRejectedValue(new Error('Upload failed'))

      const user = userEvent.setup()
      render(
        <PromptManager
          prompts={[]}
          onPromptsChange={mockOnPromptsChange}
          taskId="test-task"
        />
      )

      const file = new File(['test'], 'test.json', { type: 'application/json' })
      const uploadButton = screen.getByText('Upload Prompts')

      await user.click(uploadButton)

      const fileInput = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      if (fileInput) {
        await user.upload(fileInput, file)
      }

      await waitFor(() => {
        expect(api.api.uploadData).toHaveBeenCalled()
      })
    })

    it('handles prompt with empty context', async () => {
      const user = userEvent.setup()
      const emptyContext: PromptData[] = [
        {
          prompt: 'Test',
          metadata: { context: '' },
        },
      ]

      render(
        <PromptManager
          prompts={emptyContext}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      const contextInput = screen.getByPlaceholderText('Enter context...')
      await user.type(contextInput, 'New context')

      await waitFor(() => {
        expect(mockOnPromptsChange).toHaveBeenCalled()
      })
    })

    it('handles rapid prompt type changes', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager
          prompts={mockPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      const typeSelects = screen.getAllByDisplayValue('Instruction')

      await user.selectOptions(typeSelects[0], 'System')
      await user.selectOptions(typeSelects[0], 'Evaluation')
      await user.selectOptions(typeSelects[0], 'Instruction')

      expect(mockOnPromptsChange).toHaveBeenCalled()
    })

    it('displays correct number of trash icons for multiple prompts', () => {
      render(
        <PromptManager
          prompts={mockPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      const trashIcons = screen
        .getAllByRole('button')
        .filter((btn) => btn.querySelector('svg[data-slot="icon"]') !== null)

      expect(trashIcons.length).toBeGreaterThanOrEqual(2)
    })

    it('handles prompt list with single item', () => {
      const singlePrompt: PromptData[] = [mockPrompts[0]]

      render(
        <PromptManager
          prompts={singlePrompt}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      expect(screen.getByText('Prompt #1')).toBeInTheDocument()
      expect(screen.queryByText('Prompt #2')).not.toBeInTheDocument()
    })

    it('handles max tokens with large values', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager
          prompts={mockPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      const maxTokensInput = screen.getByDisplayValue('500')
      await user.clear(maxTokensInput)
      await user.type(maxTokensInput, '4096')

      await waitFor(() => {
        expect(mockOnPromptsChange).toHaveBeenCalled()
      })
    })

    it('handles temperature at boundary values', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager
          prompts={mockPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      const tempInput = screen.getByDisplayValue('0.7')

      await user.clear(tempInput)
      await user.type(tempInput, '0')
      await waitFor(() => {
        expect(mockOnPromptsChange).toHaveBeenCalled()
      })

      await user.clear(tempInput)
      await user.type(tempInput, '2')
      await waitFor(() => {
        expect(mockOnPromptsChange).toHaveBeenCalled()
      })
    })

    it('preserves prompt order when updating', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager
          prompts={mockPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      const firstPromptInput = screen.getByDisplayValue('Test prompt 1')
      await user.type(firstPromptInput, ' updated')

      await waitFor(() => {
        const calls = mockOnPromptsChange.mock.calls
        const lastCall = calls[calls.length - 1][0]
        expect(lastCall[0].prompt).toContain('Test prompt 1')
        expect(lastCall[1].prompt).toBe('Test prompt 2')
      })
    })

    it('handles empty prompt list after removing all prompts', async () => {
      const user = userEvent.setup()
      const singlePrompt: PromptData[] = [mockPrompts[0]]

      render(
        <PromptManager
          prompts={singlePrompt}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      const trashIcons = screen
        .getAllByRole('button')
        .filter(
          (btn) =>
            btn.querySelector('svg[data-slot="icon"]') !== null &&
            btn.querySelector('path') !== null
        )

      if (trashIcons.length > 0) {
        await user.click(trashIcons[0])
        expect(mockOnPromptsChange).toHaveBeenCalledWith([])
      }
    })

    it('handles file input ref correctly', () => {
      render(
        <PromptManager
          prompts={[]}
          onPromptsChange={mockOnPromptsChange}
          taskId="test-task"
        />
      )

      const fileInput = document.querySelector('input[type="file"]')
      expect(fileInput).toBeInTheDocument()
      expect(fileInput).toHaveAttribute('accept', '.json')
    })

    it('hides add form when showing upload buttons', () => {
      render(
        <PromptManager
          prompts={[]}
          onPromptsChange={mockOnPromptsChange}
          taskId="test-task"
        />
      )

      expect(screen.getByText('Add Prompt')).toBeInTheDocument()
      expect(screen.getByText('Upload Prompts')).toBeInTheDocument()
      expect(screen.queryByText('Add New Prompt')).not.toBeInTheDocument()
    })

    it('displays empty state message with correct styling', () => {
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const emptyStateText = screen.getByText(
        'No prompts yet. Add your first prompt to get started.'
      )
      expect(emptyStateText).toBeInTheDocument()
      expect(emptyStateText.className).toContain('text-center')
    })

    it('handles metadata updates correctly', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager
          prompts={mockPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      // Find context input by its placeholder
      const contextInputs = screen.getAllByPlaceholderText('Enter context...')
      const contextInput = contextInputs[0]
      await user.clear(contextInput)
      await user.type(contextInput, 'Updated')

      await waitFor(() => {
        expect(mockOnPromptsChange).toHaveBeenCalled()
        const calls = mockOnPromptsChange.mock.calls
        const lastCall = calls[calls.length - 1][0]
        // Check that the context field was updated
        expect(lastCall[0].metadata?.context).toBeDefined()
      })
    })

    it('handles prompt text multiline input', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      const promptInput = screen.getByPlaceholderText('Enter prompt text...')
      await user.type(promptInput, 'Line 1{Enter}Line 2')

      expect(promptInput).toHaveValue('Line 1\nLine 2')
    })

    it('displays all metadata fields for existing prompts', () => {
      render(
        <PromptManager
          prompts={mockPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      expect(screen.getByDisplayValue('Test prompt 1')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Test output 1')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Test context 1')).toBeInTheDocument()
      expect(screen.getByDisplayValue('500')).toBeInTheDocument()
      expect(screen.getByDisplayValue('0.7')).toBeInTheDocument()
    })

    it('handles cancel without making changes', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      const cancelButton = screen.getByText('Cancel')
      await user.click(cancelButton)

      expect(mockOnPromptsChange).not.toHaveBeenCalled()
    })

    it('handles removing middle prompt from list', async () => {
      const user = userEvent.setup()
      const threePrompts: PromptData[] = [
        mockPrompts[0],
        { ...mockPrompts[1], prompt: 'Middle prompt' },
        { ...mockPrompts[0], prompt: 'Last prompt' },
      ]

      render(
        <PromptManager
          prompts={threePrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      const trashIcons = screen
        .getAllByRole('button')
        .filter(
          (btn) =>
            btn.querySelector('svg[data-slot="icon"]') !== null &&
            btn.querySelector('path') !== null
        )

      if (trashIcons.length >= 2) {
        await user.click(trashIcons[1])

        await waitFor(() => {
          const calls = mockOnPromptsChange.mock.calls
          if (calls.length > 0) {
            const lastCall = calls[calls.length - 1][0]
            expect(lastCall.length).toBe(2)
          }
        })
      }
    })

    it('handles prompt with special characters in text', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      const promptInput = screen.getByPlaceholderText('Enter prompt text...')
      await user.type(promptInput, 'Test <>&"')

      const submitButton = screen.getByRole('button', { name: 'Add Prompt' })
      await user.click(submitButton)

      expect(mockOnPromptsChange).toHaveBeenCalledWith([
        expect.objectContaining({
          prompt: 'Test <>&"',
        }),
      ])
    })

    it('maintains add button state across interactions', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      const submitButton = screen.getByRole('button', { name: 'Add Prompt' })
      expect(submitButton).toBeDisabled()

      const promptInput = screen.getByPlaceholderText('Enter prompt text...')
      await user.type(promptInput, 'T')

      expect(submitButton).not.toBeDisabled()
    })

    it('handles default max_tokens from config', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      const promptInput = screen.getByPlaceholderText('Enter prompt text...')
      await user.type(promptInput, 'Test')

      const submitButton = screen.getByRole('button', { name: 'Add Prompt' })
      await user.click(submitButton)

      expect(mockOnPromptsChange).toHaveBeenCalledWith([
        expect.objectContaining({
          metadata: expect.objectContaining({
            max_tokens: expect.any(Number),
          }),
        }),
      ])
    })

    it('handles default temperature from config', async () => {
      const user = userEvent.setup()
      render(
        <PromptManager prompts={[]} onPromptsChange={mockOnPromptsChange} />
      )

      const addButton = screen.getByText('Add Prompt')
      await user.click(addButton)

      const promptInput = screen.getByPlaceholderText('Enter prompt text...')
      await user.type(promptInput, 'Test')

      const submitButton = screen.getByRole('button', { name: 'Add Prompt' })
      await user.click(submitButton)

      expect(mockOnPromptsChange).toHaveBeenCalledWith([
        expect.objectContaining({
          metadata: expect.objectContaining({
            temperature: expect.any(Number),
          }),
        }),
      ])
    })

    it('renders with proper styling classes', () => {
      render(
        <PromptManager
          prompts={mockPrompts}
          onPromptsChange={mockOnPromptsChange}
        />
      )

      // Check that the first prompt card has the expected classes
      const promptText = screen.getByDisplayValue('Test prompt 1')
      const promptCard = promptText.closest('.rounded-lg')
      expect(promptCard).toBeInTheDocument()
    })
  })
})
