/**
 * @jest-environment jsdom
 *
 * ProjectBillingCard — the "Abrechnung" sidebar card on the project detail
 * page. Wording matrix over the linked org's api-key settings:
 *   - org linked + require_private_keys=false → org pays (names the org)
 *   - org linked + require_private_keys=true  → personal API key
 *   - settings request fails (non-member 403) → depends-on-access (quiet)
 *   - no org linked                            → personal API key, no request
 * plus the `project-billing-extended` slot hosting the extended line.
 */
import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'

import { registerSlot } from '@/lib/extensions/slots'
import { ProjectBillingCard } from '../ProjectBillingCard'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, any>) =>
      vars && typeof vars === 'object'
        ? `${key}:${Object.values(vars).join(',')}`
        : key,
    locale: 'de',
  }),
}))

const mockGetSettings = jest.fn()
jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    getOrgApiKeySettings: (...a: any[]) => mockGetSettings(...a),
  },
}))

const orgProject = {
  id: 'p1',
  organizations: [{ id: 'org-1', name: 'Uni Testhausen' }],
}

beforeEach(() => {
  jest.clearAllMocks()
  registerSlot('project-billing-extended', null as any)
})

describe('ProjectBillingCard', () => {
  it('says the org pays (naming it) when the org allows shared keys', async () => {
    mockGetSettings.mockResolvedValue({ require_private_keys: false })
    render(<ProjectBillingCard project={orgProject} />)
    expect(screen.getByText('project.billing.title')).toBeInTheDocument()
    expect(
      await screen.findByText('project.billing.orgPays:Uni Testhausen'),
    ).toBeInTheDocument()
    expect(mockGetSettings).toHaveBeenCalledWith('org-1')
  })

  it('says personal keys when the org requires private keys', async () => {
    mockGetSettings.mockResolvedValue({ require_private_keys: true })
    render(<ProjectBillingCard project={orgProject} />)
    expect(
      await screen.findByText('project.billing.personalKey'),
    ).toBeInTheDocument()
  })

  it('falls back to depends-on-access when the settings request fails', async () => {
    mockGetSettings.mockRejectedValue(new Error('403'))
    render(<ProjectBillingCard project={orgProject} />)
    expect(
      await screen.findByText('project.billing.dependsOnAccess'),
    ).toBeInTheDocument()
  })

  it('says personal keys without any request when no org is linked', async () => {
    render(<ProjectBillingCard project={{ id: 'p2' }} />)
    expect(
      await screen.findByText('project.billing.personalKey'),
    ).toBeInTheDocument()
    expect(mockGetSettings).not.toHaveBeenCalled()
  })

  it('hosts the project-billing-extended slot with the project prop', async () => {
    mockGetSettings.mockResolvedValue({ require_private_keys: true })
    const Extra = ({ project }: any) => (
      <div data-testid="billing-extra">{project.id}</div>
    )
    registerSlot('project-billing-extended', Extra)
    render(<ProjectBillingCard project={orgProject} />)
    expect(screen.getByTestId('billing-extra')).toHaveTextContent('p1')
    await waitFor(() => expect(mockGetSettings).toHaveBeenCalled())
  })
})
