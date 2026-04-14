/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/api'
import { render } from '@testing-library/react'
import { AuthFailureHandler } from '../auth/AuthFailureHandler'

// Mock dependencies
const mockPush = jest.fn()
const mockLogout = jest.fn()
const mockAddToast = jest.fn()
const mockRemoveToast = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
  }),
  usePathname: () => '/dashboard', // Use non-public page for testing
  useParams: () => ({}),
  useSearchParams: () => new URLSearchParams(),
}))

jest.mock('@/contexts/AuthContext')
jest.mock('@/lib/api')

// Mock the useToast hook directly at module level - use the same path as component
jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(() => ({
    addToast: mockAddToast,
    removeToast: mockRemoveToast,
    toasts: [],
  })),
  ToastProvider: ({ children }: any) => children,
}))

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>
const mockApi = api as jest.Mocked<typeof api>

const mockApiClient = {
  setAuthFailureHandler: jest.fn(),

  getUser: jest.fn(),
  getCurrentUser: jest.fn(),
  login: jest.fn(),
  logout: jest.fn(),
  signup: jest.fn(),
  getOrganizations: jest.fn(),
  getTasks: jest.fn(),
  getTask: jest.fn(),
  createTask: jest.fn(),
  updateTask: jest.fn(),
  deleteTask: jest.fn(),
  getAllUsers: jest.fn(),
  getAnnotationOverview: jest.fn(),
  exportBulkData: jest.fn(),
  importBulkData: jest.fn(),
  organizations: {
    list: jest.fn(),
    get: jest.fn(),
    create: jest.fn(),
    update: jest.fn(),
    delete: jest.fn(),
  },
}

const mockUser = {
  id: '1',
  username: 'testuser',
  email: 'test@example.com',
  name: 'Test User',
  role: 'USER',
  is_active: true,
  created_at: '2023-01-01T00:00:00Z',
}

const mockAuthContext = {
  user: mockUser, // Authenticated user for testing session expired scenarios
  login: jest.fn(),
  logout: mockLogout,
  signup: jest.fn(),
  updateUser: jest.fn(),
  refreshAuth: jest.fn(),
  isLoading: false,
  apiClient: mockApiClient as any,
  organizations: [],
  currentOrganization: null,
  setCurrentOrganization: jest.fn(),
  refreshOrganizations: jest.fn(),
}

