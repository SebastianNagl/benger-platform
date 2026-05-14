/**
 * @jest-environment jsdom
 *
 * DevAuthHelper Test Suite
 * Tests manual logout tracking (the only remaining functionality after
 * auto-login was moved to the inline script in layout.tsx).
 */

import { devAuthHelper } from '@/lib/auth/devAuthHelper'

jest.mock('@/lib/utils/subdomain', () => ({
  getCookieDomain: jest.fn(() => ''),
}))

describe('DevAuthHelper', () => {
  const clearCookies = () => {
    document.cookie.split(';').forEach((c) => {
      document.cookie = c.trim().split('=')[0] + '=; max-age=0'
    })
  }

  beforeEach(() => {
    clearCookies()
    jest.clearAllMocks()
  })

  afterEach(() => {
    clearCookies()
  })

  describe('markManualLogout', () => {
    it('should record manual logout timestamp in cookie', () => {
      const beforeTime = Date.now()
      devAuthHelper.markManualLogout()
      const afterTime = Date.now()

      const match = document.cookie.match(/(?:^|; )manual_logout=([^;]*)/)
      expect(match).toBeTruthy()

      const timestamp = parseInt(match![1])
      expect(timestamp).toBeGreaterThanOrEqual(beforeTime)
      expect(timestamp).toBeLessThanOrEqual(afterTime)
    })

    // Server-side case lives in devAuthHelper.ssr.test.ts (node env).
  })

  describe('clearManualLogout', () => {
    it('should remove manual logout cookie', () => {
      document.cookie = `manual_logout=${Date.now()}; path=/`
      expect(document.cookie).toContain('manual_logout=')

      devAuthHelper.clearManualLogout()
      expect(document.cookie).not.toContain('manual_logout=')
    })

    // Server-side case lives in devAuthHelper.ssr.test.ts (node env).
  })
})
