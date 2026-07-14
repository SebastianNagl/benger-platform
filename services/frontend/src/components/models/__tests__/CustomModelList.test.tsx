/**
 * CustomModelList — owner vs. non-owner rows, badges, delete confirm flow.
 */

import { customModelsAPI } from '@/lib/api/customModels'
import type { CustomModel } from '@/lib/api/types'
import { render, screen, waitFor } from '@testing-library/react'
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

const baseModel: CustomModel = {
  id: 'custom-own',
  name: 'Own Model',
  description: 'My own endpoint',
  provider: 'Custom',
  model_type: 'chat',
  capabilities: ['text-generation'],
  base_url: 'https://own.example.com/v1',
  endpoint_model_name: 'llama-own',
  requires_api_key: true,
  input_cost_per_million: 1,
  output_cost_per_million: 2,
  parameter_constraints: null,
  is_active: true,
  is_official: false,
  created_by: 'user-1',
  created_by_username: 'me',
  is_private: true,
  is_public: false,
  organization_ids: [],
  has_credential: true,
  can_edit: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: null,
}

const ownModel = baseModel

const foreignModel: CustomModel = {
  ...baseModel,
  id: 'custom-foreign',
  name: 'Foreign Model',
  base_url: 'https://foreign.example.com/v1',
  endpoint_model_name: 'llama-foreign',
  created_by: 'user-2',
  created_by_username: 'alice',
  is_private: false,
  is_public: false,
  organization_ids: ['org-1'],
  has_credential: false,
  can_edit: false,
}

describe('CustomModelList', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(customModelsAPI.remove as jest.Mock).mockResolvedValue(undefined)
    ;(customModelsAPI.getCredentialStatus as jest.Mock).mockResolvedValue({
      has_credential: false,
    })
  })

  it('renders the empty state', () => {
    render(<CustomModelList models={[]} emptyMessage="Nothing here" />)

    expect(screen.getByTestId('custom-model-list-empty')).toHaveTextContent(
      'Nothing here'
    )
  })

  it('shows owner actions only on owner rows', () => {
    render(<CustomModelList models={[ownModel, foreignModel]} />)

    expect(
      screen.getByTestId('custom-model-edit-custom-own')
    ).toBeInTheDocument()
    expect(
      screen.getByTestId('custom-model-visibility-custom-own')
    ).toBeInTheDocument()
    expect(
      screen.getByTestId('custom-model-delete-custom-own')
    ).toBeInTheDocument()

    expect(
      screen.queryByTestId('custom-model-edit-custom-foreign')
    ).not.toBeInTheDocument()
    expect(
      screen.queryByTestId('custom-model-visibility-custom-foreign')
    ).not.toBeInTheDocument()
    expect(
      screen.queryByTestId('custom-model-delete-custom-foreign')
    ).not.toBeInTheDocument()
  })

  it('renders badges: custom (with owner on foreign rows), visibility, credential pill', () => {
    render(<CustomModelList models={[ownModel, foreignModel]} />)

    // Two custom badges; the foreign one uses the owner variant (the
    // global i18n test mock returns raw keys, so assert on the key).
    const customBadges = screen.getAllByTestId('custom-badge')
    expect(customBadges).toHaveLength(2)
    expect(
      customBadges.some((el) =>
        el.textContent?.includes('customModels.badges.customBy')
      )
    ).toBe(true)
    expect(
      customBadges.some(
        (el) => el.textContent === 'customModels.badges.custom'
      )
    ).toBe(true)

    // Official badge never appears in this list.
    expect(screen.queryByTestId('official-badge')).not.toBeInTheDocument()

    // Visibility badges: own model private, foreign model org-shared.
    expect(
      screen.getByTestId('visibility-badge-private')
    ).toBeInTheDocument()
    expect(
      screen.getByTestId('visibility-badge-organization')
    ).toBeInTheDocument()

    // Credential pills reflect has_credential.
    expect(
      screen.getByTestId('credential-pill-custom-own')
    ).toHaveTextContent('customModels.badges.keyConfigured')
    expect(
      screen.getByTestId('credential-pill-custom-foreign')
    ).toHaveTextContent('customModels.badges.keyMissing')
  })

  it('expands a non-owner row to read-only detail with a credential row', async () => {
    const user = userEvent.setup()
    render(<CustomModelList models={[foreignModel]} />)

    expect(
      screen.queryByTestId('custom-model-detail-custom-foreign')
    ).not.toBeInTheDocument()

    await user.click(
      screen.getByTestId('custom-model-expand-custom-foreign')
    )

    expect(
      screen.getByTestId('custom-model-detail-custom-foreign')
    ).toBeInTheDocument()
    expect(
      screen.getByTestId('custom-model-credential-row-custom-foreign')
    ).toBeInTheDocument()
    // No permissions panel for non-owners.
    expect(
      screen.queryByTestId('custom-model-visibility-panel-custom-foreign')
    ).not.toBeInTheDocument()
  })

  it('opens the visibility panel from the owner action', async () => {
    const user = userEvent.setup()
    render(<CustomModelList models={[ownModel]} />)

    await user.click(screen.getByTestId('custom-model-visibility-custom-own'))

    await waitFor(() => {
      expect(
        screen.getByTestId('custom-model-visibility-panel-custom-own')
      ).toBeInTheDocument()
    })
    expect(
      screen.getByTestId('model-permissions-panel')
    ).toBeInTheDocument()
  })

  it('calls onEdit with the model', async () => {
    const user = userEvent.setup()
    const onEdit = jest.fn()
    render(<CustomModelList models={[ownModel]} onEdit={onEdit} />)

    await user.click(screen.getByTestId('custom-model-edit-custom-own'))

    expect(onEdit).toHaveBeenCalledWith(ownModel)
  })

  describe('Delete confirm flow', () => {
    it('deletes only after confirmation and refreshes the parent', async () => {
      const user = userEvent.setup()
      const onChanged = jest.fn()
      render(<CustomModelList models={[ownModel]} onChanged={onChanged} />)

      await user.click(screen.getByTestId('custom-model-delete-custom-own'))

      // Confirmation dialog appears; nothing deleted yet.
      await waitFor(() => {
        expect(
          screen.getByTestId('confirm-dialog-confirm-button')
        ).toBeInTheDocument()
      })
      expect(customModelsAPI.remove).not.toHaveBeenCalled()

      await user.click(screen.getByTestId('confirm-dialog-confirm-button'))

      await waitFor(() => {
        expect(customModelsAPI.remove).toHaveBeenCalledWith('custom-own')
      })
      expect(onChanged).toHaveBeenCalled()
    })

    it('does not delete when the dialog is cancelled', async () => {
      const user = userEvent.setup()
      render(<CustomModelList models={[ownModel]} />)

      await user.click(screen.getByTestId('custom-model-delete-custom-own'))

      await waitFor(() => {
        expect(
          screen.getByTestId('confirm-dialog-cancel-button')
        ).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('confirm-dialog-cancel-button'))

      expect(customModelsAPI.remove).not.toHaveBeenCalled()
    })
  })
})
