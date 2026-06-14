/**
 * Behavioral tests for the StepModels wizard step.
 *
 * Covers uncovered branches: loading state, NO_API_KEYS error card, model
 * selection / deselection (with per-model config cleanup), the expand/collapse
 * config panel, per-model temperature + max_tokens edits, the collapsible
 * default-generation-parameters panel (temperature slider, max_tokens, batch
 * size, seed), and provider grouping.
 *
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import { StepModels } from '../StepModels'
import { GenerationParameters, ModelConfig } from '../types'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      if (params && typeof params === 'object') {
        return `${key} ${JSON.stringify(params)}`
      }
      return key
    },
    locale: 'en',
  }),
}))

// useModels is mocked so we control loading / error / models per test.
jest.mock('@/hooks/useModels', () => ({
  useModels: jest.fn(),
}))

import { useModels } from '@/hooks/useModels'

const mockUseModels = useModels as jest.MockedFunction<typeof useModels>

const MODELS = [
  {
    id: 'gpt-4',
    name: 'GPT-4',
    description: 'OpenAI flagship',
    provider: 'openai',
    model_type: 'chat',
    capabilities: [],
    is_active: true,
    created_at: null,
  },
  {
    id: 'claude-3',
    name: 'Claude 3',
    description: 'Anthropic model',
    provider: 'anthropic',
    model_type: 'chat',
    capabilities: [],
    is_active: true,
    created_at: null,
  },
]

function setModels(
  overrides: Partial<ReturnType<typeof useModels>> = {}
): void {
  mockUseModels.mockReturnValue({
    models: MODELS as any,
    loading: false,
    error: null,
    refetch: jest.fn(),
    hasApiKeys: true,
    apiKeyStatus: null,
    ...overrides,
  })
}

const DEFAULT_GEN_PARAMS: GenerationParameters = {
  temperature: 0.7,
  max_tokens: 4096,
  batch_size: 10,
  seed: 42,
}

function renderStep({
  selectedModelIds = [],
  modelConfigs = {},
  generationParameters = DEFAULT_GEN_PARAMS,
}: {
  selectedModelIds?: string[]
  modelConfigs?: Record<string, ModelConfig>
  generationParameters?: GenerationParameters
} = {}) {
  const onSelectedModelsChange = jest.fn()
  const onModelConfigsChange = jest.fn()
  const onGenerationParametersChange = jest.fn()
  const utils = render(
    <StepModels
      selectedModelIds={selectedModelIds}
      modelConfigs={modelConfigs}
      generationParameters={generationParameters}
      onSelectedModelsChange={onSelectedModelsChange}
      onModelConfigsChange={onModelConfigsChange}
      onGenerationParametersChange={onGenerationParametersChange}
    />
  )
  return {
    onSelectedModelsChange,
    onModelConfigsChange,
    onGenerationParametersChange,
    ...utils,
  }
}

describe('StepModels', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    setModels()
  })

  describe('async states', () => {
    it('shows the loading message while models load', () => {
      setModels({ models: [] as any, loading: true })
      renderStep()
      expect(
        screen.getByText('projects.creation.wizard.step5.loading')
      ).toBeInTheDocument()
    })

    it('shows the no-API-keys card when error type is NO_API_KEYS', () => {
      setModels({
        models: [] as any,
        loading: false,
        error: { type: 'NO_API_KEYS', message: 'none' } as any,
      })
      renderStep()
      expect(
        screen.getByText('projects.creation.wizard.step5.noApiKeys')
      ).toBeInTheDocument()
    })

    it('does not render the model list when there are zero models', () => {
      setModels({ models: [] as any })
      renderStep()
      expect(screen.queryByTestId('wizard-model-gpt-4')).not.toBeInTheDocument()
    })
  })

  describe('model selection', () => {
    it('renders models grouped by provider', () => {
      renderStep()
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
      expect(screen.getByText('Claude 3')).toBeInTheDocument()
      // Provider chips (capitalized via CSS, raw text in DOM)
      expect(screen.getByText('openai')).toBeInTheDocument()
      expect(screen.getByText('anthropic')).toBeInTheDocument()
    })

    it('adds a model to the selection on check', () => {
      const { onSelectedModelsChange } = renderStep({ selectedModelIds: [] })
      fireEvent.click(screen.getByTestId('wizard-model-gpt-4'))
      expect(onSelectedModelsChange).toHaveBeenCalledWith(['gpt-4'])
    })

    it('removes a model and clears its config on uncheck', () => {
      const { onSelectedModelsChange, onModelConfigsChange } = renderStep({
        selectedModelIds: ['gpt-4'],
        modelConfigs: { 'gpt-4': { temperature: 0.5 } },
      })
      fireEvent.click(screen.getByTestId('wizard-model-gpt-4'))
      expect(onSelectedModelsChange).toHaveBeenCalledWith([])
      // The model's config entry is deleted
      expect(onModelConfigsChange).toHaveBeenCalledWith({})
    })
  })

  // The expand chevron is the only type="button" inside a selected model's
  // controls cluster (the checkbox's immediate parent div).
  function expandModel(modelId: string) {
    const checkbox = screen.getByTestId(`wizard-model-${modelId}`)
    const controls = checkbox.closest('div')! // flex items-center gap-2
    const expandBtn = controls.querySelector(
      'button[type="button"]'
    ) as HTMLButtonElement
    fireEvent.click(expandBtn)
  }

  describe('per-model config panel', () => {
    it('expands the config panel for a selected model and edits temperature', () => {
      const { onModelConfigsChange } = renderStep({
        selectedModelIds: ['gpt-4'],
      })

      // Expand toggle (chevron) only renders for a selected model
      expandModel('gpt-4')

      // Temperature input now visible
      const tempLabel = screen.getByText(
        'projects.creation.wizard.step5.temperature'
      )
      const tempInput = tempLabel.parentElement!.querySelector(
        'input[type="number"]'
      ) as HTMLInputElement
      fireEvent.change(tempInput, { target: { value: '0.9' } })

      expect(onModelConfigsChange).toHaveBeenCalledWith({
        'gpt-4': { temperature: 0.9 },
      })
    })

    it('clears a per-model field when its input is emptied', () => {
      const { onModelConfigsChange } = renderStep({
        selectedModelIds: ['gpt-4'],
        modelConfigs: { 'gpt-4': { temperature: 0.9 } },
      })

      expandModel('gpt-4')

      const tempLabel = screen.getByText(
        'projects.creation.wizard.step5.temperature'
      )
      const tempInput = tempLabel.parentElement!.querySelector(
        'input[type="number"]'
      ) as HTMLInputElement
      fireEvent.change(tempInput, { target: { value: '' } })

      expect(onModelConfigsChange).toHaveBeenCalledWith({
        'gpt-4': { temperature: undefined },
      })
    })
  })

  describe('default generation parameters', () => {
    it('toggles the default-params panel and edits max_tokens, batch size and seed', () => {
      const { onGenerationParametersChange } = renderStep({
        generationParameters: DEFAULT_GEN_PARAMS,
      })

      // The default-params section is collapsed initially; expand it
      fireEvent.click(
        screen.getByText('projects.creation.wizard.step5.defaultParams')
      )

      // max_tokens
      const maxTokensInput = screen.getByDisplayValue('4096') as HTMLInputElement
      fireEvent.change(maxTokensInput, { target: { value: '8192' } })
      expect(onGenerationParametersChange).toHaveBeenCalledWith(
        expect.objectContaining({ max_tokens: 8192 })
      )

      // batch size
      const batchInput = screen.getByDisplayValue('10') as HTMLInputElement
      fireEvent.change(batchInput, { target: { value: '25' } })
      expect(onGenerationParametersChange).toHaveBeenCalledWith(
        expect.objectContaining({ batch_size: 25 })
      )

      // seed
      const seedInput = screen.getByDisplayValue('42') as HTMLInputElement
      fireEvent.change(seedInput, { target: { value: '7' } })
      expect(onGenerationParametersChange).toHaveBeenCalledWith(
        expect.objectContaining({ seed: 7 })
      )
    })

    it('falls back to defaults when numeric inputs are cleared', () => {
      const { onGenerationParametersChange } = renderStep()
      fireEvent.click(
        screen.getByText('projects.creation.wizard.step5.defaultParams')
      )

      const maxTokensInput = screen.getByDisplayValue('4096') as HTMLInputElement
      fireEvent.change(maxTokensInput, { target: { value: '' } })
      // parseInt('') || 4096 -> 4096
      expect(onGenerationParametersChange).toHaveBeenCalledWith(
        expect.objectContaining({ max_tokens: 4096 })
      )
    })

    it('updates temperature via the range slider', () => {
      const { onGenerationParametersChange } = renderStep()
      fireEvent.click(
        screen.getByText('projects.creation.wizard.step5.defaultParams')
      )

      const slider = document.querySelector(
        'input[type="range"]'
      ) as HTMLInputElement
      fireEvent.change(slider, { target: { value: '1.5' } })
      expect(onGenerationParametersChange).toHaveBeenCalledWith(
        expect.objectContaining({ temperature: 1.5 })
      )
    })
  })
})
