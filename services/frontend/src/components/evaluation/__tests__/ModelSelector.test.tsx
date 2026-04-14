/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ModelSelector } from '../ModelSelector'

// Mock available models returned by the API
const mockAvailableModels = [
  {
    id: 'gpt-5',
    name: 'GPT-5',
    description: 'Flagship model',
    provider: 'OpenAI',
    model_type: 'chat',
    capabilities: ['chat'],
    is_active: true,
  },
  {
    id: 'claude-opus-4-6',
    name: 'Claude Opus 4.6',
    description: 'Latest Claude model',
    provider: 'Anthropic',
    model_type: 'chat',
    capabilities: ['chat', 'thinking'],
    is_active: true,
  },
  {
    id: 'gemini-2.5-pro',
    name: 'Gemini 2.5 Pro',
    description: 'State-of-the-art thinking model',
    provider: 'Google',
    model_type: 'chat',
    capabilities: ['chat', 'thinking'],
    is_active: true,
  },
]

// Mock the api module
const mockGetAvailableModels = jest.fn()
jest.mock('@/lib/api', () => ({
  api: {
    getAvailableModels: (...args: any[]) => mockGetAvailableModels(...args),
  },
}))

// Mock i18n context - t must be a stable reference to avoid useCallback loops
jest.mock('@/contexts/I18nContext', () => {
  const translations: Record<string, string> = {
    'evaluation.modelSelector.loading': 'Loading models...',
    'evaluation.modelSelector.failedToLoad': 'Failed to load models',
    'evaluation.modelSelector.noModelsAvailable': 'No models available. Configure API keys in your profile settings.',
    'evaluation.modelSelector.modelSelection': 'Model Selection',
    'evaluation.modelSelector.selectedCount': '{selected} of {max} selected',
    'evaluation.modelSelector.searchPlaceholder': 'Search models...',
    'evaluation.modelSelector.selectAll': 'Select All',
    'evaluation.modelSelector.clear': 'Clear',
    'evaluation.modelSelector.maxSelectionWarning': 'Maximum {max} models can be selected',
    'evaluation.modelSelector.noSearchResults': 'No models match your search',
    'evaluation.modelSelector.noModels': 'No models available',
  }
  const stableT = (key: string, arg2?: any) => {
    const vars = typeof arg2 === 'object' ? arg2 : undefined
    let result = translations[key] || key
    if (vars) {
      Object.entries(vars).forEach(([k, v]) => {
        result = result.replace(`{${k}}`, String(v))
      })
    }
    return result
  }
  const stableSetLocale = jest.fn()
  const stableReturn = { t: stableT, locale: 'en', setLocale: stableSetLocale }
  return {
    useI18n: () => stableReturn,
  }
})

