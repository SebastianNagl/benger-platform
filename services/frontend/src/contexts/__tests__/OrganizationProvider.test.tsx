/**
 * @jest-environment jsdom
 */

import { act, renderHook } from '@testing-library/react'
import { OrganizationProvider, useOrganization } from '../OrganizationProvider'

jest.mock('@/lib/auth/organizationManager', () => ({
  OrganizationManager: jest.fn().mockImplementation(() => ({
    setOrganizations: jest.fn(),
    setCurrentOrganization: jest.fn(),
  })),
}))

jest.mock('@/lib/api', () => ({}))

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <OrganizationProvider>{children}</OrganizationProvider>
)

describe('OrganizationProvider', () => {
  it('should provide organization context', () => {
    const { result } = renderHook(() => useOrganization(), { wrapper })

    expect(result.current.organizations).toEqual([])
    expect(result.current.currentOrganization).toBeNull()
    expect(result.current.manager).toBeDefined()
  })

  it('should set organizations', () => {
    const { result } = renderHook(() => useOrganization(), { wrapper })

    const orgs = [
      { id: 'org1', name: 'Org 1', slug: 'org1', role: 'admin' as const },
    ]

    act(() => {
      result.current.setOrganizations(orgs as any)
    })

    expect(result.current.organizations).toEqual(orgs)
    // Auto-selects first org when none selected
    expect(result.current.currentOrganization).toEqual(orgs[0])
  })

  it('should set current organization', () => {
    const { result } = renderHook(() => useOrganization(), { wrapper })

    const org = { id: 'org2', name: 'Org 2', slug: 'org2', role: 'admin' as const }

    act(() => {
      result.current.setCurrentOrganization(org as any)
    })

    expect(result.current.currentOrganization).toEqual(org)
  })

  it('should clear current organization when set to null', () => {
    const { result } = renderHook(() => useOrganization(), { wrapper })

    act(() => {
      result.current.setCurrentOrganization(null)
    })

    expect(result.current.currentOrganization).toBeNull()
  })
})

describe('useOrganization', () => {
  it('should throw when used outside provider', () => {
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation()

    expect(() => {
      renderHook(() => useOrganization())
    }).toThrow('useOrganization must be used within an OrganizationProvider')

    consoleSpy.mockRestore()
  })
})