describe('AuthFailureHandler', () => {
  beforeEach(() => {
    jest.clearAllMocks()

    // Clear the mock functions
    mockAddToast.mockClear()
    mockRemoveToast.mockClear()
    mockLogout.mockClear()
    mockPush.mockClear()

    mockUseAuth.mockReturnValue(mockAuthContext)
  })

  describe('initialization and setup', () => {
    it('renders without crashing', async () => {
      render(<AuthFailureHandler />)
      // Component should render without any visible content
      expect(document.body).toBeInTheDocument()
    })

    it('sets up auth failure handler on api client', async () => {
      render(<AuthFailureHandler />)

      // Verify that setAuthFailureHandler was called on the api client
      expect(mockApiClient.setAuthFailureHandler).toHaveBeenCalledWith(
        expect.any(Function)
      )
    })

    it('sets up auth failure handler on each useEffect call', async () => {
      const { rerender } = render(<AuthFailureHandler />)

      // Should be called once initially
      expect(mockApiClient.setAuthFailureHandler).toHaveBeenCalledTimes(1)

      rerender(<AuthFailureHandler />)

      // In React strict mode or when dependencies change, useEffect runs again
      expect(mockApiClient.setAuthFailureHandler).toHaveBeenCalledTimes(2)
    })
  })

  describe('auth failure handling', () => {
    const getLatestAuthFailureHandler = () => {
      const calls = mockApiClient.setAuthFailureHandler.mock.calls
      return calls[calls.length - 1][0]
    }

    beforeEach(async () => {
      render(<AuthFailureHandler />)
      // Wait for useEffect to complete
      await new Promise((resolve) => setTimeout(resolve, 0))
    })

    it('shows session expired toast when auth failure occurs', async () => {
      mockLogout.mockResolvedValue(undefined)

      const authFailureHandler = getLatestAuthFailureHandler()
      await authFailureHandler()

      expect(mockAddToast).toHaveBeenCalledWith(
        'Your session has expired. Please log in again.',
        'warning'
      )
    })

    it('calls logout when auth failure occurs', async () => {
      mockLogout.mockResolvedValue(undefined)

      const authFailureHandler = getLatestAuthFailureHandler()
      await authFailureHandler()

      expect(mockLogout).toHaveBeenCalledTimes(1)
    })

    it('does not redirect if logout succeeds', async () => {
      mockLogout.mockResolvedValue(undefined)

      const authFailureHandler = getLatestAuthFailureHandler()
      await authFailureHandler()

      expect(mockPush).not.toHaveBeenCalled()
    })

    it('redirects to home if logout fails', async () => {
      const logoutError = new Error('Logout failed')
      mockLogout.mockRejectedValue(logoutError)

      const authFailureHandler = getLatestAuthFailureHandler()
      await authFailureHandler()

      expect(mockLogout).toHaveBeenCalledTimes(1)
      expect(mockPush).toHaveBeenCalledWith('/')
    })

    it('redirects to home if logout throws non-Error exception', async () => {
      mockLogout.mockRejectedValue('String error')

      const authFailureHandler = getLatestAuthFailureHandler()
      await authFailureHandler()

      expect(mockLogout).toHaveBeenCalledTimes(1)
      expect(mockPush).toHaveBeenCalledWith('/')
    })

    it('handles multiple rapid auth failures gracefully', async () => {
      mockLogout.mockResolvedValue(undefined)

      const authFailureHandler = getLatestAuthFailureHandler()
      // Simulate rapid auth failures
      await Promise.all([
        authFailureHandler(),
        authFailureHandler(),
        authFailureHandler(),
      ])

      // Should show toast for each failure
      expect(mockAddToast).toHaveBeenCalledTimes(3)
      expect(mockLogout).toHaveBeenCalledTimes(3)
    })
  })

  describe('error scenarios', () => {
    let authFailureHandler: () => void

    beforeEach(() => {
      render(<AuthFailureHandler />)

      const setAuthFailureHandlerCall =
        mockApiClient.setAuthFailureHandler.mock.calls[0]
      authFailureHandler = setAuthFailureHandlerCall[0]
    })

    it('handles router.push failure gracefully', async () => {
      const logoutError = new Error('Logout failed')
      const routerError = new Error('Router push failed')

      mockLogout.mockRejectedValue(logoutError)
      mockPush.mockImplementation(() => {
        throw routerError
      })

      // Should not throw an error due to improved error handling
      await authFailureHandler()

      expect(mockLogout).toHaveBeenCalledTimes(1)
      expect(mockPush).toHaveBeenCalledWith('/')
    })

    it('continues execution even if toast fails', async () => {
      mockAddToast.mockImplementation(() => {
        throw new Error('Toast failed')
      })
      mockLogout.mockResolvedValue(undefined)

      // Should not throw an error due to improved error handling
      await authFailureHandler()

      expect(mockLogout).toHaveBeenCalledTimes(1)
    })
  })

  describe('component lifecycle', () => {
    it('does not interfere with normal component rendering', async () => {
      const TestComponent = () => (
        <div data-testid="test-component">Test Content</div>
      )

      const { getByTestId } = render(
        <>
          <AuthFailureHandler />
          <TestComponent />
        </>
      )

      expect(getByTestId('test-component')).toBeInTheDocument()
      expect(getByTestId('test-component')).toHaveTextContent('Test Content')
    })

    it('works when rendered multiple times', async () => {
      const { rerender } = render(<AuthFailureHandler />)

      expect(mockApiClient.setAuthFailureHandler).toHaveBeenCalledTimes(1)

      rerender(<AuthFailureHandler />)

      // Will be called again on rerender due to useEffect dependencies
      expect(mockApiClient.setAuthFailureHandler).toHaveBeenCalledTimes(2)
    })
  })

  describe('api client integration', () => {
    it('verifies auth failure handler function signature', async () => {
      render(<AuthFailureHandler />)

      const setAuthFailureHandlerCall =
        mockApiClient.setAuthFailureHandler.mock.calls[0]
      const authFailureHandler = setAuthFailureHandlerCall[0]

      expect(typeof authFailureHandler).toBe('function')
      expect(authFailureHandler.length).toBe(0) // No parameters expected
    })

    it('does not call auth failure handler during normal operation', async () => {
      render(<AuthFailureHandler />)

      // Just rendering should not trigger the handler
      expect(mockAddToast).not.toHaveBeenCalled()
      expect(mockLogout).not.toHaveBeenCalled()
      expect(mockPush).not.toHaveBeenCalled()
    })
  })

  describe('concurrent auth failures', () => {
    const getLatestAuthFailureHandler = () => {
      const calls = mockApiClient.setAuthFailureHandler.mock.calls
      return calls[calls.length - 1][0]
    }

    beforeEach(() => {
      render(<AuthFailureHandler />)
    })

    it('handles concurrent logout attempts', async () => {
      let logoutCallCount = 0
      mockLogout.mockImplementation(() => {
        logoutCallCount++
        return Promise.resolve()
      })

      const authFailureHandler = getLatestAuthFailureHandler()
      // Trigger multiple concurrent auth failures
      const promises = [
        authFailureHandler(),
        authFailureHandler(),
        authFailureHandler(),
      ]

      await Promise.all(promises)

      expect(logoutCallCount).toBe(3)
      expect(mockAddToast).toHaveBeenCalledTimes(3)
    })

    it('handles mixed success/failure logout attempts', async () => {
      let callCount = 0
      mockLogout.mockImplementation(() => {
        callCount++
        if (callCount === 1) {
          return Promise.resolve() // First call succeeds
        } else {
          return Promise.reject(new Error('Logout failed')) // Subsequent calls fail
        }
      })

      const authFailureHandler = getLatestAuthFailureHandler()
      const promises = [authFailureHandler(), authFailureHandler()]

      await Promise.all(promises)

      expect(mockLogout).toHaveBeenCalledTimes(2)
      expect(mockAddToast).toHaveBeenCalledTimes(2)
      // Only the failed logout should trigger router.push
      expect(mockPush).toHaveBeenCalledTimes(1)
      expect(mockPush).toHaveBeenCalledWith('/')
    })
  })

  describe('toast message customization', () => {
    const getLatestAuthFailureHandler = () => {
      const calls = mockApiClient.setAuthFailureHandler.mock.calls
      return calls[calls.length - 1][0]
    }

    beforeEach(() => {
      render(<AuthFailureHandler />)
    })

    it('uses correct toast message, type, and duration', async () => {
      mockLogout.mockResolvedValue(undefined)

      const authFailureHandler = getLatestAuthFailureHandler()
      await authFailureHandler()

      expect(mockAddToast).toHaveBeenCalledWith(
        'Your session has expired. Please log in again.',
        'warning'
      )
    })

    it('maintains consistent toast parameters across multiple calls', async () => {
      mockLogout.mockResolvedValue(undefined)

      const authFailureHandler = getLatestAuthFailureHandler()
      await authFailureHandler()
      await authFailureHandler()

      expect(mockAddToast).toHaveBeenNthCalledWith(
        1,
        'Your session has expired. Please log in again.',
        'warning'
      )
      expect(mockAddToast).toHaveBeenNthCalledWith(
        2,
        'Your session has expired. Please log in again.',
        'warning'
      )
    })
  })
})
