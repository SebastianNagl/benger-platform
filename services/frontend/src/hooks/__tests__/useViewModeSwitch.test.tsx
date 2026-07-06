/**
 * @jest-environment jsdom
 *
 * Tests for useViewModeSwitch — the shared student⇄expert switch gating + action
 * (Issue #35).
 *
 * Under the CLOSED-BETA LOCK the switch is never offered on the benchmark
 * platform: the status is only ever 'unavailable' (or 'loading' before
 * hydration). switchTo still performs the optimistic local flip + navigate +
 * server persist, so it stays correct for when opt-in switching is reopened and
 * for the student-locked-host sidebar surface.
 */

import { renderHook, act, waitFor } from '@testing-library/react'

const EDITION_KEY = 'NEXT_PUBLIC_BENGER_EDITION'
const originalEdition = process.env[EDITION_KEY]

const mockSetUiMode = jest.fn()
const mockUpdateUser = jest.fn()
const mockPush = jest.fn()
const mockPrefetch = jest.fn()
let mockResolved: 'student' | 'expert' = 'student'
let mockHydrated = true
let mockAuth: any = {
  user: { id: 'u1', is_superadmin: true },
  organizations: [],
  isLoading: false,
  updateUser: mockUpdateUser,
}

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, prefetch: mockPrefetch }),
}))
jest.mock('@/stores', () => ({
  useUIStore: (selector: any) => selector({ setUiMode: mockSetUiMode }),
}))
jest.mock('@/contexts/AuthContext', () => ({ useAuth: () => mockAuth }))
jest.mock('@/contexts/HydrationContext', () => ({ useHydration: () => mockHydrated }))

// Hoist-safe: the api-client mock fn is created INSIDE the factory (jest.mock is
// hoisted above the module-under-test's require, so a top-level const would TDZ),
// then re-grabbed below.
jest.mock('@/contexts/ApiClientContext', () => {
  const fn = jest.fn().mockResolvedValue({ preferred_ui_mode: 'expert' })
  return {
    __esModule: true,
    useOptionalApiClient: () => ({ setUiMode: fn }),
    __mockApiSetUiMode: fn,
  }
})
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: { setUiMode: jest.fn().mockResolvedValue({ preferred_ui_mode: 'expert' }) },
}))
jest.mock('@/hooks/useResolvedUiMode', () => ({
  isExtendedEdition: () => process.env.NEXT_PUBLIC_BENGER_EDITION === 'extended',
  useResolvedUiMode: () => mockResolved,
}))

const mockApiSetUiMode = (require('@/contexts/ApiClientContext') as any)
  .__mockApiSetUiMode as jest.Mock

import { useViewModeSwitch } from '../useViewModeSwitch'

describe('useViewModeSwitch', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockResolved = 'student'
    mockHydrated = true
    mockAuth = {
      user: { id: 'u1', is_superadmin: true },
      organizations: [],
      isLoading: false,
      updateUser: mockUpdateUser,
    }
    process.env[EDITION_KEY] = 'extended'
  })
  afterEach(() => {
    if (originalEdition === undefined) delete process.env[EDITION_KEY]
    else process.env[EDITION_KEY] = originalEdition
  })

  it('is unavailable in the community edition', () => {
    delete process.env[EDITION_KEY]
    const { result } = renderHook(() => useViewModeSwitch())
    expect(result.current.status).toBe('unavailable')
  })

  it("is 'loading' until hydrated (role-flicker guard)", () => {
    mockHydrated = false
    const { result } = renderHook(() => useViewModeSwitch())
    expect(result.current.status).toBe('loading')
  })

  it("is 'loading' while auth is loading", () => {
    mockAuth = { ...mockAuth, isLoading: true }
    const { result } = renderHook(() => useViewModeSwitch())
    expect(result.current.status).toBe('loading')
  })

  it('CLOSED-BETA LOCK: unavailable even for a capable superadmin on the benchmark platform', () => {
    // extended + mounted + superadmin would previously be 'ready'; the beta lock
    // forces 'unavailable' so the toggle never shows to admins/contributors.
    const { result } = renderHook(() => useViewModeSwitch())
    expect(result.current.status).toBe('unavailable')
  })

  it('switchTo performs the optimistic flip, navigates, and persists server-side', async () => {
    mockResolved = 'student'
    const { result } = renderHook(() => useViewModeSwitch())
    await act(async () => {
      await result.current.switchTo('expert')
    })
    expect(mockSetUiMode).toHaveBeenCalledWith('expert') // optimistic local flip
    expect(mockPush).toHaveBeenCalledWith('/dashboard') // navigate to the expert home
    await waitFor(() => expect(mockApiSetUiMode).toHaveBeenCalledWith('expert'))
    expect(mockUpdateUser).toHaveBeenCalledWith({ preferred_ui_mode: 'expert' })
  })

  it('switchTo(student) navigates to the student home', async () => {
    mockResolved = 'expert'
    const { result } = renderHook(() => useViewModeSwitch())
    await act(async () => {
      await result.current.switchTo('student')
    })
    expect(mockSetUiMode).toHaveBeenCalledWith('student')
    expect(mockPush).toHaveBeenCalledWith('/student')
  })

  it('switchTo is a no-op when the target already equals the resolved mode', async () => {
    mockResolved = 'student'
    const { result } = renderHook(() => useViewModeSwitch())
    await act(async () => {
      await result.current.switchTo('student')
    })
    expect(mockSetUiMode).not.toHaveBeenCalled()
    expect(mockPush).not.toHaveBeenCalled()
  })
})
