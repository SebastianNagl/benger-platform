/**
 * @jest-environment jsdom
 *
 * usePublicApiEnabled: null while unknown, the server's answer per user,
 * errors count as off, one request per user shared by every consumer.
 */

import { act, renderHook, waitFor } from '@testing-library/react'

let mockAuth: { user: { id: string } | null; isLoading: boolean } = {
  user: { id: 'user-1' },
  isLoading: false,
}
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockAuth,
}))

const mockAvailability = jest.fn()
jest.mock('@/lib/api/accessKeys', () => ({
  getPublicApiAvailability: () => mockAvailability(),
}))

import {
  resetPublicApiAvailabilityCache,
  usePublicApiEnabled,
} from '../usePublicApiEnabled'

beforeEach(() => {
  resetPublicApiAvailabilityCache()
  mockAvailability.mockReset()
  mockAuth = { user: { id: 'user-1' }, isLoading: false }
})

describe('usePublicApiEnabled', () => {
  it('is null while loading, then true when the server says enabled', async () => {
    mockAvailability.mockResolvedValue({ enabled: true })
    const { result } = renderHook(() => usePublicApiEnabled())
    expect(result.current).toBeNull()
    await waitFor(() => expect(result.current).toBe(true))
  })

  it('is false when the server says disabled', async () => {
    mockAvailability.mockResolvedValue({ enabled: false })
    const { result } = renderHook(() => usePublicApiEnabled())
    await waitFor(() => expect(result.current).toBe(false))
  })

  it('treats a failing call as disabled', async () => {
    mockAvailability.mockRejectedValue(new Error('boom'))
    const { result } = renderHook(() => usePublicApiEnabled())
    await waitFor(() => expect(result.current).toBe(false))
  })

  it('treats a malformed answer as disabled', async () => {
    mockAvailability.mockResolvedValue({})
    const { result } = renderHook(() => usePublicApiEnabled())
    await waitFor(() => expect(result.current).toBe(false))
  })

  it('stays null and does not ask while auth is still loading', () => {
    mockAuth = { user: null, isLoading: true }
    const { result } = renderHook(() => usePublicApiEnabled())
    expect(result.current).toBeNull()
    expect(mockAvailability).not.toHaveBeenCalled()
  })

  it('asks once per user and shares the answer between consumers', async () => {
    mockAvailability.mockResolvedValue({ enabled: true })
    const a = renderHook(() => usePublicApiEnabled())
    const b = renderHook(() => usePublicApiEnabled())
    await waitFor(() => expect(a.result.current).toBe(true))
    await waitFor(() => expect(b.result.current).toBe(true))
    const c = renderHook(() => usePublicApiEnabled())
    expect(c.result.current).toBe(true)
    expect(mockAvailability).toHaveBeenCalledTimes(1)
  })

  it('re-evaluates when the logged-in user changes', async () => {
    mockAvailability.mockResolvedValueOnce({ enabled: true })
    const { result, rerender } = renderHook(() => usePublicApiEnabled())
    await waitFor(() => expect(result.current).toBe(true))

    mockAvailability.mockResolvedValueOnce({ enabled: false })
    mockAuth = { user: { id: 'user-2' }, isLoading: false }
    rerender()
    expect(result.current).toBeNull()
    await waitFor(() => expect(result.current).toBe(false))

    // Back to the first user: answered from the cache, no new request.
    mockAuth = { user: { id: 'user-1' }, isLoading: false }
    rerender()
    expect(result.current).toBe(true)
    expect(mockAvailability).toHaveBeenCalledTimes(2)
  })

  it('asks anonymously for signed-out visitors and again after login', async () => {
    mockAuth = { user: null, isLoading: false }
    mockAvailability.mockResolvedValueOnce({ enabled: false })
    const { result, rerender } = renderHook(() => usePublicApiEnabled())
    await waitFor(() => expect(result.current).toBe(false))

    mockAvailability.mockResolvedValueOnce({ enabled: true })
    mockAuth = { user: { id: 'user-1' }, isLoading: false }
    rerender()
    await waitFor(() => expect(result.current).toBe(true))
    expect(mockAvailability).toHaveBeenCalledTimes(2)
  })

  it('reset forgets cached answers', async () => {
    mockAvailability.mockResolvedValue({ enabled: true })
    const first = renderHook(() => usePublicApiEnabled())
    await waitFor(() => expect(first.result.current).toBe(true))
    first.unmount()

    act(() => resetPublicApiAvailabilityCache())
    mockAvailability.mockResolvedValue({ enabled: false })
    const second = renderHook(() => usePublicApiEnabled())
    expect(second.result.current).toBeNull()
    await waitFor(() => expect(second.result.current).toBe(false))
  })
})
