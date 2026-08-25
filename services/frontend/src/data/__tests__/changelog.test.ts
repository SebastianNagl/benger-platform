/**
 * Guards on the platform changelog data itself. The extended repo has the
 * mirror-image test for EXTENDED_CHANGELOG (audience ∈ {vertretbar, both});
 * this side pins that vertretbar-audience wording never enters the PUBLIC
 * platform repo, plus the entry-format contract the /changelog page relies on.
 */
import { PLATFORM_CHANGELOG } from '../changelog'

describe('PLATFORM_CHANGELOG', () => {
  it('has at least one entry', () => {
    expect(PLATFORM_CHANGELOG.length).toBeGreaterThan(0)
  })

  it.each(PLATFORM_CHANGELOG.map((e, i) => [i, e] as const))(
    'entry %#: well-formed, and never vertretbar-audience (public repo)',
    (_i, entry) => {
      // Vertretbar wording lives in the private extended repo only.
      expect(['benger', 'both']).toContain(entry.audience)
      expect(entry.date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
      expect(entry.text.de.trim()).not.toBe('')
      expect(entry.text.en.trim()).not.toBe('')
    },
  )

  it('is ordered newest first', () => {
    const dates = PLATFORM_CHANGELOG.map((e) => e.date)
    const sorted = [...dates].sort((a, b) => (a < b ? 1 : a > b ? -1 : 0))
    expect(dates).toEqual(sorted)
  })
})
