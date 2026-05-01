/**
 * ProjectPermissionsPanel Test Suite
 *
 * Comprehensive test coverage for project permissions management:
 * - Permissions panel rendering
 * - Public/private toggle
 * - Organization assignment
 * - User role display
 * - Permission changes
 * - Save/cancel functionality
 * - Permission validation
 * - Error handling
 */

import { organizationsAPI } from '@/lib/api/organizations'
import { projectsAPI } from '@/lib/api/projects'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { mockToast } from '@/test-utils/setupTests'
import { ProjectPermissionsPanel } from '../ProjectPermissionsPanel'

// Toast assertions read through the global mock from setupTests; alias the
// per-type mocks so existing expect(toast.success/error...) call sites work.
const toast = { success: mockToast.success, error: mockToast.error }

// Mock dependencies
jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    getOrganizations: jest.fn(),
  },
}))
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    update: jest.fn(),
  },
}))
const mockUseAuth = jest.fn(() => ({
  user: {
    id: 'user-1',
    email: 'admin@test.com',
    is_superadmin: true,
  },
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'project.permissions.noPermission': 'No permission to edit',
        'project.permissions.validation.privateNeedsOrganization':
          'Private projects need at least one organization',
        'project.permissions.saveSuccess': 'Permissions saved successfully',
        'project.permissions.viewOnly': 'You can only view these permissions',
        'project.permissions.visibility': 'Visibility',
        'project.permissions.public': 'Public',
        'project.permissions.private': 'Private',
        'project.permissions.organizations': 'Organizations',
        'project.permissions.visibilityDescription':
          'Control who can access this project',
        'project.permissions.publicDescription':
          'Accessible to all authenticated users',
        'project.permissions.privateDescription':
          'Only accessible to organization members',
        'project.permissions.organizationsDescription':
          'Select organizations that can access this project',
        'project.permissions.loadingOrganizations': 'Loading organizations...',
        'project.permissions.noOrganizationsAvailable':
          'No organizations available',
        'project.permissions.cancel': 'Cancel',
        'project.permissions.save': 'Save',
        'project.permissions.saving': 'Saving...',
      }
      return translations[key] || key
    },
  }),
}))

const mockOrganizations = [
  { id: 'org-1', name: 'TUM', slug: 'tum' },
  { id: 'org-2', name: 'LMU', slug: 'lmu' },
  { id: 'org-3', name: 'MIT', slug: 'mit' },
]

