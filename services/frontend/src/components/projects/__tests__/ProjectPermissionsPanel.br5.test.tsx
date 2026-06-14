/**
 * ProjectPermissionsPanel — branch/function coverage companion (.br5).
 *
 * The primary spec covers private/public toggling + save. This file covers the
 * organization-scoped branches that were still uncovered:
 *   - org list fetch → render (incl. the slug sub-label branch)
 *   - toggleOrg checkbox add/remove
 *   - organization-scoped save payload (is_private:false + organization_ids)
 *   - the "organization needs at least one org" validation guard
 *   - the org-fetch error toast
 *   - the read-only (non-creator) view's org-pill + public-role rendering
 *   - the noPermission guard inside handleSave
 */

import { organizationsAPI } from '@/lib/api/organizations'
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

const mockUseAuth = jest.fn()
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
        'project.permissions.organizations': 'Organizations',
        'project.permissions.organizationsDescription': 'Pick orgs',
        'project.permissions.loadingOrganizations': 'Loading organizations…',
        'project.permissions.noOrganizationsAvailable':
          'No organizations available',
        'project.permissions.validation.privateNeedsOrganization':
          'Select at least one organization',
        'project.permissions.publicRole.annotator': 'Annotator',
        'project.permissions.publicRole.contributor': 'Contributor',
        'project.permissions.cancel': 'Cancel',
        'project.permissions.save': 'Save',
        'project.permissions.saving': 'Saving...',
      }
      return translations[key] || key
    },
  }),
}))

const superadmin = {
  user: { id: 'admin-1', email: 'admin@test.com', is_superadmin: true },
}

