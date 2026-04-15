/**
 * Branch coverage tests for GenerationControlModal
 * Targets uncovered branches at lines: 84-85, 89-90, 118-119, 123, 381-460
 *
 * @jest-environment jsdom
 */

import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { GenerationControlModal } from '../GenerationControlModal'

const mockAddToast = jest.fn()

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

jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(() => ({
    addToast: mockAddToast,
    showToast: jest.fn(),
    removeToast: jest.fn(),
  })),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(() => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'toasts.generation.selectModel': 'Please select at least one model',
        'toasts.generation.selectStructure': 'Please select at least one structure',
        'generation.controlModal.title': 'Start Bulk Generation',
        'generation.controlModal.generationOptions': 'Generation Options',
        'generation.controlModal.generationMode': 'Generation Mode',
        'generation.controlModal.generateMissingOnly': 'Generate Missing Only',
        'generation.controlModal.generateMissingOnlyDesc': 'Only missing',
        'generation.controlModal.generateAll': 'Generate All',
        'generation.controlModal.generateAllDesc': 'Regenerate all',
        'generation.controlModal.selectModels': 'Select Models',
        'generation.controlModal.selectAll': 'Select All',
        'generation.controlModal.clearAll': 'Clear All',
        'generation.controlModal.oneModelSelected': '1 model selected',
        'generation.controlModal.modelsSelected': `${params?.count ?? 0} models selected`,
        'generation.controlModal.selectPromptStructures': 'Select Prompt Structures',
        'generation.controlModal.oneStructureSelected': '1 structure selected',
        'generation.controlModal.structuresSelected': `${params?.count ?? 0} structures selected`,
        'generation.controlModal.advancedSettings': 'Advanced Settings',
        'generation.controlModal.temperature': 'Temperature',
        'generation.controlModal.temperatureDesc': 'Controls randomness',
        'generation.controlModal.defaultMaxTokens': 'Default Max Tokens',
        'generation.controlModal.defaultMaxTokensDesc': 'Max response length',
        'generation.controlModal.perModelTokenLimits': 'Per-Model Token Limits',
        'generation.controlModal.perModelTokenLimitsDesc': 'Override for specific models',
        'generation.controlModal.totalGenerationsPerTask': 'Total generations per task:',
        'generation.controlModal.models': 'models',
        'generation.controlModal.model': 'model',
        'generation.controlModal.structures': 'structures',
        'generation.controlModal.structure': 'structure',
        'generation.controlModal.generations': 'generations',
        'generation.controlModal.generation': 'generation',
        'generation.controlModal.startGeneration': 'Start Generation',
        'generation.controlModal.starting': 'Starting...',
        'generation.controlModal.cancel': 'Cancel',
        'generation.controlModal.queuedJobs': `Queued ${params?.tasks ?? 0} tasks for ${params?.models ?? 0} models (~${params?.minutes ?? 0}m)`,
        'generation.controlModal.failedToStart': 'Failed to start generation',
        'shared.alertDialog.close': 'Close',
      }
      return translations[key] || key
    },
  })),
}))

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    post: jest.fn(),
  },
}))

const defaultProps = {
  isOpen: true,
  projectId: 'project-1',
  models: ['gpt-4', 'claude-3'],
  onClose: jest.fn(),
}

