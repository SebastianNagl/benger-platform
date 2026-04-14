/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/components/auth/SimpleAuth'
import { useToast } from '@/components/shared/SimpleToast'
import { render } from '@testing-library/react'
import { usePathname, useRouter } from 'next/navigation'
import { SimpleAuthFailureHandler } from '../SimpleAuthFailureHandler'

// Mock Next.js navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  usePathname: jest.fn(),
}))

// Mock SimpleAuth
jest.mock('@/components/auth/SimpleAuth', () => ({
  useAuth: jest.fn(),
}))

// Mock SimpleToast
jest.mock('@/components/shared/SimpleToast', () => ({
  useToast: jest.fn(),
}))

describe('SimpleAuthFailureHandler Component', () => {
  const mockPush = jest.fn()
  const mockRouter = { push: mockPush }
  const mockLogout = jest.fn()
  const mockAddToast = jest.fn()

  const mockUseRouter = useRouter as jest.Mock
  const mockUsePathname = usePathname as jest.Mock
  const mockUseAuth = useAuth as jest.Mock
  const mockUseToast = useToast as jest.Mock

  beforeEach(() => {
    jest.clearAllMocks()
    jest.spyOn(console, 'log').mockImplementation()
    jest.spyOn(console, 'warn').mockImplementation()

    mockUseRouter.mockReturnValue(mockRouter)
    mockUsePathname.mockReturnValue('/dashboard')
    mockUseAuth.mockReturnValue({
      user: { id: '1', username: 'testuser' },
      isLoading: false,
      logout: mockLogout,
    })
    mockUseToast.mockReturnValue({
      addToast: mockAddToast,
    })
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('Component Rendering', () => {
    it('renders without crashing', () => {
      const { container } = render(<SimpleAuthFailureHandler />)
      expect(container).toBeDefined()
    })

    it('returns null (no visible UI)', () => {
      const { container } = render(<SimpleAuthFailureHandler />)
      expect(container.firstChild).toBeNull()
    })

    it('has no DOM elements', () => {
      const { container } = render(<SimpleAuthFailureHandler />)
      expect(container).toBeEmptyDOMElement()
    })
  })

  // Note: Initialization logging uses logger.debug() - not testable in unit tests without mocking logger

  describe('Public Pages Detection', () => {
    const publicPages = ['/', '/login', '/register', '/reset-password']

    publicPages.forEach((page) => {
      it(`does not trigger logout on ${page}`, () => {
        mockUsePathname.mockReturnValue(page)
        mockUseAuth.mockReturnValue({
          user: null,
          isLoading: false,
          logout: mockLogout,
        })

        render(<SimpleAuthFailureHandler />)

        expect(mockLogout).not.toHaveBeenCalled()
        expect(mockAddToast).not.toHaveBeenCalled()
      })
    })
  })

  describe('Loading State Behavior', () => {
    it('does not trigger actions during loading', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
        logout: mockLogout,
      })

      render(<SimpleAuthFailureHandler />)

      expect(mockLogout).not.toHaveBeenCalled()
      expect(mockAddToast).not.toHaveBeenCalled()
    })

    it('does not call logout during loading', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
        logout: mockLogout,
      })

      render(<SimpleAuthFailureHandler />)

      expect(mockLogout).not.toHaveBeenCalled()
    })

    it('does not show toast during loading', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
        logout: mockLogout,
      })

      render(<SimpleAuthFailureHandler />)

      expect(mockAddToast).not.toHaveBeenCalled()
    })
  })

  describe('Unauthenticated User Behavior', () => {
    it('does not trigger when user is null', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        logout: mockLogout,
      })

      render(<SimpleAuthFailureHandler />)

      expect(mockLogout).not.toHaveBeenCalled()
      expect(mockAddToast).not.toHaveBeenCalled()
    })

    it('does not show toast when user is null', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        logout: mockLogout,
      })

      render(<SimpleAuthFailureHandler />)

      expect(mockAddToast).not.toHaveBeenCalled()
    })

    it('does not logout when user is null', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        logout: mockLogout,
      })

      render(<SimpleAuthFailureHandler />)

      expect(mockLogout).not.toHaveBeenCalled()
    })

  })

  describe('Edge Cases', () => {
    it('handles undefined pathname gracefully', () => {
      mockUsePathname.mockReturnValue(undefined)

      render(<SimpleAuthFailureHandler />)

      expect(mockLogout).not.toHaveBeenCalled()
    })

    it('handles null pathname gracefully', () => {
      mockUsePathname.mockReturnValue(null)

      render(<SimpleAuthFailureHandler />)

      expect(mockLogout).not.toHaveBeenCalled()
    })

    it('handles empty pathname gracefully', () => {
      mockUsePathname.mockReturnValue('')

      render(<SimpleAuthFailureHandler />)

      expect(mockLogout).not.toHaveBeenCalled()
    })

    it('handles undefined user gracefully', () => {
      mockUseAuth.mockReturnValue({
        user: undefined,
        isLoading: false,
        logout: mockLogout,
      })

      render(<SimpleAuthFailureHandler />)

      expect(mockLogout).not.toHaveBeenCalled()
      expect(mockAddToast).not.toHaveBeenCalled()
    })

    it('handles missing logout function gracefully', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1' },
        isLoading: false,
        logout: undefined,
      })

      expect(() => render(<SimpleAuthFailureHandler />)).not.toThrow()
    })

    it('handles missing addToast function gracefully', () => {
      mockUseToast.mockReturnValue({
        addToast: undefined,
      })

      expect(() => render(<SimpleAuthFailureHandler />)).not.toThrow()
    })

    it('handles missing router gracefully', () => {
      mockUseRouter.mockReturnValue(undefined)

      expect(() => render(<SimpleAuthFailureHandler />)).not.toThrow()
    })
  })

  describe('Component Lifecycle', () => {
    it('renders and handles unmounting correctly', () => {
      const { unmount } = render(<SimpleAuthFailureHandler />)

      expect(() => unmount()).not.toThrow()
    })
  })

  describe('Multiple Instances', () => {
    it('can render multiple instances without issues', () => {
      const { container } = render(
        <div>
          <SimpleAuthFailureHandler />
          <SimpleAuthFailureHandler />
          <SimpleAuthFailureHandler />
        </div>
      )

      // Component renders null, so container has only the wrapper div
      expect(container.firstChild).toBeInstanceOf(HTMLDivElement)
    })
  })

  describe('Context Integration', () => {
    it('uses auth context correctly', () => {
      render(<SimpleAuthFailureHandler />)

      expect(mockUseAuth).toHaveBeenCalled()
    })

    it('uses toast context correctly', () => {
      render(<SimpleAuthFailureHandler />)

      expect(mockUseToast).toHaveBeenCalled()
    })

    it('uses router hook correctly', () => {
      render(<SimpleAuthFailureHandler />)

      expect(mockUseRouter).toHaveBeenCalled()
    })

    it('uses pathname hook correctly', () => {
      render(<SimpleAuthFailureHandler />)

      expect(mockUsePathname).toHaveBeenCalled()
    })
  })

  describe('Comparison with AuthFailureHandler', () => {
    it('returns null like AuthFailureHandler', () => {
      const { container } = render(<SimpleAuthFailureHandler />)

      expect(container).toBeEmptyDOMElement()
    })
  })

  describe('Error Display and Handling', () => {
    it('should handle toast error gracefully', async () => {
      mockAddToast.mockImplementation(() => {
        throw new Error('Toast error')
      })

      mockUsePathname.mockReturnValue('/projects')
      mockUseAuth.mockReturnValue({
        user: { id: '1', username: 'testuser' },
        isLoading: false,
        logout: mockLogout,
      })

      expect(() => render(<SimpleAuthFailureHandler />)).not.toThrow()
    })
  })

  describe('Redirect Handling', () => {
    it('should not redirect on public pages', () => {
      mockUsePathname.mockReturnValue('/login')
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        logout: mockLogout,
      })

      render(<SimpleAuthFailureHandler />)

      expect(mockPush).not.toHaveBeenCalled()
    })

    it('should not redirect during loading', () => {
      mockUsePathname.mockReturnValue('/projects')
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
        logout: mockLogout,
      })

      render(<SimpleAuthFailureHandler />)

      expect(mockPush).not.toHaveBeenCalled()
    })
  })
})
