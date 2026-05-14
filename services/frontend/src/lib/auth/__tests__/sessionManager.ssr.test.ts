/**
 * @jest-environment node
 *
 * SSR (no-DOM) behavior of SessionManager. Lives in a separate file because
 * JSDOM 21+ makes `window` non-configurable; running under the node test
 * environment gives us `typeof window === 'undefined'` without `delete`.
 */

import { ApiClient, User } from '@/lib/api'
import { SessionManager } from '@/lib/auth/sessionManager'

jest.mock('@/lib/api', () => ({
  ApiClient: jest.fn().mockImplementation(() => ({
    clearCache: jest.fn(),
    clearUserCache: jest.fn(),
  })),
}))

jest.mock('@/utils/clearAllStores', () => ({
  clearAllStores: jest.fn(),
}))

describe('SessionManager (SSR)', () => {
  let mockApiClient: jest.Mocked<ApiClient>
  let manager: SessionManager

  beforeEach(() => {
    jest.clearAllMocks()
    mockApiClient = new ApiClient() as jest.Mocked<ApiClient>
    manager = new SessionManager()
  })

  it('trackUserSession does not throw when window is undefined', () => {
    const user: User = { id: 123, name: 'Test User' } as User
    expect(() => manager.trackUserSession(user)).not.toThrow()
  })

  it('getLastSessionUserId returns null when window is undefined', () => {
    expect(manager.getLastSessionUserId()).toBeNull()
  })

  it('detectUserSwitch returns false when window is undefined', () => {
    const user: User = { id: 123, name: 'Test' } as User
    expect(manager.detectUserSwitch(user)).toBe(false)
  })

  it('isLoginInProgress returns false when window is undefined', () => {
    expect(manager.isLoginInProgress()).toBe(false)
  })

  it('setLoginInProgress does not throw when window is undefined', () => {
    expect(() => manager.setLoginInProgress(true)).not.toThrow()
    expect(() => manager.setLoginInProgress(false)).not.toThrow()
  })

  it('hasAuthVerification returns false when window is undefined', () => {
    expect(manager.hasAuthVerification()).toBe(false)
  })

  it('clearAuthVerification does not throw when window is undefined', () => {
    expect(() => manager.clearAuthVerification()).not.toThrow()
  })

  it('handleUserSwitch does not throw when window is undefined', () => {
    expect(() =>
      manager.handleUserSwitch(mockApiClient, '123', '456')
    ).not.toThrow()
  })

  it('clearSession does not throw when window is undefined', () => {
    expect(() => manager.clearSession(mockApiClient)).not.toThrow()
  })

  it('prepareForLogin does not throw when window is undefined', () => {
    expect(() => manager.prepareForLogin(mockApiClient)).not.toThrow()
  })
})