describe('ProjectPermissionsPanel', () => {
  const mockOnSave = jest.fn()
  const mockOnCancel = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    // Reset to default superadmin user
    mockUseAuth.mockReturnValue({
      user: {
        id: 'user-1',
        email: 'admin@test.com',
        is_superadmin: true,
      },
    })
    ;(organizationsAPI.getOrganizations as jest.Mock).mockResolvedValue(
      mockOrganizations
    )
    ;(projectsAPI.update as jest.Mock).mockResolvedValue({})
    ;(toast.error as jest.Mock).mockImplementation(() => {})
    ;(toast.success as jest.Mock).mockImplementation(() => {})
  })

  describe('Rendering', () => {
    it('should render permissions panel for superadmin', async () => {
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[mockOrganizations[0]]}
        />
      )

      await waitFor(() => {
        expect(
          screen.getByTestId('project-permissions-panel')
        ).toBeInTheDocument()
      })

      expect(screen.getByText('Visibility')).toBeInTheDocument()
      expect(screen.getByTestId('public-option')).toBeInTheDocument()
      expect(screen.getByTestId('private-option')).toBeInTheDocument()
    })

    it('should show read-only view for non-superadmin users', async () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: 'user-2',
          email: 'user@test.com',
          is_superadmin: false,
        },
      })

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[mockOrganizations[0]]}
        />
      )

      expect(
        screen.getByText('You can only view these permissions')
      ).toBeInTheDocument()
      expect(
        screen.queryByTestId('project-permissions-panel')
      ).not.toBeInTheDocument()
    })

    it('should display initial public visibility correctly', async () => {
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={true}
          initialOrganizations={[]}
        />
      )

      await waitFor(() => {
        const publicRadio = screen.getByTestId(
          'public-radio'
        ) as HTMLInputElement
        expect(publicRadio.checked).toBe(true)
      })
    })

    it('should display initial private visibility correctly', async () => {
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[mockOrganizations[0]]}
        />
      )

      await waitFor(() => {
        const privateRadio = screen.getByTestId(
          'private-radio'
        ) as HTMLInputElement
        expect(privateRadio.checked).toBe(true)
      })
    })
  })

  describe('Visibility Toggle', () => {
    it('should toggle from private to public', async () => {
      const user = userEvent.setup()

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[mockOrganizations[0]]}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('private-radio')).toBeInTheDocument()
      })

      const publicOption = screen.getByTestId('public-option')
      await user.click(publicOption)

      const publicRadio = screen.getByTestId('public-radio') as HTMLInputElement
      expect(publicRadio.checked).toBe(true)
    })

    it('should toggle from public to private', async () => {
      const user = userEvent.setup()

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={true}
          initialOrganizations={[]}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('public-radio')).toBeInTheDocument()
      })

      const privateOption = screen.getByTestId('private-option')
      await user.click(privateOption)

      const privateRadio = screen.getByTestId(
        'private-radio'
      ) as HTMLInputElement
      expect(privateRadio.checked).toBe(true)
    })

    it('should show organization section when private is selected', async () => {
      const user = userEvent.setup()

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={true}
          initialOrganizations={[]}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('public-radio')).toBeInTheDocument()
      })

      const privateOption = screen.getByTestId('private-option')
      await user.click(privateOption)

      await waitFor(() => {
        expect(screen.getByTestId('organization-section')).toBeInTheDocument()
      })
    })

    it('should hide organization section when public is selected', async () => {
      const user = userEvent.setup()

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[mockOrganizations[0]]}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('organization-section')).toBeInTheDocument()
      })

      const publicOption = screen.getByTestId('public-option')
      await user.click(publicOption)

      await waitFor(() => {
        expect(
          screen.queryByTestId('organization-section')
        ).not.toBeInTheDocument()
      })
    })
  })

  describe('Organization Assignment', () => {
    it('should load and display available organizations', async () => {
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[]}
        />
      )

      await waitFor(() => {
        expect(organizationsAPI.getOrganizations).toHaveBeenCalled()
        expect(screen.getByTestId('organization-list')).toBeInTheDocument()
      })

      expect(screen.getByText('TUM')).toBeInTheDocument()
      expect(screen.getByText('LMU')).toBeInTheDocument()
      expect(screen.getByText('MIT')).toBeInTheDocument()
    })

    it('should pre-select initial organizations', async () => {
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[mockOrganizations[0], mockOrganizations[1]]}
        />
      )

      await waitFor(() => {
        const org1Checkbox = screen.getByTestId(
          'organization-checkbox-org-1'
        ) as HTMLInputElement
        const org2Checkbox = screen.getByTestId(
          'organization-checkbox-org-2'
        ) as HTMLInputElement
        const org3Checkbox = screen.getByTestId(
          'organization-checkbox-org-3'
        ) as HTMLInputElement

        expect(org1Checkbox.checked).toBe(true)
        expect(org2Checkbox.checked).toBe(true)
        expect(org3Checkbox.checked).toBe(false)
      })
    })

    it('should toggle organization selection', async () => {
      const user = userEvent.setup()

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[mockOrganizations[0]]}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('organization-list')).toBeInTheDocument()
      })

      const org2Checkbox = screen.getByTestId('organization-checkbox-org-2')
      await user.click(org2Checkbox)

      const checkbox = org2Checkbox as HTMLInputElement
      expect(checkbox.checked).toBe(true)
    })

    it('should deselect organization when clicked again', async () => {
      const user = userEvent.setup()

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[mockOrganizations[0]]}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('organization-list')).toBeInTheDocument()
      })

      const org1Checkbox = screen.getByTestId('organization-checkbox-org-1')
      await user.click(org1Checkbox)

      const checkbox = org1Checkbox as HTMLInputElement
      expect(checkbox.checked).toBe(false)
    })

    it('should show loading state while fetching organizations', () => {
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[]}
        />
      )

      expect(screen.getByText('Loading organizations...')).toBeInTheDocument()
    })

    it('should show message when no organizations available', async () => {
      ;(organizationsAPI.getOrganizations as jest.Mock).mockResolvedValue([])

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[]}
        />
      )

      await waitFor(() => {
        expect(
          screen.getByText('No organizations available')
        ).toBeInTheDocument()
      })
    })

    it('should handle organization API error', async () => {
      const errorMessage = 'Failed to load organizations'
      ;(organizationsAPI.getOrganizations as jest.Mock).mockRejectedValue(
        new Error(errorMessage)
      )

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[]}
        />
      )

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(errorMessage)
      })
    })
  })

  describe('Save Functionality', () => {
    it('should save public project permissions', async () => {
      const user = userEvent.setup()

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[mockOrganizations[0]]}
          onSave={mockOnSave}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('public-radio')).toBeInTheDocument()
      })

      const publicOption = screen.getByTestId('public-option')
      await user.click(publicOption)

      const saveButton = screen.getByTestId('save-button')
      await user.click(saveButton)

      await waitFor(() => {
        expect(projectsAPI.update).toHaveBeenCalledWith('project-1', {
          is_public: true,
          organization_ids: ['org-1'],
        })
        expect(toast.success).toHaveBeenCalledWith(
          'Permissions saved successfully'
        )
        expect(mockOnSave).toHaveBeenCalledWith({
          is_public: true,
          organization_ids: ['org-1'],
        })
      })
    })

    it('should save private project with selected organizations', async () => {
      const user = userEvent.setup()

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[]}
          onSave={mockOnSave}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('organization-list')).toBeInTheDocument()
      })

      // Select organizations
      const org1Checkbox = screen.getByTestId('organization-checkbox-org-1')
      const org2Checkbox = screen.getByTestId('organization-checkbox-org-2')
      await user.click(org1Checkbox)
      await user.click(org2Checkbox)

      const saveButton = screen.getByTestId('save-button')
      await user.click(saveButton)

      await waitFor(() => {
        expect(projectsAPI.update).toHaveBeenCalledWith('project-1', {
          is_public: false,
          organization_ids: ['org-1', 'org-2'],
        })
        expect(mockOnSave).toHaveBeenCalled()
      })
    })

    it('should show saving state during save operation', async () => {
      const user = userEvent.setup()
      let resolveUpdate: any
      ;(projectsAPI.update as jest.Mock).mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveUpdate = resolve
          })
      )

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={true}
          initialOrganizations={[]}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('save-button')).toBeInTheDocument()
      })

      const saveButton = screen.getByTestId('save-button')
      await user.click(saveButton)

      expect(screen.getByText('Saving...')).toBeInTheDocument()
      expect(saveButton).toBeDisabled()

      resolveUpdate({})
      await waitFor(() => {
        expect(screen.getByText('Save')).toBeInTheDocument()
      })
    })

    it('should handle save API error', async () => {
      const user = userEvent.setup()
      const errorMessage = 'Failed to save permissions'
      ;(projectsAPI.update as jest.Mock).mockRejectedValue(
        new Error(errorMessage)
      )

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={true}
          initialOrganizations={[]}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('save-button')).toBeInTheDocument()
      })

      const saveButton = screen.getByTestId('save-button')
      await user.click(saveButton)

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(errorMessage)
        expect(
          screen.getByTestId('project-permissions-error')
        ).toBeInTheDocument()
        expect(screen.getByText(errorMessage)).toBeInTheDocument()
      })
    })
  })

  describe('Validation', () => {
    it('should prevent saving private project without organizations', async () => {
      const user = userEvent.setup()

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[]}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('save-button')).toBeInTheDocument()
      })

      const saveButton = screen.getByTestId('save-button')
      await user.click(saveButton)

      await waitFor(() => {
        expect(projectsAPI.update).not.toHaveBeenCalled()
        expect(
          screen.getByText('Private projects need at least one organization')
        ).toBeInTheDocument()
      })
    })

    it('should allow saving public project without organizations', async () => {
      const user = userEvent.setup()

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={true}
          initialOrganizations={[]}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('save-button')).toBeInTheDocument()
      })

      const saveButton = screen.getByTestId('save-button')
      await user.click(saveButton)

      await waitFor(() => {
        expect(projectsAPI.update).toHaveBeenCalledWith('project-1', {
          is_public: true,
          organization_ids: [],
        })
      })
    })

    it('should show permission error for non-superadmin attempting save', async () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: 'user-2',
          email: 'user@test.com',
          is_superadmin: false,
        },
      })

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[mockOrganizations[0]]}
        />
      )

      // Should show read-only view, no save button
      expect(screen.queryByTestId('save-button')).not.toBeInTheDocument()
    })

    it('should handle null user gracefully', async () => {
      mockUseAuth.mockReturnValue({
        user: null,
      })

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[mockOrganizations[0]]}
        />
      )

      // Should show read-only view when no user
      expect(
        screen.getByText('You can only view these permissions')
      ).toBeInTheDocument()
    })
  })

  describe('Cancel Functionality', () => {
    it('should reset visibility to initial value on cancel', async () => {
      const user = userEvent.setup()

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[mockOrganizations[0]]}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('public-option')).toBeInTheDocument()
      })

      // Change to public
      const publicOption = screen.getByTestId('public-option')
      await user.click(publicOption)

      // Cancel
      const cancelButton = screen.getByTestId('cancel-button')
      await user.click(cancelButton)

      // Should reset to private
      const privateRadio = screen.getByTestId(
        'private-radio'
      ) as HTMLInputElement
      expect(privateRadio.checked).toBe(true)
      expect(mockOnCancel).toHaveBeenCalled()
    })

    it('should reset organization selection on cancel', async () => {
      const user = userEvent.setup()

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[mockOrganizations[0]]}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('organization-list')).toBeInTheDocument()
      })

      // Add another organization
      const org2Checkbox = screen.getByTestId('organization-checkbox-org-2')
      await user.click(org2Checkbox)

      // Cancel
      const cancelButton = screen.getByTestId('cancel-button')
      await user.click(cancelButton)

      // Should reset to initial selection
      await waitFor(() => {
        const org1Checkbox = screen.getByTestId(
          'organization-checkbox-org-1'
        ) as HTMLInputElement
        const org2CheckboxAfter = screen.getByTestId(
          'organization-checkbox-org-2'
        ) as HTMLInputElement

        expect(org1Checkbox.checked).toBe(true)
        expect(org2CheckboxAfter.checked).toBe(false)
      })
    })

    it('should clear error on cancel', async () => {
      const user = userEvent.setup()

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[]}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('save-button')).toBeInTheDocument()
      })

      // Try to save without organizations (triggers error)
      const saveButton = screen.getByTestId('save-button')
      await user.click(saveButton)

      await waitFor(() => {
        expect(
          screen.getByTestId('project-permissions-error')
        ).toBeInTheDocument()
      })

      // Cancel should clear error
      const cancelButton = screen.getByTestId('cancel-button')
      await user.click(cancelButton)

      expect(
        screen.queryByTestId('project-permissions-error')
      ).not.toBeInTheDocument()
    })
  })

  describe('User Role Display (Read-Only)', () => {
    it('should display current visibility in read-only mode', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: 'user-2',
          email: 'user@test.com',
          is_superadmin: false,
        },
      })

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={true}
          initialOrganizations={[]}
        />
      )

      expect(screen.getByText('Public')).toBeInTheDocument()
    })

    it('should display assigned organizations in read-only mode', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: 'user-2',
          email: 'user@test.com',
          is_superadmin: false,
        },
      })

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[mockOrganizations[0], mockOrganizations[1]]}
        />
      )

      expect(screen.getByText('Private')).toBeInTheDocument()
      expect(screen.getByText('TUM')).toBeInTheDocument()
      expect(screen.getByText('LMU')).toBeInTheDocument()
    })

    it('should not show organizations section for public projects in read-only mode', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: 'user-2',
          email: 'user@test.com',
          is_superadmin: false,
        },
      })

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={true}
          initialOrganizations={[]}
        />
      )

      expect(screen.queryByText('Organizations')).not.toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('should have proper ARIA labels for visibility options', async () => {
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[]}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('public-radio')).toBeInTheDocument()
      })

      const publicRadio = screen.getByTestId('public-radio')
      const privateRadio = screen.getByTestId('private-radio')

      expect(publicRadio).toHaveAttribute('type', 'radio')
      expect(privateRadio).toHaveAttribute('type', 'radio')
      expect(publicRadio).toHaveAttribute('name', 'visibility')
      expect(privateRadio).toHaveAttribute('name', 'visibility')
    })

    it('should have proper labels for organization checkboxes', async () => {
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[]}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('organization-list')).toBeInTheDocument()
      })

      const org1Checkbox = screen.getByTestId('organization-checkbox-org-1')
      expect(org1Checkbox).toHaveAttribute('type', 'checkbox')
    })

    it('should disable buttons during save operation', async () => {
      const user = userEvent.setup()
      let resolveUpdate: any
      ;(projectsAPI.update as jest.Mock).mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveUpdate = resolve
          })
      )

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={true}
          initialOrganizations={[]}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('save-button')).toBeInTheDocument()
      })

      const saveButton = screen.getByTestId('save-button')
      const cancelButton = screen.getByTestId('cancel-button')

      await user.click(saveButton)

      expect(saveButton).toBeDisabled()
      expect(cancelButton).toBeDisabled()

      resolveUpdate({})
      await waitFor(() => {
        expect(saveButton).not.toBeDisabled()
      })
    })
  })

  describe('Edge Cases', () => {
    it('should handle empty initial organizations array', async () => {
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[]}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('organization-list')).toBeInTheDocument()
      })

      const org1Checkbox = screen.getByTestId(
        'organization-checkbox-org-1'
      ) as HTMLInputElement
      expect(org1Checkbox.checked).toBe(false)
    })

    it('should handle undefined initial organizations', async () => {
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('organization-list')).toBeInTheDocument()
      })

      // Should render without errors
      expect(screen.getByText('TUM')).toBeInTheDocument()
    })

    it('should handle missing onSave callback', async () => {
      const user = userEvent.setup()

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={true}
          initialOrganizations={[]}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('save-button')).toBeInTheDocument()
      })

      const saveButton = screen.getByTestId('save-button')
      await user.click(saveButton)

      // Should not throw error
      await waitFor(() => {
        expect(projectsAPI.update).toHaveBeenCalled()
      })
    })

    it('should handle missing onCancel callback', async () => {
      const user = userEvent.setup()

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[]}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('cancel-button')).toBeInTheDocument()
      })

      const cancelButton = screen.getByTestId('cancel-button')
      await user.click(cancelButton)

      // Should not throw error
      expect(cancelButton).toBeInTheDocument()
    })

    it('should handle rapid visibility toggles', async () => {
      const user = userEvent.setup()

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialIsPublic={false}
          initialOrganizations={[mockOrganizations[0]]}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('public-option')).toBeInTheDocument()
      })

      const publicOption = screen.getByTestId('public-option')
      const privateOption = screen.getByTestId('private-option')

      // Rapid toggles
      await user.click(publicOption)
      await user.click(privateOption)
      await user.click(publicOption)

      const publicRadio = screen.getByTestId('public-radio') as HTMLInputElement
      expect(publicRadio.checked).toBe(true)
    })
  })
})
