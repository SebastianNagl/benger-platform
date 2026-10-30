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

describe('api-research-workflow guide', () => {
  const workflow = API_ACCESS_GUIDES.find(
    (g) => g.id === 'api-research-workflow',
  )!
  const texts = (['de', 'en', 'fr'] as const).map((l) => guideText(workflow, l))

  it('is registered once and hidden unless the public API is on', () => {
    expect(
      PLATFORM_HOWTO_GUIDES.filter((g) => g.id === 'api-research-workflow'),
    ).toHaveLength(1)
    expect(workflow.requires).toBe('publicApi')
  })

  it('walks from the key to the results in every language', () => {
    for (const text of texts) {
      expect(text.steps).toHaveLength(7)
      const all = text.steps.join(' ')
      for (const path of [
        'POST /api/custom-models/',
        'PUT /api/projects/{id}/generation-config',
        'POST /api/generation-tasks/projects/{id}/generate',
        'GET /api/projects/{id}/generation-status',
        'PUT /api/evaluations/projects/{id}/evaluation-config',
        'POST /api/evaluations/run',
        'GET /api/evaluations/run/results/project/{id}',
      ]) {
        expect(all).toContain(path)
      }
      expect(text.tips.join(' ')).toContain(
        'from benger_client import BengerClient',
      )
      expect(text.links.map((l) => l.href)).toEqual([
        '/profile',
        '/how-to#api-zugaenge',
      ])
    }
  })

  it('cross-links from api-zugaenge', () => {
    expect(guide.links).toContain('/how-to#api-research-workflow')
  })
})
