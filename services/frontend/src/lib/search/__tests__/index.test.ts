import type { HowToGuide } from '@/lib/howto'

import {
  buildGuideIndex,
  buildPageIndex,
  buildSearchIndex,
  expandQuery,
  rankSearchResults,
} from '../index'

const t = (key: string, fallback?: string) => fallback ?? key

const guide: HowToGuide = {
  id: 'api-keys',
  category: 'generation',
  title: { de: 'Wie hinterlege ich einen API-Schlüssel?', en: 'How do I add an API key?' },
  summary: { de: 'Unter **Einstellungen** → `Modelle`.', en: 'Under **Settings** → `Models`.' },
  keywords: { de: ['OpenAI', 'Mistral'], en: ['provider'] },
}

describe('buildPageIndex', () => {
  it('hides flag-gated and role-gated pages for a plain user', () => {
    const urls = buildPageIndex({ t, locale: 'de', flags: {}, user: {}, organizations: [] }).map((p) => p.url)
    expect(urls).toContain('/dashboard')
    expect(urls).toContain('/runs')
    expect(urls).toContain('/settings/models')
    expect(urls).not.toContain('/reports')
    expect(urls).not.toContain('/organizations')
    expect(urls).not.toContain('/admin/users')
  })

  it('shows /organizations to org admins and admin pages to superadmins', () => {
    const orgAdmin = buildPageIndex({ t, locale: 'de', flags: {}, user: {}, organizations: [{ role: 'ORG_ADMIN' }] }).map((p) => p.url)
    expect(orgAdmin).toContain('/organizations')
    expect(orgAdmin).not.toContain('/admin/users')
    const superadmin = buildPageIndex({ t, locale: 'de', flags: { reports: true }, user: { is_superadmin: true }, organizations: [] }).map((p) => p.url)
    expect(superadmin).toEqual(expect.arrayContaining(['/organizations', '/admin/users', '/admin/lti', '/projects/deleted', '/reports']))
  })

  it('omits signed-in-only pages for anonymous visitors', () => {
    const urls = buildPageIndex({ t, locale: 'de', flags: {}, user: null, organizations: null }).map((p) => p.url)
    expect(urls).not.toContain('/runs')
    expect(urls).toContain('/')
  })
})

describe('buildGuideIndex / buildSearchIndex', () => {
  it('turns guides into deep links with the localized title and summary', () => {
    const [entry] = buildGuideIndex({ t, locale: 'en', flags: {}, user: {}, organizations: [], guides: [guide] })
    expect(entry.url).toBe('/how-to#api-keys')
    expect(entry.title).toBe('How do I add an API key?')
    expect(entry.description).toBe('Under Settings → Models.')
    expect(entry.category).toBe('Anleitung')
  })

  it('combines pages and guides', () => {
    const all = buildSearchIndex({ t, locale: 'de', flags: {}, user: {}, organizations: [], guides: [guide] })
    expect(all.some((e) => e.url === '/how-to#api-keys')).toBe(true)
    expect(all.some((e) => e.url === '/dashboard')).toBe(true)
  })
})

describe('ranking', () => {
  const entries = buildSearchIndex({ t, locale: 'de', flags: { 'how-to': true }, user: {}, organizations: [], guides: [guide] })

  it('finds a guide via a keyword that is not in its title', () => {
    const results = rankSearchResults(entries, 'mistral')
    expect(results[0]?.url).toBe('/how-to#api-keys')
  })

  it('finds pages through the static keyword list (German synonym for an English title key)', () => {
    // Titles are raw keys in this test; the keyword list still matches.
    const results = rankSearchResults(entries, 'bestenliste')
    expect(results.map((r) => r.url)).not.toContain('/leaderboards') // flag off
    expect(rankSearchResults(entries, 'lernstatistik').map((r) => r.url)).toContain('/learning-stats')
  })

  it('expands queries across languages', () => {
    expect(expandQuery('gruppen')).toEqual(expect.arrayContaining(['gruppen', 'groups']))
    expect(expandQuery('api key')).toEqual(expect.arrayContaining(['api schlüssel']))
  })

  it('caps the result list and strips internal fields', () => {
    const results = rankSearchResults(entries, 'e', 3)
    expect(results.length).toBeLessThanOrEqual(3)
    results.forEach((r) => expect(r).not.toHaveProperty('keywords'))
  })

  it('returns nothing for an empty query', () => {
    expect(rankSearchResults(entries, '   ')).toEqual([])
  })
})
