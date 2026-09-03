/**
 * Guards the nav-bar search index (lib/search) against dead links.
 * Addresses Issue #150: invalid search results caused 404s. The index
 * moved out of the Search component into lib/search/index.ts (2026-09), so
 * this test reads that file: every static URL must be a real route.
 */

import fs from 'fs'
import path from 'path'

const INVALID_URLS = [
  '/docs',
  '/api-docs',
  '/getting-started',
  '/results',
  '/admin',
  '/admin/tasks',
  '/admin/system',
  '/settings',
]

const REQUIRED_URLS = [
  '/',
  '/dashboard',
  '/reports',
  '/leaderboards',
  '/runs',
  '/learning-stats',
  '/architecture',
  '/changelog',
  '/projects',
  '/projects/create',
  '/projects/archived',
  '/data',
  '/generations',
  '/evaluations',
  '/how-to',
  '/models',
  '/profile',
  '/settings/notifications',
  '/settings/models',
  '/users-organizations',
  '/organizations',
  '/admin/users',
  '/admin/lti',
]

function staticUrls(source: string): string[] {
  const matches = source.matchAll(/page\(t,\s*'([^']+)'/g)
  return [...matches].map((m) => m[1])
}

describe('Search index - static pages are real routes', () => {
  let source: string
  let appDir: string

  beforeAll(() => {
    source = fs.readFileSync(path.join(__dirname, '../lib/search/index.ts'), 'utf-8')
    appDir = path.join(__dirname, '../app')
  })

  it('contains no known-dead URLs', () => {
    const urls = staticUrls(source)
    INVALID_URLS.forEach((u) => expect(urls).not.toContain(u))
    expect(source).not.toMatch(/\/api-docs/)
  })

  it('lists every page users regularly look for', () => {
    const urls = staticUrls(source)
    REQUIRED_URLS.forEach((u) => expect(urls).toContain(u))
  })

  it('every static URL resolves to an app route (page.tsx)', () => {
    const urls = staticUrls(source)
    expect(urls.length).toBeGreaterThan(20)
    urls.forEach((u) => {
      const route = u === '/' ? '' : u
      const pagePath = path.join(appDir, route, 'page.tsx')
      expect({ url: u, exists: fs.existsSync(pagePath) }).toEqual({ url: u, exists: true })
    })
  })
})
