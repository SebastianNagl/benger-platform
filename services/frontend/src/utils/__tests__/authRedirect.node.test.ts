/**
 * @jest-environment node
 */

/**
 * sanitizeNext without a browser window (server render): the structural
 * checks still apply, the same-origin comparison is skipped.
 */

jest.mock('@/lib/utils/subdomain', () => ({
  isStudentLockedHost: jest.fn(() => false),
}))

import { authRedirect } from '../authRedirect'

describe('authRedirect.sanitizeNext without window', () => {
  it('keeps a safe internal path', () => {
    expect(typeof window).toBe('undefined')
    expect(authRedirect.sanitizeNext('/projects/1?x=1')).toBe('/projects/1?x=1')
  })

  it('still rejects external, backslash and control-character paths', () => {
    expect(authRedirect.sanitizeNext('//evil.example')).toBeNull()
    expect(authRedirect.sanitizeNext('/\\evil.example')).toBeNull()
    expect(authRedirect.sanitizeNext('javascript:alert(1)')).toBeNull()
    expect(authRedirect.sanitizeNext('/\t/evil.example')).toBeNull()
  })
})
