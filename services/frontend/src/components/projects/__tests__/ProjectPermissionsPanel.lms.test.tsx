/**
 * ProjectPermissionsPanel: organizations attached through a learning platform
 * connection (`attached_via: 'lti'`) are locked. They stay checked, their
 * group cannot be changed, a note names them, and a 409
 * `lti_attachment_conflict` shows translated copy instead of the API text.
 */

import { organizationsAPI } from '@/lib/api/organizations'
import { projectsAPI } from '@/lib/api/projects'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ProjectPermissionsPanel } from '../ProjectPermissionsPanel'

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: { updateVisibility: jest.fn() },
}))
jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    getOrganizations: jest.fn(),
    getGroups: jest.fn(),
  },
}))
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'owner-1', is_superadmin: false } }),
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, string>) =>
      vars ? `${key} ${JSON.stringify(vars)}` : key,
  }),
}))

const lmsOrg = {
  id: 'uni',
  name: 'Uni',
  group_id: 'chair',
  attached_via: 'lti' as const,
}
const manualOrg = {
  id: 'other',
  name: 'Other',
  attached_via: 'manual' as const,
}

function renderPanel(visibility: 'organization' | 'private' = 'organization') {
  return render(
    <ProjectPermissionsPanel
      projectId="p1"
      projectCreatorId="owner-1"
      initialVisibility={visibility}
      initialOrganizations={
        visibility === 'private' ? [lmsOrg] : [lmsOrg, manualOrg]
      }
    />,
  )
}

beforeEach(() => {
  jest.clearAllMocks()
  ;(organizationsAPI.getOrganizations as jest.Mock).mockResolvedValue([
    { id: 'uni', name: 'Uni', role: 'CONTRIBUTOR' },
    { id: 'other', name: 'Other', role: 'CONTRIBUTOR' },
  ])
  ;(organizationsAPI.getGroups as jest.Mock).mockImplementation(
    (orgId: string) =>
      Promise.resolve(
        orgId === 'uni'
          ? [
              {
                id: 'chair',
                name: 'Lehrstuhl',
                is_active: true,
                is_member: true,
              },
            ]
          : [],
      ),
  )
  ;(projectsAPI.updateVisibility as jest.Mock).mockResolvedValue({})
})

describe('ProjectPermissionsPanel with LMS-linked organizations', () => {
  it('locks the linked organization and names it', async () => {
    const user = userEvent.setup()
    renderPanel()

    const checkbox = await screen.findByTestId('organization-checkbox-uni')
    expect(checkbox).toBeChecked()
    expect(checkbox).toBeDisabled()
    expect(screen.getByTestId('organization-lms-badge-uni')).toHaveTextContent(
      'project.permissions.lmsBadge',
    )
    expect(
      screen.queryByTestId('organization-lms-badge-other'),
    ).not.toBeInTheDocument()
    expect(
      screen.getByTestId('project-permissions-lms-note'),
    ).toHaveTextContent('project.permissions.lmsNote {"organizations":"Uni"}')
    const select = await screen.findByTestId('organization-group-select-uni')
    expect(select).toBeDisabled()
    expect(select).toHaveValue('chair')

    // Clicking the locked box changes nothing; the manual one toggles.
    await user.click(checkbox)
    expect(checkbox).toBeChecked()
    const other = screen.getByTestId('organization-checkbox-other')
    await user.click(other)
    expect(other).not.toBeChecked()

    await user.click(screen.getByTestId('save-button'))
    await waitFor(() =>
      expect(projectsAPI.updateVisibility).toHaveBeenCalledWith('p1', {
        is_private: false,
        organization_attachments: [
          { organization_id: 'uni', group_id: 'chair' },
        ],
      }),
    )
  })

  it('shows the note on a private linked exam too', async () => {
    renderPanel('private')
    expect(
      screen.getByTestId('project-permissions-lms-note'),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('organization-section')).not.toBeInTheDocument()
  })

  it('translates the LMS conflict error', async () => {
    const user = userEvent.setup()
    ;(projectsAPI.updateVisibility as jest.Mock).mockRejectedValue(
      Object.assign(new Error('Uni is attached through a learning platform'), {
        response: {
          status: 409,
          data: {
            detail: { code: 'lti_attachment_conflict', message: 'English' },
          },
        },
      }),
    )
    renderPanel()
    await screen.findByTestId('organization-checkbox-uni')

    await user.click(screen.getByTestId('save-button'))

    expect(
      await screen.findByTestId('project-permissions-error'),
    ).toHaveTextContent('project.permissions.lmsConflict')
  })

  it('keeps other API errors as they are', async () => {
    const user = userEvent.setup()
    ;(projectsAPI.updateVisibility as jest.Mock).mockRejectedValue(
      Object.assign(new Error('Organization x not found'), {
        response: { status: 404, data: { detail: 'Organization x not found' } },
      }),
    )
    renderPanel()
    await screen.findByTestId('organization-checkbox-uni')

    await user.click(screen.getByTestId('save-button'))

    expect(
      await screen.findByTestId('project-permissions-error'),
    ).toHaveTextContent('Organization x not found')
  })
})
