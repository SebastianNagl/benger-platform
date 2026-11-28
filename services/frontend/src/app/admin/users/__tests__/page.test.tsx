/**
 * @jest-environment jsdom
 *
 * /admin/users is a legacy address: it sends the reader straight to the
 * users tab of /users-organizations and loads nothing itself.
 */

import { api } from '@/lib/api'
import { render, waitFor } from '@testing-library/react'
import { useRouter } from 'next/navigation'
import LegacyAdminUsersPage from '../page'

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useSearchParams: jest.fn(() => ({ get: jest.fn().mockReturnValue(null) })),
}))

describe('LegacyAdminUsersPage', () => {
  const mockReplace = jest.fn()
  const mockPush = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue({
      replace: mockReplace,
      push: mockPush,
      prefetch: jest.fn(),
    })
  })

  it('replaces the address with the users tab of the unified page', async () => {
    const { container } = render(<LegacyAdminUsersPage />)

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/users-organizations?tab=users')
    })
    expect(mockPush).not.toHaveBeenCalled()
    expect(container.innerHTML).toBe('')
  })

  it('loads no user list on the way', async () => {
    render(<LegacyAdminUsersPage />)

    await waitFor(() => expect(mockReplace).toHaveBeenCalled())
    expect(api.getAllUsers).not.toHaveBeenCalled()
  })
})
