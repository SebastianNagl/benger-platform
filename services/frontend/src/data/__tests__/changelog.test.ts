/**
 * Guards on the platform changelog data itself. The extended repo has the
 * mirror-image test for EXTENDED_CHANGELOG (audience ∈ {vertretbar, both});
 * this side pins that vertretbar-audience wording never enters the PUBLIC
 * platform repo, plus the entry-format contract the /changelog page relies on
 * (id, date, audience here; the text at changelogEntries.<id> in the catalog).
 */
import { hasTranslation, lookup } from '@/lib/i18n/catalog'
import deChangelog from '@/locales/de/changelog.json'

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
      expect(entry.id).toMatch(/^\d{4}-\d{2}-\d{2}-[a-z0-9]+(-[a-z0-9]+)*$/)
      expect(entry.id.startsWith(`${entry.date}-`)).toBe(true)
      for (const locale of ['de', 'en'] as const) {
        const key = `changelogEntries.${entry.id}`
        expect(hasTranslation(locale, key)).toBe(true)
        expect(String(lookup(locale, key)).trim()).not.toBe('')
      }
    },
  )

  it('has unique ids and no orphaned catalog text', () => {
    const ids = PLATFORM_CHANGELOG.map((e) => e.id)
    expect(new Set(ids).size).toBe(ids.length)
    expect(Object.keys(deChangelog.changelogEntries).sort()).toEqual(
      [...ids].sort(),
    )
  })

  it('is ordered newest first', () => {
    const dates = PLATFORM_CHANGELOG.map((e) => e.date)
    const sorted = [...dates].sort((a, b) => (a < b ? 1 : a > b ? -1 : 0))
    expect(dates).toEqual(sorted)
  })

  it('gates the API-access announcement behind the public_api flag', () => {
    const gated = PLATFORM_CHANGELOG.filter((e) =>
      e.id.startsWith('2026-10-13-api-access'),
    )
    expect(gated.length).toBeGreaterThan(0)
    for (const entry of gated) expect(entry.requires).toBe('publicApi')
  })
})
