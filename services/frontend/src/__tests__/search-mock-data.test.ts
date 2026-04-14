/**
 * Unit test to verify that invalid search results have been removed from Search component
 * Addresses Issue #150: Remove invalid search results causing 404 errors
 *
 * This test directly examines the mock search data to ensure no invalid URLs are present.
 */

// We'll read the Search component file and extract the mock data to test
import fs from 'fs'
import path from 'path'

describe('Search Mock Data - Invalid Results Cleanup', () => {
  // List of invalid URLs that should NOT appear in search results
  const invalidUrls = [
    '/docs',
    '/api-docs',
    '/getting-started',
    '/results',
    '/admin',
    '/admin/tasks',
    '/admin/system',
    '/settings',
  ]

  // List of valid URLs that SHOULD appear in search results
  const validUrls = [
    '/',
    '/dashboard',
    '/reports',
    '/leaderboards',
    '/architecture',
    '/projects',
    '/projects/create',
    '/data',
    '/generations',
    '/evaluations',
    '/how-to',
    '/models',
    '/profile',
    '/organizations',
    '/admin/users',
  ]

  let searchComponentContent: string

  beforeAll(() => {
    // Read the Search component file
    const searchFilePath = path.join(
      __dirname,
      '../components/shared/Search.tsx'
    )
    searchComponentContent = fs.readFileSync(searchFilePath, 'utf-8')
  })

  it('should not contain any invalid URLs in the mock data', () => {
    // Check that none of the invalid URLs appear in the file
    invalidUrls.forEach((invalidUrl) => {
      const urlPattern = new RegExp(
        `url:\\s*['"\`]${invalidUrl.replace('/', '\\/')}['"\`]`
      )
      expect(searchComponentContent).not.toMatch(urlPattern)
    })
  })

  it('should still contain all valid URLs in the mock data', () => {
    // Check that all valid URLs are still present
    validUrls.forEach((validUrl) => {
      const urlPattern = new RegExp(
        `url:\\s*['"\`]${validUrl.replace('/', '\\/')}['"\`]`
      )
      expect(searchComponentContent).toMatch(urlPattern)
    })
  })

  it('should not contain "API Documentation" text', () => {
    // Specifically check that the problematic "API Documentation" entry is gone
    expect(searchComponentContent).not.toMatch(/['"`]API Documentation['"`]/)
  })

  it('should not contain references to /api-docs', () => {
    // Make sure no references to the broken /api-docs URL exist
    expect(searchComponentContent).not.toMatch(/\/api-docs/)
  })

  it('should have reduced the total number of mock results', () => {
    // Check that getLocalizedResults function exists and contains the expected URLs
    expect(searchComponentContent).toContain('getLocalizedResults')

    // Count the number of URL entries in the entire search results
    const urlMatches = searchComponentContent.match(/url:\s*['"`][^'"`]+['"`]/g)
    const urlCount = urlMatches ? urlMatches.length : 0

    // Should have exactly 16 valid URLs (15 static + 1 dynamic project template)
    expect(urlCount).toBe(16)
  })

  it('should maintain proper JavaScript syntax after cleanup', () => {
    // Basic syntax check - the file should still be valid JavaScript/TypeScript
    expect(searchComponentContent).toContain('getLocalizedResults')
    expect(searchComponentContent).toContain('return [')
    expect(searchComponentContent).toContain('return allPages')
    // Check that useCallback dependencies include at least 't' for translations
    expect(searchComponentContent).toMatch(/\[t,/) // Check function dependencies include t
  })

  it('should not have any malformed entries after cleanup', () => {
    // Check that the getLocalizedResults function contains proper structure
    expect(searchComponentContent).toContain('getLocalizedResults')

    // Check that all remaining entries have the basic required fields
    expect(searchComponentContent).toContain('url:')
    expect(searchComponentContent).toContain('title:')
    expect(searchComponentContent).toContain('description:')
    expect(searchComponentContent).toContain('category:')

    // Check that translation functions are used properly
    expect(searchComponentContent).toContain("t('search.pages.")
    expect(searchComponentContent).toContain("t('search.categories.")
  })
})
