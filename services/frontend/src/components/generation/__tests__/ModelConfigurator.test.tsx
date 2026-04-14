/**
 * @jest-environment jsdom
 */

import { Project } from '@/types/labelStudio'
import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ModelConfigurator } from '../ModelConfigurator'

// Mock available models returned by the API
const mockAvailableModels = [
  {
    id: 'gpt-5',
    name: 'GPT-5',
    description: 'Flagship model with PhD-level intelligence',
    provider: 'OpenAI',
    model_type: 'chat',
    capabilities: ['chat', 'json_mode'],
    config_schema: null,
    default_config: null,
    is_active: true,
    created_at: null,
    updated_at: null,
  },
  {
    id: 'claude-opus-4-6',
    name: 'Claude Opus 4.6',
    description: 'Latest flagship Claude model',
    provider: 'Anthropic',
    model_type: 'chat',
    capabilities: ['chat', 'thinking'],
    config_schema: null,
    default_config: {
      reasoning_config: {
        parameter: 'thinking_budget',
        type: 'number',
        min: 1024,
        max: 128000,
        default: 10000,
        label: 'generation.configurator.thinkingBudget',
      },
    },
    is_active: true,
    created_at: null,
    updated_at: null,
  },
  {
    id: 'gemini-2.5-pro',
    name: 'Gemini 2.5 Pro',
    description: 'State-of-the-art thinking model',
    provider: 'Google',
    model_type: 'chat',
    capabilities: ['chat', 'thinking'],
    config_schema: null,
    default_config: {
      reasoning_config: {
        parameter: 'thinking_budget',
        type: 'number',
        min: 0,
        max: 24576,
        default: 1024,
        label: 'generation.configurator.thinkingBudget',
      },
    },
    is_active: true,
    created_at: null,
    updated_at: null,
  },
  {
    id: 'deepseek-ai/DeepSeek-V3.1',
    name: 'DeepSeek-V3.1',
    description: '671B params MoE model',
    provider: 'DeepInfra',
    model_type: 'chat',
    capabilities: ['chat'],
    config_schema: null,
    default_config: null,
    is_active: true,
    created_at: null,
    updated_at: null,
  },
]

// Mock the api module
const mockGetAvailableModels = jest.fn()
jest.mock('@/lib/api', () => ({
  api: {
    getAvailableModels: (...args: any[]) => mockGetAvailableModels(...args),
  },
}))

// Mock the API client module (used for saving config)
jest.mock('@/lib/api/client', () => ({
  apiClient: {
    put: jest.fn(),
  },
}))

// Mock the toast hook
const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: mockAddToast,
  }),
}))

