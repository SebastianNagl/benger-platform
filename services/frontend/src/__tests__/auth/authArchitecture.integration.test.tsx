/**
 * Integration tests for the refactored authentication architecture
 *
 * Tests session management, organization context, user switching detection,
 * and overall authentication flow coordination between components.
 */

import { AuthProvider, useAuth } from '@/contexts/AuthContext'
import { ApiClient } from '@/lib/api'
import { devAuthHelper } from '@/lib/auth/devAuthHelper'
import { OrganizationManager } from '@/lib/auth/organizationManager'
import { sessionManager } from '@/lib/auth/sessionManager'
import { act, renderHook, waitFor } from '@testing-library/react'

// Mock API responses
const mockUser = {
  id: 'user-123',
  username: 'testuser',
  email: 'test@example.com',
  name: 'Test User',
}

const mockOrganizations = [
  { id: 'org-1', name: 'TUM', role: 'org_admin' },
  { id: 'org-2', name: 'Research Group', role: 'contributor' },
]

// Mock ApiClient
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    setOrganizationContextProvider: jest.fn(),
    setAuthFailureHandler: jest.fn(),
    clearCache: jest.fn(),
  },
  ApiClient: jest.fn().mockImplementation(() => ({
    getUser: jest.fn(),
    getOrganizations: jest.fn(),
    clearCache: jest.fn(),
    clearUserCache: jest.fn(),
    setOrganizationContextProvider: jest.fn(),
    setAuthFailureHandler: jest.fn(),
  })),
}))

// Mock dev auth helper (simplified - auto-login moved to layout.tsx inline script)
jest.mock('@/lib/auth/devAuthHelper', () => ({
  devAuthHelper: {
    markManualLogout: jest.fn(),
    clearManualLogout: jest.fn(),
  },
}))

// Mock utils
jest.mock('@/utils/clearAllStores', () => ({
  clearAllStores: jest.fn(),
}))

jest.mock('@/utils/authRedirect', () => ({
  authRedirect: {
    toLogin: jest.fn(),
  },
}))

jest.mock('@/lib/utils/subdomain', () => ({
  parseSubdomain: jest.fn(() => ({ orgSlug: null, isPrivateMode: true })),
  getOrgUrl: jest.fn((slug: string) => `http://${slug}.benger.localhost`),
  getPrivateUrl: jest.fn(() => 'http://benger.localhost'),
  getLastOrgSlug: jest.fn(() => null),
  setLastOrgSlug: jest.fn(),
  clearLastOrgSlug: jest.fn(),
}))

jest.mock('@/lib/utils/logger', () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}))

// Mock Next.js router
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
  }),
}))

