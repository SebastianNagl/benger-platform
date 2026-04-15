/**
 * @jest-environment jsdom
 */

import { render, waitFor } from '@testing-library/react'
import { useRouter, useSearchParams } from 'next/navigation'
import LegacyAdminUsersOrganizationsPage from '../page'

// Mock modules
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useSearchParams: jest.fn(),
}))

describe('LegacyAdminUsersOrganizationsPage', () => {
  const mockReplace = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue({
      replace: mockReplace,
      push: jest.fn(),
      prefetch: jest.fn(),
    })
    ;(useSearchParams as jest.Mock).mockReturnValue({
      get: jest.fn().mockReturnValue(null),
    })
  })

  it('should redirect to /users-organizations without tab param', async () => {
    render(<LegacyAdminUsersOrganizationsPage />)

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/users-organizations')
    })
  })

  it('should redirect to /users-organizations with tab param preserved', async () => {
    ;(useSearchParams as jest.Mock).mockReturnValue({
      get: jest.fn().mockReturnValue('organizations'),
    })

    render(<LegacyAdminUsersOrganizationsPage />)

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith(
        '/users-organizations?tab=organizations'
      )
    })
  })

  it('should render null (no visible content)', () => {
    const { container } = render(<LegacyAdminUsersOrganizationsPage />)
    expect(container.innerHTML).toBe('')
  })
})
