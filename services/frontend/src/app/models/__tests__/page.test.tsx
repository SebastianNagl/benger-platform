/**
 * @jest-environment jsdom
 */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ModelsPage from '../page'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, any>) => {
      if (vars) {
        let result = key
        for (const [k, v] of Object.entries(vars)) {
          result = result.replace(`{${k}}`, String(v))
        }
        return result
      }
      return key
    },
  }),
}))

jest.mock('@/components/shared', () => ({
  HeroPattern: () => <div data-testid="hero-pattern" />,
}))

jest.mock('@heroicons/react/24/outline', () => ({
  ChevronDownIcon: () => <div data-testid="chevron-down" />,
}))
jest.mock('@/components/shared/FilterToolbar', () => {
  const FilterToolbar = ({
    searchValue,
    onSearchChange,
    searchPlaceholder,
    searchLabel,
    clearLabel = 'Clear filters',
    onClearFilters,
    hasActiveFilters,
    leftExtras,
    rightExtras,
    children,
  }: any) => (
    <div data-testid="filter-toolbar">
      {leftExtras}
      {onSearchChange && (
        <input
          data-testid="filter-toolbar-search"
          type="search"
          placeholder={searchPlaceholder}
          title={searchPlaceholder || searchLabel}
          value={searchValue ?? ''}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      )}
      <div data-testid="filter-toolbar-fields">{children}</div>
      {onClearFilters && (
        <button
          data-testid="filter-toolbar-clear"
          onClick={onClearFilters}
          disabled={!hasActiveFilters}
          title={clearLabel}
          aria-label={clearLabel}
        />
      )}
      {rightExtras}
    </div>
  )
  FilterToolbar.Field = ({ children }: any) => <div>{children}</div>
  return { FilterToolbar }
})


const mockModels = [
  {
    id: 'gpt-4',
    name: 'GPT-4',
    description: 'Advanced language model',
    provider: 'OpenAI',
    model_type: 'chat',
    capabilities: ['text', 'code', 'reasoning', 'vision'],
    config_schema: null,
    default_config: null,
    input_cost_per_million: 30.0,
    output_cost_per_million: 60.0,
    is_active: true,
  },
  {
    id: 'gemini-2.5-pro',
    name: 'Gemini 2.5 Pro',
    description: 'Google multimodal model',
    provider: 'Google',
    model_type: 'chat',
    capabilities: ['text', 'vision'],
    config_schema: null,
    default_config: null,
    input_cost_per_million: 2.5,
    output_cost_per_million: 10.0,
    is_active: true,
  },
  {
    id: 'claude-3-opus',
    name: 'Claude 3 Opus',
    description: null,
    provider: 'Anthropic',
    model_type: 'chat',
    capabilities: ['text', 'code'],
    config_schema: null,
    default_config: null,
    input_cost_per_million: null,
    output_cost_per_million: null,
    is_active: true,
  },
]

const mockProviderCapabilities = {
  openai: {
    display_name: 'OpenAI',
    temperature: { min: 0, max: 2, default: 1 },
    structured_output: { method: 'json_schema', strict_mode: true, guaranteed: true },
    determinism: { seed_support: true, recommended_seed: 42 },
  },
}

