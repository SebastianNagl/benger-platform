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
      expect(text.steps).toHaveLength(9)
      const all = text.steps.join(' ')
      for (const path of [
        'POST /api/custom-models/',
        'POST /api/projects/',
        '`organization_id`',
        'POST /api/projects/{id}/imports/upload-url?filename=tasks.json',
        '{\"data\": [',
        '`fields`',
        'POST /api/projects/{id}/imports',
        'PUT /api/projects/{id}/generation-config/structures/{key}',
        '{{question}}',
        'PUT /api/projects/{id}/generation-config',
        '\"structure_keys\": [\"default\"]',
        'POST /api/generation-tasks/projects/{id}/generate',
        'GET /api/projects/{id}/generation-status',
        'PUT /api/evaluations/projects/{id}/evaluation-config',
        'POST /api/evaluations/run',
        'GET /api/evaluations/run/results/{evaluation_id}',
        'GET /api/evaluations/run/results/project/{id}',
      ]) {
        expect(all).toContain(path)
      }
      const tips = text.tips.join(' ')
      expect(tips).toContain('from benger_client import BengerClient')
      expect(tips).toContain('POST /api/llm-models/cost-estimate')
      expect(tips).toContain('/how-to#api-round-trip')
      expect(text.links.map((l) => l.href)).toEqual([
        '/profile',
        '/how-to#api-zugaenge',
        '/how-to#api-round-trip',
      ])
    }
  })

  it('addresses the reader with du in German', () => {
    const de = texts[0]
    const text = [de.title, de.summary, ...de.steps, ...de.tips, ...de.pitfalls]
    expect(text.join(' ')).not.toMatch(/\b(Sie|Ihre?[nmrs]?|Ihnen)\b/)
  })

  it('cross-links from api-zugaenge', () => {
    expect(guide.links).toContain('/how-to#api-research-workflow')
  })
})

describe('api-round-trip guide', () => {
  const roundTrip = API_ACCESS_GUIDES.find((g) => g.id === 'api-round-trip')!
  const texts = (['de', 'en', 'fr'] as const).map((l) =>
    guideText(roundTrip, l),
  )

  it('is registered once and hidden unless the public API is on', () => {
    expect(
      PLATFORM_HOWTO_GUIDES.filter((g) => g.id === 'api-round-trip'),
    ).toHaveLength(1)
    expect(roundTrip.requires).toBe('publicApi')
  })

  it('exports, imports as a new project and merges back in every language', () => {
    for (const text of texts) {
      expect(text.steps).toHaveLength(6)
      const all = text.steps.join(' ')
      for (const part of [
        'POST /api/projects/{id}/exports?format=ndjson_gz',
        'GET /api/projects/{id}/exports/{job_id}',
        '/download?json=1',
        'POST /api/projects/project-imports/upload-url?filename=export.ndjson.gz',
        'POST /api/projects/project-imports',
        '`organization_id`',
        'GET /api/projects/project-imports/{job_id}',
        '\"mode\": \"merge\"',
        '\"dry_run\": true',
        '\"model_id_map\"',
        'merge_preview',
        'GET /api/projects/{id}/imports/{job_id}',
      ]) {
        expect(all).toContain(part)
      }
      expect(text.pitfalls.join(' ')).toMatch(/5 Gi[Bo]/)
      expect(text.links.map((l) => l.href)).toEqual([
        '/how-to#api-research-workflow',
        '/how-to#export-import-project',
      ])
    }
  })

  it('addresses the reader with du in German', () => {
    const de = texts[0]
    const text = [de.title, de.summary, ...de.steps, ...de.tips, ...de.pitfalls]
    expect(text.join(' ')).not.toMatch(/\b(Sie|Ihre?[nmrs]?|Ihnen)\b/)
    expect(text.join(' ')).toMatch(/\bdu\b/)
  })
})
