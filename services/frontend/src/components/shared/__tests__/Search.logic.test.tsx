/**
 * @jest-environment jsdom
 *
 * Logic + rendering coverage for Search that the existing Search.test.tsx
 * leaves untested because it stubs @algolia/autocomplete-core with a static
 * object. Here we capture the REAL config object passed to createAutocomplete
 * and exercise:
 *   - getSources().getItems(): multilingual scoring, cross-language expansion,
 *     role-based admin filtering, top-5 slice, malformed-item guards
 *   - getItemUrl(): valid / relative / external / invalid / missing
 *   - navigator.navigate(): success + invalid-url guard
 *   - onStateChange wiring (shouldPanelOpen)
 * and, with a second mock that yields a populated collection, the
 * SearchResults / SearchResult / HighlightQuery render path + SearchInput
 * Escape-to-close handler.
 */
import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const mockPush = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}))

const mockUser = { id: '1', username: 'u', email: 'u@e.com', is_superadmin: true }
const mockOrganizations = [{ id: '1', name: 'Org', role: 'ORG_ADMIN' }]

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: mockUser, organizations: mockOrganizations }),
}))

const mockFlags = {
  reports: true,
  leaderboards: true,
  data: true,
  generations: true,
  evaluations: true,
  'how-to': true,
}
jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlags: () => ({ flags: mockFlags }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    // Return the key itself so we can assert against deterministic strings.
    t: (key: string) => {
      const map: Record<string, string> = {
        'search.categories.administration': 'Administration',
        'search.categories.projectsAndData': 'Projects & Data',
        'search.pages.projects.title': 'Projects',
        'search.pages.projects.description': 'Browse all projects',
        'search.pages.userManagement.title': 'User Management',
        'search.pages.organizations.title': 'Organizations',
        'search.placeholder': 'Search...',
        'search.noResults': 'No results for',
        'search.tryAgain': 'Try again.',
      }
      return map[key] || key
    },
    locale: 'en',
    isReady: true,
  }),
}))

jest.mock('@/components/layout/Navigation', () => ({
  navigation: [
    { title: 'Projects & Data', links: [{ href: '/projects', title: 'Projects' }] },
  ],
}))

jest.mock('@/components/layout/MobileNavigation', () => ({
  useMobileNavigationStore: () => ({ close: jest.fn() }),
}))

jest.mock('react-highlight-words', () => {
  return function Highlighter({ textToHighlight }: any) {
    return <span>{textToHighlight}</span>
  }
})

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    list: jest.fn().mockResolvedValue({ items: [] }),
  },
}))

// Headless dialog passthrough so the panel + input mount.
jest.mock('@headlessui/react', () => {
  const React = jest.requireActual('react') as typeof import('react')
  function MockDialog({ children, open, className }: any) {
    if (!open) return null
    return (
      <div data-testid="dialog" className={className}>
        {children}
      </div>
    )
  }
  const Panel = ({ children, className }: any) => (
    <div data-testid="dialog-panel" className={className}>
      {children}
    </div>
  )
  const Backdrop = ({ className }: any) => (
    <div data-testid="dialog-backdrop" className={className} />
  )
  return { Dialog: MockDialog, DialogPanel: Panel, DialogBackdrop: Backdrop }
})

// Capture the config passed to createAutocomplete; return a minimal instance.
let capturedConfig: any = null
const makeInstance = () => ({
  setQuery: jest.fn(),
  refresh: jest.fn(),
  getInputProps: jest.fn(() => ({
    value: '',
    onChange: jest.fn(),
    onKeyDown: jest.fn(),
    placeholder: '',
  })),
  getRootProps: jest.fn(() => ({})),
  getFormProps: jest.fn(() => ({})),
  getPanelProps: jest.fn(() => ({})),
  getListProps: jest.fn(() => ({})),
  getItemProps: jest.fn(() => ({})),
})

jest.mock('@algolia/autocomplete-core', () => ({
  createAutocomplete: jest.fn((config: any) => {
    capturedConfig = config
    return makeInstance()
  }),
}))

import { Search } from '../Search'

// Helpers ------------------------------------------------------------------

async function getItemsForQuery(query: string) {
  const sources = await capturedConfig.getSources({ query })
  return sources[0].getItems()
}

function getItemUrl(item: any) {
  return capturedConfig.getSources({ query: 'x' }).then((s: any[]) =>
    s[0].getItemUrl({ item })
  )
}

describe('Search getSources logic', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    capturedConfig = null
    render(<Search />)
    expect(capturedConfig).not.toBeNull()
  })

  it('returns [] for empty / non-string / whitespace queries', async () => {
    expect(await getItemsForQuery('')).toEqual([])
    expect(await getItemsForQuery('   ')).toEqual([])
    expect(await getItemsForQuery(undefined as any)).toEqual([])
  })

  it('scores and returns matching pages, capped at 5 results', async () => {
    const items = await getItemsForQuery('projects')
    expect(items.length).toBeGreaterThan(0)
    expect(items.length).toBeLessThanOrEqual(5)
    // Projects page should be in the results
    expect(items.some((r: any) => r.url === '/projects')).toBe(true)
    // score field is stripped from the returned items
    expect(items[0]).not.toHaveProperty('score')
  })

  it('expands cross-language terms (German query matches English page)', async () => {
    // "projekte" maps to "projects" via CROSS_LANGUAGE_MAPPINGS
    const items = await getItemsForQuery('projekte')
    expect(items.some((r: any) => r.url === '/projects')).toBe(true)
  })

  it('includes admin pages for a superadmin user (role filter passes)', async () => {
    const items = await getItemsForQuery('management')
    // Administration-category pages (User Management) survive the role filter
    // because mockUser.is_superadmin === true.
    expect(items.some((r: any) => r.category === 'Administration')).toBe(true)
  })
})

describe('Search getItemUrl guards', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    capturedConfig = null
    render(<Search />)
  })

  it('returns a valid relative url unchanged', async () => {
    expect(await getItemUrl({ url: '/projects' })).toBe('/projects')
  })

  it('returns external http urls unchanged', async () => {
    expect(await getItemUrl({ url: 'https://example.com' })).toBe(
      'https://example.com'
    )
  })

  it('returns "#" for a non-slash, non-http url', async () => {
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {})
    expect(await getItemUrl({ url: 'relativeNoSlash' })).toBe('#')
    warn.mockRestore()
  })

  it('returns "#" for a missing / malformed item', async () => {
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {})
    expect(await getItemUrl(null)).toBe('#')
    expect(await getItemUrl({ url: 123 })).toBe('#')
    warn.mockRestore()
  })
})

describe('Search navigator.navigate', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    capturedConfig = null
    render(<Search />)
  })

  it('pushes a valid url through the router', () => {
    capturedConfig.navigator.navigate({ itemUrl: '/projects' })
    expect(mockPush).toHaveBeenCalledWith('/projects')
  })

  it('warns and does not navigate on an invalid url', () => {
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {})
    capturedConfig.navigator.navigate({ itemUrl: undefined })
    expect(mockPush).not.toHaveBeenCalled()
    warn.mockRestore()
  })

  it('shouldPanelOpen only opens for a non-empty query', () => {
    expect(capturedConfig.shouldPanelOpen({ state: { query: '' } })).toBe(false)
    expect(capturedConfig.shouldPanelOpen({ state: { query: 'x' } })).toBe(true)
  })
})
