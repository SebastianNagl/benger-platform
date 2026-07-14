/**
 * ModelPermissionsPanel — private/organization/public visibility for a
 * custom model (BYOM). No public-role sub-radio: sharing a model only
 * grants usage, never editing.
 */

import { customModelsAPI } from '@/lib/api/customModels'
import { mockToast } from '@/test-utils/setupTests'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ModelPermissionsPanel } from '../ModelPermissionsPanel'

const toast = { success: mockToast.success, error: mockToast.error }

jest.mock('@/lib/api/customModels', () => ({
  customModelsAPI: {
    updateVisibility: jest.fn(),
  },
}))
jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    getOrganizations: jest
      .fn()
      .mockResolvedValue([
        { id: 'org-1', name: 'Org One' },
        { id: 'org-2', name: 'Org Two' },
      ]),
  },
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'customModels.permissions.noPermission': 'No permission to edit',
        'customModels.permissions.saveSuccess': 'Visibility saved',
        'customModels.permissions.viewOnly':
          'Only the creator can change visibility',
        'customModels.permissions.visibility': 'Visibility',
        'customModels.permissions.visibilityDescription':
          'Control who can use this model',
        'customModels.permissions.private': 'Private',
        'customModels.permissions.privateDescription': 'Only you',
        'customModels.permissions.organization': 'Organization',
        'customModels.permissions.organizationDescription':
          'Members of selected organizations',
        'customModels.permissions.public': 'Public',
        'customModels.permissions.publicDescription':
          'Every authenticated user',
        'customModels.permissions.organizations': 'Organizations',
        'customModels.permissions.organizationsDescription':
          'Select at least one organization',
        'customModels.permissions.loadingOrganizations':
          'Loading organizations...',
        'customModels.permissions.noOrganizationsAvailable':
          'No organizations available',
        'customModels.permissions.validation.needsOrganization':
          'Please select at least one organization',
        'customModels.permissions.cancel': 'Cancel',
        'customModels.permissions.save': 'Save',
        'customModels.permissions.saving': 'Saving...',
      }
      return translations[key] || key
    },
  }),
}))

