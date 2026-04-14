/**
 * @jest-environment jsdom
 *
 * Branch coverage: clearAllStores.ts
 * Targets: br1[1] L31 (typeof window !== 'undefined' false branch) and br2[1] L61
 * Since we're in jsdom, we test the true branches and preserveInitialized=false path
 */

jest.mock('@/lib/utils/logger', () => ({
  logger: { debug: jest.fn() },
}))

jest.mock('@/stores/notificationStore', () => ({
  useNotificationStore: {
    getState: jest.fn(() => ({})),
    setState: jest.fn(),
  },
}))

jest.mock('@/stores/projectStore', () => ({
  useProjectStore: {
    getState: jest.fn(() => ({})),
    setState: jest.fn(),
  },
}))

jest.mock('@/stores/uiStore', () => ({
  useUIStore: {
    getState: jest.fn(() => ({
      isSidebarHidden: false,
      isHydrated: true,
      theme: 'light',
    })),
    setState: jest.fn(),
  },
}))

describe('clearAllStores branch coverage', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('clears session user key when preserveInitialized=false', () => {
    localStorage.setItem('benger_last_session_user', '123')
    localStorage.setItem('auth_token', 'xyz')
    localStorage.setItem('user_prefs', 'something')
    localStorage.setItem('session_data', 'data')

    const { clearAllStores } = require('../../utils/clearAllStores')
    clearAllStores(false)

    expect(localStorage.getItem('benger_last_session_user')).toBeNull()
  })

  it('preserves session user key when preserveInitialized=true', () => {
    localStorage.setItem('benger_last_session_user', '123')
    localStorage.setItem('auth_verified', 'true')

    const { clearAllStores } = require('../../utils/clearAllStores')
    clearAllStores(true)

    // benger_last_session_user should be preserved
    expect(localStorage.getItem('benger_last_session_user')).toBe('123')
  })
})
