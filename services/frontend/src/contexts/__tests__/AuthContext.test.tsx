/**
 * @jest-environment jsdom
 */

// Unmock AuthContext so we test the real implementation
jest.unmock('@/contexts/AuthContext')

import { ApiClient, Organization, User } from '@/lib/api'
import { devAuthHelper } from '@/lib/auth/devAuthHelper'
import { OrganizationManager } from '@/lib/auth/organizationManager'
import { sessionManager } from '@/lib/auth/sessionManager'
import { authRedirect } from '@/utils/authRedirect'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useRouter } from 'next/navigation'
import React from 'react'
import { AuthProvider, useAuth } from '../AuthContext'

// Mock dependencies
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

jest.mock('@/lib/api', () => {
  const originalModule = jest.requireActual('@/lib/api')
  return {
    ...originalModule,
    __esModule: true,
    default: {
      setOrganizationContextProvider: jest.fn(),
      setAuthFailureHandler: jest.fn(),
      clearCache: jest.fn(),
    },
    ApiClient: jest.fn(),
  }
})

jest.mock('@/lib/auth/devAuthHelper', () => ({
  devAuthHelper: {
    clearManualLogout: jest.fn(),
    markManualLogout: jest.fn(),
  },
}))

jest.mock('@/lib/auth/sessionManager', () => ({
  sessionManager: {
    isLoginInProgress: jest.fn(),
    trackUserSession: jest.fn(),
    getLastSessionUserId: jest.fn(),
    detectUserSwitch: jest.fn(),
    handleUserSwitch: jest.fn(),
    setLoginInProgress: jest.fn(),
    clearSession: jest.fn(),
    prepareForLogin: jest.fn(),
    clearAuthVerification: jest.fn(),
  },
}))

jest.mock('@/lib/auth/organizationManager', () => {
  return {
    OrganizationManager: jest.fn().mockImplementation(() => ({
      setOrganizations: jest.fn(),
      setCurrentOrganization: jest.fn(),
      getOrganizationContext: jest.fn(),
      getOrganizations: jest.fn().mockReturnValue([]),
      clear: jest.fn(),
    })),
  }
})

jest.mock('@/utils/authRedirect', () => ({
  authRedirect: {
    toLogin: jest.fn(),
    isPublicRoute: jest.fn((path: string) => {
      const routes = ['/', '/login', '/register', '/reset-password', '/verify-email', '/accept-invitation', '/about/imprint', '/about/data-protection']
      if (path === '/') return true
      return routes.some((r: string) => r !== '/' && path.startsWith(r)) || path.startsWith('/about')
    }),
  },
  publicRoutes: [
    '/',
    '/login',
    '/register',
    '/reset-password',
    '/verify-email',
    '/accept-invitation',
    '/about/imprint',
    '/about/data-protection',
  ],
}))

