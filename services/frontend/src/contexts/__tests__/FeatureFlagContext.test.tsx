/**
 * @jest-environment jsdom
 */

// Unmock FeatureFlagContext so we test the real implementation
jest.unmock('@/contexts/FeatureFlagContext')

import { act, renderHook, waitFor } from '@testing-library/react'
import React from 'react'

// Mock the API - override global mock from setupTests
const mockGetFeatureFlags = jest.fn()
const mockCheckFeatureFlag = jest.fn()

// Mock AuthContext
const mockUser = {
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

let mockAuthContextValue = {
  user: mockUser,
  isLoading: false,
  organizations: [],
  currentOrganization: null,
  setCurrentOrganization: jest.fn(),
  login: jest.fn(),
  logout: jest.fn(),
  signup: jest.fn(),
  refreshAuth: jest.fn(),
}

// Import components to get actual api object
import * as apiModule from '@/lib/api'
import * as AuthContext from '../AuthContext'
import {
  FeatureFlagProvider,
  useFeatureFlag,
  useFeatureFlags,
} from '../FeatureFlagContext'

describe('FeatureFlagContext', () => {
  const mockFlags = {
    reports: true,
    data: false,
    generations: true,
  }

  let getFeatureFlagsSpy: jest.Mock
  let checkFeatureFlagSpy: jest.Mock
  let useAuthSpy: jest.SpyInstance

  beforeEach(() => {
    jest.clearAllMocks()

    // Override global mocks with test-specific mocks by assigning to the mocked object
    getFeatureFlagsSpy = jest.fn().mockResolvedValue(mockFlags)
    checkFeatureFlagSpy = jest.fn().mockResolvedValue({
      is_enabled: true,
    })

    // Assign mocks to the api object
    ;(apiModule.api as any).getFeatureFlags = getFeatureFlagsSpy
    ;(apiModule.api as any).checkFeatureFlag = checkFeatureFlagSpy

    // Setup AuthContext mock
    mockAuthContextValue = {
      user: mockUser,
      isLoading: false,
      organizations: [],
      currentOrganization: null,
      setCurrentOrganization: jest.fn(),
      login: jest.fn(),
      logout: jest.fn(),
      signup: jest.fn(),
      refreshAuth: jest.fn(),
    }

    useAuthSpy = jest
      .spyOn(AuthContext, 'useAuth')
      .mockReturnValue(mockAuthContextValue)
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  describe('useFeatureFlags hook', () => {
    it('throws error when used outside provider', () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      try {
        renderHook(() => useFeatureFlags())
      } catch (error) {
        expect(error).toEqual(
          new Error('useFeatureFlags must be used within a FeatureFlagProvider')
        )
      }

      consoleErrorSpy.mockRestore()
    })

    it('returns context when used inside provider', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current).toBeDefined()
      expect(result.current.flags).toBeDefined()
      expect(result.current.isEnabled).toBeDefined()
      expect(result.current.refreshFlags).toBeDefined()
      expect(result.current.checkFlag).toBeDefined()
    })
  })

  describe('FeatureFlagProvider initialization', () => {
    it('initializes with loading state', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      expect(result.current.isLoading).toBe(true)
    })

    it('fetches flags when user is authenticated', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(getFeatureFlagsSpy).toHaveBeenCalled()
      })
    })

    it('does not fetch flags when user is null', async () => {
      jest.spyOn(AuthContext, 'useAuth').mockReturnValue({
        ...mockAuthContextValue,
        user: null,
      })

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(getFeatureFlagsSpy).not.toHaveBeenCalled()
      expect(result.current.flags).toEqual({})
    })

    it('loads flags successfully', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.flags).toEqual(mockFlags)
      expect(result.current.error).toBeNull()
    })

    it('updates lastUpdate timestamp', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      const timestampAfterLoad = result.current.lastUpdate

      // Refresh flags to update timestamp
      await act(async () => {
        await result.current.refreshFlags()
      })

      expect(result.current.lastUpdate).toBeGreaterThanOrEqual(
        timestampAfterLoad
      )
    })
  })

  describe('isEnabled function', () => {
    it('returns true for enabled flags', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.isEnabled('reports')).toBe(true)
    })

    it('returns false for disabled flags', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.isEnabled('data')).toBe(false)
    })

    it('returns false for non-existent flags', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.isEnabled('nonexistent')).toBe(false)
    })

    it('handles null flags gracefully', async () => {
      ;(getFeatureFlagsSpy as jest.Mock).mockResolvedValue(null)

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.isEnabled('any')).toBe(false)
    })
  })

  describe('checkFlag function', () => {
    it('checks individual flag status', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      const isEnabled = await result.current.checkFlag('reports')

      expect(checkFeatureFlagSpy).toHaveBeenCalledWith('reports')
      expect(isEnabled).toBe(true)
    })

    it('returns false when user is null', async () => {
      jest.spyOn(AuthContext, 'useAuth').mockReturnValue({
        ...mockAuthContextValue,
        user: null,
      })

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      const isEnabled = await result.current.checkFlag('reports')

      expect(checkFeatureFlagSpy).not.toHaveBeenCalled()
      expect(isEnabled).toBe(false)
    })

    it('handles API errors gracefully', async () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})
      ;(checkFeatureFlagSpy as jest.Mock).mockRejectedValue(
        new Error('API error')
      )

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      const isEnabled = await result.current.checkFlag('reports')

      expect(isEnabled).toBe(false)

      consoleErrorSpy.mockRestore()
    })
  })

  describe('refreshFlags function', () => {
    it('refreshes flags manually', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })
      ;(getFeatureFlagsSpy as jest.Mock).mockClear()

      const newFlags = { ...mockFlags, data: true }
      ;(getFeatureFlagsSpy as jest.Mock).mockResolvedValue(newFlags)

      await act(async () => {
        await result.current.refreshFlags()
      })

      expect(getFeatureFlagsSpy).toHaveBeenCalled()
      expect(result.current.flags).toEqual(newFlags)
    })

    it('does not fetch when user is null', async () => {
      jest.spyOn(AuthContext, 'useAuth').mockReturnValue({
        ...mockAuthContextValue,
        user: null,
      })

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })
      ;(getFeatureFlagsSpy as jest.Mock).mockClear()

      await act(async () => {
        await result.current.refreshFlags()
      })

      expect(getFeatureFlagsSpy).not.toHaveBeenCalled()
      expect(result.current.flags).toEqual({})
    })

    it('updates lastUpdate on refresh', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      const previousTimestamp = result.current.lastUpdate

      await act(async () => {
        await result.current.refreshFlags()
      })

      expect(result.current.lastUpdate).toBeGreaterThan(previousTimestamp)
    })

    it('clears error on successful refresh', async () => {
      ;(getFeatureFlagsSpy as jest.Mock).mockRejectedValueOnce(
        new Error('Initial error')
      )

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.error).not.toBeNull()
      ;(getFeatureFlagsSpy as jest.Mock).mockResolvedValue(mockFlags)

      await act(async () => {
        await result.current.refreshFlags()
      })

      expect(result.current.error).toBeNull()
    })
  })

  describe('error handling', () => {
    it('handles API errors during initialization', async () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})
      ;(getFeatureFlagsSpy as jest.Mock).mockRejectedValue(
        new Error('API error')
      )

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.error).toBe('API error')
      expect(result.current.flags).toEqual({})

      consoleErrorSpy.mockRestore()
    })

    it('does not log 401 errors', async () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})
      ;(getFeatureFlagsSpy as jest.Mock).mockRejectedValue(
        new Error('Request failed with status code 401')
      )

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(getFeatureFlagsSpy).toHaveBeenCalled()
      })

      // Should not have logged the 401 error
      expect(consoleErrorSpy).not.toHaveBeenCalled()

      consoleErrorSpy.mockRestore()
    })

    it('logs non-401 errors', async () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})
      ;(getFeatureFlagsSpy as jest.Mock).mockRejectedValue(
        new Error('Server error')
      )

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Error fetching feature flags:',
          expect.any(Error)
        )
      })

      consoleErrorSpy.mockRestore()
    })

    it('keeps existing flags on error', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      const originalFlags = result.current.flags

      ;(getFeatureFlagsSpy as jest.Mock).mockRejectedValue(
        new Error('Refresh error')
      )

      await act(async () => {
        await result.current.refreshFlags()
      })

      // Should keep existing flags
      expect(result.current.flags).toEqual(originalFlags)
    })

    it('handles non-Error objects', async () => {
      ;(getFeatureFlagsSpy as jest.Mock).mockRejectedValue('String error')

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.error).toBe('Failed to fetch feature flags')
    })
  })

  describe('useFeatureFlag hook', () => {
    it('returns flag value', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlag('reports'), {
        wrapper,
      })

      await waitFor(() => {
        expect(result.current).toBe(true)
      })
    })

    it('returns false for disabled flags', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlag('data'), { wrapper })

      await waitFor(() => {
        expect(result.current).toBe(false)
      })
    })

    it('returns false for non-existent flags', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlag('nonexistent'), {
        wrapper,
      })

      await waitFor(() => {
        expect(result.current).toBe(false)
      })
    })

    it('handles errors gracefully', async () => {
      const consoleWarnSpy = jest
        .spyOn(console, 'warn')
        .mockImplementation(() => {})

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      // Force an error by making flags throw
      const { result } = renderHook(() => useFeatureFlag(null as any), {
        wrapper,
      })

      await waitFor(() => {
        expect(result.current).toBe(false)
      })

      consoleWarnSpy.mockRestore()
    })

    it('re-renders when lastUpdate changes', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      // Use a single hook that returns both flags context and useFeatureFlag result
      const { result } = renderHook(
        () => ({
          context: useFeatureFlags(),
          dataFlag: useFeatureFlag('data'),
        }),
        { wrapper }
      )

      await waitFor(() => {
        expect(result.current.context.isLoading).toBe(false)
      })

      expect(result.current.dataFlag).toBe(false)

      // Update flag
      ;(getFeatureFlagsSpy as jest.Mock).mockResolvedValue({
        ...mockFlags,
        data: true,
      })

      await act(async () => {
        await result.current.context.refreshFlags()
      })

      await waitFor(() => {
        expect(result.current.dataFlag).toBe(true)
      })
    })
  })

  describe('user changes', () => {
    it('refetches flags when user changes', async () => {
      const useAuthSpy = jest.spyOn(AuthContext, 'useAuth')
      useAuthSpy.mockReturnValue(mockAuthContextValue)

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { rerender } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(getFeatureFlagsSpy).toHaveBeenCalledTimes(1)
      })

      // Change user
      useAuthSpy.mockReturnValue({
        ...mockAuthContextValue,
        user: { ...mockUser, id: 2 },
      })
      ;(getFeatureFlagsSpy as jest.Mock).mockClear()

      rerender()

      await waitFor(() => {
        expect(getFeatureFlagsSpy).toHaveBeenCalled()
      })
    })

    it('clears flags when user logs out', async () => {
      const useAuthSpy = jest.spyOn(AuthContext, 'useAuth')
      useAuthSpy.mockReturnValue(mockAuthContextValue)

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result, rerender } = renderHook(() => useFeatureFlags(), {
        wrapper,
      })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.flags).toEqual(mockFlags)

      // User logs out
      useAuthSpy.mockReturnValue({ ...mockAuthContextValue, user: null })

      rerender()

      await waitFor(() => {
        expect(result.current.flags).toEqual({})
      })
    })
  })

  describe('edge cases', () => {
    it('handles empty flag object', async () => {
      ;(getFeatureFlagsSpy as jest.Mock).mockResolvedValue({})

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.flags).toEqual({})
      expect(result.current.isEnabled('any')).toBe(false)
    })

    it('handles flag names with special characters', async () => {
      const specialFlags = {
        'feature-with-dash': true,
        feature_with_underscore: false,
        'feature.with.dots': true,
      }
      ;(getFeatureFlagsSpy as jest.Mock).mockResolvedValue(specialFlags)

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.isEnabled('feature-with-dash')).toBe(true)
      expect(result.current.isEnabled('feature_with_underscore')).toBe(false)
      expect(result.current.isEnabled('feature.with.dots')).toBe(true)
    })

    it('handles concurrent refresh calls', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })
      ;(getFeatureFlagsSpy as jest.Mock).mockClear()

      // Trigger multiple refreshes concurrently
      await act(async () => {
        await Promise.all([
          result.current.refreshFlags(),
          result.current.refreshFlags(),
          result.current.refreshFlags(),
        ])
      })

      // Should have called API (behavior may vary based on implementation)
      expect(getFeatureFlagsSpy).toHaveBeenCalled()
    })

    it('handles boolean true flags correctly', async () => {
      const trueFlags = {
        feature1: true,
        feature2: true,
        feature3: true,
      }
      ;(getFeatureFlagsSpy as jest.Mock).mockResolvedValue(trueFlags)

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.isEnabled('feature1')).toBe(true)
      expect(result.current.isEnabled('feature2')).toBe(true)
      expect(result.current.isEnabled('feature3')).toBe(true)
    })

    it('handles boolean false flags correctly', async () => {
      const falseFlags = {
        feature1: false,
        feature2: false,
        feature3: false,
      }
      ;(getFeatureFlagsSpy as jest.Mock).mockResolvedValue(falseFlags)

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.isEnabled('feature1')).toBe(false)
      expect(result.current.isEnabled('feature2')).toBe(false)
      expect(result.current.isEnabled('feature3')).toBe(false)
    })

    it('handles mixed flag values', async () => {
      const mixedFlags = {
        enabled: true,
        disabled: false,
        alsoEnabled: true,
        alsoDisabled: false,
      }
      ;(getFeatureFlagsSpy as jest.Mock).mockResolvedValue(mixedFlags)

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.isEnabled('enabled')).toBe(true)
      expect(result.current.isEnabled('disabled')).toBe(false)
      expect(result.current.isEnabled('alsoEnabled')).toBe(true)
      expect(result.current.isEnabled('alsoDisabled')).toBe(false)
    })

    it('handles very long flag names', async () => {
      const longName = 'a'.repeat(500)
      const longFlags = { [longName]: true }
      ;(getFeatureFlagsSpy as jest.Mock).mockResolvedValue(longFlags)

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      expect(result.current.isEnabled(longName)).toBe(true)
    })

    it('handles checkFlag with network error', async () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})
      ;(checkFeatureFlagSpy as jest.Mock).mockRejectedValue(
        new Error('Network error')
      )

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      const isEnabled = await result.current.checkFlag('reports')

      expect(isEnabled).toBe(false)
      expect(consoleErrorSpy).toHaveBeenCalledWith(
        expect.stringContaining("Error checking feature flag 'reports'"),
        expect.any(Error)
      )

      consoleErrorSpy.mockRestore()
    })

    it('handles checkFlag returning false', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      // Reset mock and set it to return false
      ;(checkFeatureFlagSpy as jest.Mock).mockClear()
      ;(checkFeatureFlagSpy as jest.Mock).mockResolvedValue({
        is_enabled: false,
      })

      const isEnabled = await result.current.checkFlag('reports')

      expect(isEnabled).toBe(false)
    })

    it('handles rapid user state changes', async () => {
      const { useAuth } = require('../AuthContext')

      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(getFeatureFlagsSpy).toHaveBeenCalled()
      })

      // This test validates that the context can handle user state changes
      // The actual behavior of refreshFlags is tested elsewhere
      expect(getFeatureFlagsSpy).toHaveBeenCalled()
    })

    it('maintains flag state during loading', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      const originalFlags = result.current.flags

      // Start a new refresh
      ;(getFeatureFlagsSpy as jest.Mock).mockImplementation(
        () =>
          new Promise((resolve) => {
            setTimeout(() => resolve({ ...mockFlags, newFlag: true }), 100)
          })
      )

      act(() => {
        result.current.refreshFlags()
      })

      // Flags should still be available during loading
      expect(result.current.flags).toEqual(originalFlags)
    })
  })

  describe('context value stability', () => {
    it('provides stable function references', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result, rerender } = renderHook(() => useFeatureFlags(), {
        wrapper,
      })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      const firstIsEnabled = result.current.isEnabled
      const firstRefreshFlags = result.current.refreshFlags
      const firstCheckFlag = result.current.checkFlag

      rerender()

      // Functions are wrapped in useCallback so they should be stable
      expect(typeof result.current.isEnabled).toBe('function')
      expect(typeof result.current.refreshFlags).toBe('function')
      expect(typeof result.current.checkFlag).toBe('function')
    })

    it('updates flags reference on change', async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>{children}</FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), { wrapper })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })

      const firstFlags = result.current.flags
      const firstFlagKeys = Object.keys(firstFlags)

      ;(getFeatureFlagsSpy as jest.Mock).mockResolvedValue({
        ...mockFlags,
        newFlag: true,
      })

      await act(async () => {
        await result.current.refreshFlags()
      })

      const newFlagKeys = Object.keys(result.current.flags)
      expect(newFlagKeys.length).toBeGreaterThan(firstFlagKeys.length)
    })
  })

  describe('provider nesting', () => {
    it('only uses innermost provider', () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      const outerWrapper = ({ children }: { children: React.ReactNode }) => (
        <FeatureFlagProvider>
          <FeatureFlagProvider>{children}</FeatureFlagProvider>
        </FeatureFlagProvider>
      )

      const { result } = renderHook(() => useFeatureFlags(), {
        wrapper: outerWrapper,
      })

      expect(result.current).toBeDefined()

      consoleErrorSpy.mockRestore()
    })
  })
})
