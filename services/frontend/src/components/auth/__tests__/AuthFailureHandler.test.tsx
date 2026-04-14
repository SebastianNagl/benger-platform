/**
 * @jest-environment jsdom
 */

import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { render } from '@testing-library/react'
import { usePathname, useRouter } from 'next/navigation'
import { AuthFailureHandler } from '../AuthFailureHandler'

// Mock Next.js navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  usePathname: jest.fn(),
}))

// Mock AuthContext
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

// Mock Toast
jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(),
}))

describe('AuthFailureHandler Component', () => {
  const mockPush = jest.fn()
  const mockRouter = { push: mockPush }
  const mockLogout = jest.fn()
  const mockAddToast = jest.fn()
  const mockSetAuthFailureHandler = jest.fn()
  const mockApiClient = { setAuthFailureHandler: mockSetAuthFailureHandler }

  const mockUseRouter = useRouter as jest.Mock
  const mockUsePathname = usePathname as jest.Mock
  const mockUseAuth = useAuth as jest.Mock
  const mockUseToast = useToast as jest.Mock

  beforeEach(() => {
    jest.clearAllMocks()
    mockUseRouter.mockReturnValue(mockRouter)
    mockUsePathname.mockReturnValue('/dashboard')
    mockUseAuth.mockReturnValue({
      user: { id: '1', email: 'user@example.com' },
      isLoading: false,
      logout: mockLogout,
      apiClient: mockApiClient,
    })
    mockUseToast.mockReturnValue({
      addToast: mockAddToast,
    })
  })

  describe('Component Rendering', () => {
    it('renders without crashing', () => {
      const { container } = render(<AuthFailureHandler />)
      expect(container.firstChild).toBeNull()
    })

    it('returns null (no visible UI)', () => {
      const { container } = render(<AuthFailureHandler />)
      expect(container).toBeEmptyDOMElement()
    })
  })

  describe('Auth Failure Handler Registration', () => {
    it('registers auth failure handler on mount', () => {
      render(<AuthFailureHandler />)

      expect(mockSetAuthFailureHandler).toHaveBeenCalledTimes(1)
      expect(mockSetAuthFailureHandler).toHaveBeenCalledWith(
        expect.any(Function)
      )
    })

    it('does not register handler if apiClient is null', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1' },
        isLoading: false,
        logout: mockLogout,
        apiClient: null,
      })

      render(<AuthFailureHandler />)

      expect(mockSetAuthFailureHandler).not.toHaveBeenCalled()
    })

    it('does not register handler if setAuthFailureHandler is undefined', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1' },
        isLoading: false,
        logout: mockLogout,
        apiClient: {},
      })

      render(<AuthFailureHandler />)

      expect(mockSetAuthFailureHandler).not.toHaveBeenCalled()
    })

    it('re-registers handler when dependencies change', () => {
      const { rerender } = render(<AuthFailureHandler />)

      expect(mockSetAuthFailureHandler).toHaveBeenCalledTimes(1)

      // Change pathname
      mockUsePathname.mockReturnValue('/projects')

      rerender(<AuthFailureHandler />)

      expect(mockSetAuthFailureHandler).toHaveBeenCalledTimes(2)
    })
  })

  describe('Public Pages Behavior', () => {
    const publicPages = ['/', '/login', '/register', '/reset-password']

    publicPages.forEach((page) => {
      it(`does not trigger auth failure on public page: ${page}`, async () => {
        mockUsePathname.mockReturnValue(page)
        mockUseAuth.mockReturnValue({
          user: null,
          isLoading: false,
          logout: mockLogout,
          apiClient: mockApiClient,
        })

        render(<AuthFailureHandler />)

        // Get the registered handler
        const handler = mockSetAuthFailureHandler.mock.calls[0][0]

        // Invoke the handler
        await handler()

        expect(mockAddToast).not.toHaveBeenCalled()
        expect(mockLogout).not.toHaveBeenCalled()
      })
    })

    it('skips session expired message on public pages', async () => {
      mockUsePathname.mockReturnValue('/login')

      render(<AuthFailureHandler />)

      const handler = mockSetAuthFailureHandler.mock.calls[0][0]
      await handler()

      expect(mockAddToast).not.toHaveBeenCalled()
    })
  })

  describe('Loading State Behavior', () => {
    it('does not trigger auth failure during initial loading', async () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
        logout: mockLogout,
        apiClient: mockApiClient,
      })

      render(<AuthFailureHandler />)

      const handler = mockSetAuthFailureHandler.mock.calls[0][0]
      await handler()

      expect(mockAddToast).not.toHaveBeenCalled()
      expect(mockLogout).not.toHaveBeenCalled()
    })

    it('does not show session expired during auth loading', async () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
        logout: mockLogout,
        apiClient: mockApiClient,
      })

      render(<AuthFailureHandler />)

      const handler = mockSetAuthFailureHandler.mock.calls[0][0]
      await handler()

      expect(mockAddToast).not.toHaveBeenCalled()
    })
  })

  describe('Unauthenticated User Behavior', () => {
    it('does not trigger auth failure when user was never authenticated', async () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        logout: mockLogout,
        apiClient: mockApiClient,
      })

      render(<AuthFailureHandler />)

      const handler = mockSetAuthFailureHandler.mock.calls[0][0]
      await handler()

      expect(mockAddToast).not.toHaveBeenCalled()
      expect(mockLogout).not.toHaveBeenCalled()
    })

    it('skips session expired message when user is null', async () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        logout: mockLogout,
        apiClient: mockApiClient,
      })

      render(<AuthFailureHandler />)

      const handler = mockSetAuthFailureHandler.mock.calls[0][0]
      await handler()

      expect(mockAddToast).not.toHaveBeenCalled()
    })
  })

  describe('Authenticated User Session Expiry', () => {
    it('shows session expired toast when authenticated user session expires', async () => {
      render(<AuthFailureHandler />)

      const handler = mockSetAuthFailureHandler.mock.calls[0][0]
      await handler()

      expect(mockAddToast).toHaveBeenCalledWith(
        'Your session has expired. Please log in again.',
        'warning'
      )
    })

    it('logs out user when session expires', async () => {
      render(<AuthFailureHandler />)

      const handler = mockSetAuthFailureHandler.mock.calls[0][0]
      await handler()

      expect(mockLogout).toHaveBeenCalledTimes(1)
    })

    it('logs out user after showing toast', async () => {
      const callOrder: string[] = []

      mockAddToast.mockImplementation(() => {
        callOrder.push('toast')
      })

      mockLogout.mockImplementation(async () => {
        callOrder.push('logout')
      })

      render(<AuthFailureHandler />)

      const handler = mockSetAuthFailureHandler.mock.calls[0][0]
      await handler()

      expect(callOrder).toEqual(['toast', 'logout'])
    })
  })

  describe('Error Handling', () => {
    it('continues even if toast fails', async () => {
      mockAddToast.mockImplementation(() => {
        throw new Error('Toast error')
      })

      render(<AuthFailureHandler />)

      const handler = mockSetAuthFailureHandler.mock.calls[0][0]
      await handler()

      expect(mockLogout).toHaveBeenCalled()
    })

    it('redirects to home if logout fails', async () => {
      mockLogout.mockRejectedValue(new Error('Logout failed'))

      render(<AuthFailureHandler />)

      const handler = mockSetAuthFailureHandler.mock.calls[0][0]
      await handler()

      expect(mockPush).toHaveBeenCalledWith('/')
    })

    it('handles logout failure gracefully', async () => {
      mockLogout.mockRejectedValue(new Error('Network error'))

      render(<AuthFailureHandler />)

      const handler = mockSetAuthFailureHandler.mock.calls[0][0]

      await expect(handler()).resolves.not.toThrow()
    })

    it('handles router push failure gracefully', async () => {
      mockLogout.mockRejectedValue(new Error('Logout failed'))
      mockPush.mockImplementation(() => {
        throw new Error('Router error')
      })

      render(<AuthFailureHandler />)

      const handler = mockSetAuthFailureHandler.mock.calls[0][0]

      await expect(handler()).resolves.not.toThrow()
    })

    it('does not crash if both logout and redirect fail', async () => {
      mockLogout.mockRejectedValue(new Error('Logout failed'))
      mockPush.mockImplementation(() => {
        throw new Error('Router failed')
      })

      render(<AuthFailureHandler />)

      const handler = mockSetAuthFailureHandler.mock.calls[0][0]
      await handler()

      expect(mockLogout).toHaveBeenCalled()
      expect(mockPush).toHaveBeenCalledWith('/')
    })
  })

  describe('Edge Cases', () => {
    it('handles undefined pathname gracefully', async () => {
      mockUsePathname.mockReturnValue(undefined)

      render(<AuthFailureHandler />)

      const handler = mockSetAuthFailureHandler.mock.calls[0][0]
      await handler()

      expect(mockAddToast).not.toHaveBeenCalled()
      expect(mockLogout).not.toHaveBeenCalled()
    })

    it('handles null pathname gracefully', async () => {
      mockUsePathname.mockReturnValue(null)

      render(<AuthFailureHandler />)

      const handler = mockSetAuthFailureHandler.mock.calls[0][0]
      await handler()

      expect(mockAddToast).not.toHaveBeenCalled()
      expect(mockLogout).not.toHaveBeenCalled()
    })

    it('handles empty pathname gracefully', async () => {
      mockUsePathname.mockReturnValue('')

      render(<AuthFailureHandler />)

      const handler = mockSetAuthFailureHandler.mock.calls[0][0]
      await handler()

      expect(mockAddToast).not.toHaveBeenCalled()
      expect(mockLogout).not.toHaveBeenCalled()
    })

    it('handles undefined user gracefully', async () => {
      mockUseAuth.mockReturnValue({
        user: undefined,
        isLoading: false,
        logout: mockLogout,
        apiClient: mockApiClient,
      })

      render(<AuthFailureHandler />)

      const handler = mockSetAuthFailureHandler.mock.calls[0][0]
      await handler()

      expect(mockAddToast).not.toHaveBeenCalled()
      expect(mockLogout).not.toHaveBeenCalled()
    })
  })

  describe('Protected Pages Behavior', () => {
    const protectedPages = [
      '/dashboard',
      '/projects',
      '/admin',
      '/settings',
      '/profile',
    ]

    protectedPages.forEach((page) => {
      it(`triggers auth failure on protected page: ${page}`, async () => {
        mockUsePathname.mockReturnValue(page)

        render(<AuthFailureHandler />)

        const handler = mockSetAuthFailureHandler.mock.calls[0][0]
        await handler()

        expect(mockAddToast).toHaveBeenCalled()
        expect(mockLogout).toHaveBeenCalled()
      })
    })
  })

  // Note: Debug logging uses logger.debug() - not testable in unit tests without mocking logger
})
