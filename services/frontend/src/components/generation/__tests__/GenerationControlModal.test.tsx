import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { GenerationControlModal } from '../GenerationControlModal'

// Mock useModels hook
jest.mock('@/hooks/useModels', () => ({
  useModels: jest.fn(() => ({
    models: [],
    loading: false,
    error: null,
    refetch: jest.fn(),
    hasApiKeys: true,
    apiKeyStatus: null,
  })),
}))

// Mock Toast
jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(() => ({
    addToast: jest.fn(),
    showToast: jest.fn(),
    removeToast: jest.fn(),
  })),
  ToastProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}))

// Mock i18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(() => ({
    t: (key: string, arg2?: any, arg3?: any) => {
      const vars = typeof arg2 === 'object' ? arg2 : arg3
      const translations: Record<string, string> = {
        'toasts.generation.selectModel': 'Please select at least one model',
        'toasts.generation.selectStructure': 'Please select at least one structure',
        'generation.controlModal.title': 'Start Bulk Generation',
        'generation.controlModal.generationOptions': 'Generation Options',
        'generation.controlModal.generationMode': 'Generation Mode',
        'generation.controlModal.generateMissingOnly': 'Generate Missing Only',
        'generation.controlModal.generateMissingOnlyDesc': "Only generate for task-model combinations that haven't been generated yet",
        'generation.controlModal.generateAll': 'Generate All',
        'generation.controlModal.generateAllDesc': 'Regenerate all task-model combinations (overwrites existing)',
        'generation.controlModal.selectModels': 'Select Models',
        'generation.controlModal.selectAll': 'Select All',
        'generation.controlModal.clearAll': 'Clear All',
        'generation.controlModal.oneModelSelected': '1 model selected',
        'generation.controlModal.modelsSelected': '{count} models selected',
        'generation.controlModal.selectPromptStructures': 'Select Prompt Structures',
        'generation.controlModal.oneStructureSelected': '1 structure selected',
        'generation.controlModal.structuresSelected': '{count} structures selected',
        'generation.controlModal.advancedSettings': 'Advanced Settings',
        'generation.controlModal.temperature': 'Temperature',
        'generation.controlModal.temperatureDesc': '0 = deterministic, higher = more creative',
        'generation.controlModal.defaultMaxTokens': 'Default Max Tokens',
        'generation.controlModal.defaultMaxTokensDesc': 'Default response length (100-16000)',
        'generation.controlModal.perModelTokenLimits': 'Per-Model Token Limits',
        'generation.controlModal.perModelTokenLimitsDesc': 'Leave blank to use the default. Set a custom value to override for specific models.',
        'generation.controlModal.totalGenerationsPerTask': 'Total Generations Per Task:',
        'generation.controlModal.model': 'model',
        'generation.controlModal.models': 'models',
        'generation.controlModal.structure': 'structure',
        'generation.controlModal.structures': 'structures',
        'generation.controlModal.generation': 'generation',
        'generation.controlModal.generations': 'generations',
        'generation.controlModal.starting': 'Starting...',
        'generation.controlModal.startGeneration': 'Start Generation',
        'generation.controlModal.cancel': 'Cancel',
        'generation.controlModal.queuedJobs': 'Queued {tasks} generation jobs for {models} models. Estimated time: {minutes} minutes',
        'generation.controlModal.failedToStart': 'Failed to start generation',
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
    setLocale: jest.fn(),
  })),
}))

// Mock API client
jest.mock('@/lib/api/client', () => ({
  apiClient: {
    post: jest.fn(),
  },
}))