describe('ModelsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('should show loading state initially', () => {
    global.fetch = jest.fn(() => new Promise(() => {})) as any
    render(<ModelsPage />)
    expect(screen.getByText('models.loading')).toBeInTheDocument()
  })

  it('should render models after successful fetch', async () => {
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockModels),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockProviderCapabilities),
      }) as any

    render(<ModelsPage />)

    await waitFor(() => {
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
    })

    expect(screen.getByText('Gemini 2.5 Pro')).toBeInTheDocument()
    expect(screen.getByText('Claude 3 Opus')).toBeInTheDocument()
  })

  it('should group models by provider', async () => {
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockModels),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({}),
      }) as any

    render(<ModelsPage />)

    await waitFor(() => {
      // Provider names appear as heading text elements in the grouped sections
      expect(screen.getAllByText('OpenAI').length).toBeGreaterThan(0)
      expect(screen.getAllByText('Google').length).toBeGreaterThan(0)
      expect(screen.getAllByText('Anthropic').length).toBeGreaterThan(0)
    })
  })

  it('should show error state when fetch fails', async () => {
    global.fetch = jest.fn().mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({}),
    }) as any

    render(<ModelsPage />)

    await waitFor(() => {
      expect(screen.getByText(/models.error/)).toBeInTheDocument()
    })
  })

  it('should filter models by search query', async () => {
    const user = userEvent.setup()
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockModels),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({}),
      }) as any

    render(<ModelsPage />)

    await waitFor(() => {
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
    })

    const searchInput = screen.getByPlaceholderText('models.searchPlaceholder')
    await user.type(searchInput, 'GPT')

    expect(screen.getByText('GPT-4')).toBeInTheDocument()
    expect(screen.queryByText('Claude 3 Opus')).not.toBeInTheDocument()
  })

  it('should filter models by provider', async () => {
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockModels),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({}),
      }) as any

    render(<ModelsPage />)

    await waitFor(() => {
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
    })

    const select = screen.getByRole('combobox')
    fireEvent.change(select, { target: { value: 'OpenAI' } })

    expect(screen.getByText('GPT-4')).toBeInTheDocument()
    expect(screen.queryByText('Claude 3 Opus')).not.toBeInTheDocument()
    expect(screen.queryByText('Gemini 2.5 Pro')).not.toBeInTheDocument()
  })

  it('should show no models message when filtered results are empty', async () => {
    const user = userEvent.setup()
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockModels),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({}),
      }) as any

    render(<ModelsPage />)

    await waitFor(() => {
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
    })

    const searchInput = screen.getByPlaceholderText('models.searchPlaceholder')
    await user.type(searchInput, 'nonexistent-model-xyz')

    expect(screen.getByText('models.noModels')).toBeInTheDocument()
  })

  it('should display pricing for models with cost data', async () => {
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockModels),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({}),
      }) as any

    render(<ModelsPage />)

    await waitFor(() => {
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
    })

    // GPT-4 has pricing
    expect(screen.getByText(/\$30\.00/)).toBeInTheDocument()
    expect(screen.getByText(/\$60\.00/)).toBeInTheDocument()
  })

  it('should show content policy warning for gemini-2.5-pro', async () => {
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockModels),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({}),
      }) as any

    render(<ModelsPage />)

    await waitFor(() => {
      expect(screen.getByText('models.contentPolicyWarning')).toBeInTheDocument()
    })
  })

  it('should open model settings modal when clicking a model', async () => {
    const user = userEvent.setup()
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockModels),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockProviderCapabilities),
      }) as any

    render(<ModelsPage />)

    await waitFor(() => {
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
    })

    // Click on the GPT-4 row
    const gpt4Row = screen.getByText('GPT-4').closest('tr')!
    await user.click(gpt4Row)

    // Modal should appear with model name and JSON settings
    await waitFor(() => {
      expect(screen.getByText('models.copyJson')).toBeInTheDocument()
      expect(screen.getByText('models.close')).toBeInTheDocument()
    })
  })

  it('should close modal when clicking close button', async () => {
    const user = userEvent.setup()
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockModels),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({}),
      }) as any

    render(<ModelsPage />)

    await waitFor(() => {
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
    })

    const gpt4Row = screen.getByText('GPT-4').closest('tr')!
    await user.click(gpt4Row)

    await waitFor(() => {
      expect(screen.getByText('models.close')).toBeInTheDocument()
    })

    await user.click(screen.getByText('models.close'))

    await waitFor(() => {
      expect(screen.queryByText('models.close')).not.toBeInTheDocument()
    })
  })

  it('should copy JSON to clipboard when clicking copy button', async () => {
    const user = userEvent.setup()
    const mockWriteText = jest.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: mockWriteText },
      writable: true,
      configurable: true,
    })

    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockModels),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockProviderCapabilities),
      }) as any

    render(<ModelsPage />)

    await waitFor(() => {
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
    })

    const gpt4Row = screen.getByText('GPT-4').closest('tr')!
    await user.click(gpt4Row)

    await waitFor(() => {
      expect(screen.getByText('models.copyJson')).toBeInTheDocument()
    })

    await user.click(screen.getByText('models.copyJson'))

    expect(mockWriteText).toHaveBeenCalledWith(
      expect.stringContaining('"gpt-4"')
    )
  })

  it('should show capabilities badges with overflow indicator', async () => {
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockModels),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({}),
      }) as any

    render(<ModelsPage />)

    await waitFor(() => {
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
    })

    // GPT-4 has 4 capabilities but only 3 shown, with +1 overflow
    expect(screen.getByText('+1')).toBeInTheDocument()
  })

  it('should handle capabilities fetch failure gracefully', async () => {
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockModels),
      })
      .mockResolvedValueOnce({
        ok: false,
        json: () => Promise.resolve({}),
      }) as any

    render(<ModelsPage />)

    await waitFor(() => {
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
    })

    // Should still render models even if capabilities fetch fails
    expect(screen.getByText('Claude 3 Opus')).toBeInTheDocument()
  })

  it('should display page title and subtitle', async () => {
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([]),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({}),
      }) as any

    render(<ModelsPage />)

    await waitFor(() => {
      expect(screen.getByText('models.title')).toBeInTheDocument()
    })
  })

  it('should show model settings with provider capabilities in modal JSON', async () => {
    const user = userEvent.setup()
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockModels),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockProviderCapabilities),
      }) as any

    render(<ModelsPage />)

    await waitFor(() => {
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
    })

    const gpt4Row = screen.getByText('GPT-4').closest('tr')!
    await user.click(gpt4Row)

    await waitFor(() => {
      const pre = screen.getByText(/provider_settings/).closest('pre')
      expect(pre).toBeTruthy()
      expect(pre!.textContent).toContain('OpenAI')
      expect(pre!.textContent).toContain('temperature')
    })
  })

  it('should show null provider_settings for model without capabilities', async () => {
    const user = userEvent.setup()
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockModels),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockProviderCapabilities),
      }) as any

    render(<ModelsPage />)

    await waitFor(() => {
      expect(screen.getByText('Claude 3 Opus')).toBeInTheDocument()
    })

    // Click on Claude (Anthropic - not in capabilities)
    const claudeRow = screen.getByText('Claude 3 Opus').closest('tr')!
    await user.click(claudeRow)

    await waitFor(() => {
      const pre = screen.getByText(/provider_settings/).closest('pre')
      expect(pre!.textContent).toContain('"provider_settings": null')
    })
  })
})
