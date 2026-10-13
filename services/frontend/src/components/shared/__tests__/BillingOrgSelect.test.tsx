/**
 * @jest-environment jsdom
 */

import {
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from '@testing-library/react'

import { useBillingOrganization } from '@/hooks/useBillingOrganization'
import { BillingOrgSelect } from '../BillingOrgSelect'

jest.mock('@/lib/api', () => ({
  api: {
    getBillingOptions: jest.fn(),
  },
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, string>) =>
      vars?.name ? `${key}:${vars.name}` : key,
  }),
}))

import { api } from '@/lib/api'

const mockGetBillingOptions = api.getBillingOptions as jest.Mock

const TWO_ORGS = {
  default_organization_id: 'org-tum',
  options: [
    { id: 'org-gsj', name: 'GSJ', providers: ['OpenAI', 'DeepInfra'] },
    { id: 'org-tum', name: 'TUM', providers: ['OpenAI'] },
  ],
}

beforeEach(() => {
  mockGetBillingOptions.mockReset()
  window.localStorage.clear()
})

describe('BillingOrgSelect', () => {
  it('renders nothing with fewer than two options', async () => {
    mockGetBillingOptions.mockResolvedValue({
      default_organization_id: 'org-tum',
      options: [TWO_ORGS.options[1]],
    })
    const { container } = render(<BillingOrgSelect projectId="p1" />)
    await waitFor(() =>
      expect(mockGetBillingOptions).toHaveBeenCalledWith('p1'),
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('lists the default and every org with its providers', async () => {
    mockGetBillingOptions.mockResolvedValue(TWO_ORGS)
    render(<BillingOrgSelect projectId="p1" />)
    const select = await screen.findByTestId('billing-org-select')
    const labels = Array.from((select as HTMLSelectElement).options).map(
      (o) => o.textContent,
    )
    expect(labels).toEqual([
      'billingChoice.default:TUM (OpenAI)',
      'GSJ (OpenAI, DeepInfra)',
      'TUM (OpenAI)',
    ])
    expect((select as HTMLSelectElement).value).toBe('')
  })

  it('shares and remembers the pick per project', async () => {
    mockGetBillingOptions.mockResolvedValue(TWO_ORGS)
    render(<BillingOrgSelect projectId="p1" />)
    const { result } = renderHook(() => useBillingOrganization('p1'))
    const select = await screen.findByTestId('billing-org-select')

    fireEvent.change(select, { target: { value: 'org-gsj' } })

    await waitFor(() =>
      expect(result.current.billingOrganizationId).toBe('org-gsj'),
    )
    expect(window.localStorage.getItem('benger:billing-org:p1')).toBe('org-gsj')

    fireEvent.change(select, { target: { value: '' } })
    await waitFor(() => expect(result.current.billingOrganizationId).toBeNull())
    expect(window.localStorage.getItem('benger:billing-org:p1')).toBeNull()
  })

  it('ignores a remembered pick that is no longer an option', async () => {
    window.localStorage.setItem('benger:billing-org:p1', 'org-gone')
    mockGetBillingOptions.mockResolvedValue(TWO_ORGS)
    const { result } = renderHook(() => useBillingOrganization('p1'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.options).toHaveLength(2)
    expect(result.current.billingOrganizationId).toBeNull()
  })

  it('offers no choice when the options request fails', async () => {
    mockGetBillingOptions.mockRejectedValue(new Error('403'))
    const { result } = renderHook(() => useBillingOrganization('p1'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.options).toEqual([])
    expect(result.current.defaultOrganizationId).toBeNull()
  })
})