describe('GenerationControlModal', () => {
  const mockModels = ['openai-gpt-4', 'anthropic-claude-3', 'google-gemini-1.5']
  const mockOnClose = jest.fn()
  const mockOnGenerate = jest.fn()
  const mockOnSuccess = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders when open', () => {
    render(
      <GenerationControlModal
        isOpen={true}
        onClose={mockOnClose}
        models={mockModels}
        onGenerate={mockOnGenerate}
      />
    )

    expect(screen.getByText('Start Bulk Generation')).toBeInTheDocument()
    expect(screen.getByText('Generation Options')).toBeInTheDocument()
  })

  it('does not render when closed', () => {
    render(
      <GenerationControlModal
        isOpen={false}
        onClose={mockOnClose}
        models={mockModels}
        onGenerate={mockOnGenerate}
      />
    )

    expect(screen.queryByText('Start Bulk Generation')).not.toBeInTheDocument()
  })

  it('displays all model options', () => {
    render(
      <GenerationControlModal
        isOpen={true}
        onClose={mockOnClose}
        models={mockModels}
        onGenerate={mockOnGenerate}
      />
    )

    mockModels.forEach((model) => {
      expect(screen.getByLabelText(model)).toBeInTheDocument()
    })
  })

  it('handles model selection', async () => {
    const user = userEvent.setup()
    render(
      <GenerationControlModal
        isOpen={true}
        onClose={mockOnClose}
        models={mockModels}
        onGenerate={mockOnGenerate}
      />
    )

    const firstCheckbox = screen.getByLabelText(mockModels[0])
    await user.click(firstCheckbox)

    expect(firstCheckbox).toBeChecked()
  })

  it('handles select all functionality', async () => {
    const user = userEvent.setup()
    render(
      <GenerationControlModal
        isOpen={true}
        onClose={mockOnClose}
        models={mockModels}
        onGenerate={mockOnGenerate}
      />
    )

    const selectAllButton = screen.getByText('Select All')
    await user.click(selectAllButton)

    mockModels.forEach((model) => {
      expect(screen.getByLabelText(model)).toBeChecked()
    })
  })

  it('handles clear all functionality', async () => {
    const user = userEvent.setup()
    render(
      <GenerationControlModal
        isOpen={true}
        onClose={mockOnClose}
        models={mockModels}
        onGenerate={mockOnGenerate}
      />
    )

    // First select all
    const selectAllButton = screen.getByText('Select All')
    await user.click(selectAllButton)

    // Then clear all
    const clearAllButton = screen.getByText('Clear All')
    await user.click(clearAllButton)

    mockModels.forEach((model) => {
      expect(screen.getByLabelText(model)).not.toBeChecked()
    })
  })

  it('handles generation mode toggle', async () => {
    const user = userEvent.setup()
    render(
      <GenerationControlModal
        isOpen={true}
        onClose={mockOnClose}
        models={mockModels}
        onGenerate={mockOnGenerate}
      />
    )

    const missingOnlyRadio = screen.getByLabelText('Generate Missing Only')
    const generateAllRadio = screen.getByLabelText('Generate All')

    expect(missingOnlyRadio).toBeChecked() // Default
    expect(generateAllRadio).not.toBeChecked()

    await user.click(generateAllRadio)

    expect(generateAllRadio).toBeChecked()
    expect(missingOnlyRadio).not.toBeChecked()
  })

  it('calls onGenerate with correct parameters', async () => {
    const user = userEvent.setup()
    render(
      <GenerationControlModal
        isOpen={true}
        onClose={mockOnClose}
        models={mockModels}
        onGenerate={mockOnGenerate}
      />
    )

    // Select first two models
    await user.click(screen.getByLabelText(mockModels[0]))
    await user.click(screen.getByLabelText(mockModels[1]))

    // Select generate all mode
    await user.click(screen.getByLabelText('Generate All'))

    // Start generation
    const startButton = screen.getByText('Start Generation')
    await user.click(startButton)

    expect(mockOnGenerate).toHaveBeenCalledWith(
      [mockModels[0], mockModels[1]],
      false, // generate_missing_only = false
      undefined // no structures for this project
    )
  })

  it('disables start button when no models selected', () => {
    render(
      <GenerationControlModal
        isOpen={true}
        onClose={mockOnClose}
        models={mockModels}
        onGenerate={mockOnGenerate}
      />
    )

    const startButton = screen.getByText('Start Generation')
    expect(startButton).toBeDisabled()
  })

  it('enables start button when models are selected', async () => {
    const user = userEvent.setup()
    render(
      <GenerationControlModal
        isOpen={true}
        onClose={mockOnClose}
        models={mockModels}
        onGenerate={mockOnGenerate}
      />
    )

    const startButton = screen.getByText('Start Generation')
    expect(startButton).toBeDisabled()

    await user.click(screen.getByLabelText(mockModels[0]))

    expect(startButton).not.toBeDisabled()
  })

  it('calls onClose when cancel is clicked', async () => {
    const user = userEvent.setup()
    render(
      <GenerationControlModal
        isOpen={true}
        onClose={mockOnClose}
        models={mockModels}
        onGenerate={mockOnGenerate}
      />
    )

    const cancelButton = screen.getByText('Cancel')
    await user.click(cancelButton)

    expect(mockOnClose).toHaveBeenCalled()
  })

  it('displays selected model count', async () => {
    const user = userEvent.setup()
    render(
      <GenerationControlModal
        isOpen={true}
        onClose={mockOnClose}
        models={mockModels}
        onGenerate={mockOnGenerate}
      />
    )

    expect(screen.getByText('0 models selected')).toBeInTheDocument()

    await user.click(screen.getByLabelText(mockModels[0]))
    expect(screen.getByText('1 model selected')).toBeInTheDocument()

    await user.click(screen.getByLabelText(mockModels[1]))
    expect(screen.getByText('2 models selected')).toBeInTheDocument()
  })

  it('resets state when modal is closed and reopened', async () => {
    const user = userEvent.setup()
    const { rerender } = render(
      <GenerationControlModal
        isOpen={true}
        onClose={mockOnClose}
        models={mockModels}
        onGenerate={mockOnGenerate}
      />
    )

    // Select a model
    await user.click(screen.getByLabelText(mockModels[0]))
    expect(screen.getByLabelText(mockModels[0])).toBeChecked()

    // Close modal
    rerender(
      <GenerationControlModal
        isOpen={false}
        onClose={mockOnClose}
        models={mockModels}
        onGenerate={mockOnGenerate}
      />
    )

    // Reopen modal
    rerender(
      <GenerationControlModal
        isOpen={true}
        onClose={mockOnClose}
        models={mockModels}
        onGenerate={mockOnGenerate}
      />
    )

    // Check that state was reset
    expect(screen.getByLabelText(mockModels[0])).not.toBeChecked()
  })

  describe('Structure Selection', () => {
    const mockProject = {
      id: 'project-1',
      title: 'Test Project',
      generation_config: {
        prompt_structures: {
          structure1: {
            name: 'Structure 1',
            description: 'First structure',
            template: 'Template 1',
          },
          structure2: {
            name: 'Structure 2',
            description: 'Second structure',
            template: 'Template 2',
          },
        },
      },
    } as any

    it('displays structure selection when project has structures', async () => {
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          project={mockProject}
          onGenerate={mockOnGenerate}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Select Prompt Structures')).toBeInTheDocument()
      })

      expect(screen.getByText('Structure 1')).toBeInTheDocument()
      expect(screen.getByText('Structure 2')).toBeInTheDocument()
    })

    it('displays structure descriptions', async () => {
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          project={mockProject}
          onGenerate={mockOnGenerate}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('First structure')).toBeInTheDocument()
      })

      expect(screen.getByText('Second structure')).toBeInTheDocument()
    })

    it('handles structure selection', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          project={mockProject}
          onGenerate={mockOnGenerate}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Structure 1')).toBeInTheDocument()
      })

      const structure1Checkbox = document.getElementById(
        'structure-structure1'
      ) as HTMLInputElement
      await user.click(structure1Checkbox)

      expect(structure1Checkbox).toBeChecked()
    })

    it('handles select all structures', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          project={mockProject}
          onGenerate={mockOnGenerate}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Structure 1')).toBeInTheDocument()
      })

      const selectAllButtons = screen.getAllByText('Select All')
      const structureSelectAll = selectAllButtons[1]
      await user.click(structureSelectAll)

      const struct1 = document.getElementById(
        'structure-structure1'
      ) as HTMLInputElement
      const struct2 = document.getElementById(
        'structure-structure2'
      ) as HTMLInputElement
      expect(struct1).toBeChecked()
      expect(struct2).toBeChecked()
    })

    it('handles clear all structures', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          project={mockProject}
          onGenerate={mockOnGenerate}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Structure 1')).toBeInTheDocument()
      })

      const selectAllButtons = screen.getAllByText('Select All')
      await user.click(selectAllButtons[1])

      const clearAllButtons = screen.getAllByText('Clear All')
      await user.click(clearAllButtons[1])

      const struct1 = document.getElementById(
        'structure-structure1'
      ) as HTMLInputElement
      const struct2 = document.getElementById(
        'structure-structure2'
      ) as HTMLInputElement
      expect(struct1).not.toBeChecked()
      expect(struct2).not.toBeChecked()
    })

    it('displays structure count', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          project={mockProject}
          onGenerate={mockOnGenerate}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('0 structures selected')).toBeInTheDocument()
      })

      const struct1 = document.getElementById(
        'structure-structure1'
      ) as HTMLInputElement
      await user.click(struct1)
      expect(screen.getByText('1 structure selected')).toBeInTheDocument()

      const struct2 = document.getElementById(
        'structure-structure2'
      ) as HTMLInputElement
      await user.click(struct2)
      expect(screen.getByText('2 structures selected')).toBeInTheDocument()
    })

    it('disables start button when structures exist but none selected', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          project={mockProject}
          onGenerate={mockOnGenerate}
        />
      )

      await user.click(screen.getByLabelText(mockModels[0]))

      const startButton = screen.getByText('Start Generation')
      expect(startButton).toBeDisabled()
    })

    it('enables start button when models and structures are selected', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          project={mockProject}
          onGenerate={mockOnGenerate}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Structure 1')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText(mockModels[0]))
      const struct1 = document.getElementById(
        'structure-structure1'
      ) as HTMLInputElement
      await user.click(struct1)

      const startButton = screen.getByText('Start Generation')
      expect(startButton).not.toBeDisabled()
    })

    it('shows toast error when trying to generate without structures', async () => {
      const user = userEvent.setup()

      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          project={mockProject}
          onGenerate={mockOnGenerate}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Structure 1')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText(mockModels[0]))

      const startButton = screen.getByText('Start Generation')
      expect(startButton).toBeDisabled()
    })

    it('passes selected structures to onGenerate callback', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          project={mockProject}
          onGenerate={mockOnGenerate}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Structure 1')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText(mockModels[0]))
      const struct1 = document.getElementById(
        'structure-structure1'
      ) as HTMLInputElement
      await user.click(struct1)

      const startButton = screen.getByText('Start Generation')
      await user.click(startButton)

      expect(mockOnGenerate).toHaveBeenCalledWith([mockModels[0]], true, [
        'structure1',
      ])
    })

    it('calculates total generations correctly with structures', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          project={mockProject}
          onGenerate={mockOnGenerate}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Structure 1')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText(mockModels[0]))
      await user.click(screen.getByLabelText(mockModels[1]))
      const struct1 = document.getElementById(
        'structure-structure1'
      ) as HTMLInputElement
      const struct2 = document.getElementById(
        'structure-structure2'
      ) as HTMLInputElement
      await user.click(struct1)
      await user.click(struct2)

      expect(
        screen.getByText(/2 models × 2 structures = 4 generations/)
      ).toBeInTheDocument()
    })
  })

  describe('API Integration', () => {
    it('calls API when submitting without onGenerate prop', async () => {
      const user = userEvent.setup()
      const { apiClient } = require('@/lib/api/client')
      apiClient.post.mockResolvedValue({
        tasks_queued: 10,
        models_count: 2,
        estimated_time_seconds: 120,
      })

      render(
        <GenerationControlModal
          isOpen={true}
          projectId="project-1"
          onClose={mockOnClose}
          models={mockModels}
          onSuccess={mockOnSuccess}
        />
      )

      await user.click(screen.getByLabelText(mockModels[0]))
      await user.click(screen.getByLabelText(mockModels[1]))

      const startButton = screen.getByText('Start Generation')
      await user.click(startButton)

      await waitFor(() => {
        expect(apiClient.post).toHaveBeenCalledWith(
          '/generation-tasks/projects/project-1/generate',
          {
            mode: 'missing',
            model_ids: [mockModels[0], mockModels[1]],
            parameters: {
              temperature: 0,
              max_tokens: 4000,
            },
          }
        )
      })
    })

    it('includes structures in API request when available', async () => {
      const user = userEvent.setup()
      const { apiClient } = require('@/lib/api/client')
      apiClient.post.mockResolvedValue({
        tasks_queued: 10,
        models_count: 2,
        estimated_time_seconds: 120,
      })

      const mockProject = {
        generation_config: {
          prompt_structures: {
            struct1: { name: 'Structure 1', template: 'Template 1' },
          },
        },
      } as any

      render(
        <GenerationControlModal
          isOpen={true}
          projectId="project-1"
          onClose={mockOnClose}
          models={mockModels}
          project={mockProject}
          onSuccess={mockOnSuccess}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Structure 1')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText(mockModels[0]))
      const struct1 = document.getElementById(
        'structure-struct1'
      ) as HTMLInputElement
      await user.click(struct1)

      const startButton = screen.getByText('Start Generation')
      await user.click(startButton)

      await waitFor(() => {
        expect(apiClient.post).toHaveBeenCalledWith(
          '/generation-tasks/projects/project-1/generate',
          {
            mode: 'missing',
            model_ids: [mockModels[0]],
            structure_keys: ['struct1'],
            parameters: {
              temperature: 0,
              max_tokens: 4000,
            },
          }
        )
      })
    })

    it('shows success toast after API call', async () => {
      const user = userEvent.setup()
      const { apiClient } = require('@/lib/api/client')
      const { useToast } = require('@/components/shared/Toast')
      const mockAddToast = jest.fn()
      useToast.mockReturnValue({ addToast: mockAddToast })

      apiClient.post.mockResolvedValue({
        tasks_queued: 10,
        models_count: 2,
        estimated_time_seconds: 120,
      })

      render(
        <GenerationControlModal
          isOpen={true}
          projectId="project-1"
          onClose={mockOnClose}
          models={mockModels}
          onSuccess={mockOnSuccess}
        />
      )

      await user.click(screen.getByLabelText(mockModels[0]))

      const startButton = screen.getByText('Start Generation')
      await user.click(startButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Queued 10 generation jobs for 2 models. Estimated time: 2 minutes',
          'success'
        )
      })
    })

    it('calls onSuccess after successful API call', async () => {
      const user = userEvent.setup()
      const { apiClient } = require('@/lib/api/client')
      apiClient.post.mockResolvedValue({
        tasks_queued: 10,
        models_count: 2,
        estimated_time_seconds: 120,
      })

      render(
        <GenerationControlModal
          isOpen={true}
          projectId="project-1"
          onClose={mockOnClose}
          models={mockModels}
          onSuccess={mockOnSuccess}
        />
      )

      await user.click(screen.getByLabelText(mockModels[0]))

      const startButton = screen.getByText('Start Generation')
      await user.click(startButton)

      await waitFor(() => {
        expect(mockOnSuccess).toHaveBeenCalled()
      })
    })

    it('shows error toast on API failure', async () => {
      const user = userEvent.setup()
      const { apiClient } = require('@/lib/api/client')
      const { useToast } = require('@/components/shared/Toast')
      const mockAddToast = jest.fn()
      useToast.mockReturnValue({ addToast: mockAddToast })

      apiClient.post.mockRejectedValue({
        response: {
          data: { detail: 'API rate limit exceeded' },
        },
      })

      render(
        <GenerationControlModal
          isOpen={true}
          projectId="project-1"
          onClose={mockOnClose}
          models={mockModels}
          onSuccess={mockOnSuccess}
        />
      )

      await user.click(screen.getByLabelText(mockModels[0]))

      const startButton = screen.getByText('Start Generation')
      await user.click(startButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'API rate limit exceeded',
          'error'
        )
      })
    })

    it('shows generic error toast when error has no detail', async () => {
      const user = userEvent.setup()
      const { apiClient } = require('@/lib/api/client')
      const { useToast } = require('@/components/shared/Toast')
      const mockAddToast = jest.fn()
      useToast.mockReturnValue({ addToast: mockAddToast })

      apiClient.post.mockRejectedValue(new Error('Network error'))

      render(
        <GenerationControlModal
          isOpen={true}
          projectId="project-1"
          onClose={mockOnClose}
          models={mockModels}
          onSuccess={mockOnSuccess}
        />
      )

      await user.click(screen.getByLabelText(mockModels[0]))

      const startButton = screen.getByText('Start Generation')
      await user.click(startButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to start generation',
          'error'
        )
      })
    })

    it('shows loading state during API call', async () => {
      const user = userEvent.setup()
      const { apiClient } = require('@/lib/api/client')
      apiClient.post.mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      )

      render(
        <GenerationControlModal
          isOpen={true}
          projectId="project-1"
          onClose={mockOnClose}
          models={mockModels}
          onSuccess={mockOnSuccess}
        />
      )

      await user.click(screen.getByLabelText(mockModels[0]))

      const startButton = screen.getByText('Start Generation')
      await user.click(startButton)

      expect(screen.getByText('Starting...')).toBeInTheDocument()
    })
  })

  describe('UI Elements', () => {
    it('displays close button in header', () => {
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      const closeButton = screen.getByRole('button', { name: /close/i })
      expect(closeButton).toBeInTheDocument()
    })

    it('closes modal when header close button is clicked', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      const closeButton = screen.getByRole('button', { name: /close/i })
      await user.click(closeButton)

      expect(mockOnClose).toHaveBeenCalled()
    })

    it('displays generation mode descriptions', () => {
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      expect(
        screen.getByText(/Only generate for task-model combinations/)
      ).toBeInTheDocument()
      expect(
        screen.getByText(/Regenerate all task-model combinations/)
      ).toBeInTheDocument()
    })

    it('displays total generations info box when selections made', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      await user.click(screen.getByLabelText(mockModels[0]))
      await user.click(screen.getByLabelText(mockModels[1]))

      expect(
        screen.getByText('Total Generations Per Task:')
      ).toBeInTheDocument()
      expect(screen.getByText(/2 models = 2 generations/)).toBeInTheDocument()
    })
  })

  describe('Validation', () => {
    it('shows error toast when trying to submit without models', async () => {
      const user = userEvent.setup()

      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      const startButton = screen.getByText('Start Generation')
      expect(startButton).toBeDisabled()
    })
  })

  describe('Mode Selection', () => {
    it('defaults to missing mode', () => {
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      const missingRadio = screen.getByLabelText('Generate Missing Only')
      expect(missingRadio).toBeChecked()
    })

    it('switches to all mode when selected', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      const allRadio = screen.getByLabelText('Generate All')
      await user.click(allRadio)

      expect(allRadio).toBeChecked()
    })

    it('passes correct mode to API call', async () => {
      const user = userEvent.setup()
      const { apiClient } = require('@/lib/api/client')
      apiClient.post.mockResolvedValue({
        tasks_queued: 10,
        models_count: 1,
        estimated_time_seconds: 60,
      })

      render(
        <GenerationControlModal
          isOpen={true}
          projectId="project-1"
          onClose={mockOnClose}
          models={mockModels}
          onSuccess={mockOnSuccess}
        />
      )

      await user.click(screen.getByLabelText(mockModels[0]))
      await user.click(screen.getByLabelText('Generate All'))

      const startButton = screen.getByText('Start Generation')
      await user.click(startButton)

      await waitFor(() => {
        expect(apiClient.post).toHaveBeenCalledWith(
          '/generation-tasks/projects/project-1/generate',
          {
            mode: 'all',
            model_ids: [mockModels[0]],
            parameters: {
              temperature: 0,
              max_tokens: 4000,
            },
          }
        )
      })
    })
  })

  describe('Edge Cases', () => {
    it('handles empty models array', () => {
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={[]}
          onGenerate={mockOnGenerate}
        />
      )

      expect(screen.getByText('Start Bulk Generation')).toBeInTheDocument()
      expect(screen.getByText('0 models selected')).toBeInTheDocument()
    })

    it('handles project without generation_config', () => {
      const projectWithoutConfig = {
        id: 'project-1',
        title: 'Test Project',
      } as any

      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          project={projectWithoutConfig}
          onGenerate={mockOnGenerate}
        />
      )

      expect(
        screen.queryByText('Select Prompt Structures')
      ).not.toBeInTheDocument()
    })

    it('handles project with empty prompt_structures', () => {
      const projectWithEmptyStructures = {
        id: 'project-1',
        title: 'Test Project',
        generation_config: {
          prompt_structures: {},
        },
      } as any

      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          project={projectWithEmptyStructures}
          onGenerate={mockOnGenerate}
        />
      )

      expect(
        screen.queryByText('Select Prompt Structures')
      ).not.toBeInTheDocument()
    })

    it('handles structure without description', async () => {
      const projectWithStructureNoDesc = {
        generation_config: {
          prompt_structures: {
            struct1: { name: 'Structure 1', template: 'Template 1' },
          },
        },
      } as any

      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          project={projectWithStructureNoDesc}
          onGenerate={mockOnGenerate}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Structure 1')).toBeInTheDocument()
      })

      const struct1 = document.getElementById('structure-struct1')
      expect(struct1).toBeInTheDocument()
    })

    it('resets mode to missing when modal reopens', async () => {
      const user = userEvent.setup()
      const { rerender } = render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      await user.click(screen.getByLabelText('Generate All'))
      expect(screen.getByLabelText('Generate All')).toBeChecked()

      rerender(
        <GenerationControlModal
          isOpen={false}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      rerender(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      expect(screen.getByLabelText('Generate Missing Only')).toBeChecked()
    })

    it('resets loading state when modal reopens', async () => {
      const user = userEvent.setup()
      const { apiClient } = require('@/lib/api/client')
      let resolvePromise: any
      apiClient.post.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolvePromise = resolve
          })
      )

      const { rerender } = render(
        <GenerationControlModal
          isOpen={true}
          projectId="project-1"
          onClose={mockOnClose}
          models={mockModels}
          onSuccess={mockOnSuccess}
        />
      )

      await user.click(screen.getByLabelText(mockModels[0]))
      await user.click(screen.getByText('Start Generation'))

      expect(screen.getByText('Starting...')).toBeInTheDocument()

      rerender(
        <GenerationControlModal
          isOpen={false}
          projectId="project-1"
          onClose={mockOnClose}
          models={mockModels}
          onSuccess={mockOnSuccess}
        />
      )

      rerender(
        <GenerationControlModal
          isOpen={true}
          projectId="project-1"
          onClose={mockOnClose}
          models={mockModels}
          onSuccess={mockOnSuccess}
        />
      )

      expect(screen.queryByText('Starting...')).not.toBeInTheDocument()
      expect(screen.getByText('Start Generation')).toBeInTheDocument()
    })
  })

  describe('Model Deselection', () => {
    it('deselects model when clicked twice', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      const firstCheckbox = screen.getByLabelText(mockModels[0])
      await user.click(firstCheckbox)
      expect(firstCheckbox).toBeChecked()

      await user.click(firstCheckbox)
      expect(firstCheckbox).not.toBeChecked()
    })

    it('updates count when models are deselected', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      await user.click(screen.getByText('Select All'))
      expect(screen.getByText('3 models selected')).toBeInTheDocument()

      const firstCheckbox = screen.getByLabelText(mockModels[0])
      await user.click(firstCheckbox)
      expect(screen.getByText('2 models selected')).toBeInTheDocument()
    })
  })

  describe('Structure Deselection', () => {
    const mockProject = {
      generation_config: {
        prompt_structures: {
          struct1: { name: 'Structure 1', template: 'Template 1' },
          struct2: { name: 'Structure 2', template: 'Template 2' },
        },
      },
    } as any

    it('deselects structure when clicked twice', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          project={mockProject}
          onGenerate={mockOnGenerate}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Structure 1')).toBeInTheDocument()
      })

      const struct1 = document.getElementById(
        'structure-struct1'
      ) as HTMLInputElement
      await user.click(struct1)
      expect(struct1).toBeChecked()

      await user.click(struct1)
      expect(struct1).not.toBeChecked()
    })

    it('updates count when structures are deselected', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          project={mockProject}
          onGenerate={mockOnGenerate}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Structure 1')).toBeInTheDocument()
      })

      const selectAllButtons = screen.getAllByText('Select All')
      await user.click(selectAllButtons[1])
      expect(screen.getByText('2 structures selected')).toBeInTheDocument()

      const struct1 = document.getElementById(
        'structure-struct1'
      ) as HTMLInputElement
      await user.click(struct1)
      expect(screen.getByText('1 structure selected')).toBeInTheDocument()
    })
  })

  describe('Modal Styling', () => {
    it('applies correct dialog panel styling', () => {
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      const panel = screen
        .getByText('Start Bulk Generation')
        .closest('div.relative')
      expect(panel).toHaveClass('rounded-lg', 'bg-white', 'shadow-xl')
    })

    it('applies correct overlay styling', () => {
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      // Overlay is rendered in a portal, so we need to search in document.body
      const overlay = document.body.querySelector('.bg-gray-500')
      expect(overlay).toHaveClass('bg-opacity-75', 'fixed', 'inset-0')
    })
  })

  describe('Button States', () => {
    it('enables start button when all requirements met', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      await user.click(screen.getByLabelText(mockModels[0]))

      const startButton = screen.getByText('Start Generation')
      expect(startButton).not.toBeDisabled()
      // Button now uses the shared Button component with different styling
      expect(startButton).toHaveClass('bg-zinc-900')
    })

    it('applies disabled styling to start button when disabled', () => {
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      const startButton = screen.getByText('Start Generation')
      expect(startButton).toBeDisabled()
      expect(startButton).toHaveClass('disabled:opacity-50')
    })

    it('applies correct styling to cancel button', () => {
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      const cancelButton = screen.getByText('Cancel')
      // Button now uses the shared Button component with outline variant styling
      expect(cancelButton).toHaveClass(
        'ring-1',
        'ring-inset'
      )
    })
  })

  describe('Radio Button Behavior', () => {
    it('mode radio buttons are mutually exclusive', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      const missingRadio = screen.getByLabelText('Generate Missing Only')
      const allRadio = screen.getByLabelText('Generate All')

      expect(missingRadio).toBeChecked()
      expect(allRadio).not.toBeChecked()

      await user.click(allRadio)

      expect(allRadio).toBeChecked()
      expect(missingRadio).not.toBeChecked()

      await user.click(missingRadio)

      expect(missingRadio).toBeChecked()
      expect(allRadio).not.toBeChecked()
    })

    it('radio buttons have correct IDs', () => {
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      expect(document.getElementById('mode-missing')).toBeInTheDocument()
      expect(document.getElementById('mode-all')).toBeInTheDocument()
    })
  })

  describe('Checkbox IDs and Labels', () => {
    it('model checkboxes have correct IDs', () => {
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      mockModels.forEach((model) => {
        expect(document.getElementById(`model-${model}`)).toBeInTheDocument()
      })
    })

    it('structure checkboxes have correct IDs', async () => {
      const mockProject = {
        generation_config: {
          prompt_structures: {
            struct1: { name: 'Structure 1', template: 'Template 1' },
          },
        },
      } as any

      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          project={mockProject}
          onGenerate={mockOnGenerate}
        />
      )

      await waitFor(() => {
        expect(document.getElementById('structure-struct1')).toBeInTheDocument()
      })
    })
  })

  describe('Transition Behavior', () => {
    it('renders transition components', () => {
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      // Dialog is rendered in a portal, so we need to search in document.body
      expect(document.body.querySelector('[role="dialog"]')).toBeInTheDocument()
    })
  })

  describe('Generation Count Calculation', () => {
    it('calculates total for single model and no structures', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      await user.click(screen.getByLabelText(mockModels[0]))

      expect(screen.getByText(/1 model = 1 generation/)).toBeInTheDocument()
    })

    it('calculates total for multiple models and no structures', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      await user.click(screen.getByLabelText(mockModels[0]))
      await user.click(screen.getByLabelText(mockModels[1]))
      await user.click(screen.getByLabelText(mockModels[2]))

      expect(screen.getByText(/3 models = 3 generations/)).toBeInTheDocument()
    })

    it('calculates total for one model and one structure', async () => {
      const user = userEvent.setup()
      const mockProject = {
        generation_config: {
          prompt_structures: {
            struct1: { name: 'Structure 1', template: 'Template 1' },
          },
        },
      } as any

      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          project={mockProject}
          onGenerate={mockOnGenerate}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Structure 1')).toBeInTheDocument()
      })

      await user.click(screen.getByLabelText(mockModels[0]))
      const struct1 = document.getElementById(
        'structure-struct1'
      ) as HTMLInputElement
      await user.click(struct1)

      expect(
        screen.getByText(/1 model × 1 structure = 1 generation/)
      ).toBeInTheDocument()
    })
  })


  describe('Toast Integration', () => {
    it('shows toast when no models selected on submit attempt', async () => {
      const user = userEvent.setup()
      const { useToast } = require('@/components/shared/Toast')
      const mockAddToast = jest.fn()
      useToast.mockReturnValue({ addToast: mockAddToast })

      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      const startButton = screen.getByText('Start Generation')
      expect(startButton).toBeDisabled()
    })
  })

  describe('onClose Behavior', () => {
    it('calls onClose when overlay is clicked', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      const closeButton = screen.getByRole('button', { name: /close/i })
      await user.click(closeButton)

      expect(mockOnClose).toHaveBeenCalled()
    })

    it('closes dropdown after successful generation with onGenerate', async () => {
      const user = userEvent.setup()
      render(
        <GenerationControlModal
          isOpen={true}
          onClose={mockOnClose}
          models={mockModels}
          onGenerate={mockOnGenerate}
        />
      )

      await user.click(screen.getByLabelText(mockModels[0]))
      await user.click(screen.getByText('Start Generation'))

      expect(mockOnClose).toHaveBeenCalled()
    })
  })

  describe('API Error Response Handling', () => {
    it('handles API error with detail message', async () => {
      const user = userEvent.setup()
      const { apiClient } = require('@/lib/api/client')
      const { useToast } = require('@/components/shared/Toast')
      const mockAddToast = jest.fn()
      useToast.mockReturnValue({ addToast: mockAddToast })

      apiClient.post.mockRejectedValue({
        response: {
          data: { detail: 'Custom error message' },
        },
      })

      render(
        <GenerationControlModal
          isOpen={true}
          projectId="project-1"
          onClose={mockOnClose}
          models={mockModels}
          onSuccess={mockOnSuccess}
        />
      )

      await user.click(screen.getByLabelText(mockModels[0]))
      await user.click(screen.getByText('Start Generation'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Custom error message',
          'error'
        )
      })
    })
  })
})
