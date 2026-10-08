/**
 * @jest-environment jsdom
 *
 * Group scope of the API key dialog: who pays for AI calls on a group's
 * projects (follow the organization / organization provides keys / members'
 * own keys), settable by org admins and by that group's admins.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { OrgApiKeys } from '../OrgApiKeys'

jest.mock('@headlessui/react', () => {
  const Dialog = ({ children, open }: any) =>
    open ? <div data-testid="dialog">{children}</div> : null
  // eslint-disable-next-line react/display-name
  Dialog.Panel = ({ children }: any) => <div>{children}</div>
  // eslint-disable-next-line react/display-name
  Dialog.Title = ({ children }: any) => <h2>{children}</h2>
  return { Dialog }
})

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: 'en' }),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, ...props }: any) => (
    <button {...props}>{children}</button>
  ),
}))

const mockGetSettings = jest.fn()
const mockUpdateSettings = jest.fn()

jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    getOrgApiKeySettings: (...args: any[]) => mockGetSettings(...args),
    updateOrgApiKeySettings: (...args: any[]) => mockUpdateSettings(...args),
    getOrgApiKeyStatus: jest.fn().mockResolvedValue({ api_key_status: {} }),
    getGroups: jest.fn().mockResolvedValue([
      {
        id: 'g-lehrstuhl',
        name: 'LS Guckelberger',
        is_active: true,
        my_role: 'ORG_ADMIN',
      },
    ]),
    listOrgCustomModels: jest.fn().mockResolvedValue([]),
    invalidateCache: jest.fn(),
  },
}))

const groupSettings = (group: boolean | null, org = true) => ({
  require_private_keys: group ?? org,
  group_require_private_keys: group,
  org_require_private_keys: org,
})

describe('OrgApiKeys group "who pays" setting', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetSettings.mockImplementation((_org: string, groupId?: string) =>
      Promise.resolve(
        groupId ? groupSettings(null) : { require_private_keys: true },
      ),
    )
    mockUpdateSettings.mockResolvedValue({ message: 'ok' })
  })

  it('lets a group admin switch their group to org-provided keys', async () => {
    render(
      <OrgApiKeys
        organizationId="org-saar"
        isAdmin={false}
        canManageGroups
        open
        onOpenChange={jest.fn()}
      />,
    )

    const select = await screen.findByTestId('org-api-keys-group-pays-select')
    await waitFor(() =>
      expect(mockGetSettings).toHaveBeenCalledWith('org-saar', 'g-lehrstuhl'),
    )
    expect(select).toHaveValue('inherit')
    expect(
      screen.getByText('organization.apiKeys.groupPaysInheritMembers'),
    ).toBeInTheDocument()
    // The org-wide switch is org-admin territory.
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()

    fireEvent.change(select, { target: { value: 'org' } })

    await waitFor(() =>
      expect(mockUpdateSettings).toHaveBeenCalledWith(
        'org-saar',
        false,
        'g-lehrstuhl',
      ),
    )
    expect(
      await screen.findByText('organization.apiKeys.groupPaysSaved'),
    ).toBeInTheDocument()
    expect(select).toHaveValue('org')
  })

  it('sends null to make the group follow the organization again', async () => {
    mockGetSettings.mockImplementation((_org: string, groupId?: string) =>
      Promise.resolve(
        groupId ? groupSettings(false, false) : { require_private_keys: false },
      ),
    )
    render(
      <OrgApiKeys
        organizationId="org-saar"
        isAdmin={false}
        canManageGroups
        open
        onOpenChange={jest.fn()}
      />,
    )

    const select = await screen.findByTestId('org-api-keys-group-pays-select')
    await waitFor(() => expect(select).toHaveValue('org'))
    expect(
      screen.getByText('organization.apiKeys.groupPaysInheritOrg'),
    ).toBeInTheDocument()

    fireEvent.change(select, { target: { value: 'inherit' } })

    await waitFor(() =>
      expect(mockUpdateSettings).toHaveBeenCalledWith(
        'org-saar',
        null,
        'g-lehrstuhl',
      ),
    )
  })

  it('shows org admins the org-wide switch and the group setting per scope', async () => {
    render(
      <OrgApiKeys
        organizationId="org-saar"
        isAdmin
        open
        onOpenChange={jest.fn()}
      />,
    )

    expect(await screen.findByRole('switch')).toBeInTheDocument()
    expect(
      screen.queryByTestId('org-api-keys-group-pays-select'),
    ).not.toBeInTheDocument()

    fireEvent.change(await screen.findByTestId('org-api-keys-scope-select'), {
      target: { value: 'g-lehrstuhl' },
    })

    const select = await screen.findByTestId('org-api-keys-group-pays-select')
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    fireEvent.change(select, { target: { value: 'members' } })
    await waitFor(() =>
      expect(mockUpdateSettings).toHaveBeenCalledWith(
        'org-saar',
        true,
        'g-lehrstuhl',
      ),
    )
  })

  it('reports a failed save and keeps the previous choice', async () => {
    mockUpdateSettings.mockRejectedValue({
      response: { data: { detail: 'Nope' } },
    })
    render(
      <OrgApiKeys
        organizationId="org-saar"
        isAdmin={false}
        canManageGroups
        open
        onOpenChange={jest.fn()}
      />,
    )

    const select = await screen.findByTestId('org-api-keys-group-pays-select')
    await waitFor(() => expect(mockGetSettings).toHaveBeenCalledTimes(2))
    fireEvent.change(select, { target: { value: 'org' } })

    expect(await screen.findByText('Nope')).toBeInTheDocument()
    expect(select).toHaveValue('inherit')
  })
})
