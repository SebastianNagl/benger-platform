/**
 * CustomModelList — the "Scores" action opens the per-project score dialog
 * for custom models too (owner and non-owner rows alike).
 */

import type { CustomModel } from '@/lib/api/types'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CustomModelList } from '../CustomModelList'

jest.mock('@/lib/api/customModels', () => ({
  customModelsAPI: {
    remove: jest.fn(),
    updateVisibility: jest.fn(),
    getCredentialStatus: jest.fn(),
    setCredential: jest.fn(),
    deleteCredential: jest.fn(),
    testConnection: jest.fn(),
  },
}))
jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    getOrganizations: jest.fn().mockResolvedValue([]),
  },
}))

const mockModal = jest.fn()
jest.mock('../ModelDetailModal', () => ({
  ModelDetailModal: (props: any) => {
    mockModal(props)
    return props.model ? (
      <div data-testid="model-detail-modal">
        {props.model.name}
        <button onClick={props.onClose}>close</button>
      </div>
    ) : null
  },
}))

const model: CustomModel = {
  id: 'custom-shared',
  name: 'Shared Model',
  description: null,
  provider: 'Custom',
  model_type: 'chat',
  capabilities: ['text-generation'],
  base_url: 'https://shared.example.com/v1',
  endpoint_model_name: 'llama-shared',
  requires_api_key: false,
  input_cost_per_million: null,
  output_cost_per_million: null,
  parameter_constraints: null,
  is_active: true,
  is_official: false,
  created_by: 'someone-else',
  created_by_username: 'colleague',
  is_private: false,
  is_public: false,
  organization_ids: ['org-1'],
  has_credential: false,
  can_edit: false,
  created_at: '2026-10-01T00:00:00Z',
}

describe('CustomModelList scores action', () => {
  beforeEach(() => mockModal.mockClear())

  it('shows a Scores button on non-owner rows and opens the dialog', async () => {
    const user = userEvent.setup()
    render(<CustomModelList models={[model]} />)

    // Closed: the dialog is not mounted at all.
    expect(screen.queryByTestId('model-detail-modal')).toBeNull()
    expect(mockModal).not.toHaveBeenCalled()

    await user.click(screen.getByTestId('custom-model-scores-custom-shared'))

    expect(screen.getByTestId('model-detail-modal')).toHaveTextContent(
      'Shared Model',
    )
    expect(mockModal).toHaveBeenLastCalledWith(
      expect.objectContaining({
        model: {
          id: 'custom-shared',
          name: 'Shared Model',
          provider: 'Custom',
        },
      }),
    )

    await user.click(screen.getByText('close'))
    expect(screen.queryByTestId('model-detail-modal')).toBeNull()
  })
})