// Mock i18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(() => ({
    t: (key: string, arg2?: any, arg3?: any) => {
      const vars = typeof arg2 === 'object' ? arg2 : arg3
      const translations: Record<string, string> = {
        'toasts.generation.selectModel': 'Please select at least one model',
        'toasts.generation.configSaved': 'Configuration saved successfully',
        'toasts.error.saveFailed': 'Failed to save',
        'generation.configurator.selectModels': 'Select Models',
        'generation.configurator.loadingModels': 'Loading available models...',
        'generation.configurator.noModelsAvailable': 'No models available. Configure API keys in your profile settings to enable models.',
        'generation.configurator.noModelsHint': 'Select one or more models to generate responses',
        'generation.configurator.prompts': 'Prompts',
        'generation.configurator.systemPrompt': 'System Prompt',
        'generation.configurator.instructionPrompt': 'Instruction Prompt',
        'generation.configurator.advancedSettings': 'Advanced Settings',
        'generation.configurator.temperature': 'Temperature',
        'generation.configurator.maxTokens': 'Max Tokens',
        'generation.configurator.batchSize': 'Batch Size',
        'generation.configurator.presentationMode': 'Presentation Mode',
        'generation.configurator.autoDetect': 'Auto-detect',
        'generation.configurator.useLabelConfig': 'Use Label Config',
        'generation.configurator.templateMode': 'Template Mode',
        'generation.configurator.rawJson': 'Raw JSON',
        'generation.configurator.saving': 'Saving...',
        'generation.configurator.saveConfiguration': 'Save Configuration',
        'generation.configurator.startGeneration': 'Start Generation',
        'generation.configurator.thinkingBudget': 'Thinking Budget',
        'generation.thinkingCapable': 'Thinking',
        'generation.maxTokens': 'Max Tokens',
        'generation.defaultLabel': 'Default',
        'generation.enabled': 'Enabled',
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

describe('ModelConfigurator', () => {
  const mockOnConfigUpdate = jest.fn()
  const mockOnStartGeneration = jest.fn()

  const mockProject: Project = {
    id: 'project-123',
    title: 'Test Project',
    description: 'Test Description',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
    created_by_id: 'user-1',
    tasks_count: 10,
    completed_tasks_count: 0,
    total_annotations_count: 0,
    label_config: '<View></View>',
    expert_instruction: '',
    show_instruction: false,
    show_skip_button: false,
    enable_empty_annotation: false,
    show_annotation_history: false,
    organization_id: 'org-1',
    is_published: false,
    is_visible_to_all: false,
    llm_model_ids: [],
    generation_config: null,
  }

  const defaultProps = {
    project: mockProject,
    onConfigUpdate: mockOnConfigUpdate,
    onStartGeneration: mockOnStartGeneration,
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockGetAvailableModels.mockResolvedValue(mockAvailableModels)
  })

  describe('Component Rendering', () => {
    it('renders all main sections', async () => {
      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('Select Models')).toBeInTheDocument()
        expect(screen.getByText('Prompts')).toBeInTheDocument()
        expect(screen.getByText('Advanced Settings')).toBeInTheDocument()
      })
    })

    it('displays action buttons', async () => {
      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /Save Configuration/i })
        ).toBeInTheDocument()
        expect(
          screen.getByRole('button', { name: /Start Generation/i })
        ).toBeInTheDocument()
      })
    })

    it('renders models from API response', async () => {
      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('GPT-5')).toBeInTheDocument()
        expect(screen.getByText('Claude Opus 4.6')).toBeInTheDocument()
        expect(screen.getByText('Gemini 2.5 Pro')).toBeInTheDocument()
        expect(screen.getByText('DeepSeek-V3.1')).toBeInTheDocument()
      })
    })

    it('shows loading state while fetching models', async () => {
      mockGetAvailableModels.mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(mockAvailableModels), 100))
      )

      render(<ModelConfigurator {...defaultProps} />)

      expect(screen.getByText('Loading available models...')).toBeInTheDocument()

      await waitFor(() => {
        expect(screen.getByText('GPT-5')).toBeInTheDocument()
      })
    })

    it('shows empty state when no models available', async () => {
      mockGetAvailableModels.mockResolvedValue([])

      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(
          screen.getByText(/No models available/)
        ).toBeInTheDocument()
      })
    })

    it('shows provider badges', async () => {
      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument()
        expect(screen.getByText('Anthropic')).toBeInTheDocument()
        expect(screen.getByText('Google')).toBeInTheDocument()
        expect(screen.getByText('DeepInfra')).toBeInTheDocument()
      })
    })
  })

  describe('Model Selection', () => {
    it('allows selecting a model', async () => {
      const user = userEvent.setup()

      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('GPT-5')).toBeInTheDocument()
      })

      const gptModelTitle = screen.getByText('GPT-5')
      const gptModel = gptModelTitle.closest('div[class*="rounded-lg border"]')
      await user.click(gptModel!)

      expect(gptModel).toHaveClass('bg-emerald-50')
    })

    it('allows selecting multiple models', async () => {
      const user = userEvent.setup()

      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('GPT-5')).toBeInTheDocument()
      })

      const gptModel = screen
        .getByText('GPT-5')
        .closest('div[class*="rounded-lg border"]')
      const claudeModel = screen
        .getByText('Claude Opus 4.6')
        .closest('div[class*="rounded-lg border"]')

      await user.click(gptModel!)
      await user.click(claudeModel!)

      expect(gptModel).toHaveClass('bg-emerald-50')
      expect(claudeModel).toHaveClass('bg-emerald-50')
    })

    it('allows deselecting a model', async () => {
      const user = userEvent.setup()

      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('GPT-5')).toBeInTheDocument()
      })

      const gptModel = screen
        .getByText('GPT-5')
        .closest('div[class*="rounded-lg border"]')

      await user.click(gptModel!)
      expect(gptModel).toHaveClass('bg-emerald-50')

      await user.click(gptModel!)
      expect(gptModel).not.toHaveClass('bg-emerald-50')
    })

    it('shows empty state message when no models selected', async () => {
      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(
          screen.getByText('Select one or more models to generate responses')
        ).toBeInTheDocument()
      })
    })

    it('all models are clickable (no disabled state)', async () => {
      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        const gptModel = screen
          .getByText('GPT-5')
          .closest('div[class*="rounded-lg border"]')
        expect(gptModel).toHaveClass('cursor-pointer')
        expect(gptModel).not.toHaveClass('cursor-not-allowed')
      })
    })
  })

  describe('API Integration', () => {
    it('fetches available models on mount', async () => {
      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(mockGetAvailableModels).toHaveBeenCalledTimes(1)
      })
    })

    it('handles API fetch failure gracefully', async () => {
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      mockGetAvailableModels.mockRejectedValue(new Error('API Error'))

      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Failed to fetch available models:',
          expect.any(Error)
        )
      })

      // Should show empty state after error
      expect(
        screen.getByText(/No models available/)
      ).toBeInTheDocument()

      consoleErrorSpy.mockRestore()
    })
  })

  describe('Reasoning Config', () => {
    it('shows thinking badge for models with reasoning config', async () => {
      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        // Claude Opus 4.6 has reasoning config from backend default_config
        // Gemini 2.5 Pro has reasoning config from backend default_config
        const thinkingBadges = screen.getAllByText('Thinking')
        expect(thinkingBadges.length).toBeGreaterThanOrEqual(2)
      })
    })

    it('uses backend reasoning config when available', async () => {
      const user = userEvent.setup()

      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('Claude Opus 4.6')).toBeInTheDocument()
      })

      // Select Claude to show per-model settings
      const claudeModel = screen
        .getByText('Claude Opus 4.6')
        .closest('div[class*="rounded-lg border"]')
      await user.click(claudeModel!)

      // Should show thinking budget config from backend default_config
      await waitFor(() => {
        expect(screen.getByText('Thinking Budget')).toBeInTheDocument()
      })
    })
  })

  describe('Prompt Configuration', () => {
    it('allows editing system prompt', async () => {
      const user = userEvent.setup()
      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByLabelText('System Prompt')).toBeInTheDocument()
      })

      const systemPromptInput = screen.getByLabelText('System Prompt')
      await user.clear(systemPromptInput)
      await user.type(systemPromptInput, 'Custom system prompt')

      expect(systemPromptInput).toHaveValue('Custom system prompt')
    })

    it('allows editing instruction prompt', async () => {
      const user = userEvent.setup()
      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByLabelText('Instruction Prompt')).toBeInTheDocument()
      })

      const instructionPromptInput = screen.getByLabelText('Instruction Prompt')
      await user.clear(instructionPromptInput)
      await user.type(instructionPromptInput, 'Custom instruction prompt')

      expect(instructionPromptInput).toHaveValue('Custom instruction prompt')
    })
  })

  describe('Advanced Settings', () => {
    it('toggles advanced settings visibility', async () => {
      const user = userEvent.setup()
      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('Advanced Settings')).toBeInTheDocument()
      })

      expect(screen.queryByLabelText(/Temperature/i)).not.toBeInTheDocument()

      const advancedButton = screen
        .getByText('Advanced Settings')
        .closest('button')
      await user.click(advancedButton!)

      expect(screen.getByLabelText(/Temperature/i)).toBeInTheDocument()
    })

    it('allows adjusting temperature', async () => {
      const user = userEvent.setup()
      render(<ModelConfigurator {...defaultProps} />)

      const advancedButton = screen
        .getByText('Advanced Settings')
        .closest('button')
      await user.click(advancedButton!)

      await waitFor(() => {
        expect(screen.getByLabelText(/Temperature: 0/i)).toBeInTheDocument()
      })

      const temperatureSlider = screen.getByLabelText(
        /Temperature: 0/i
      ) as HTMLInputElement

      fireEvent.change(temperatureSlider, { target: { value: '1.5' } })

      await waitFor(() => {
        expect(screen.getByLabelText(/Temperature: 1.5/i)).toBeInTheDocument()
      })
    })

    it('shows all presentation mode options', async () => {
      const user = userEvent.setup()
      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        const advancedButton = screen
          .getByText('Advanced Settings')
          .closest('button')
        return user.click(advancedButton!)
      })

      expect(
        screen.getByRole('option', { name: 'Auto-detect' })
      ).toBeInTheDocument()
      expect(
        screen.getByRole('option', { name: 'Use Label Config' })
      ).toBeInTheDocument()
      expect(
        screen.getByRole('option', { name: 'Template Mode' })
      ).toBeInTheDocument()
      expect(
        screen.getByRole('option', { name: 'Raw JSON' })
      ).toBeInTheDocument()
    })
  })

  describe('Configuration Saving', () => {
    it('saves configuration successfully', async () => {
      const user = userEvent.setup()
      const { apiClient } = require('@/lib/api/client')
      apiClient.put.mockResolvedValue({ data: {} })

      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('GPT-5')).toBeInTheDocument()
      })

      const gptModel = screen.getByText('GPT-5').closest('div')
      await user.click(gptModel!)

      const saveButton = screen.getByRole('button', {
        name: /Save Configuration/i,
      })
      await user.click(saveButton)

      await waitFor(() => {
        expect(apiClient.put).toHaveBeenCalledWith(
          '/projects/project-123/generation-config',
          expect.objectContaining({
            selected_configuration: expect.objectContaining({
              models: ['gpt-5'],
            }),
          })
        )
      })

      expect(mockAddToast).toHaveBeenCalledWith(
        'Configuration saved successfully',
        'success'
      )
      expect(mockOnConfigUpdate).toHaveBeenCalled()
    })

    it('disables save button when no models selected', async () => {
      render(<ModelConfigurator {...defaultProps} />)

      const saveButton = screen.getByRole('button', {
        name: /Save Configuration/i,
      })

      expect(saveButton).toBeDisabled()
    })

    it('handles API errors during save', async () => {
      const user = userEvent.setup()
      const { apiClient } = require('@/lib/api/client')
      apiClient.put.mockRejectedValue({
        response: {
          data: {
            detail: 'Save failed',
          },
        },
      })

      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('GPT-5')).toBeInTheDocument()
      })

      const gptModel = screen.getByText('GPT-5').closest('div')
      await user.click(gptModel!)

      const saveButton = screen.getByRole('button', {
        name: /Save Configuration/i,
      })
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith('Save failed', 'error')
      })
    })

    it('disables save button while saving', async () => {
      const user = userEvent.setup()
      const { apiClient } = require('@/lib/api/client')
      apiClient.put.mockImplementation(
        () =>
          new Promise((resolve) => setTimeout(() => resolve({ data: {} }), 100))
      )

      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('GPT-5')).toBeInTheDocument()
      })

      const gptModel = screen.getByText('GPT-5').closest('div')
      await user.click(gptModel!)

      const saveButton = screen.getByRole('button', {
        name: /Save Configuration/i,
      })
      await user.click(saveButton)

      expect(saveButton).toBeDisabled()
      expect(screen.getByText('Saving...')).toBeInTheDocument()
    })
  })

  describe('Start Generation', () => {
    it('allows starting generation with selected models', async () => {
      const user = userEvent.setup()

      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('GPT-5')).toBeInTheDocument()
      })

      const gptModel = screen.getByText('GPT-5').closest('div')
      await user.click(gptModel!)

      const startButton = screen.getByRole('button', {
        name: /Start Generation/i,
      })
      expect(startButton).not.toBeDisabled()

      await user.click(startButton)

      expect(mockOnStartGeneration).toHaveBeenCalled()
    })

    it('disables start generation when no models selected', async () => {
      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        const startButton = screen.getByRole('button', {
          name: /Start Generation/i,
        })
        expect(startButton).toBeDisabled()
      })
    })
  })

  describe('Existing Configuration Loading', () => {
    it('loads existing configuration from project', async () => {
      const projectWithConfig: Project = {
        ...mockProject,
        generation_config: {
          detected_data_types: [],
          available_options: {
            models: {},
            presentation_modes: [],
          },
          selected_configuration: {
            models: ['gpt-5', 'claude-opus-4-6'],
            prompts: {
              system: 'Custom system prompt',
              instruction: 'Custom instruction prompt',
            },
            parameters: {
              temperature: 0.7,
              max_tokens: 2000,
              batch_size: 20,
            },
            presentation_mode: 'template',
            field_mappings: {},
            model_configs: {},
          },
          last_updated: '2025-01-01T00:00:00Z',
        },
      }

      render(
        <ModelConfigurator {...defaultProps} project={projectWithConfig} />
      )

      await waitFor(() => {
        const systemPromptInput = screen.getByLabelText('System Prompt')
        expect(systemPromptInput).toHaveValue('Custom system prompt')

        const instructionPromptInput =
          screen.getByLabelText('Instruction Prompt')
        expect(instructionPromptInput).toHaveValue('Custom instruction prompt')
      })
    })

    it('loads models from llm_model_ids when no config exists', async () => {
      const projectWithModelIds: Project = {
        ...mockProject,
        llm_model_ids: ['gpt-5', 'claude-opus-4-6'],
      }

      render(
        <ModelConfigurator {...defaultProps} project={projectWithModelIds} />
      )

      await waitFor(() => {
        const systemPromptInput = screen.getByLabelText('System Prompt')
        expect(systemPromptInput).toHaveValue(
          'You are an expert annotator. Follow the instructions carefully.'
        )
      })
    })
  })

  describe('Accessibility', () => {
    it('has accessible form labels', async () => {
      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByLabelText('System Prompt')).toBeInTheDocument()
        expect(screen.getByLabelText('Instruction Prompt')).toBeInTheDocument()
      })
    })

    it('has accessible buttons', async () => {
      render(<ModelConfigurator {...defaultProps} />)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /Save Configuration/i })
        ).toBeInTheDocument()
        expect(
          screen.getByRole('button', { name: /Start Generation/i })
        ).toBeInTheDocument()
      })
    })
  })
})