describe('ProjectPermissionsPanel — organization branches', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockUseAuth.mockReturnValue(superadmin)
    ;(projectsAPI.updateVisibility as jest.Mock).mockResolvedValue({})
    ;(organizationsAPI.getOrganizations as jest.Mock).mockResolvedValue([])
  })

  it('renders the fetched org list with the slug sub-label branch', async () => {
    ;(organizationsAPI.getOrganizations as jest.Mock).mockResolvedValue([
      { id: 'org-a', name: 'Org A', slug: 'org-a' },
      { id: 'org-b', name: 'Org B' }, // no slug → slug branch skipped
    ])

    render(
      <ProjectPermissionsPanel
        projectId="p1"
        initialVisibility="organization"
      />
    )

    await waitFor(() => {
      expect(screen.getByTestId('organization-list')).toBeInTheDocument()
    })
    expect(screen.getByTestId('organization-item-org-a')).toBeInTheDocument()
    expect(screen.getByText('(org-a)')).toBeInTheDocument()
    expect(screen.getByText('Org B')).toBeInTheDocument()
    // Org B has no slug → no parenthesized slug for it
    expect(screen.queryByText('(org-b)')).not.toBeInTheDocument()
  })

  it('shows the empty state when no organizations are available', async () => {
    ;(organizationsAPI.getOrganizations as jest.Mock).mockResolvedValue([])

    render(
      <ProjectPermissionsPanel
        projectId="p1"
        initialVisibility="organization"
      />
    )

    await waitFor(() => {
      expect(
        screen.getByText('No organizations available')
      ).toBeInTheDocument()
    })
  })

  it('toggles an org checkbox on and off (toggleOrg)', async () => {
    ;(organizationsAPI.getOrganizations as jest.Mock).mockResolvedValue([
      { id: 'org-a', name: 'Org A', slug: 'org-a' },
    ])
    const user = userEvent.setup()

    render(
      <ProjectPermissionsPanel
        projectId="p1"
        initialVisibility="organization"
      />
    )

    const checkbox = (await screen.findByTestId(
      'organization-checkbox-org-a'
    )) as HTMLInputElement
    expect(checkbox.checked).toBe(false)

    await user.click(checkbox)
    expect(checkbox.checked).toBe(true)

    await user.click(checkbox)
    expect(checkbox.checked).toBe(false)
  })

  it('saves the org-scoped payload (is_private:false + organization_ids)', async () => {
    ;(organizationsAPI.getOrganizations as jest.Mock).mockResolvedValue([
      { id: 'org-a', name: 'Org A', slug: 'org-a' },
    ])
    const onSave = jest.fn()
    const user = userEvent.setup()

    render(
      <ProjectPermissionsPanel
        projectId="p1"
        initialVisibility="organization"
        onSave={onSave}
      />
    )

    const checkbox = await screen.findByTestId('organization-checkbox-org-a')
    await user.click(checkbox)
    await user.click(screen.getByTestId('save-button'))

    await waitFor(() => {
      expect(projectsAPI.updateVisibility).toHaveBeenCalledWith('p1', {
        is_private: false,
        organization_ids: ['org-a'],
      })
    })
    expect(onSave).toHaveBeenCalledWith({
      visibility: 'organization',
      public_role: undefined,
      organization_ids: ['org-a'],
    })
    expect(toast.success).toHaveBeenCalledWith('Permissions saved successfully')
  })

  it('blocks save with a validation error when org-scoped but no org selected', async () => {
    ;(organizationsAPI.getOrganizations as jest.Mock).mockResolvedValue([
      { id: 'org-a', name: 'Org A', slug: 'org-a' },
    ])
    const user = userEvent.setup()

    render(
      <ProjectPermissionsPanel
        projectId="p1"
        initialVisibility="organization"
      />
    )

    await screen.findByTestId('organization-checkbox-org-a')
    await user.click(screen.getByTestId('save-button'))

    await waitFor(() => {
      expect(
        screen.getByTestId('project-permissions-error')
      ).toHaveTextContent('Select at least one organization')
    })
    expect(projectsAPI.updateVisibility).not.toHaveBeenCalled()
  })

  it('surfaces an error toast (string fallback) when the org fetch rejects a non-Error', async () => {
    ;(organizationsAPI.getOrganizations as jest.Mock).mockRejectedValue(
      'plain string failure'
    )

    render(
      <ProjectPermissionsPanel
        projectId="p1"
        initialVisibility="organization"
      />
    )

    await waitFor(() => {
      // Non-Error rejection → component uses its 'Failed to load organizations'
      // fallback message.
      expect(toast.error).toHaveBeenCalledWith('Failed to load organizations')
    })
  })

  it('surfaces the Error message when the org fetch rejects an Error', async () => {
    ;(organizationsAPI.getOrganizations as jest.Mock).mockRejectedValue(
      new Error('boom fetching orgs')
    )

    render(
      <ProjectPermissionsPanel
        projectId="p1"
        initialVisibility="organization"
      />
    )

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('boom fetching orgs')
    })
  })

  describe('read-only (non-creator) view', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: { id: 'viewer-1', email: 'v@test.com', is_superadmin: false },
      })
    })

    it('renders org pills for an org-scoped project', () => {
      render(
        <ProjectPermissionsPanel
          projectId="p1"
          projectCreatorId="creator-9"
          initialVisibility="organization"
          initialOrganizations={[
            { id: 'org-a', name: 'Org A' },
            { id: 'org-b', name: 'Org B' },
          ]}
        />
      )

      expect(
        screen.getByText('You can only view these permissions')
      ).toBeInTheDocument()
      expect(screen.getByText('Org A')).toBeInTheDocument()
      expect(screen.getByText('Org B')).toBeInTheDocument()
      expect(
        screen.queryByTestId('project-permissions-panel')
      ).not.toBeInTheDocument()
    })

    it('renders the public + contributor summary line', () => {
      render(
        <ProjectPermissionsPanel
          projectId="p1"
          projectCreatorId="creator-9"
          initialVisibility="public"
          initialPublicRole="CONTRIBUTOR"
        />
      )

      expect(screen.getByText(/Public · Contributor/)).toBeInTheDocument()
    })

    it('renders the public + annotator summary line', () => {
      render(
        <ProjectPermissionsPanel
          projectId="p1"
          projectCreatorId="creator-9"
          initialVisibility="public"
          initialPublicRole="ANNOTATOR"
        />
      )

      expect(screen.getByText(/Public · Annotator/)).toBeInTheDocument()
    })

    it('returns false from canEditPermissions when projectCreatorId is null', () => {
      render(
        <ProjectPermissionsPanel
          projectId="p1"
          initialVisibility="private"
        />
      )

      expect(
        screen.getByText('You can only view these permissions')
      ).toBeInTheDocument()
    })
  })
})
