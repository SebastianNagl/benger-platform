/**
 * ProjectPermissionsPanel — private/public toggle (org assignment is managed
 * on the dedicated Members page and is read-only here).
 */

import { SettingRiskProvider } from '@/components/shared/settingRisk'
import { organizationsAPI } from '@/lib/api/organizations'
import { projectsAPI } from '@/lib/api/projects'
import { mockToast } from '@/test-utils/setupTests'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ProjectPermissionsPanel } from '../ProjectPermissionsPanel'
import { registerProjectSettingRisks } from '../projectSettingRisks'

/** Past the shared auto-save delay (2 s). */
const SAVED = { timeout: 4000 }

const toast = { success: mockToast.success, error: mockToast.error }

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    updateVisibility: jest.fn(),
  },
}))
jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    getOrganizations: jest.fn().mockResolvedValue([]),
    getGroups: jest.fn().mockResolvedValue([]),
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
        'project.permissions.saving': 'Saving...',
      }
      return translations[key] || key
    },
  }),
}))

describe('ProjectPermissionsPanel', () => {
  const mockOnSave = jest.fn()

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
    ;(organizationsAPI.getOrganizations as jest.Mock).mockResolvedValue([])
    ;(toast.error as jest.Mock).mockImplementation(() => {})
    ;(toast.success as jest.Mock).mockImplementation(() => {})
  })

  describe('Rendering', () => {
    it('renders private, organization, and public options for superadmin', async () => {
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialVisibility="private"
        />,
      )

      await waitFor(() => {
        expect(
          screen.getByTestId('project-permissions-panel'),
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
        />,
      )

      await waitFor(() => {
        expect(screen.getByTestId('organization-section')).toBeInTheDocument()
      })
    })

    it('lets an org admin of an attached org edit', () => {
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
          effectiveRole="ORG_ADMIN"
          initialVisibility="organization"
        />,
      )

      expect(screen.getByTestId('private-radio')).toBeEnabled()
      expect(
        screen.queryByTestId('project-permissions-readonly'),
      ).not.toBeInTheDocument()
    })

    it('stays read-only for a contributor', () => {
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
          effectiveRole="CONTRIBUTOR"
          initialVisibility="organization"
        />,
      )

      expect(screen.getByTestId('private-radio')).toBeDisabled()
      expect(screen.queryByTestId('save-button')).not.toBeInTheDocument()
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
        />,
      )

      expect(
        screen.getByText('You can only view these permissions'),
      ).toBeInTheDocument()
      // The whole setting stays visible, greyed out and without a way to save.
      expect(screen.getByTestId('organization-radio')).toBeDisabled()
      expect(screen.getByTestId('organization-radio')).toBeChecked()
      expect(screen.getByTestId('private-radio')).toBeDisabled()
      expect(screen.getByTestId('public-radio')).toBeDisabled()
      expect(screen.queryByTestId('save-button')).not.toBeInTheDocument()
      expect(screen.queryByTestId('cancel-button')).not.toBeInTheDocument()
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
        />,
      )

      await waitFor(() => {
        expect(
          screen.getByTestId('project-permissions-panel'),
        ).toBeInTheDocument()
      })
    })

    it('reflects initial public visibility and role', async () => {
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialVisibility="public"
          initialPublicRole="CONTRIBUTOR"
        />,
      )

      await waitFor(() => {
        expect(
          (screen.getByTestId('public-radio') as HTMLInputElement).checked,
        ).toBe(true)
      })
      expect(
        (
          screen.getByTestId(
            'public-role-contributor-radio',
          ) as HTMLInputElement
        ).checked,
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
        />,
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
        />,
      )

      await waitFor(() => {
        expect(screen.getByTestId('public-role-section')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('private-option'))

      await waitFor(() => {
        expect(
          screen.queryByTestId('public-role-section'),
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
        />,
      )

      await waitFor(() => {
        expect(
          (
            screen.getByTestId(
              'public-role-annotator-radio',
            ) as HTMLInputElement
          ).checked,
        ).toBe(true)
      })

      // CONTRIBUTOR opens every signed-in account to full export: the radio
      // only switches after an explicit confirmation.
      await user.click(screen.getByTestId('public-role-contributor-option'))
      expect(
        (
          screen.getByTestId(
            'public-role-contributor-radio',
          ) as HTMLInputElement
        ).checked,
      ).toBe(false)
      await waitFor(() =>
        expect(
          screen.getByTestId('confirm-dialog-confirm-button'),
        ).toBeInTheDocument(),
      )
      await user.click(screen.getByTestId('confirm-dialog-confirm-button'))

      expect(
        (
          screen.getByTestId(
            'public-role-contributor-radio',
          ) as HTMLInputElement
        ).checked,
      ).toBe(true)
    })

    it('keeps the annotator role when the contributor confirmation is cancelled', async () => {
      const user = userEvent.setup()
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialVisibility="public"
          initialPublicRole="ANNOTATOR"
        />,
      )

      await user.click(screen.getByTestId('public-role-contributor-option'))
      await waitFor(() =>
        expect(
          screen.getByTestId('confirm-dialog-cancel-button'),
        ).toBeInTheDocument(),
      )
      await user.click(screen.getByTestId('confirm-dialog-cancel-button'))

      expect(
        (screen.getByTestId('public-role-annotator-radio') as HTMLInputElement)
          .checked,
      ).toBe(true)
    })

    it('needs no confirmation when the saved role already is contributor', async () => {
      const user = userEvent.setup()
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialVisibility="public"
          initialPublicRole="CONTRIBUTOR"
        />,
      )

      await user.click(screen.getByTestId('public-role-annotator-option'))
      await user.click(screen.getByTestId('public-role-contributor-option'))

      expect(
        screen.queryByTestId('confirm-dialog-confirm-button'),
      ).not.toBeInTheDocument()
      expect(
        (
          screen.getByTestId(
            'public-role-contributor-radio',
          ) as HTMLInputElement
        ).checked,
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
        />,
      )

      await waitFor(() => {
        expect(screen.getByTestId('public-option')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('public-option'))
      await user.click(screen.getByTestId('public-role-contributor-option'))
      await user.click(
        await screen.findByTestId('confirm-dialog-confirm-button'),
      )

      // Saved on its own (no save button), with the one saved toast.
      await waitFor(() => {
        expect(projectsAPI.updateVisibility).toHaveBeenCalledWith('project-1', {
          is_public: true,
          public_role: 'CONTRIBUTOR',
        })
        expect(toast.success).toHaveBeenCalledWith('shared.autoSave.saved')
      }, SAVED)
      expect(projectsAPI.updateVisibility).toHaveBeenCalledTimes(1)
      expect(toast.success).toHaveBeenCalledTimes(1)
    })

    it('saves private payload', async () => {
      const user = userEvent.setup()
      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialVisibility="public"
          initialPublicRole="ANNOTATOR"
          onSave={mockOnSave}
        />,
      )

      await waitFor(() => {
        expect(screen.getByTestId('private-option')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('private-option'))

      await waitFor(() => {
        expect(projectsAPI.updateVisibility).toHaveBeenCalledWith('project-1', {
          is_private: true,
        })
      }, SAVED)
    })

    it('handles save API error', async () => {
      const user = userEvent.setup()
      const errorMessage = 'Failed to save permissions'
      ;(projectsAPI.updateVisibility as jest.Mock).mockRejectedValue(
        new Error(errorMessage),
      )

      render(
        <ProjectPermissionsPanel
          projectId="project-1"
          initialVisibility="public"
        />,
      )

      await user.click(screen.getByTestId('private-option'))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(errorMessage)
        expect(
          screen.getByTestId('project-permissions-error'),
        ).toBeInTheDocument()
      }, SAVED)
      expect(toast.success).not.toHaveBeenCalled()
    })
  })

  describe('Risky change confirmation', () => {
    beforeAll(() => registerProjectSettingRisks())
    const renderGated = () =>
      render(
        <SettingRiskProvider
          context={{ project: null, runningExam: false, submittedCount: 0 }}
        >
          <ProjectPermissionsPanel
            projectId="project-1"
            initialVisibility="private"
          />
        </SettingRiskProvider>,
      )

    it('asks before widening who sees the project and keeps it on cancel', async () => {
      const user = userEvent.setup()
      renderGated()
      await user.click(screen.getByTestId('public-option'))
      await user.click(
        await screen.findByTestId('confirm-dialog-cancel-button'),
      )
      expect(
        (screen.getByTestId('private-radio') as HTMLInputElement).checked,
      ).toBe(true)
      await new Promise((r) => setTimeout(r, 2500))
      expect(projectsAPI.updateVisibility).not.toHaveBeenCalled()
    })

    it('applies and saves the change once confirmed', async () => {
      const user = userEvent.setup()
      renderGated()
      await user.click(screen.getByTestId('public-option'))
      await user.click(
        await screen.findByTestId('confirm-dialog-confirm-button'),
      )
      await waitFor(() => {
        expect(projectsAPI.updateVisibility).toHaveBeenCalledWith('project-1', {
          is_public: true,
          public_role: 'ANNOTATOR',
        })
      }, SAVED)
    })

    it('asks once for an organization choice, not again while its organizations are picked', async () => {
      ;(organizationsAPI.getOrganizations as jest.Mock).mockResolvedValue([
        { id: 'org-a', name: 'Org A', slug: 'org-a', role: 'ORG_ADMIN' },
        { id: 'org-b', name: 'Org B', slug: 'org-b', role: 'ORG_ADMIN' },
      ])
      const user = userEvent.setup()
      renderGated()
      await user.click(screen.getByTestId('organization-option'))
      await user.click(
        await screen.findByTestId('confirm-dialog-confirm-button'),
      )
      await waitFor(() =>
        expect(
          screen.queryByTestId('confirm-dialog-confirm-button'),
        ).not.toBeInTheDocument(),
      )
      await user.click(await screen.findByTestId('organization-checkbox-org-a'))
      await user.click(screen.getByTestId('organization-checkbox-org-b'))
      expect(
        screen.queryByTestId('confirm-dialog-confirm-button'),
      ).not.toBeInTheDocument()
      await waitFor(() => {
        expect(projectsAPI.updateVisibility).toHaveBeenCalledWith('project-1', {
          is_private: false,
          organization_attachments: [
            { organization_id: 'org-a', group_id: null },
            { organization_id: 'org-b', group_id: null },
          ],
        })
      }, SAVED)
      expect(projectsAPI.updateVisibility).toHaveBeenCalledTimes(1)
    })

    it('asks again for another visibility while a confirmed one is not saved yet', async () => {
      const user = userEvent.setup()
      renderGated()
      await user.click(screen.getByTestId('organization-option'))
      await user.click(
        await screen.findByTestId('confirm-dialog-confirm-button'),
      )
      await user.click(screen.getByTestId('public-option'))
      await user.click(
        await screen.findByTestId('confirm-dialog-cancel-button'),
      )
      expect(
        (screen.getByTestId('organization-radio') as HTMLInputElement).checked,
      ).toBe(true)
    })

    it('asks before an undo gives the public back the contributor role', async () => {
      const user = userEvent.setup()
      render(
        <SettingRiskProvider
          context={{ project: null, runningExam: false, submittedCount: 0 }}
        >
          <ProjectPermissionsPanel
            projectId="project-1"
            initialVisibility="public"
            initialPublicRole="CONTRIBUTOR"
          />
        </SettingRiskProvider>,
      )
      await user.click(screen.getByTestId('public-role-annotator-radio'))
      await waitFor(() => {
        expect(projectsAPI.updateVisibility).toHaveBeenCalledWith('project-1', {
          is_public: true,
          public_role: 'ANNOTATOR',
        })
      }, SAVED)
      const savedToast = (mockToast.addToast as jest.Mock).mock.calls.find(
        ([, type, , options]) => type === 'success' && options?.action,
      )
      act(() => savedToast![3].action.onClick())
      expect(
        await screen.findByText(
          /project\.permissions\.publicContributorConfirm\.message/,
        ),
      ).toBeInTheDocument()
      await user.click(screen.getByTestId('confirm-dialog-cancel-button'))
      expect(
        (screen.getByTestId('public-role-annotator-radio') as HTMLInputElement)
          .checked,
      ).toBe(true)
      await new Promise((r) => setTimeout(r, 2500))
      expect(projectsAPI.updateVisibility).toHaveBeenCalledTimes(1)
    })

    it('asks for the contributor role when switching back to public with it', async () => {
      const user = userEvent.setup()
      const { rerender } = render(
        <SettingRiskProvider
          context={{ project: null, runningExam: false, submittedCount: 0 }}
        >
          <ProjectPermissionsPanel
            projectId="project-1"
            initialVisibility="public"
            initialPublicRole="CONTRIBUTOR"
          />
        </SettingRiskProvider>,
      )
      await user.click(screen.getByTestId('private-option'))
      await user.click(
        await screen.findByTestId('confirm-dialog-confirm-button'),
      )
      await waitFor(() => {
        expect(projectsAPI.updateVisibility).toHaveBeenCalledWith('project-1', {
          is_private: true,
        })
      }, SAVED)
      // The refetched project is private now.
      rerender(
        <SettingRiskProvider
          context={{ project: null, runningExam: false, submittedCount: 0 }}
        >
          <ProjectPermissionsPanel
            projectId="project-1"
            initialVisibility="private"
            initialPublicRole="CONTRIBUTOR"
          />
        </SettingRiskProvider>,
      )
      await waitFor(() =>
        expect(
          screen.queryByTestId('confirm-dialog-confirm-button'),
        ).not.toBeInTheDocument(),
      )
      await user.click(screen.getByTestId('public-option'))
      expect(
        await screen.findByText(
          /project\.permissions\.publicContributorConfirm\.message/,
        ),
      ).toBeInTheDocument()
    })

    it('asks before an undo widens who sees the project and keeps the saved audience on cancel', async () => {
      const user = userEvent.setup()
      render(
        <SettingRiskProvider
          context={{ project: null, runningExam: false, submittedCount: 0 }}
        >
          <ProjectPermissionsPanel
            projectId="project-1"
            initialVisibility="public"
          />
        </SettingRiskProvider>,
      )
      await user.click(screen.getByTestId('private-option'))
      await user.click(
        await screen.findByTestId('confirm-dialog-confirm-button'),
      )
      await waitFor(() => {
        expect(projectsAPI.updateVisibility).toHaveBeenCalledWith('project-1', {
          is_private: true,
        })
      }, SAVED)
      const savedToast = (mockToast.addToast as jest.Mock).mock.calls.find(
        ([, type, , options]) => type === 'success' && options?.action,
      )
      expect(savedToast).toBeDefined()
      act(() => savedToast![3].action.onClick())
      await user.click(
        await screen.findByTestId('confirm-dialog-cancel-button'),
      )
      expect(
        (screen.getByTestId('private-radio') as HTMLInputElement).checked,
      ).toBe(true)
      await new Promise((r) => setTimeout(r, 2500))
      expect(projectsAPI.updateVisibility).toHaveBeenCalledTimes(1)
    })
  })
})