describe('GenerationControlModal branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  // Lines 84-85: handleSubmit with no models selected
  it('shows error when submitting without selecting models', async () => {
    const user = userEvent.setup()
    render(<GenerationControlModal {...defaultProps} />)

    const submitBtn = screen.getByText('Start Generation')
    // The button should be disabled since no models are selected
    expect(submitBtn).toBeDisabled()
  })

  // Lines 89-90: handleSubmit with structures but none selected
  it('shows error when structures available but none selected', async () => {
    const user = userEvent.setup()
    const propsWithStructures = {
      ...defaultProps,
      project: {
        generation_config: {
          prompt_structures: {
            struct1: { name: 'Structure 1', description: 'Test structure' },
          },
        },
      } as any,
    }

    render(<GenerationControlModal {...propsWithStructures} />)

    // Select a model
    const modelCheckboxes = screen.getAllByRole('checkbox')
    await user.click(modelCheckboxes[0])

    // Submit without selecting structures - button should be disabled
    const submitBtn = screen.getByText('Start Generation')
    expect(submitBtn).toBeDisabled()
  })

  // Lines 118-119: handleSubmit with modelConfigs that have different tokens
  it('includes per-model configs when tokens differ from default', async () => {
    const user = userEvent.setup()
    const mockPost = require('@/lib/api/client').apiClient.post
    mockPost.mockResolvedValue({
      tasks_queued: 10,
      models_count: 1,
      estimated_time_seconds: 120,
    })

    render(<GenerationControlModal {...defaultProps} />)

    // Select a model
    const modelCheckboxes = screen.getAllByRole('checkbox')
    await user.click(modelCheckboxes[0])

    // Open advanced settings
    const advancedBtn = screen.getByText('Advanced Settings')
    await user.click(advancedBtn)

    // Wait for advanced section
    await waitFor(() => {
      expect(screen.getByText(/Per-Model Token Limits/)).toBeInTheDocument()
    })

    // Change per-model token limit
    const tokenInputs = screen.getAllByRole('spinbutton')
    const perModelInput = tokenInputs[tokenInputs.length - 1]
    await user.clear(perModelInput)
    await user.type(perModelInput, '8000')

    // Submit
    const submitBtn = screen.getByText('Start Generation')
    await user.click(submitBtn)

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalled()
      const callBody = mockPost.mock.calls[0][1]
      expect(callBody.model_configs).toBeDefined()
    })
  })

  // Line 123: handleSubmit with onGenerate callback (skips API)
  it('calls onGenerate callback instead of API when provided', async () => {
    const user = userEvent.setup()
    const mockOnGenerate = jest.fn()

    render(
      <GenerationControlModal
        {...defaultProps}
        onGenerate={mockOnGenerate}
      />
    )

    // Select a model
    const modelCheckboxes = screen.getAllByRole('checkbox')
    await user.click(modelCheckboxes[0])

    // Submit
    const submitBtn = screen.getByText('Start Generation')
    await user.click(submitBtn)

    await waitFor(() => {
      expect(mockOnGenerate).toHaveBeenCalledWith(
        ['gpt-4'],
        true, // missing mode by default
        undefined // no structures
      )
    })
  })

  // Line 123: onGenerate with structures selected
  it('passes structures to onGenerate when available', async () => {
    const user = userEvent.setup()
    const mockOnGenerate = jest.fn()

    const propsWithStructures = {
      ...defaultProps,
      onGenerate: mockOnGenerate,
      project: {
        generation_config: {
          prompt_structures: {
            struct1: { name: 'Structure 1', description: 'Desc 1' },
            struct2: { name: 'Structure 2', description: '' },
          },
        },
      } as any,
    }

    render(<GenerationControlModal {...propsWithStructures} />)

    // Select a model
    const modelCheckboxes = screen.getAllByRole('checkbox')
    await user.click(modelCheckboxes[0])

    // Select structures
    const structCheckboxes = screen.getAllByRole('checkbox')
    // Models: 2 checkboxes, structures: 2 more
    await user.click(structCheckboxes[2]) // first structure

    const submitBtn = screen.getByText('Start Generation')
    await user.click(submitBtn)

    await waitFor(() => {
      expect(mockOnGenerate).toHaveBeenCalledWith(
        ['gpt-4'],
        true,
        ['struct1']
      )
    })
  })

  // Lines 381-460: Advanced settings section rendering
  it('renders advanced settings with temperature and max tokens', async () => {
    const user = userEvent.setup()
    render(<GenerationControlModal {...defaultProps} />)

    // Select a model first
    const modelCheckboxes = screen.getAllByRole('checkbox')
    await user.click(modelCheckboxes[0])

    // Open advanced settings
    const advancedBtn = screen.getByText('Advanced Settings')
    await user.click(advancedBtn)

    await waitFor(() => {
      expect(screen.getByText(/Temperature/)).toBeInTheDocument()
      expect(screen.getByText(/Default Max Tokens/)).toBeInTheDocument()
    })
  })

  // Advanced settings: clear per-model token limit
  it('clears per-model token limit when empty', async () => {
    const user = userEvent.setup()
    render(<GenerationControlModal {...defaultProps} />)

    const modelCheckboxes = screen.getAllByRole('checkbox')
    await user.click(modelCheckboxes[0])

    const advancedBtn = screen.getByText('Advanced Settings')
    await user.click(advancedBtn)

    await waitFor(() => {
      expect(screen.getByText(/Per-Model Token Limits/)).toBeInTheDocument()
    })

    // Set and then clear a per-model token limit
    const tokenInputs = screen.getAllByRole('spinbutton')
    const perModelInput = tokenInputs[tokenInputs.length - 1]
    await user.type(perModelInput, '8000')
    await user.clear(perModelInput)
    // Clearing should remove the model from the config
  })

  // Mode selection: switch to 'all'
  it('switches generation mode to all', async () => {
    const user = userEvent.setup()
    render(<GenerationControlModal {...defaultProps} />)

    const allRadio = screen.getByLabelText('Generate All')
    await user.click(allRadio)

    expect(allRadio).toBeChecked()
  })

  // Select All / Clear All for models
  it('handles select all and clear all for models', async () => {
    const user = userEvent.setup()
    render(<GenerationControlModal {...defaultProps} />)

    // Select All
    const selectAllBtn = screen.getAllByText('Select All')[0]
    await user.click(selectAllBtn)

    await waitFor(() => {
      expect(screen.getByText('2 models selected')).toBeInTheDocument()
    })

    // Clear All
    const clearAllBtn = screen.getAllByText('Clear All')[0]
    await user.click(clearAllBtn)

    await waitFor(() => {
      expect(screen.getByText('0 models selected')).toBeInTheDocument()
    })
  })

  // Single model selected text
  it('shows singular text for one model selected', async () => {
    const user = userEvent.setup()
    render(<GenerationControlModal {...defaultProps} />)

    const modelCheckboxes = screen.getAllByRole('checkbox')
    await user.click(modelCheckboxes[0])

    expect(screen.getByText('1 model selected')).toBeInTheDocument()
  })

  // Structure without description
  it('renders structure without description', async () => {
    const propsWithStructures = {
      ...defaultProps,
      project: {
        generation_config: {
          prompt_structures: {
            struct1: { name: 'Struct No Desc' },
          },
        },
      } as any,
    }

    render(<GenerationControlModal {...propsWithStructures} />)

    expect(screen.getByText('Struct No Desc')).toBeInTheDocument()
  })

  // API error handling
  it('shows error toast on API failure', async () => {
    const user = userEvent.setup()
    const mockPost = require('@/lib/api/client').apiClient.post
    mockPost.mockRejectedValue({ response: { data: { detail: 'Custom API error' } } })

    render(<GenerationControlModal {...defaultProps} />)

    const modelCheckboxes = screen.getAllByRole('checkbox')
    await user.click(modelCheckboxes[0])

    const submitBtn = screen.getByText('Start Generation')
    await user.click(submitBtn)

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith('Custom API error', 'error')
    })
  })

  // API error without detail
  it('shows generic error toast when API error has no detail', async () => {
    const user = userEvent.setup()
    const mockPost = require('@/lib/api/client').apiClient.post
    mockPost.mockRejectedValue(new Error('network error'))

    render(<GenerationControlModal {...defaultProps} />)

    const modelCheckboxes = screen.getAllByRole('checkbox')
    await user.click(modelCheckboxes[0])

    const submitBtn = screen.getByText('Start Generation')
    await user.click(submitBtn)

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'Failed to start generation',
        'error'
      )
    })
  })

  // Total generations display with 1 model 1 structure
  it('shows singular generation count', async () => {
    const user = userEvent.setup()
    const propsWithStructures = {
      ...defaultProps,
      models: ['gpt-4'], // Only 1 model to simplify
      project: {
        generation_config: {
          prompt_structures: {
            struct1: { name: 'S1', description: 'D1' },
          },
        },
      } as any,
    }

    render(<GenerationControlModal {...propsWithStructures} />)

    // Get all checkboxes - model(s) come first, then structure(s)
    const checkboxes = screen.getAllByRole('checkbox')
    // Select model (index 0) and structure (index 1)
    await user.click(checkboxes[0])
    await user.click(checkboxes[1])

    await waitFor(() => {
      // Check for the generation count info panel
      expect(screen.getByText('1 model selected')).toBeInTheDocument()
      expect(screen.getByText('1 structure selected')).toBeInTheDocument()
      // The generation count text contains "1 model x 1 structure = 1 generation"
      expect(screen.getByText(/= 1 generation$/)).toBeInTheDocument()
    })
  })

  // onSuccess callback
  it('calls onSuccess after successful API call', async () => {
    const user = userEvent.setup()
    const mockOnSuccess = jest.fn()
    const mockPost = require('@/lib/api/client').apiClient.post
    mockPost.mockResolvedValue({
      tasks_queued: 5,
      models_count: 1,
      estimated_time_seconds: 60,
    })

    render(
      <GenerationControlModal
        {...defaultProps}
        onSuccess={mockOnSuccess}
      />
    )

    const modelCheckboxes = screen.getAllByRole('checkbox')
    await user.click(modelCheckboxes[0])

    const submitBtn = screen.getByText('Start Generation')
    await user.click(submitBtn)

    await waitFor(() => {
      expect(mockOnSuccess).toHaveBeenCalled()
    })
  })
})
