/** @jest-environment jsdom */
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { CustomModelsManager } from '../CustomModelsManager'
import { customModelsAPI } from '@/lib/api/customModels'

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'test-user-id', username: 'testuser' } }),
}))

jest.mock('@/lib/api/customModels', () => ({
  customModelsAPI: {
    list: jest.fn(),
    getCredentialStatus: jest.fn().mockResolvedValue({ has_credential: false }),
    testConnection: jest.fn(),
    delete: jest.fn(),
    updateVisibility: jest.fn(),
    create: jest.fn(),
    update: jest.fn(),
  },
}))

const models = [
  { id: 'custom-own-1', name: 'My vLLM', description: null, provider: 'Custom',
    model_type: 'chat', capabilities: [], base_url: 'https://own.example.org/v1',
    endpoint_model_name: 'own-llm-7b', requires_api_key: true, input_cost_per_million: null,
    output_cost_per_million: null, parameter_constraints: null, default_config: null,
    is_active: true, is_official: false, created_by: 'test-user-id', created_by_username: 'testuser',
    is_private: true, is_public: false, organization_ids: [], has_credential: true, can_edit: true,
    created_at: '2026-01-01T00:00:00Z', updated_at: null },
  { id: 'custom-shared-1', name: 'Group Soofi Endpoint', description: 'shared', provider: 'Custom',
    model_type: 'chat', capabilities: [], base_url: 'https://group.example.org/v1',
    endpoint_model_name: 'soofi-s-isar', requires_api_key: true, input_cost_per_million: null,
    output_cost_per_million: null, parameter_constraints: null, default_config: null,
    is_active: true, is_official: false, created_by: 'someone-else', created_by_username: 'groupmate',
    is_private: false, is_public: false, organization_ids: ['org-1'], has_credential: false, can_edit: false,
    created_at: '2026-01-02T00:00:00Z', updated_at: null },
]

describe('CustomModelsManager', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(customModelsAPI.list as jest.Mock).mockResolvedValue(models)
  })

  it('renders own and shared sections with the register button', async () => {
    render(<CustomModelsManager />)
    expect(screen.getByTestId('custom-model-register-button')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('My vLLM')).toBeInTheDocument())
    expect(screen.getByTestId('custom-models-own-section')).toHaveTextContent('My vLLM')
    expect(screen.getByTestId('custom-models-shared-section')).toHaveTextContent('Group Soofi Endpoint')
  })

  it('filterQuery narrows both lists', async () => {
    const { rerender } = render(<CustomModelsManager filterQuery="" />)
    await waitFor(() => expect(screen.getByText('My vLLM')).toBeInTheDocument())
    rerender(<CustomModelsManager filterQuery="soofi" />)
    await waitFor(() => expect(screen.queryByText('My vLLM')).not.toBeInTheDocument())
    expect(screen.getByText('Group Soofi Endpoint')).toBeInTheDocument()
  })

  it('reports the post-filter visible count', async () => {
    const onCount = jest.fn()
    const { rerender } = render(<CustomModelsManager onVisibleCountChange={onCount} filterQuery="" />)
    await waitFor(() => expect(onCount).toHaveBeenCalledWith(2))
    rerender(<CustomModelsManager onVisibleCountChange={onCount} filterQuery="soofi" />)
    await waitFor(() => expect(onCount).toHaveBeenCalledWith(1))
  })
})