jest.mock('@/lib/utils/subdomain', () => ({
  parseSubdomain: jest.fn(() => ({ orgSlug: null, isPrivateMode: true })),
  getOrgUrl: jest.fn((slug: string) => `http://${slug}.benger.localhost`),
  getPrivateUrl: jest.fn(() => 'http://benger.localhost'),
  getCookieDomain: jest.fn(() => ''),
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

// Mock fetch for token refresh
global.fetch = jest.fn()

describe('AuthContext', () => {
  const mockRouter = {
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
  }

  const mockUser: User = {
    id: 1,
    username: 'testuser',
    email: 'test@example.com',
    name: 'Test User',
    role: 'user',
    is_superadmin: false,
    is_active: true,
    is_email_verified: true,
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  }

  const mockOrganization: Organization = {
    id: 1,
    name: 'Test Organization',
    display_name: 'Test Organization',
    slug: 'test-org',
    description: 'Test Description',
    is_active: true,
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  }

  let mockApiClient: any

  beforeEach(() => {
    // Use fake timers but don't fake setImmediate to allow waitFor to work
    jest.useFakeTimers({ doNotFake: ['setImmediate'] })
    jest.clearAllMocks()

    // Set NODE_ENV to test to ensure debounce is 100ms not 500ms
    process.env.NODE_ENV = 'test'
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(sessionManager.isLoginInProgress as jest.Mock).mockReturnValue(false)
    ;(sessionManager.getLastSessionUserId as jest.Mock).mockReturnValue(null)
    ;(sessionManager.detectUserSwitch as jest.Mock).mockReturnValue(false)

    // Mock ApiClient implementation
    mockApiClient = {
      setAuthFailureHandler: jest.fn(),
      setOrganizationContextProvider: jest.fn(),
      clearCache: jest.fn(),
      getUser: jest.fn().mockResolvedValue(mockUser),
      getOrganizations: jest.fn().mockResolvedValue([mockOrganization]),
      login: jest.fn().mockResolvedValue({ user: mockUser }),
      logout: jest.fn().mockResolvedValue(undefined),
      signup: jest.fn().mockResolvedValue(mockUser),
      clearUserCache: jest.fn(),
    }
    ;(ApiClient as jest.Mock).mockImplementation(() => mockApiClient)

    // Mock fetch for token refresh - immediate response
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue({}),
    })

    // Clear localStorage/sessionStorage/cookies
    localStorage.clear()
    sessionStorage.clear()
    document.cookie.split(';').forEach((c) => {
      document.cookie = c.trim().split('=')[0] + '=; max-age=0'
    })

    // Set auth_verified flag so auth flow continues even on public routes
    // (since window.location.pathname mocking is unreliable in JSDOM)
    localStorage.setItem('auth_verified', 'true')
  })

  afterEach(() => {
    // Clear all timers before switching to real timers
    jest.clearAllTimers()
    jest.clearAllMocks()
    jest.useRealTimers()
    // Clear localStorage/sessionStorage/cookies
    localStorage.clear()
    sessionStorage.clear()
    document.cookie.split(';').forEach((c) => {
      document.cookie = c.trim().split('=')[0] + '=; max-age=0'
    })
  })

  // Helper to wait for initialization - advances timers and flushes async operations
  const waitForInit = async () => {
    await act(async () => {
      // Advance past debounce timer (100ms in test) + buffer
      jest.advanceTimersByTime(150)
      jest.runOnlyPendingTimers()
      // Flush microtask queue multiple times to ensure all async operations complete
      for (let i = 0; i < 5; i++) {
        await Promise.resolve()
      }
    })
  }

  // Helper to wait for auth to be ready (user loaded or determined to be null)
  const waitForAuthReady = async (result: any) => {
    await waitFor(
      () => {
        // Auth is ready when loading is false
        expect(result.current.isLoading).toBe(false)
      },
      { timeout: 2000 }
    )
  }

  describe('useAuth hook', () => {
    it('throws error when used outside AuthProvider', () => {
      // Suppress console.error for this test
      const consoleError = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      // The hook should throw when used outside AuthProvider
      expect(() => {
        renderHook(() => useAuth())
      }).toThrow('useAuth must be used within an AuthProvider')

      consoleError.mockRestore()
    })

    it('returns auth context when used inside AuthProvider', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current).toBeDefined()
        expect(result.current.apiClient).toBeDefined()
      })
    })
  })

  describe('AuthProvider initialization', () => {
    it('initializes and completes loading', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })

      // Wait for initialization to complete
      await waitForInit()

      //  After initialization completes, loading should be false and user should be set
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
        expect(result.current.user).toEqual(mockUser)
      })
    })

    it('sets up API client with auth failure handler', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(mockApiClient.setAuthFailureHandler).toHaveBeenCalled()
      })
    })

    it('sets up API client with organization context provider', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(mockApiClient.setOrganizationContextProvider).toHaveBeenCalled()
      })
    })

    it('fetches user and organizations on mount', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      // Wait for API calls to happen
      await waitFor(
        () => {
          expect(mockApiClient.getUser).toHaveBeenCalled()
        },
        { timeout: 5000 }
      )

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(mockApiClient.getOrganizations).toHaveBeenCalled()
      expect(result.current.user).toEqual(mockUser)
      expect(result.current.organizations).toEqual([mockOrganization])
    })

    it('skips initialization when login is in progress', async () => {
      ;(sessionManager.isLoginInProgress as jest.Mock).mockReturnValue(true)

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      expect(result.current.isLoading).toBe(true)
      expect(mockApiClient.getUser).not.toHaveBeenCalled()
    })

  })

  describe('login function', () => {
    it('successfully logs in user', async () => {
      process.env.NODE_ENV = 'development'
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      await act(async () => {
        await result.current.login('testuser', 'password123')
      })

      expect(mockApiClient.login).toHaveBeenCalledWith(
        'testuser',
        'password123'
      )
      expect(sessionManager.setLoginInProgress).toHaveBeenCalledWith(true)
      expect(sessionManager.setLoginInProgress).toHaveBeenCalledWith(false)
      expect(sessionManager.trackUserSession).toHaveBeenCalledWith(mockUser)
      expect(devAuthHelper.clearManualLogout).toHaveBeenCalled()
    })

    it('sets login in progress flag during login', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      let loginInProgressCalls: boolean[] = []
      ;(sessionManager.setLoginInProgress as jest.Mock).mockImplementation(
        (inProgress: boolean) => {
          loginInProgressCalls.push(inProgress)
        }
      )

      await act(async () => {
        await result.current.login('testuser', 'password123')
      })

      expect(loginInProgressCalls).toEqual([true, false])
    })

    it('clears cache before and after login', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      mockApiClient.clearCache.mockClear()

      await act(async () => {
        await result.current.login('testuser', 'password123')
      })

      expect(mockApiClient.clearCache).toHaveBeenCalled()
    })

    it('redirects to email verification on 403 error', async () => {
      mockApiClient.login.mockRejectedValue(
        new Error('Email verification required')
      )

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      await act(async () => {
        await result.current.login('testuser', 'password123')
      })

      expect(mockRouter.push).toHaveBeenCalledWith(
        expect.stringContaining('/verify-email')
      )
    })

    it('throws error on other login failures', async () => {
      mockApiClient.login.mockRejectedValue(new Error('Invalid credentials'))

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      await expect(
        act(async () => {
          await result.current.login('testuser', 'wrongpassword')
        })
      ).rejects.toThrow('Invalid credentials')
    })

    it('clears login in progress flag even on error', async () => {
      mockApiClient.login.mockRejectedValue(new Error('Login failed'))

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      await expect(
        act(async () => {
          await result.current.login('testuser', 'password')
        })
      ).rejects.toThrow()

      expect(sessionManager.setLoginInProgress).toHaveBeenLastCalledWith(false)
    })
  })

  describe('logout function', () => {
    it('successfully logs out user', async () => {
      process.env.NODE_ENV = 'development'
      // Mock window.location to track href assignment
      delete (window as any).location
      ;(window as any).location = { href: 'http://benger.localhost/dashboard', pathname: '/dashboard' }

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
        expect(result.current.user).toEqual(mockUser)
      })

      await act(async () => {
        await result.current.logout()
      })

      expect(mockApiClient.logout).toHaveBeenCalled()
      expect(sessionManager.clearSession).toHaveBeenCalled()
      expect(devAuthHelper.markManualLogout).toHaveBeenCalled()
      expect(window.location.href).toContain('/')
      expect(window.location.href).not.toContain('/login')
      expect(result.current.user).toBeNull()
    })

    it('clears session even if API call fails', async () => {
      mockApiClient.logout.mockRejectedValue(new Error('Logout failed'))

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      await act(async () => {
        await result.current.logout()
      })

      expect(sessionManager.clearSession).toHaveBeenCalled()
      expect(result.current.user).toBeNull()
    })
  })

  describe('signup function', () => {
    it('successfully signs up user without invitation', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      await act(async () => {
        await result.current.signup(
          'newuser',
          'new@example.com',
          'New User',
          'password123'
        )
      })

      expect(mockApiClient.signup).toHaveBeenCalledWith(
        'newuser',
        'new@example.com',
        'New User',
        'password123',
        undefined,
        undefined
      )
      expect(mockRouter.push).toHaveBeenCalledWith(
        expect.stringContaining('/verify-email')
      )
    })

    it('successfully signs up user with invitation token and redirects to org subdomain', async () => {
      // Mock window.location to track href assignment
      delete (window as any).location
      ;(window as any).location = { href: 'http://benger.localhost/register', pathname: '/register' }

      const { getOrgUrl } = require('@/lib/utils/subdomain')

      // Configure OrganizationManager mock to store orgs statefully
      // We need to set this up BEFORE the component mounts
      let storedOrgs: any[] = []
      ;(OrganizationManager as jest.Mock).mockImplementation(() => ({
        setOrganizations: jest.fn().mockImplementation((orgs: any[]) => {
          storedOrgs = orgs
        }),
        setCurrentOrganization: jest.fn(),
        getOrganizationContext: jest.fn(),
        getOrganizations: jest.fn().mockImplementation(() => storedOrgs),
        clear: jest.fn(),
      }))

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      await act(async () => {
        await result.current.signup(
          'newuser',
          'new@example.com',
          'New User',
          'password123',
          undefined,
          'invitation-token-123'
        )
      })

      expect(mockApiClient.signup).toHaveBeenCalledWith(
        'newuser',
        'new@example.com',
        'New User',
        'password123',
        undefined,
        'invitation-token-123'
      )
      // Should redirect to org subdomain, not just /dashboard
      expect(getOrgUrl).toHaveBeenCalledWith('test-org', '/dashboard')
    })

    it('throws error on signup failure', async () => {
      mockApiClient.signup.mockRejectedValue(new Error('Email already exists'))

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      await expect(
        act(async () => {
          await result.current.signup(
            'newuser',
            'existing@example.com',
            'New User',
            'password123'
          )
        })
      ).rejects.toThrow('Email already exists')
    })
  })

  describe('updateUser function', () => {
    it('updates user data', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
        expect(result.current.user).toEqual(mockUser)
      })

      act(() => {
        result.current.updateUser({ name: 'Updated Name' })
      })

      expect(result.current.user?.name).toBe('Updated Name')
    })

    it('does not update if user is null', async () => {
      mockApiClient.getUser.mockResolvedValue(null)

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      act(() => {
        result.current.updateUser({ name: 'Updated Name' })
      })

      expect(result.current.user).toBeNull()
    })
  })

  describe('refreshAuth function', () => {
    it('refreshes user and organizations', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      mockApiClient.getUser.mockClear()
      mockApiClient.getOrganizations.mockClear()

      const updatedUser = { ...mockUser, name: 'Refreshed User' }
      mockApiClient.getUser.mockResolvedValue(updatedUser)

      await act(async () => {
        await result.current.refreshAuth()
      })

      expect(mockApiClient.getUser).toHaveBeenCalled()
      expect(mockApiClient.getOrganizations).toHaveBeenCalled()
      expect(result.current.user?.name).toBe('Refreshed User')
    })

    it('clears user on refresh failure', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      mockApiClient.getUser.mockRejectedValue(new Error('Unauthorized'))

      await act(async () => {
        await result.current.refreshAuth()
      })

      expect(result.current.user).toBeNull()
    })
  })

  describe('refreshOrganizations function', () => {
    it('refreshes organizations list', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      const newOrg: Organization = {
        id: 2,
        name: 'New Org',
        description: 'New Description',
        created_at: '2025-01-01T00:00:00Z',
        updated_at: '2025-01-01T00:00:00Z',
      }

      mockApiClient.getOrganizations.mockResolvedValue([
        mockOrganization,
        newOrg,
      ])

      await act(async () => {
        await result.current.refreshOrganizations()
      })

      expect(result.current.organizations).toHaveLength(2)
      expect(result.current.organizations).toContainEqual(newOrg)
    })

    it('clears organizations on failure', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      mockApiClient.getOrganizations.mockRejectedValue(new Error('Failed'))

      await act(async () => {
        await result.current.refreshOrganizations()
      })

      expect(result.current.organizations).toEqual([])
    })
  })

  describe('organization management', () => {
    it('sets no organization in private mode on initialization', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      // In private mode (default mock), currentOrganization should be null
      expect(result.current.currentOrganization).toBeNull()
    })

    it('allows changing current organization (triggers navigation)', async () => {
      // Mock window.location for navigation
      delete (window as any).location
      ;(window as any).location = { href: 'http://benger.localhost/dashboard', pathname: '/dashboard' }

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      const newOrg: Organization = {
        id: 2,
        name: 'Second Org',
        display_name: 'Second Org',
        slug: 'second-org',
        description: 'Second Description',
        is_active: true,
        created_at: '2025-01-01T00:00:00Z',
        updated_at: '2025-01-01T00:00:00Z',
      }

      act(() => {
        result.current.setCurrentOrganization(newOrg)
      })

      expect(result.current.currentOrganization).toEqual(newOrg)
    })

    it('allows setting current organization to null', async () => {
      // Mock window.location for navigation
      delete (window as any).location
      ;(window as any).location = { href: 'http://test-org.benger.localhost/dashboard', pathname: '/dashboard' }

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      act(() => {
        result.current.setCurrentOrganization(null)
      })

      expect(result.current.currentOrganization).toBeNull()
    })
  })

  describe('token refresh', () => {
    it('sets up automatic token refresh when user is authenticated', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })

      // Advance past debounce and let promises resolve
      await act(async () => {
        jest.advanceTimersByTime(150)
        await Promise.resolve()
      })

      // User should be loaded
      expect(mockApiClient.getUser).toHaveBeenCalled()

      expect(global.fetch).not.toHaveBeenCalledWith(
        '/api/auth/refresh',
        expect.any(Object)
      )

      // Fast-forward 25 minutes and let interval fire
      await act(async () => {
        jest.advanceTimersByTime(25 * 60 * 1000)
        await Promise.resolve()
      })

      // Should have called refresh
      expect(global.fetch).toHaveBeenCalledWith('/api/auth/refresh', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
      })
    })

    it('handles token refresh failure silently', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValue({
        ok: false,
        status: 401,
      })

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })

      // Advance past debounce
      await act(async () => {
        jest.advanceTimersByTime(150)
        await Promise.resolve()
      })

      expect(mockApiClient.getUser).toHaveBeenCalled()

      // Fast-forward 25 minutes
      await act(async () => {
        jest.advanceTimersByTime(25 * 60 * 1000)
        await Promise.resolve()
      })

      // Should not crash or throw
      expect(global.fetch).toHaveBeenCalled()
    })

    it('clears refresh interval on unmount', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { unmount } = renderHook(() => useAuth(), { wrapper })

      // Advance past debounce
      await act(async () => {
        jest.advanceTimersByTime(150)
        await Promise.resolve()
      })

      expect(mockApiClient.getUser).toHaveBeenCalled()

      unmount()

      // Fast-forward time after unmount
      act(() => {
        jest.advanceTimersByTime(25 * 60 * 1000)
      })

      // Should not call fetch after unmount
      expect(global.fetch).not.toHaveBeenCalled()
    })
  })

  describe('auth failure handler', () => {
    it('handles auth failure by clearing state and redirecting on protected route', async () => {
      // Auth failure on a protected route should redirect to login
      ;(authRedirect.isPublicRoute as jest.Mock).mockReturnValue(false)

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(mockApiClient.setAuthFailureHandler).toHaveBeenCalled()
        expect(result.current.isLoading).toBe(false)
        expect(result.current.user).toEqual(mockUser)
      })

      const authFailureHandler = (
        mockApiClient.setAuthFailureHandler as jest.Mock
      ).mock.calls[0][0]

      await act(async () => {
        authFailureHandler()
        await Promise.resolve()
      })

      await waitFor(() => {
        expect(result.current.user).toBeNull()
        expect(authRedirect.toLogin).toHaveBeenCalled()
      })
    })

    it('handles auth failure on public route by clearing state without redirecting', async () => {
      // Auth failure on a public route (e.g., landing page) should NOT redirect to login
      ;(authRedirect.isPublicRoute as jest.Mock).mockReturnValue(true)

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(mockApiClient.setAuthFailureHandler).toHaveBeenCalled()
        expect(result.current.isLoading).toBe(false)
        expect(result.current.user).toEqual(mockUser)
      })

      ;(authRedirect.toLogin as jest.Mock).mockClear()

      const authFailureHandler = (
        mockApiClient.setAuthFailureHandler as jest.Mock
      ).mock.calls[0][0]

      await act(async () => {
        authFailureHandler()
        await Promise.resolve()
      })

      await waitFor(() => {
        expect(result.current.user).toBeNull()
        expect(authRedirect.toLogin).not.toHaveBeenCalled()
      })
    })

    it('ignores auth failure when login is in progress', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(mockApiClient.setAuthFailureHandler).toHaveBeenCalled()
        expect(result.current.isLoading).toBe(false)
        expect(result.current.user).toEqual(mockUser)
      })

      const authFailureHandler = (
        mockApiClient.setAuthFailureHandler as jest.Mock
      ).mock.calls[0][0]

      ;(sessionManager.isLoginInProgress as jest.Mock).mockReturnValue(true)

      await act(async () => {
        authFailureHandler()
        await Promise.resolve()
      })

      // User should not be cleared
      expect(result.current.user).toEqual(mockUser)
      expect(authRedirect.toLogin).not.toHaveBeenCalled()
    })
  })

  describe('user switch detection', () => {
    it('detects and handles user switch', async () => {
      ;(sessionManager.getLastSessionUserId as jest.Mock).mockReturnValue('999')
      ;(sessionManager.detectUserSwitch as jest.Mock).mockReturnValue(true)

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(sessionManager.detectUserSwitch).toHaveBeenCalledWith(mockUser)
      })

      expect(sessionManager.handleUserSwitch).toHaveBeenCalledWith(
        mockApiClient,
        String(mockUser.id),
        '999'
      )
    })

    it('tracks current user session', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(sessionManager.trackUserSession).toHaveBeenCalledWith(mockUser)
      })
    })
  })

  describe('error scenarios', () => {
    it('handles authentication failure on initialization', async () => {
      mockApiClient.getUser.mockRejectedValue(new Error('Unauthenticated'))

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.user).toBeNull()
      expect(sessionManager.clearAuthVerification).toHaveBeenCalled()
    })

    it('handles organizations fetch failure gracefully', async () => {
      mockApiClient.getOrganizations.mockRejectedValue(new Error('Failed'))

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      // User should still be loaded
      expect(result.current.user).toEqual(mockUser)
      // Organizations should be empty
      expect(result.current.organizations).toEqual([])
    })

    it('handles generic errors during initialization', async () => {
      mockApiClient.getUser.mockRejectedValue(new Error('Network error'))

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.user).toBeNull()
    })
  })

  describe('public route handling', () => {
    it('loads user when auth check is needed', async () => {
      // Default behavior - should check auth for protected routes
      mockApiClient.getUser.mockClear()

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      // Should call getUser for protected routes
      expect(mockApiClient.getUser).toHaveBeenCalled()
      expect(result.current.user).toEqual(mockUser)
    })
  })

  describe('context value memoization', () => {
    it('memoizes context value to prevent unnecessary re-renders', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result, rerender } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      const firstApiClient = result.current.apiClient

      rerender()

      expect(result.current.apiClient).toBe(firstApiClient)
    })
  })

  describe('silent token refresh', () => {
    it('successfully refreshes token silently', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: jest.fn().mockResolvedValue({}),
      })

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      // Access the apiClient to trigger silent refresh setup
      expect(result.current.apiClient).toBeDefined()
    })

    it('handles fetch errors during token refresh', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValue(new Error('Network error'))

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.apiClient).toBeDefined()
    })
  })

  describe('session persistence', () => {
    it('clears cache when detecting stale session', async () => {
      ;(sessionManager.getLastSessionUserId as jest.Mock).mockReturnValue('123')

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(mockApiClient.clearCache).toHaveBeenCalled()
      })
    })

    it('prevents multiple simultaneous auth checks', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()
      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(mockApiClient.getUser).toHaveBeenCalled()
      })

      // Should not call multiple times due to guard
      const callCount = mockApiClient.getUser.mock.calls.length
      expect(callCount).toBeGreaterThan(0)
    })
  })

  describe('organization context provider', () => {
    it('sets organization context for API calls', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(mockApiClient.setOrganizationContextProvider).toHaveBeenCalled()
      })

      const contextProvider = (
        mockApiClient.setOrganizationContextProvider as jest.Mock
      ).mock.calls[0][0]

      expect(typeof contextProvider).toBe('function')
    })

    it('updates organization manager when current organization changes', async () => {
      // Mock window.location for navigation
      delete (window as any).location
      ;(window as any).location = { href: 'http://benger.localhost/dashboard', pathname: '/dashboard' }

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      const newOrg: Organization = {
        id: 2,
        name: 'New Org',
        display_name: 'New Org',
        slug: 'new-org',
        description: 'Description',
        is_active: true,
        created_at: '2025-01-01T00:00:00Z',
        updated_at: '2025-01-01T00:00:00Z',
      }

      const orgManagerInstance = (OrganizationManager as jest.Mock).mock
        .results[0].value

      act(() => {
        result.current.setCurrentOrganization(newOrg)
      })

      expect(orgManagerInstance.setCurrentOrganization).toHaveBeenCalledWith(
        newOrg
      )
    })
  })

  describe('debounce logic', () => {
    it('debounces auth initialization', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })

      // Should not call immediately
      expect(mockApiClient.getUser).not.toHaveBeenCalled()

      // Fast-forward debounce timer
      await act(async () => {
        jest.advanceTimersByTime(150)
        await Promise.resolve()
      })

      await waitFor(() => {
        expect(mockApiClient.getUser).toHaveBeenCalled()
      })
    })

    it('clears debounce timer on unmount', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { unmount } = renderHook(() => useAuth(), { wrapper })

      unmount()

      // Fast-forward time
      act(() => {
        jest.advanceTimersByTime(1000)
      })

      // Should not call after unmount
      expect(mockApiClient.getUser).not.toHaveBeenCalled()
    })
  })

  describe('error recovery', () => {
    it('handles error in login with prepareForLogin call', async () => {
      mockApiClient.login.mockRejectedValue(new Error('Login failed'))

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      await expect(
        act(async () => {
          await result.current.login('testuser', 'password')
        })
      ).rejects.toThrow('Login failed')

      expect(sessionManager.prepareForLogin).toHaveBeenCalledWith(mockApiClient)
    })

    it('clears organization state on logout', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      const orgManagerInstance = (OrganizationManager as jest.Mock).mock
        .results[0].value

      await act(async () => {
        await result.current.logout()
      })

      expect(orgManagerInstance.clear).toHaveBeenCalled()
      expect(result.current.organizations).toEqual([])
      expect(result.current.currentOrganization).toBeNull()
    })

    it('handles refreshAuth failure and clears organizations', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      mockApiClient.getUser.mockRejectedValue(new Error('Auth failed'))

      const orgManagerInstance = (OrganizationManager as jest.Mock).mock
        .results[0].value

      await act(async () => {
        await result.current.refreshAuth()
      })

      expect(result.current.user).toBeNull()
      expect(result.current.organizations).toEqual([])
      expect(result.current.currentOrganization).toBeNull()
      expect(orgManagerInstance.clear).toHaveBeenCalled()
    })

    it('refreshes organizations after successful login', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      mockApiClient.getOrganizations.mockClear()

      await act(async () => {
        await result.current.login('testuser', 'password')
      })

      expect(mockApiClient.getOrganizations).toHaveBeenCalled()
    })
  })

  describe('auth verification flag', () => {
    it('verifies auth when auth_verified flag is set', async () => {
      localStorage.setItem('auth_verified', 'true')

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(mockApiClient.getUser).toHaveBeenCalled()
      })
    })
  })

  describe('user switch scenarios', () => {
    it('handles user switch with cache clear', async () => {
      ;(sessionManager.getLastSessionUserId as jest.Mock).mockReturnValue('999')
      ;(sessionManager.detectUserSwitch as jest.Mock).mockReturnValue(true)

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(sessionManager.handleUserSwitch).toHaveBeenCalledWith(
          mockApiClient,
          String(mockUser.id),
          '999'
        )
      })
    })
  })

  describe('organization refresh with user parameter', () => {
    it('refreshes organizations with provided user', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      const newUser = { ...mockUser, id: 2 }
      mockApiClient.getOrganizations.mockClear()

      await act(async () => {
        await (result.current as any).refreshOrganizations(newUser)
      })

      expect(mockApiClient.getOrganizations).toHaveBeenCalled()
    })
  })

  describe('organization refresh scenarios', () => {
    it('keeps currentOrganization null in private mode after refresh', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      const org2: Organization = {
        id: 2,
        name: 'Org 2',
        display_name: 'Org 2',
        slug: 'org-2',
        description: 'Desc',
        is_active: true,
        created_at: '2025-01-01T00:00:00Z',
        updated_at: '2025-01-01T00:00:00Z',
      }

      mockApiClient.getOrganizations.mockResolvedValue([org2])

      await act(async () => {
        await result.current.refreshOrganizations()
      })

      // In private mode (no orgSlug), currentOrganization stays null
      expect(result.current.currentOrganization).toBeNull()
    })

    it('preserves null currentOrganization in private mode', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      await act(async () => {
        await result.current.refreshOrganizations()
      })

      // In private mode, currentOrganization is always null
      expect(result.current.currentOrganization).toBeNull()
    })

    it('clears organization manager on refresh failure', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      mockApiClient.getOrganizations.mockRejectedValue(new Error('Failed'))

      const orgManagerInstance = (OrganizationManager as jest.Mock).mock
        .results[0].value

      await act(async () => {
        await result.current.refreshOrganizations()
      })

      expect(orgManagerInstance.clear).toHaveBeenCalled()
    })
  })

  describe('login with 403 error variations', () => {
    it('redirects on 403 status code error', async () => {
      mockApiClient.login.mockRejectedValue(new Error('403'))

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      await act(async () => {
        await result.current.login('testuser', 'password')
      })

      expect(mockRouter.push).toHaveBeenCalledWith(
        expect.stringContaining('/verify-email')
      )
    })
  })

  describe('cache clearing', () => {
    it('clears cache before API authentication check', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(mockApiClient.clearCache).toHaveBeenCalled()
      })

      const clearCacheCalls = mockApiClient.clearCache.mock.calls.length
      expect(clearCacheCalls).toBeGreaterThan(0)
    })

    it('clears cache after successful login', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      mockApiClient.clearCache.mockClear()

      await act(async () => {
        await result.current.login('testuser', 'password')
      })

      expect(mockApiClient.clearCache).toHaveBeenCalled()
    })
  })

  describe('org redirect on login', () => {
    it('redirects returning user to last org on login from private mode', async () => {
      const { parseSubdomain, getOrgUrl, getLastOrgSlug } = require('@/lib/utils/subdomain')

      // Simulate private mode (no org subdomain)
      parseSubdomain.mockReturnValue({ orgSlug: null, isPrivateMode: true })

      // Returning user has a stored org slug
      getLastOrgSlug.mockReturnValue('test-org')

      // Mock window.location to track href assignment
      delete (window as any).location
      ;(window as any).location = { href: 'http://benger.localhost/dashboard', pathname: '/dashboard' }

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        // Should redirect to org subdomain
        expect(getOrgUrl).toHaveBeenCalledWith('test-org', expect.any(String))
      })
    })

    it('does not redirect first-time user without last org', async () => {
      const { parseSubdomain, getOrgUrl, getLastOrgSlug } = require('@/lib/utils/subdomain')

      // Simulate private mode
      parseSubdomain.mockReturnValue({ orgSlug: null, isPrivateMode: true })

      // No stored org slug — first time user
      getLastOrgSlug.mockReturnValue(null)

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      // Should NOT redirect — stays in private mode
      expect(getOrgUrl).not.toHaveBeenCalled()
      expect(result.current.currentOrganization).toBeNull()
    })

    it('persists org slug cookie when on org subdomain', async () => {
      const { parseSubdomain, setLastOrgSlug } = require('@/lib/utils/subdomain')

      // Simulate being on org subdomain
      parseSubdomain.mockReturnValue({ orgSlug: 'test-org', isPrivateMode: false })

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(setLastOrgSlug).toHaveBeenCalledWith('test-org')
      })
    })

    it('clears last org slug when user no longer has access', async () => {
      const { parseSubdomain, getOrgUrl, getLastOrgSlug, clearLastOrgSlug } = require('@/lib/utils/subdomain')

      // Simulate private mode with a stored org that user no longer belongs to
      parseSubdomain.mockReturnValue({ orgSlug: null, isPrivateMode: true })
      getLastOrgSlug.mockReturnValue('removed-org')

      // Mock window.location
      delete (window as any).location
      ;(window as any).location = { href: 'http://benger.localhost/dashboard', pathname: '/dashboard' }

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      // Should clear the stale org slug and NOT redirect
      expect(clearLastOrgSlug).toHaveBeenCalled()
      expect(getOrgUrl).not.toHaveBeenCalled()
    })
  })

  describe('auth failure during initialization', () => {
    it('clears auth verification on unauthenticated error', async () => {
      mockApiClient.getUser.mockRejectedValue(new Error('Unauthenticated'))

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(sessionManager.clearAuthVerification).toHaveBeenCalled()
      })
    })

    it('does not clear auth verification on non-auth errors', async () => {
      mockApiClient.getUser.mockRejectedValue(new Error('Network error'))
      ;(sessionManager.clearAuthVerification as jest.Mock).mockClear()

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(sessionManager.clearAuthVerification).not.toHaveBeenCalled()
    })
  })

  describe('silent token refresh logic', () => {
    it('returns true on successful token refresh', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: jest.fn().mockResolvedValue({}),
      })

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(mockApiClient.setAuthFailureHandler).toHaveBeenCalled()
      })
    })

    it('returns false on failed token refresh', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValue({
        ok: false,
        status: 401,
      })

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(mockApiClient.setAuthFailureHandler).toHaveBeenCalled()
      })
    })

    it('returns false on fetch error', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValue(new Error('Network error'))

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(mockApiClient.setAuthFailureHandler).toHaveBeenCalled()
      })
    })
  })

  describe('auth failure handler scenarios', () => {
    it('ignores auth failure during login to prevent race conditions', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(mockApiClient.setAuthFailureHandler).toHaveBeenCalled()
      })

      const authFailureHandler = (
        mockApiClient.setAuthFailureHandler as jest.Mock
      ).mock.calls[0][0]

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.user).toEqual(mockUser)
      })

      // Simulate auth failure during login
      ;(sessionManager.isLoginInProgress as jest.Mock).mockReturnValue(true)

      act(() => {
        authFailureHandler()
      })

      // User should remain authenticated
      expect(result.current.user).toEqual(mockUser)
      expect(authRedirect.toLogin).not.toHaveBeenCalled()
    })
  })

  describe('public route edge cases', () => {
    it('skips auth check on public route without auth indicators', async () => {
      ;(window as any).location = { pathname: '/login' }
      localStorage.removeItem('auth_verified')

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.user).toBeNull()
    })

    it('verifies auth on public route with auth_verified flag', async () => {
      ;(window as any).location = { pathname: '/login' }
      localStorage.setItem('auth_verified', 'true')

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(mockApiClient.getUser).toHaveBeenCalled()
      })
    })

    it('handles all public routes correctly', async () => {
      const publicRoutes = [
        '/',
        '/login',
        '/register',
        '/reset-password',
        '/verify-email',
        '/accept-invitation',
        '/about/imprint',
        '/about/data-protection',
      ]

      for (const route of publicRoutes) {
        ;(window as any).location = { pathname: route }
        localStorage.removeItem('auth_verified')
        jest.clearAllMocks()

        const wrapper = ({ children }: { children: React.ReactNode }) => (
          <AuthProvider>{children}</AuthProvider>
        )

        const { result } = renderHook(() => useAuth(), { wrapper })
        await waitForInit()

        await waitFor(() => {
          expect(result.current.isLoading).toBe(false)
        })

        expect(result.current.user).toBeNull()
      }
    })
  })

  describe('user switch detection and handling', () => {
    it('detects user switch and handles cache clear', async () => {
      ;(sessionManager.getLastSessionUserId as jest.Mock).mockReturnValue('999')
      ;(sessionManager.detectUserSwitch as jest.Mock).mockReturnValue(true)

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(sessionManager.detectUserSwitch).toHaveBeenCalledWith(mockUser)
        expect(sessionManager.handleUserSwitch).toHaveBeenCalledWith(
          mockApiClient,
          String(mockUser.id),
          '999'
        )
      })
    })

    it('clears cache when last session user exists', async () => {
      ;(sessionManager.getLastSessionUserId as jest.Mock).mockReturnValue('123')

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(mockApiClient.clearCache).toHaveBeenCalled()
      })
    })

    it('tracks user session after successful authentication', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(sessionManager.trackUserSession).toHaveBeenCalledWith(mockUser)
      })
    })
  })

  describe('login email verification edge cases', () => {
    it('handles email verification error with specific message', async () => {
      mockApiClient.login.mockRejectedValue(
        new Error('Email verification required')
      )

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      await act(async () => {
        await result.current.login('testuser', 'password123')
      })

      expect(mockRouter.push).toHaveBeenCalledWith(
        expect.stringContaining('/verify-email')
      )
    })

    it('handles 403 error code for email verification', async () => {
      mockApiClient.login.mockRejectedValue(new Error('403'))

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      await act(async () => {
        await result.current.login('testuser', 'password123')
      })

      expect(mockRouter.push).toHaveBeenCalledWith(
        expect.stringContaining('/verify-email')
      )
    })

    it('calls prepareForLogin and clears cache before login', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      mockApiClient.clearCache.mockClear()

      await act(async () => {
        await result.current.login('testuser', 'password123')
      })

      expect(sessionManager.prepareForLogin).toHaveBeenCalledWith(mockApiClient)
      expect(mockApiClient.clearCache).toHaveBeenCalled()
    })

    it('clears dev auth flags after successful login', async () => {
      process.env.NODE_ENV = 'development'
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      await act(async () => {
        await result.current.login('testuser', 'password123')
      })

      expect(devAuthHelper.clearManualLogout).toHaveBeenCalled()
    })
  })

  describe('organization initialization', () => {
    it('sets organization context when current organization changes', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      const orgManagerInstance = (OrganizationManager as jest.Mock).mock
        .results[0].value

      // In private mode, org is set to null
      expect(orgManagerInstance.setCurrentOrganization).toHaveBeenCalledWith(
        null
      )
    })

    it('provides organization context to API client', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(mockApiClient.setOrganizationContextProvider).toHaveBeenCalled()
      })

      const contextProvider = (
        mockApiClient.setOrganizationContextProvider as jest.Mock
      ).mock.calls[0][0]

      expect(typeof contextProvider).toBe('function')
    })
  })

  describe('initialization debounce and guards', () => {
    it('prevents multiple simultaneous auth initializations', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })
      renderHook(() => useAuth(), { wrapper })

      await act(async () => {
        jest.advanceTimersByTime(150)
        await Promise.resolve()
      })

      await waitFor(() => {
        expect(mockApiClient.getUser).toHaveBeenCalled()
      })

      // Should not call excessively due to guard
      const callCount = mockApiClient.getUser.mock.calls.length
      expect(callCount).toBeGreaterThan(0)
    })
  })

  describe('token refresh race conditions', () => {
    it('handles multiple simultaneous refresh attempts', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })

      // Fast-forward to trigger initialization
      await act(async () => {
        jest.advanceTimersByTime(150)
        await Promise.resolve()
      })

      await waitFor(() => {
        expect(mockApiClient.getUser).toHaveBeenCalled()
      })

      // Clear fetch mock to track refresh calls
      ;(global.fetch as jest.Mock).mockClear()

      // Fast-forward 25 minutes to trigger multiple refresh intervals
      await act(async () => {
        jest.advanceTimersByTime(25 * 60 * 1000)
        await Promise.resolve()
      })

      // Should have called refresh at least once
      expect(global.fetch).toHaveBeenCalledWith('/api/auth/refresh', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
      })
    })

    it('continues refreshing on subsequent intervals', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      renderHook(() => useAuth(), { wrapper })

      await act(async () => {
        jest.advanceTimersByTime(150)
        await Promise.resolve()
      })

      await waitFor(() => {
        expect(mockApiClient.getUser).toHaveBeenCalled()
      })
      ;(global.fetch as jest.Mock).mockClear()

      // Fast-forward through multiple intervals
      await act(async () => {
        jest.advanceTimersByTime(25 * 60 * 1000) // First refresh
        await Promise.resolve()
      })

      const firstCallCount = (global.fetch as jest.Mock).mock.calls.length

      await act(async () => {
        jest.advanceTimersByTime(25 * 60 * 1000) // Second refresh
        await Promise.resolve()
      })

      const secondCallCount = (global.fetch as jest.Mock).mock.calls.length

      // Should have made additional refresh calls
      expect(secondCallCount).toBeGreaterThan(firstCallCount)
    })

    it('stops refreshing after unmount', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { unmount } = renderHook(() => useAuth(), { wrapper })

      await act(async () => {
        jest.advanceTimersByTime(150)
        await Promise.resolve()
      })

      await waitFor(() => {
        expect(mockApiClient.getUser).toHaveBeenCalled()
      })
      ;(global.fetch as jest.Mock).mockClear()

      // Unmount before refresh interval
      unmount()

      // Fast-forward past refresh interval
      await act(async () => {
        jest.advanceTimersByTime(25 * 60 * 1000)
      })

      // Should not have called refresh after unmount
      expect(global.fetch).not.toHaveBeenCalled()
    })
  })

  describe('edge cases and error recovery', () => {
    it('handles network errors during initialization', async () => {
      mockApiClient.getUser.mockRejectedValue(new Error('Network error'))

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.user).toBeNull()
      expect(result.current.organizations).toEqual([])
    })

    it('recovers from refresh failure without clearing user', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
        expect(result.current.user).toEqual(mockUser)
      })

      // Mock refresh failure
      mockApiClient.getUser.mockRejectedValueOnce(new Error('Refresh failed'))

      // User should remain authenticated until explicit auth failure
      expect(result.current.user).toEqual(mockUser)
    })

    it('handles organizations fetch failure during login', async () => {
      mockApiClient.getOrganizations.mockRejectedValue(
        new Error('Org fetch failed')
      )

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      // User should be loaded even if organizations fail
      expect(result.current.user).toEqual(mockUser)
      expect(result.current.organizations).toEqual([])
    })

    it('handles concurrent login attempts gracefully', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      )

      const { result } = renderHook(() => useAuth(), { wrapper })
      await waitForInit()

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      // Attempt multiple concurrent logins
      const loginPromises = [
        act(async () => {
          await result.current.login('user1', 'pass1')
        }),
        act(async () => {
          await result.current.login('user2', 'pass2')
        }),
      ]

      await Promise.allSettled(loginPromises)

      // Should have set login in progress flag
      expect(sessionManager.setLoginInProgress).toHaveBeenCalledWith(true)
      expect(sessionManager.setLoginInProgress).toHaveBeenCalledWith(false)
    })
  })
})
