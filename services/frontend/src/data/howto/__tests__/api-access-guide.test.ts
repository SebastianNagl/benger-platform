/**
 * The "api-zugaenge" how-to guide: registered with the platform, a five
 * step quick start in both languages, German copy with "du".
 */

import { PLATFORM_HOWTO_GUIDES } from '../guides'
import { API_ACCESS_GUIDES } from '../guides/apiAccess'

const guide = API_ACCESS_GUIDES[0]

describe('api-zugaenge guide', () => {
  it('is registered once with the platform guides', () => {
    expect(guide.id).toBe('api-zugaenge')
    expect(
      PLATFORM_HOWTO_GUIDES.filter((g) => g.id === 'api-zugaenge'),
    ).toHaveLength(1)
  })

  it('has the five quick-start steps in both languages', () => {
    expect(guide.steps?.de).toHaveLength(5)
    expect(guide.steps?.en).toHaveLength(5)
    const starts = guide.steps!.de.map((s) => s.match(/^\*\*(.+?)\*\*/)?.[1])
    expect(starts).toEqual([
      'Schlüssel anlegen',
      'Umfang wählen',
      'Kopieren',
      'Verbindung testen',
      'In Skript oder Runner einsetzen',
    ])
    expect(guide.tips?.de).toHaveLength(guide.tips!.en.length)
    expect(guide.pitfalls?.de).toHaveLength(guide.pitfalls!.en.length)
  })

  it('addresses the reader with du', () => {
    const text = [
      guide.title.de,
      guide.summary.de,
      ...guide.steps!.de,
      ...guide.tips!.de,
      ...guide.pitfalls!.de,
    ].join(' ')
    expect(text).not.toMatch(/\b(Sie|Ihre?[nmrs]?|Ihnen)\b/)
    expect(text).toMatch(/\bdu\b/)
  })
})