describe('ModelSelector', () => {
  const mockOnSelectionChange = jest.fn()

  const defaultProps = {
    selectedModels: [] as string[],
    onSelectionChange: mockOnSelectionChange,
    maxSelections: 5,
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockGetAvailableModels.mockResolvedValue(mockAvailableModels)
  })

  describe('Loading State', () => {
    it('shows loading state while fetching models', async () => {
      mockGetAvailableModels.mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(mockAvailableModels), 100))
      )

      render(<ModelSelector {...defaultProps} />)

      expect(screen.getByText('Loading models...')).toBeInTheDocument()

      await waitFor(() => {
        expect(screen.queryByText('Loading models...')).not.toBeInTheDocument()
      })
    })
  })

  describe('Error State', () => {
    it('shows error when fetch fails', async () => {
      mockGetAvailableModels.mockRejectedValue(new Error('API Error'))

      render(<ModelSelector {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('Failed to load models')).toBeInTheDocument()
      })
    })
  })

  describe('Empty State', () => {
    it('shows no models message when API returns empty', async () => {
      mockGetAvailableModels.mockResolvedValue([])

      render(<ModelSelector {...defaultProps} />)

      await waitFor(() => {
        expect(
          screen.getByText(/No models available/)
        ).toBeInTheDocument()
      })
    })
  })

  describe('Model Display', () => {
    it('renders models after loading', async () => {
      render(<ModelSelector {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('Model Selection')).toBeInTheDocument()
      })
    })

    it('shows selected count', async () => {
      render(<ModelSelector {...defaultProps} selectedModels={['gpt-5']} />)

      await waitFor(() => {
        expect(screen.getByText('1 of 5 selected')).toBeInTheDocument()
      })
    })

    it('shows models when dropdown is opened', async () => {
      const user = userEvent.setup()

      render(<ModelSelector {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('Model Selection')).toBeInTheDocument()
      })

      // Click to open the dropdown
      await user.click(screen.getByText('Model Selection'))

      await waitFor(() => {
        expect(screen.getByText('GPT-5')).toBeInTheDocument()
        expect(screen.getByText('Claude Opus 4.6')).toBeInTheDocument()
        expect(screen.getByText('Gemini 2.5 Pro')).toBeInTheDocument()
      })
    })

    it('shows provider badges with colors', async () => {
      const user = userEvent.setup()

      render(<ModelSelector {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('Model Selection')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Model Selection'))

      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument()
        expect(screen.getByText('Anthropic')).toBeInTheDocument()
        expect(screen.getByText('Google')).toBeInTheDocument()
      })
    })

    it('shows model descriptions', async () => {
      const user = userEvent.setup()

      render(<ModelSelector {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('Model Selection')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Model Selection'))

      await waitFor(() => {
        expect(screen.getByText('Flagship model')).toBeInTheDocument()
        expect(screen.getByText('Latest Claude model')).toBeInTheDocument()
      })
    })
  })

  describe('Model Selection', () => {
    it('calls onSelectionChange when toggling a model', async () => {
      const user = userEvent.setup()

      render(<ModelSelector {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('Model Selection')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Model Selection'))

      await waitFor(() => {
        expect(screen.getByText('GPT-5')).toBeInTheDocument()
      })

      // Click the model label to select
      const modelLabel = screen.getByText('GPT-5').closest('label')
      await user.click(modelLabel!)

      expect(mockOnSelectionChange).toHaveBeenCalledWith(['gpt-5'])
    })

    it('calls onSelectionChange to deselect', async () => {
      const user = userEvent.setup()

      render(<ModelSelector {...defaultProps} selectedModels={['gpt-5']} />)

      await waitFor(() => {
        expect(screen.getByText('Model Selection')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Model Selection'))

      await waitFor(() => {
        expect(screen.getByText('GPT-5')).toBeInTheDocument()
      })

      const modelLabel = screen.getByText('GPT-5').closest('label')
      await user.click(modelLabel!)

      expect(mockOnSelectionChange).toHaveBeenCalledWith([])
    })

    it('prevents selecting more than maxSelections', async () => {
      const user = userEvent.setup()

      render(
        <ModelSelector
          {...defaultProps}
          selectedModels={['gpt-5', 'claude-opus-4-6']}
          maxSelections={2}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Model Selection')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Model Selection'))

      await waitFor(() => {
        expect(screen.getByText(/Maximum 2 models/)).toBeInTheDocument()
      })

      // Gemini should be disabled
      const geminiLabel = screen.getByText('Gemini 2.5 Pro').closest('label')
      expect(geminiLabel).toHaveClass('cursor-not-allowed')
    })
  })

  describe('Search', () => {
    it('filters models by search query', async () => {
      const user = userEvent.setup()

      render(<ModelSelector {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('Model Selection')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Model Selection'))

      await waitFor(() => {
        expect(screen.getByText('GPT-5')).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText('Search models...')
      await user.type(searchInput, 'Claude')

      expect(screen.queryByText('GPT-5')).not.toBeInTheDocument()
      expect(screen.getByText('Claude Opus 4.6')).toBeInTheDocument()
    })

    it('shows no results message for empty search', async () => {
      const user = userEvent.setup()

      render(<ModelSelector {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('Model Selection')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Model Selection'))

      await waitFor(() => {
        expect(screen.getByText('GPT-5')).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText('Search models...')
      await user.type(searchInput, 'nonexistent')

      expect(screen.getByText('No models match your search')).toBeInTheDocument()
    })
  })

  describe('Bulk Actions', () => {
    it('selects all models up to maxSelections', async () => {
      const user = userEvent.setup()

      render(<ModelSelector {...defaultProps} maxSelections={2} />)

      await waitFor(() => {
        expect(screen.getByText('Model Selection')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Model Selection'))

      await waitFor(() => {
        expect(screen.getByText('GPT-5')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Select All'))

      expect(mockOnSelectionChange).toHaveBeenCalledWith(['gpt-5', 'claude-opus-4-6'])
    })

    it('clears all selections', async () => {
      const user = userEvent.setup()

      render(
        <ModelSelector {...defaultProps} selectedModels={['gpt-5', 'claude-opus-4-6']} />
      )

      await waitFor(() => {
        expect(screen.getByText('Model Selection')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Model Selection'))

      await waitFor(() => {
        expect(screen.getByText('GPT-5')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Clear'))

      expect(mockOnSelectionChange).toHaveBeenCalledWith([])
    })
  })

  describe('API Integration', () => {
    it('fetches from available-models endpoint', async () => {
      render(<ModelSelector {...defaultProps} />)

      await waitFor(() => {
        expect(mockGetAvailableModels).toHaveBeenCalledTimes(1)
      })
    })
  })
})