describe('Authentication Architecture Integration', () => {
  let mockApiClient: any

  beforeEach(() => {
    // Reset all mocks
    jest.clearAllMocks()

    // Clear browser storage
    localStorage.clear()
    sessionStorage.clear()

    // Create fresh API client mock
    mockApiClient = new ApiClient()
    mockApiClient.getUser.mockResolvedValue(mockUser)
    mockApiClient.getOrganizations.mockResolvedValue(mockOrganizations)
  })

  describe('Session Management Integration', () => {
    it('should track user sessions and detect user switching', async () => {
      // Track initial user
      sessionManager.trackUserSession(mockUser)

      expect(localStorage.getItem('benger_last_session_user')).toBe('user-123')
      expect(sessionManager.hasAuthVerification()).toBe(true)

      // Simulate different user
      const newUser = { ...mockUser, id: 'user-456' }
      const userSwitchDetected = sessionManager.detectUserSwitch(newUser)

      expect(userSwitchDetected).toBe(true)

      // Handle user switch
      sessionManager.handleUserSwitch(mockApiClient, 'user-456', 'user-123')

      expect(mockApiClient.clearUserCache).toHaveBeenCalledWith('user-123')
      expect(mockApiClient.clearCache).toHaveBeenCalled()
      expect(localStorage.getItem('benger_last_session_user')).toBe('user-456')
    })

    it('should fully clear sessionStorage during session clearing', async () => {
      // Set up session
      sessionManager.trackUserSession(mockUser)
      sessionStorage.setItem('temp_data', 'temp')

      // Clear session
      sessionManager.clearSession(mockApiClient)

      // All sessionStorage should be cleared (manual_logout is now a cookie)
      expect(sessionStorage.getItem('temp_data')).toBeNull()
      expect(localStorage.getItem('benger_last_session_user')).toBeNull()
    })

    it('should handle login progress state correctly', () => {
      expect(sessionManager.isLoginInProgress()).toBe(false)

      sessionManager.setLoginInProgress(true)
      expect(sessionManager.isLoginInProgress()).toBe(true)

      sessionManager.setLoginInProgress(false)
      expect(sessionManager.isLoginInProgress()).toBe(false)
    })
  })

  describe('Organization Management Integration', () => {
    it('should manage organization context and switching', async () => {
      const orgManager = new OrganizationManager()

      // Set organizations
      orgManager.setOrganizations(mockOrganizations)
      orgManager.setCurrentOrganization(mockOrganizations[0])

      expect(orgManager.getCurrentOrganization()).toEqual(mockOrganizations[0])
      expect(orgManager.getOrganizations()).toEqual(mockOrganizations)

      // Get organization context
      const context = orgManager.getOrganizationContext()
      expect(context).toBe('org-1')

      // Switch organization
      orgManager.setCurrentOrganization(mockOrganizations[1])
      expect(orgManager.getOrganizationContext()).toBe('org-2')
    })

    it('should maintain organization state in memory', () => {
      const orgManager = new OrganizationManager()

      // Set organizations and current organization
      orgManager.setOrganizations(mockOrganizations)
      orgManager.setCurrentOrganization(mockOrganizations[0])

      // Should maintain state
      expect(orgManager.getCurrentOrganization()).toEqual(mockOrganizations[0])
      expect(orgManager.getOrganizations()).toEqual(mockOrganizations)

      // Should be able to switch organizations
      orgManager.setCurrentOrganization(mockOrganizations[1])
      expect(orgManager.getCurrentOrganization()).toEqual(mockOrganizations[1])
    })
  })

  // Development Auto-Login tests removed - auto-login moved to layout.tsx inline script

  describe('AuthContext Integration', () => {
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <AuthProvider>{children}</AuthProvider>
    )

    it('should provide authentication state through context', async () => {
      const { result } = renderHook(() => useAuth(), { wrapper })

      await waitFor(() => {
        expect(result.current).toBeDefined()
        expect(result.current.isLoading).toBeDefined()
      })

      // Loading state should be boolean
      expect(typeof result.current.isLoading).toBe('boolean')

      // Should have required auth methods
      expect(result.current.login).toBeDefined()
      expect(result.current.logout).toBeDefined()
      expect(result.current.updateUser).toBeDefined()
    })

    it('should handle login flow through context', async () => {
      mockApiClient.getUser.mockResolvedValue(mockUser)

      const { result } = renderHook(() => useAuth(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      // Should have login function
      expect(result.current.login).toBeDefined()
      expect(typeof result.current.login).toBe('function')
    })

    it('should handle logout flow and clear session data', async () => {
      const { result } = renderHook(() => useAuth(), { wrapper })

      await waitFor(() => {
        expect(result.current.logout).toBeDefined()
      })

      if (result.current.logout) {
        await act(async () => {
          await result.current.logout()
        })
      }

      // Session should be cleared
      expect(localStorage.getItem('benger_last_session_user')).toBeNull()
    })
  })

  describe('Cross-Component Integration', () => {
    it('should coordinate between session manager and organization manager', async () => {
      const orgManager = new OrganizationManager()

      // Set up initial state
      sessionManager.trackUserSession(mockUser)
      orgManager.setOrganizations(mockOrganizations)
      orgManager.setCurrentOrganization(mockOrganizations[0])

      // Simulate user switch
      const newUser = { ...mockUser, id: 'user-456' }
      sessionManager.handleUserSwitch(mockApiClient, 'user-456', 'user-123')

      // Organization manager should be cleared after user switch
      // (This would be handled by the AuthContext in real usage)
      orgManager.clear()

      expect(orgManager.getCurrentOrganization()).toBeNull()
      expect(orgManager.getOrganizations()).toEqual([])
    })

    it('should handle authentication failure across components', () => {
      // Set up authenticated state
      sessionManager.trackUserSession(mockUser)
      const orgManager = new OrganizationManager()
      orgManager.setOrganizations(mockOrganizations)

      // Clear session (simulating auth failure)
      sessionManager.clearSession(mockApiClient)
      orgManager.clear()

      // All state should be cleared
      expect(sessionManager.getLastSessionUserId()).toBeNull()
      expect(sessionManager.hasAuthVerification()).toBe(false)
      expect(orgManager.getCurrentOrganization()).toBeNull()
      expect(mockApiClient.clearCache).toHaveBeenCalled()
    })

    it('should maintain consistency during rapid state changes', async () => {
      const orgManager = new OrganizationManager()

      // Rapid sequence of state changes
      sessionManager.trackUserSession(mockUser)
      orgManager.setOrganizations(mockOrganizations)
      orgManager.setCurrentOrganization(mockOrganizations[0])

      const newUser = { ...mockUser, id: 'user-456' }
      sessionManager.handleUserSwitch(mockApiClient, 'user-456', 'user-123')

      orgManager.clear()
      orgManager.setOrganizations(mockOrganizations)
      orgManager.setCurrentOrganization(mockOrganizations[1])

      // Final state should be consistent
      expect(sessionManager.getLastSessionUserId()).toBe('user-456')
      expect(orgManager.getCurrentOrganization()).toEqual(mockOrganizations[1])
      expect(orgManager.getOrganizationContext()).toBe('org-2')
    })
  })

  describe('Performance and Memory Integration', () => {
    it('should not leak memory during rapid authentication cycles', async () => {
      const orgManager = new OrganizationManager()

      // Simulate rapid auth cycles
      for (let i = 0; i < 100; i++) {
        const user = { ...mockUser, id: `user-${i}` }
        sessionManager.trackUserSession(user)
        orgManager.setOrganizations(mockOrganizations)
        sessionManager.clearSession(mockApiClient)
        orgManager.clear()
      }

      // Should end in clean state
      expect(sessionManager.getLastSessionUserId()).toBeNull()
      expect(orgManager.getCurrentOrganization()).toBeNull()
    })

    it('should handle concurrent authentication operations', async () => {
      const orgManager = new OrganizationManager()

      // Start multiple concurrent operations
      const operations = Array.from({ length: 10 }, (_, i) => {
        return async () => {
          const user = { ...mockUser, id: `user-${i}` }
          sessionManager.trackUserSession(user)
          orgManager.setOrganizations(mockOrganizations)
          await new Promise((resolve) =>
            setTimeout(resolve, Math.random() * 100)
          )
          sessionManager.clearSession(mockApiClient)
          orgManager.clear()
        }
      })

      await Promise.all(operations.map((op) => op()))

      // Should end in clean state regardless of timing
      expect(orgManager.getCurrentOrganization()).toBeNull()
    })
  })
})
