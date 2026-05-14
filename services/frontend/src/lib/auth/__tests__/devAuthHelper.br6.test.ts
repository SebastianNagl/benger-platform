/**
 * @jest-environment jsdom
 *
 * Branch coverage: devAuthHelper.ts
 * Targets uncovered branches for markManualLogout and clearManualLogout
 * (the only remaining methods after auto-login moved to layout.tsx inline script).
 */

jest.mock('@/lib/utils/subdomain', () => ({
  getCookieDomain: jest.fn(),
}))

import { devAuthHelper } from '@/lib/auth/devAuthHelper'
import { getCookieDomain } from '@/lib/utils/subdomain'

const mockGetCookieDomain = getCookieDomain as jest.Mock

describe('DevAuthHelper branch coverage', () => {
  const clearCookies = () => {
    document.cookie.split(';').forEach((c) => {
      document.cookie = c.trim().split('=')[0] + '=; max-age=0'
    })
  }

  beforeEach(() => {
    clearCookies()
    jest.clearAllMocks()
    mockGetCookieDomain.mockReturnValue('')
  })

  afterEach(() => {
    clearCookies()
  })

  describe('markManualLogout', () => {
    it('sets cookie without domain when getCookieDomain returns empty', () => {
      mockGetCookieDomain.mockReturnValue('')
      devAuthHelper.markManualLogout()

      expect(document.cookie).toContain('manual_logout=')
    })

    it('calls getCookieDomain for domain attribute', () => {
      mockGetCookieDomain.mockReturnValue('.benger.localhost')
      devAuthHelper.markManualLogout()

      // jsdom ignores domain= in cookies, so just verify getCookieDomain was called
      expect(mockGetCookieDomain).toHaveBeenCalled()
    })

    // Server-side branch covered in devAuthHelper.ssr.test.ts (node env).
  })

  describe('clearManualLogout', () => {
    it('clears cookie without domain when getCookieDomain returns empty', () => {
      mockGetCookieDomain.mockReturnValue('')
      document.cookie = `manual_logout=${Date.now()}; path=/`
      devAuthHelper.clearManualLogout()

      expect(document.cookie).not.toContain('manual_logout=')
    })

    it('calls getCookieDomain for domain attribute', () => {
      mockGetCookieDomain.mockReturnValue('.benger.localhost')
      document.cookie = `manual_logout=${Date.now()}; path=/`
      devAuthHelper.clearManualLogout()

      expect(mockGetCookieDomain).toHaveBeenCalled()
    })

    // Server-side branch covered in devAuthHelper.ssr.test.ts (node env).
  })
})
