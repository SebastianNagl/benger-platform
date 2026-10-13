/**
 * @jest-environment jsdom
 *
 * The options are shared page-wide: the copy that builds a request must see
 * an org attached after the page loaded once any component has refetched.
 */

import { act, renderHook, waitFor } from '@testing-library/react'

const mockGetBillingOptions = jest.fn()
jest.mock('@/lib/api', () => ({
  api: {
    getBillingOptions: (...args: unknown[]) => mockGetBillingOptions(...args),
  },
}))

import {
  resetBillingOptionsCache,
  useBillingOrganization,
} from '../useBillingOrganization'

const TUM = { id: 'org-tum', name: 'TUM', providers: ['DeepInfra'] }
const GSJ = { id: 'org-gsj', name: 'GSJ', providers: ['DeepInfra'] }
const TITAN = { id: 'org-titan', name: 'TITAN', providers: ['OpenAI'] }

beforeEach(() => {
  resetBillingOptionsCache()
  window.localStorage.clear()
  mockGetBillingOptions.mockReset()
})

it('a pick from a later-mounted select reaches the copy mounted with the page', async () => {
  // Page load: GSJ is not attached to the project yet.
  mockGetBillingOptions.mockResolvedValue({
    options: [TUM, TITAN],
    default_organization_id: 'org-tum',
  })
  const pageCopy = renderHook(() => useBillingOrganization('p1'))
  await waitFor(() => expect(pageCopy.result.current.options).toHaveLength(2))

  // GSJ gets attached; the dialog opens and its select loads the options.
  mockGetBillingOptions.mockResolvedValue({
    options: [TUM, TITAN, GSJ],
    default_organization_id: 'org-tum',
  })
  const selectCopy = renderHook(() => useBillingOrganization('p1'))
  await waitFor(() => expect(selectCopy.result.current.options).toHaveLength(3))

  act(() => selectCopy.result.current.setBillingOrganizationId('org-gsj'))

  expect(selectCopy.result.current.billingOrganizationId).toBe('org-gsj')
  expect(pageCopy.result.current.options).toHaveLength(3)
  expect(pageCopy.result.current.billingOrganizationId).toBe('org-gsj')
})

it('a pick that is no longer an option falls back to the default rule', async () => {
  window.localStorage.setItem('benger:billing-org:p2', 'org-gone')
  mockGetBillingOptions.mockResolvedValue({
    options: [TUM, GSJ],
    default_organization_id: 'org-tum',
  })
  const { result } = renderHook(() => useBillingOrganization('p2'))
  await waitFor(() => expect(result.current.loading).toBe(false))
  expect(result.current.billingOrganizationId).toBeNull()
  expect(result.current.defaultOrganizationId).toBe('org-tum')
})
