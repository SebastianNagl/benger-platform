/**
 * The "api-zugaenge" how-to guide: registered with the platform, a five
 * step quick start in both languages, German copy with "du".
 */

import { guideText } from '@/lib/howto'

import { PLATFORM_HOWTO_GUIDES } from '../guides'
import { API_ACCESS_GUIDES } from '../guides/apiAccess'

const guide = API_ACCESS_GUIDES[0]
const de = guideText(guide, 'de')
const en = guideText(guide, 'en')

describe('api-zugaenge guide', () => {
  it('is registered once with the platform guides', () => {
    expect(guide.id).toBe('api-zugaenge')
    expect(
      PLATFORM_HOWTO_GUIDES.filter((g) => g.id === 'api-zugaenge'),
    ).toHaveLength(1)
  })

  it('is hidden unless the public API is on', () => {
    expect(guide.requires).toBe('publicApi')
  })

  it('has the five quick-start steps in both languages', () => {
    expect(de.steps).toHaveLength(5)
    expect(en.steps).toHaveLength(5)
    const starts = de.steps.map((s) => s.match(/^\*\*(.+?)\*\*/)?.[1])
    expect(starts).toEqual([
      'Schlüssel anlegen',
      'Umfang wählen',
      'Kopieren',
      'Verbindung testen',
      'In Skript oder Runner einsetzen',
    ])
    expect(de.tips).toHaveLength(en.tips.length)
    expect(de.pitfalls).toHaveLength(en.pitfalls.length)
  })

  it('addresses the reader with du', () => {
    const text = [
      de.title,
      de.summary,
      ...de.steps,
      ...de.tips,
      ...de.pitfalls,
    ].join(' ')
    expect(text).not.toMatch(/\b(Sie|Ihre?[nmrs]?|Ihnen)\b/)
    expect(text).toMatch(/\bdu\b/)
  })
})
