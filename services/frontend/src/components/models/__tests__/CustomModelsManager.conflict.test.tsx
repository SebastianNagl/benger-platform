/** @jest-environment jsdom */
/**
 * Integration: the REAL CustomModelsManager + CustomModelList +
 * CustomModelCredentialRow + customModelsAPI, with only the HTTP client
 * (`@/lib/api`) faked. The fake mimics the apiClient's GET cache: a GET is
 * served from cache until `invalidateCache` drops the matching entries.
 *
 * Scenario: the model's endpoint changes on the server after the list
 * loaded. Saving a key answers 409. The row must keep its message and the
 * typed key (no unmount behind a full-list spinner), and the refetch must
 * bypass the cache so the new base_url shows up.
 */
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { CustomModelsManager } from '../CustomModelsManager'

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'test-user-id', username: 'testuser' } }),
}))

const OLD_URL = 'https://old.example.org/v1'
const NEW_URL = 'https://new.example.org/v1'

const mockServer: { baseUrl: string } = { baseUrl: OLD_URL }
const mockCache = new Map<string, any>()

function mockModel() {
  return {
    id: 'custom-own-1',
    name: 'My vLLM',
    description: null,
    provider: 'Custom',
    model_type: 'chat',
    capabilities: [],
    base_url: mockServer.baseUrl,
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
    has_credential: false,
    can_edit: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: null,
  }
}

const mockApiClient = {
  get: jest.fn(async (endpoint: string) => {
    if (mockCache.has(endpoint)) return mockCache.get(endpoint)
    let data: any
    if (endpoint === '/custom-models') data = [mockModel()]
    else if (endpoint.endsWith('/credential')) data = { has_credential: false }
    else throw new Error(`unexpected GET ${endpoint}`)
    mockCache.set(endpoint, data)
    return data
  }),
  put: jest.fn(async (_endpoint: string, body: any) => {
    if (body.expected_base_url !== mockServer.baseUrl) {
      const err: any = new Error('conflict')
      err.response = { status: 409, data: { detail: 'endpoint changed' } }
      throw err
    }
    return { has_credential: true }
  }),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
  invalidateCache: jest.fn((pattern: string) => {
    Array.from(mockCache.keys()).forEach((key) => {
      if (key.includes(pattern)) mockCache.delete(key)
    })
  }),
}

// Getters: jest.mock is hoisted above the const, so resolve lazily.
jest.mock('@/lib/api', () => ({
  __esModule: true,
  get default() {
    return mockApiClient
  },
}))

describe('CustomModelsManager: 409 on key save', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockCache.clear()
    mockServer.baseUrl = OLD_URL
  })

  it('keeps the message and typed key and shows the new endpoint', async () => {
    render(<CustomModelsManager />)

    fireEvent.click(
      await screen.findByTestId('custom-model-expand-custom-own-1'),
    )
    const row = await screen.findByTestId(
      'custom-model-credential-row-custom-own-1',
    )
    expect(within(row).getByText(OLD_URL)).toBeInTheDocument()

    // The owner (in another tab) moves the model to a new endpoint.
    mockServer.baseUrl = NEW_URL

    fireEvent.change(within(row).getByTestId('credential-key-input'), {
      target: { value: 'sk-typed' },
    })
    await act(async () => {
      fireEvent.click(within(row).getByTestId('credential-save-button'))
    })

    // The refetch bypassed the cache and the row re-rendered in place.
    await waitFor(() => {
      const current = screen.getByTestId(
        'custom-model-credential-row-custom-own-1',
      )
      expect(within(current).getByText(NEW_URL)).toBeInTheDocument()
    })
    const current = screen.getByTestId(
      'custom-model-credential-row-custom-own-1',
    )
    // Same DOM node: the row was never unmounted behind a spinner.
    expect(current).toBe(row)
    expect(within(current).getByTestId('credential-message')).toHaveTextContent(
      'customModels.credential.endpointChanged',
    )
    expect(within(current).getByTestId('credential-key-input')).toHaveValue(
      'sk-typed',
    )
    expect(screen.queryByText('customModels.page.loading')).toBeNull()

    expect(mockApiClient.invalidateCache).toHaveBeenCalledWith('/custom-models')
    const listCalls = mockApiClient.get.mock.calls.filter(
      ([endpoint]) => endpoint === '/custom-models',
    )
    expect(listCalls).toHaveLength(2)

    // A retry now carries the new endpoint and succeeds.
    await act(async () => {
      fireEvent.click(within(current).getByTestId('credential-save-button'))
    })
    await waitFor(() =>
      expect(
        within(
          screen.getByTestId('custom-model-credential-row-custom-own-1'),
        ).getByTestId('credential-message'),
      ).toHaveTextContent('customModels.credential.saveSuccess'),
    )
    expect(mockApiClient.put).toHaveBeenLastCalledWith(
      '/custom-models/custom-own-1/credential',
      { api_key: 'sk-typed', expected_base_url: NEW_URL },
    )
  })
})
