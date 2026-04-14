/**
 * @jest-environment jsdom
 */

import { act, renderHook } from '@testing-library/react'
import { UserProvider, useUser } from '../UserProvider'

jest.mock('@/lib/api', () => ({}))

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <UserProvider>{children}</UserProvider>
)

const mockUser = {
  id: 'u1',
  name: 'Test User',
  username: 'testuser',
  email: 'test@example.com',
  is_superadmin: false,
  is_active: true,
  created_at: '2024-01-01',
  updated_at: '2024-01-01',
}

describe('UserProvider', () => {
  it('should provide initial null user', () => {
    const { result } = renderHook(() => useUser(), { wrapper })
    expect(result.current.user).toBeNull()
  })

  it('should set user', () => {
    const { result } = renderHook(() => useUser(), { wrapper })

    act(() => {
      result.current.setUser(mockUser as any)
    })

    expect(result.current.user).toEqual(mockUser)
  })

  it('should clear user when set to null', () => {
    const { result } = renderHook(() => useUser(), { wrapper })

    act(() => {
      result.current.setUser(mockUser as any)
    })
    expect(result.current.user).not.toBeNull()

    act(() => {
      result.current.setUser(null)
    })
    expect(result.current.user).toBeNull()
  })

  it('should update user partially', () => {
    const { result } = renderHook(() => useUser(), { wrapper })

    act(() => {
      result.current.setUser(mockUser as any)
    })

    act(() => {
      result.current.updateUser({ name: 'Updated Name' } as any)
    })

    expect(result.current.user?.name).toBe('Updated Name')
    expect(result.current.user?.email).toBe('test@example.com')
  })

  it('should not crash when updating null user', () => {
    const { result } = renderHook(() => useUser(), { wrapper })

    act(() => {
      result.current.updateUser({ name: 'Updated Name' } as any)
    })

    expect(result.current.user).toBeNull()
  })
})

describe('useUser', () => {
  it('should throw when used outside provider', () => {
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation()

    expect(() => {
      renderHook(() => useUser())
    }).toThrow('useUser must be used within a UserProvider')

    consoleSpy.mockRestore()
  })
})
