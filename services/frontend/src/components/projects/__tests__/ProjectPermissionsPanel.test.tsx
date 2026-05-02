/**
 * ProjectPermissionsPanel — private/public toggle (org assignment is managed
 * on the dedicated Members page and is read-only here).
 */

import { projectsAPI } from '@/lib/api/projects'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { mockToast } from '@/test-utils/setupTests'
import { ProjectPermissionsPanel } from '../ProjectPermissionsPanel'

const toast = { success: mockToast.success, error: mockToast.error }

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    updateVisibility: jest.fn(),
  },
}))
jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    getOrganizations: jest.fn().mockResolvedValue([]),
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
    t: (key: string) => {
      const translations: Record<string, string> = {
        'project.permissions.noPermission': 'No permission to edit',
        'project.permissions.saveSuccess': 'Permissions saved successfully',
        'project.permissions.viewOnly': 'You can only view these permissions',
        'project.permissions.visibility': 'Visibility',
        'project.permissions.public': 'Public',
        'project.permissions.private': 'Private',
        'project.permissions.organization': 'Organization',
        'project.permissions.organizationManagedElsewhere':
          'Manage organization assignments on the Members page.',
        'project.permissions.visibilityDescription':
          'Control who can access this project',
        'project.permissions.publicDescription':
          'Visible to every authenticated user across all organizations',
        'project.permissions.privateDescription': 'Only you can access',
        'project.permissions.publicRoleLabel': 'Public role',
        'project.permissions.publicRoleDescription':
          'How visitors interact with the project',
        'project.permissions.publicRole.annotator': 'Annotator',
        'project.permissions.publicRole.annotatorDescription':
          'View tasks and create annotations',
        'project.permissions.publicRole.contributor': 'Contributor',
        'project.permissions.publicRole.contributorDescription':
          'Add tasks, annotate, run generation/evaluation',
        'project.permissions.cancel': 'Cancel',
        'project.permissions.save': 'Save',
        'project.permissions.saving': 'Saving...',
      }
      return translations[key] || key
    },
  }),
}))

describe('ProjectPermissionsPanel', () => {
  const mockOnSave = jest.fn()
  const mockOnCancel = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    mockUseAuth.mockReturnValue({
      user: {
        id: 'user-1',
        email: 'admin@test.com',
        is_superadmin: true,
      },
    })
    ;(projectsAPI.updateVisibility as jest.Mock).mockResolvedValue({})
    ;(toast.error as jest.Mock).mockImplementation(() => {})
    ;(toast.success as jest.Mock).mockImplementation(() => {})
  })

  describe('Rendering', () => {
    it('renders private, organization, and public options for superadmin', async () => {
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialVisibility="private"
        />
      )

      await waitFor(() => {
        expect(
          screen.getByTestId('project-permissions-panel')
        ).toBeInTheDocument()
      })

      expect(screen.getByTestId('private-option')).toBeInTheDocument()
      expect(screen.getByTestId('organization-option')).toBeInTheDocument()
      expect(screen.getByTestId('public-option')).toBeInTheDocument()
    })

    it('shows the organization picker section when project is org-scoped', async () => {
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialVisibility="organization"
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('organization-section')).toBeInTheDocument()
      })
    })

    it('renders read-only view for non-creator non-superadmin', () => {
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
          projectCreatorId="someone-else"
          initialVisibility="organization"
        />
      )

      expect(
        screen.getByText('You can only view these permissions')
      ).toBeInTheDocument()
      expect(
        screen.queryByTestId('project-permissions-panel')
      ).not.toBeInTheDocument()
    })

    it('renders editable view for the project creator (non-superadmin)', async () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: 'creator-1',
          email: 'creator@test.com',
          is_superadmin: false,
        },
      })

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          projectCreatorId="creator-1"
          initialVisibility="private"
        />
      )

      await waitFor(() => {
        expect(
          screen.getByTestId('project-permissions-panel')
        ).toBeInTheDocument()
      })
    })

    it('reflects initial public visibility and role', async () => {
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialVisibility="public"
          initialPublicRole="CONTRIBUTOR"
        />
      )

      await waitFor(() => {
        expect(
          (screen.getByTestId('public-radio') as HTMLInputElement).checked
        ).toBe(true)
      })
      expect(
        (screen.getByTestId('public-role-contributor-radio') as HTMLInputElement)
          .checked
      ).toBe(true)
    })
  })

  describe('Visibility switching', () => {
    it('switching to public reveals the role sub-radio', async () => {
      const user = userEvent.setup()
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialVisibility="private"
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('private-radio')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('public-option'))

      await waitFor(() => {
        expect(screen.getByTestId('public-role-section')).toBeInTheDocument()
      })
    })

    it('switching to private hides the role sub-radio', async () => {
      const user = userEvent.setup()
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialVisibility="public"
          initialPublicRole="ANNOTATOR"
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('public-role-section')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('private-option'))

      await waitFor(() => {
        expect(
          screen.queryByTestId('public-role-section')
        ).not.toBeInTheDocument()
      })
    })
  })

  describe('Public role sub-radio', () => {
    it('toggles between annotator and contributor', async () => {
      const user = userEvent.setup()
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialVisibility="public"
          initialPublicRole="ANNOTATOR"
        />
      )

      await waitFor(() => {
        expect(
          (screen.getByTestId(
            'public-role-annotator-radio'
          ) as HTMLInputElement).checked
        ).toBe(true)
      })

      await user.click(screen.getByTestId('public-role-contributor-option'))

      expect(
        (screen.getByTestId('public-role-contributor-radio') as HTMLInputElement)
          .checked
      ).toBe(true)
    })
  })

  describe('Save', () => {
    it('saves public + role payload', async () => {
      const user = userEvent.setup()
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialVisibility="private"
          onSave={mockOnSave}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('public-option')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('public-option'))
      await user.click(screen.getByTestId('public-role-contributor-option'))
      await user.click(screen.getByTestId('save-button'))

      await waitFor(() => {
        expect(projectsAPI.updateVisibility).toHaveBeenCalledWith('project-1', {
          is_public: true,
          public_role: 'CONTRIBUTOR',
        })
        expect(toast.success).toHaveBeenCalledWith(
          'Permissions saved successfully'
        )
      })
    })

    it('saves private payload', async () => {
      const user = userEvent.setup()
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialVisibility="public"
          initialPublicRole="ANNOTATOR"
          onSave={mockOnSave}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('private-option')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('private-option'))
      await user.click(screen.getByTestId('save-button'))

      await waitFor(() => {
        expect(projectsAPI.updateVisibility).toHaveBeenCalledWith('project-1', {
          is_private: true,
        })
      })
    })

    it('handles save API error', async () => {
      const user = userEvent.setup()
      const errorMessage = 'Failed to save permissions'
      ;(projectsAPI.updateVisibility as jest.Mock).mockRejectedValue(
        new Error(errorMessage)
      )

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialVisibility="public"
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('save-button')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('save-button'))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(errorMessage)
        expect(
          screen.getByTestId('project-permissions-error')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Cancel', () => {
    it('resets visibility on cancel', async () => {
      const user = userEvent.setup()
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialVisibility="private"
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByTestId('public-option')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('public-option'))
      await user.click(screen.getByTestId('cancel-button'))

      expect(
        (screen.getByTestId('private-radio') as HTMLInputElement).checked
      ).toBe(true)
      expect(mockOnCancel).toHaveBeenCalled()
    })
  })
})
