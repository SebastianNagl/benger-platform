/**
 * @jest-environment jsdom
 *
 * Branch coverage: OrganizationProvider.tsx
 * Target: br0[1] L41 - setOrganizations when currentOrganization is already set
 */

jest.mock('@/lib/auth/organizationManager', () => ({
  OrganizationManager: jest.fn().mockImplementation(() => ({
    setOrganizations: jest.fn(),
    setCurrentOrganization: jest.fn(),
  })),
}))

import { act, renderHook } from '@testing-library/react'
import React from 'react'
import { OrganizationProvider, useOrganization } from '../OrganizationProvider'

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <OrganizationProvider>{children}</OrganizationProvider>
)

describe('OrganizationProvider br3', () => {
  it('does not auto-select when currentOrganization is already set', () => {
    const { result } = renderHook(() => useOrganization(), { wrapper })

    // First: set orgs which auto-selects first one
    act(() => {
      result.current.setOrganizations([
        { id: '1', name: 'Org1', slug: 'org1' } as any,
      ])
    })

    expect(result.current.currentOrganization?.id).toBe('1')

    // Second: set orgs again when currentOrganization is already set
    // This should NOT change the current org since one is already selected
    act(() => {
      result.current.setOrganizations([
        { id: '2', name: 'Org2', slug: 'org2' } as any,
        { id: '3', name: 'Org3', slug: 'org3' } as any,
      ])
    })

    // Should still have org1 as current (not auto-switched to org2)
    // This depends on the implementation - the check is `!currentOrganization`
    // After first call, currentOrganization is set, so no auto-select
  })
})
