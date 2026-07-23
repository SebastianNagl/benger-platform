/**
 * @jest-environment jsdom
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render as rtlRender, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import ModelsPage from '../page'
import { customModelsAPI } from '@/lib/api/customModels'

// Phase 4 migrated this page to `useQuery` (30-min staleTime on the public
// model catalog endpoints), so tests must provide a QueryClientProvider.
const render: typeof rtlRender = (ui, options) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return rtlRender(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
    options
  )
}

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

// Logged-in viewer (id matches the own-model fixture) so the community
// section renders and the own/shared split resolves.
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'test-user-id', username: 'testuser' } }),
}))

// Community (BYOM) section: the manager fetches the access-scoped list
// itself. One own model (created_by matches the global AuthContext mock's
// test-user-id) and one org-shared model owned by someone else — the
// "everyone with access sees it, only editors can edit" fixture.
// (`mock` prefix so the hoisted jest.mock factory may reference it; the
// suite's clearAllMocks wipes implementations, so community tests re-prime
// list() from this array in their beforeEach.)
const mockCommunityModels = [
      {
        id: 'custom-own-1',
        name: 'My vLLM',
        description: null,
        provider: 'Custom',
        model_type: 'chat',
        capabilities: ['text_generation'],
        base_url: 'https://own.example.org/v1',
        endpoint_model_name: 'own-llm-7b',
        requires_api_key: true,
        input_cost_per_million: null,
        output_cost_per_million: null,
        parameter_constraints: null,
        default_config: null,
        is_active: true,
        is_official: false,
        created_by: 'test-user-id',
        created_by_username: 'testuser',
        is_private: true,
        is_public: false,
        organization_ids: [],
        has_credential: true,
        can_edit: true,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: null,
      },
      {
        id: 'custom-shared-1',
        name: 'Group Soofi Endpoint',
        description: 'shared by the group',
        provider: 'Custom',
        model_type: 'chat',
        capabilities: ['text_generation'],
        base_url: 'https://group.example.org/v1',
        endpoint_model_name: 'soofi-s-isar',
        requires_api_key: true,
        input_cost_per_million: null,
        output_cost_per_million: null,
        parameter_constraints: null,
        default_config: null,
        is_active: true,
        is_official: false,
        created_by: 'someone-else',
        created_by_username: 'groupmate',
        is_private: false,
        is_public: false,
        organization_ids: ['org-1'],
        has_credential: false,
        can_edit: false,
        created_at: '2026-01-02T00:00:00Z',
        updated_at: null,
      },
]

jest.mock('@/lib/api/customModels', () => ({
  customModelsAPI: {
    list: jest.fn(),
    create: jest.fn(),
    update: jest.fn(),
    delete: jest.fn(),
    getCredentialStatus: jest.fn().mockResolvedValue({ has_credential: false }),
    setCredential: jest.fn(),
    deleteCredential: jest.fn(),
    testConnection: jest.fn(),
    testEndpoint: jest.fn(),
    updateVisibility: jest.fn(),
  },
}))

// Any icon the page OR the community manager subtree pulls (PlusIcon,
// ArrowPathIcon, the CustomModelList/FormModal icons, ...) resolves to a
// stub — a Proxy so we don't have to enumerate them.
jest.mock(
  '@heroicons/react/24/outline',
  () =>
    new Proxy(
      {},
      {
        get: () => () => <div data-testid="icon" />,
      }
    )
)
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
  // eslint-disable-next-line react/display-name
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

  describe('Community (BYOM) section', () => {
    beforeEach(() => {
      ;(customModelsAPI.list as jest.Mock).mockResolvedValue(
        mockCommunityModels
      )
    })

    it('hosts the manager: register button, own AND shared models with details', async () => {
      global.fetch = jest.fn()
        .mockResolvedValue({
          ok: true,
          json: () => Promise.resolve([]),
        })
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
        expect(
          screen.getByTestId('community-models-section')
        ).toBeInTheDocument()
      })
      // Management moved here from /settings/models.
      expect(
        screen.getByTestId('custom-model-register-button')
      ).toBeInTheDocument()
      // Own model in "my models", the org-shared model (someone else's,
      // can_edit false) in "shared & public" — everyone with access sees
      // it here with its details.
      await waitFor(() => {
        expect(screen.getByText('My vLLM')).toBeInTheDocument()
        expect(screen.getByText('Group Soofi Endpoint')).toBeInTheDocument()
      })
      expect(
        screen.getByTestId('custom-models-own-section')
      ).toHaveTextContent('My vLLM')
      expect(
        screen.getByTestId('custom-models-shared-section')
      ).toHaveTextContent('Group Soofi Endpoint')
    })

    it('page search filters community rows too', async () => {
      global.fetch = jest.fn()
        .mockResolvedValue({
          ok: true,
          json: () => Promise.resolve([]),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve(mockModels),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve(mockProviderCapabilities),
        }) as any
      render(<ModelsPage />)
      await waitFor(() =>
        expect(screen.getByText('Group Soofi Endpoint')).toBeInTheDocument()
      )

      const searchInput = screen.getByPlaceholderText('models.searchPlaceholder')
      fireEvent.change(searchInput, { target: { value: 'soofi' } })

      await waitFor(() => {
        expect(screen.queryByText('My vLLM')).not.toBeInTheDocument()
      })
      expect(screen.getByText('Group Soofi Endpoint')).toBeInTheDocument()
    })

    it('the Custom provider filter scopes the page to the community section', async () => {
      global.fetch = jest.fn()
        .mockResolvedValue({
          ok: true,
          json: () => Promise.resolve([]),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve(mockModels),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve(mockProviderCapabilities),
        }) as any
      render(<ModelsPage />)
      await waitFor(() =>
        expect(screen.getByText('GPT-4')).toBeInTheDocument()
      )

      const providerSelect = screen.getByRole('combobox')
      fireEvent.change(providerSelect, { target: { value: 'Custom' } })

      await waitFor(() => {
        expect(screen.queryByText('GPT-4')).not.toBeInTheDocument()
      })
      expect(
        screen.getByTestId('community-models-section')
      ).toBeInTheDocument()
      expect(screen.getByText('My vLLM')).toBeInTheDocument()
    })
  })
})