describe('ModelPermissionsPanel', () => {
  const mockOnSaved = jest.fn()
  const mockOnCancel = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    ;(customModelsAPI.updateVisibility as jest.Mock).mockResolvedValue({})
  })

  describe('Rendering', () => {
    it('renders private, organization, and public radios', async () => {
      render(<ModelPermissionsPanel modelId="custom-1" canEdit />)

      await waitFor(() => {
        expect(
          screen.getByTestId('model-permissions-panel')
        ).toBeInTheDocument()
      })

      expect(
        screen.getByTestId('model-visibility-private-radio')
      ).toBeInTheDocument()
      expect(
        screen.getByTestId('model-visibility-organization-radio')
      ).toBeInTheDocument()
      expect(
        screen.getByTestId('model-visibility-public-radio')
      ).toBeInTheDocument()
    })

    it('has NO public-role section (models grant usage only)', async () => {
      render(
        <ModelPermissionsPanel
          modelId="custom-1"
          canEdit
          initialVisibility="public"
        />
      )

      await waitFor(() => {
        expect(
          (screen.getByTestId('model-visibility-public-radio') as HTMLInputElement)
            .checked
        ).toBe(true)
      })

      expect(screen.queryByTestId('public-role-section')).toBeNull()
      expect(
        screen.queryByTestId('model-visibility-public-role-section')
      ).toBeNull()
    })

    it('shows the organization picker when initially org-scoped', async () => {
      render(
        <ModelPermissionsPanel
          modelId="custom-1"
          canEdit
          initialVisibility="organization"
          initialOrganizationIds={['org-1']}
        />
      )

      await waitFor(() => {
        expect(
          screen.getByTestId('model-permissions-organization-section')
        ).toBeInTheDocument()
      })

      await waitFor(() => {
        expect(
          (screen.getByTestId(
            'model-permissions-organization-checkbox-org-1'
          ) as HTMLInputElement).checked
        ).toBe(true)
      })
    })

    it('renders read-only view when canEdit is false', () => {
      render(
        <ModelPermissionsPanel
          modelId="custom-1"
          canEdit={false}
          initialVisibility="organization"
          initialOrganizationIds={['org-1']}
        />
      )

      expect(
        screen.getByText('Only the creator can change visibility')
      ).toBeInTheDocument()
      expect(
        screen.queryByTestId('model-permissions-panel')
      ).not.toBeInTheDocument()
      expect(
        screen.queryByTestId('model-permissions-save-button')
      ).not.toBeInTheDocument()
    })
  })

  describe('Validation', () => {
    it('requires at least one organization for org visibility', async () => {
      const user = userEvent.setup()
      render(
        <ModelPermissionsPanel
          modelId="custom-1"
          canEdit
          initialVisibility="private"
        />
      )

      await waitFor(() => {
        expect(
          screen.getByTestId('model-visibility-organization-option')
        ).toBeInTheDocument()
      })

      await user.click(
        screen.getByTestId('model-visibility-organization-option')
      )
      await user.click(screen.getByTestId('model-permissions-save-button'))

      await waitFor(() => {
        expect(
          screen.getByTestId('model-permissions-error')
        ).toBeInTheDocument()
      })
      expect(
        screen.getByText('Please select at least one organization')
      ).toBeInTheDocument()
      expect(customModelsAPI.updateVisibility).not.toHaveBeenCalled()
    })
  })

  describe('Save payloads', () => {
    it('saves the private payload', async () => {
      const user = userEvent.setup()
      render(
        <ModelPermissionsPanel
          modelId="custom-1"
          canEdit
          initialVisibility="public"
          onSaved={mockOnSaved}
        />
      )

      await waitFor(() => {
        expect(
          screen.getByTestId('model-visibility-private-option')
        ).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('model-visibility-private-option'))
      await user.click(screen.getByTestId('model-permissions-save-button'))

      await waitFor(() => {
        expect(customModelsAPI.updateVisibility).toHaveBeenCalledWith(
          'custom-1',
          { is_private: true }
        )
      })
      expect(toast.success).toHaveBeenCalledWith('Visibility saved')
      expect(mockOnSaved).toHaveBeenCalledWith({
        visibility: 'private',
        organization_ids: [],
      })
    })

    it('saves the organization payload with the selected org ids', async () => {
      const user = userEvent.setup()
      render(
        <ModelPermissionsPanel
          modelId="custom-1"
          canEdit
          initialVisibility="private"
          onSaved={mockOnSaved}
        />
      )

      await waitFor(() => {
        expect(
          screen.getByTestId('model-visibility-organization-option')
        ).toBeInTheDocument()
      })

      await user.click(
        screen.getByTestId('model-visibility-organization-option')
      )

      await waitFor(() => {
        expect(
          screen.getByTestId('model-permissions-organization-checkbox-org-2')
        ).toBeInTheDocument()
      })

      await user.click(
        screen.getByTestId('model-permissions-organization-checkbox-org-2')
      )
      await user.click(screen.getByTestId('model-permissions-save-button'))

      await waitFor(() => {
        expect(customModelsAPI.updateVisibility).toHaveBeenCalledWith(
          'custom-1',
          { is_private: false, organization_ids: ['org-2'] }
        )
      })
      expect(mockOnSaved).toHaveBeenCalledWith({
        visibility: 'organization',
        organization_ids: ['org-2'],
      })
    })

    it('saves the public payload without any role field', async () => {
      const user = userEvent.setup()
      render(
        <ModelPermissionsPanel
          modelId="custom-1"
          canEdit
          initialVisibility="private"
          onSaved={mockOnSaved}
        />
      )

      await waitFor(() => {
        expect(
          screen.getByTestId('model-visibility-public-option')
        ).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('model-visibility-public-option'))
      await user.click(screen.getByTestId('model-permissions-save-button'))

      await waitFor(() => {
        expect(customModelsAPI.updateVisibility).toHaveBeenCalledWith(
          'custom-1',
          { is_public: true }
        )
      })
    })

    it('surfaces API errors', async () => {
      const user = userEvent.setup()
      ;(customModelsAPI.updateVisibility as jest.Mock).mockRejectedValue(
        new Error('boom')
      )

      render(
        <ModelPermissionsPanel
          modelId="custom-1"
          canEdit
          initialVisibility="public"
        />
      )

      await waitFor(() => {
        expect(
          screen.getByTestId('model-permissions-save-button')
        ).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('model-permissions-save-button'))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('boom')
        expect(
          screen.getByTestId('model-permissions-error')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Cancel', () => {
    it('resets visibility and selected orgs on cancel', async () => {
      const user = userEvent.setup()
      render(
        <ModelPermissionsPanel
          modelId="custom-1"
          canEdit
          initialVisibility="private"
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(
          screen.getByTestId('model-visibility-public-option')
        ).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('model-visibility-public-option'))
      await user.click(screen.getByTestId('model-permissions-cancel-button'))

      expect(
        (screen.getByTestId('model-visibility-private-radio') as HTMLInputElement)
          .checked
      ).toBe(true)
      expect(mockOnCancel).toHaveBeenCalled()
    })
  })
})
