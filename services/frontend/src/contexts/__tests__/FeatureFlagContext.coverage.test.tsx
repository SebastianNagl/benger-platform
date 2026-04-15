/**
 * @jest-environment jsdom
 *
 * FeatureFlagContext branch coverage extension tests.
 * Targets: 401 error branch in refreshFlags, error object type check,
 * isEnabled with null/missing flags, checkFlag error path, useFeatureFlag error branch.
 */

jest.unmock('@/contexts/FeatureFlagContext')

import { act, renderHook, waitFor } from '@testing-library/react'
import React from 'react'

import * as apiModule from '@/lib/api'
import * as AuthContext from '../AuthContext'
import {
  FeatureFlagProvider,
  useFeatureFlag,
  useFeatureFlags,
} from '../FeatureFlagContext'

describe('FeatureFlagContext - branch coverage extensions', () => {
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

  let useAuthSpy: jest.SpyInstance

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <FeatureFlagProvider>{children}</FeatureFlagProvider>
  )

  beforeEach(() => {
    jest.clearAllMocks()
    useAuthSpy = jest.spyOn(AuthContext, 'useAuth').mockReturnValue({
      user: mockUser,
      isLoading: false,
      organizations: [],
      currentOrganization: null,
      setCurrentOrganization: jest.fn(),
      login: jest.fn(),
      logout: jest.fn(),
      signup: jest.fn(),
      refreshAuth: jest.fn(),
      updateUser: jest.fn(),
      apiClient: {} as any,
      refreshOrganizations: jest.fn(),
    } as any)
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it('should suppress console.error for 401 errors during refreshFlags', async () => {
    const error401 = new Error('Request failed with 401')
    ;(apiModule.api as any).getFeatureFlags = jest.fn().mockRejectedValue(error401)

    const consoleSpy = jest.spyOn(console, 'error').mockImplementation()

    const { result } = renderHook(() => useFeatureFlags(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    // 401 errors should NOT trigger console.error
    expect(consoleSpy).not.toHaveBeenCalledWith(
      'Error fetching feature flags:',
      error401
    )
    expect(result.current.error).toBe('Request failed with 401')

    consoleSpy.mockRestore()
  })

  it('should log non-401 errors during refreshFlags', async () => {
    const networkError = new Error('Network failure')
    ;(apiModule.api as any).getFeatureFlags = jest.fn().mockRejectedValue(networkError)

    const consoleSpy = jest.spyOn(console, 'error').mockImplementation()

    const { result } = renderHook(() => useFeatureFlags(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    // Non-401 errors SHOULD trigger console.error
    expect(consoleSpy).toHaveBeenCalledWith(
      'Error fetching feature flags:',
      networkError
    )
    expect(result.current.error).toBe('Network failure')

    consoleSpy.mockRestore()
  })

  it('should handle non-Error objects in refreshFlags error path', async () => {
    ;(apiModule.api as any).getFeatureFlags = jest.fn().mockRejectedValue('string error')

    const consoleSpy = jest.spyOn(console, 'error').mockImplementation()

    const { result } = renderHook(() => useFeatureFlags(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    // Non-Error thrown value should use fallback message
    expect(result.current.error).toBe('Failed to fetch feature flags')

    consoleSpy.mockRestore()
  })

  it('isEnabled should return false for undefined flag', async () => {
    ;(apiModule.api as any).getFeatureFlags = jest.fn().mockResolvedValue({ someFlag: true })

    const { result } = renderHook(() => useFeatureFlags(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.isEnabled('nonExistentFlag')).toBe(false)
    expect(result.current.isEnabled('someFlag')).toBe(true)
  })

  it('isEnabled should return false when flags is empty', async () => {
    ;(apiModule.api as any).getFeatureFlags = jest.fn().mockResolvedValue({})

    const { result } = renderHook(() => useFeatureFlags(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.isEnabled('anything')).toBe(false)
  })

  it('checkFlag should return false when user is null', async () => {
    useAuthSpy.mockReturnValue({
      user: null,
      isLoading: false,
      organizations: [],
      currentOrganization: null,
      setCurrentOrganization: jest.fn(),
      login: jest.fn(),
      logout: jest.fn(),
      signup: jest.fn(),
      refreshAuth: jest.fn(),
      updateUser: jest.fn(),
      apiClient: {} as any,
      refreshOrganizations: jest.fn(),
    })

    ;(apiModule.api as any).getFeatureFlags = jest.fn().mockResolvedValue({})

    const { result } = renderHook(() => useFeatureFlags(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    const flagValue = await result.current.checkFlag('someFlag')
    expect(flagValue).toBe(false)
  })

  it('checkFlag should return false on API error', async () => {
    ;(apiModule.api as any).getFeatureFlags = jest.fn().mockResolvedValue({})
    ;(apiModule.api as any).checkFeatureFlag = jest.fn().mockRejectedValue(new Error('API error'))

    const consoleSpy = jest.spyOn(console, 'error').mockImplementation()

    const { result } = renderHook(() => useFeatureFlags(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    const flagValue = await result.current.checkFlag('someFlag')
    expect(flagValue).toBe(false)
    expect(consoleSpy).toHaveBeenCalled()

    consoleSpy.mockRestore()
  })

  it('checkFlag should return is_enabled value on success', async () => {
    ;(apiModule.api as any).getFeatureFlags = jest.fn().mockResolvedValue({})
    ;(apiModule.api as any).checkFeatureFlag = jest.fn().mockResolvedValue({ is_enabled: true })

    const { result } = renderHook(() => useFeatureFlags(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    const flagValue = await result.current.checkFlag('testFlag')
    expect(flagValue).toBe(true)
  })

  it('should clear flags and stop loading when user is null', async () => {
    useAuthSpy.mockReturnValue({
      user: null,
      isLoading: false,
      organizations: [],
      currentOrganization: null,
      setCurrentOrganization: jest.fn(),
      login: jest.fn(),
      logout: jest.fn(),
      signup: jest.fn(),
      refreshAuth: jest.fn(),
      updateUser: jest.fn(),
      apiClient: {} as any,
      refreshOrganizations: jest.fn(),
    })

    const { result } = renderHook(() => useFeatureFlags(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.flags).toEqual({})
  })
})

describe('useFeatureFlag convenience hook - branch coverage', () => {
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

  beforeEach(() => {
    jest.clearAllMocks()
    jest.spyOn(AuthContext, 'useAuth').mockReturnValue({
      user: mockUser,
      isLoading: false,
      organizations: [],
      currentOrganization: null,
      setCurrentOrganization: jest.fn(),
      login: jest.fn(),
      logout: jest.fn(),
      signup: jest.fn(),
      refreshAuth: jest.fn(),
      updateUser: jest.fn(),
      apiClient: {} as any,
      refreshOrganizations: jest.fn(),
    } as any)
  })

  it('should return false for unknown flag via useFeatureFlag', async () => {
    ;(apiModule.api as any).getFeatureFlags = jest.fn().mockResolvedValue({ known: true })

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <FeatureFlagProvider>{children}</FeatureFlagProvider>
    )

    const { result } = renderHook(() => useFeatureFlag('unknown'), { wrapper })

    await waitFor(() => {
      // The flag should resolve to false for unknown keys
      expect(result.current).toBe(false)
    })
  })

  it('should return true for known enabled flag via useFeatureFlag', async () => {
    ;(apiModule.api as any).getFeatureFlags = jest.fn().mockResolvedValue({ myFlag: true })

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <FeatureFlagProvider>{children}</FeatureFlagProvider>
    )

    const { result } = renderHook(() => useFeatureFlag('myFlag'), { wrapper })

    await waitFor(() => {
      expect(result.current).toBe(true)
    })
  })

  it('should return false for known disabled flag via useFeatureFlag', async () => {
    ;(apiModule.api as any).getFeatureFlags = jest.fn().mockResolvedValue({ myFlag: false })

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <FeatureFlagProvider>{children}</FeatureFlagProvider>
    )

    const { result } = renderHook(() => useFeatureFlag('myFlag'), { wrapper })

    await waitFor(() => {
      expect(result.current).toBe(false)
    })
  })
})
