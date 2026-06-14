/**
 * @jest-environment jsdom
 *
 * Complement coverage for Search.tsx. The two existing suites stub
 * `createAutocomplete` so the panel never opens and the project-search /
 * onStateChange wiring never runs. This file fills the remaining gaps using
 * the REAL @algolia/autocomplete-core (wrapped so we can capture the config):
 *
 *   1. onStateChange debounce -> searchProjects (lines 308-332, 377-387):
 *      invoke the captured onStateChange with a query, advance the 300ms timer,
 *      assert projectsAPI.list is called; cover the short-query reset branch,
 *      the API-error branch, and the no-user early return in searchProjects.
 *
 *   2. The render path (NoResultsIcon / HighlightQuery / SearchResult /
 *      SearchResults — lines 593-751) and the SearchInput Escape handler /
 *      SearchDialog keydown (788-889): open the dialog, type, and assert the
 *      results list / no-results panel render.
 *
 * HeadlessUI's real Dialog runs `setupGlobalFocusEvents` at import time which
 * throws under jsdom, so a lightweight passthrough Dialog is used (it still
 * renders children when `open`, which is all the render path needs).
 */
import '@testing-library/jest-dom'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const mockPush = jest.fn()

// SearchDialog has an effect `setOpen(false)` keyed on [pathname, searchParams].
// Returning fresh objects each render would re-fire it and slam the dialog shut
// the instant it opens — so hand back a STABLE reference (built once in-factory).
jest.mock('next/navigation', () => {
  const mockStableSearchParams = new URLSearchParams()
  return {
    useRouter: () => ({ push: mockPush }),
    usePathname: () => '/',
    useSearchParams: () => mockStableSearchParams,
  }
})

let mockUser: any = { id: '1', username: 'u', email: 'u@e.com', is_superadmin: true }
const mockOrganizations = [{ id: '1', name: 'Org', role: 'ORG_ADMIN' }]

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: mockUser, organizations: mockOrganizations }),
}))

jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlags: () => ({
    flags: {
      reports: true,
      leaderboards: true,
      data: true,
      generations: true,
      evaluations: true,
      'how-to': true,
    },
  }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'search.placeholder': 'Search...',
        'search.noResults': 'No results for',
        'search.tryAgain': 'Try again.',
        'search.pages.projects.title': 'Projects',
        'search.pages.projects.noDescription': 'No description',
        'search.categories.projectsAndData': 'Projects & Data',
      }
      return map[key] || key
    },
    locale: 'en',
    isReady: true,
  }),
}))

jest.mock('@/components/layout/Navigation', () => ({
  navigation: [
    {
      title: 'Projects & Data',
      links: [{ href: '/projects', title: 'Projects' }],
    },
  ],
}))

jest.mock('@/components/layout/MobileNavigation', () => ({
  useMobileNavigationStore: () => ({ close: jest.fn() }),
}))

// Render the actual highlighted text so SearchResult assertions can find it.
jest.mock('react-highlight-words', () => {
  return function Highlighter({ textToHighlight }: any) {
    return <span>{textToHighlight}</span>
  }
})

// Lightweight Dialog passthrough — avoids HeadlessUI's import-time
// setupGlobalFocusEvents crash under jsdom while still mounting children.
jest.mock('@headlessui/react', () => {
  const React = jest.requireActual('react') as typeof import('react')
  const Dialog = ({ children, open, className }: any) =>
    open
      ? React.createElement(
          'div',
          { 'data-testid': 'dialog', className },
          children
        )
      : null
  const DialogPanel = ({ children, className }: any) =>
    React.createElement(
      'div',
      { 'data-testid': 'dialog-panel', className },
      children
    )
  const DialogBackdrop = ({ className }: any) =>
    React.createElement('div', { 'data-testid': 'dialog-backdrop', className })
  return { Dialog, DialogPanel, DialogBackdrop }
})

const mockProjectsList = jest.fn()
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    list: (...args: any[]) => mockProjectsList(...args),
  },
}))

// Wrap the REAL createAutocomplete so the dialog behaves authentically while we
// still capture the config object (to fire onStateChange directly in Part 1).
let capturedConfig: any = null
jest.mock('@algolia/autocomplete-core', () => {
  const actual = jest.requireActual('@algolia/autocomplete-core')
  return {
    ...actual,
    createAutocomplete: (config: any) => {
      capturedConfig = config
      return actual.createAutocomplete(config)
    },
  }
})

// eslint-disable-next-line import/first
import { Search } from '../Search'

describe('Search onStateChange -> searchProjects debounce', () => {
  beforeEach(() => {
    capturedConfig = null
    mockProjectsList.mockReset()
    mockUser = { id: '1', username: 'u', email: 'u@e.com', is_superadmin: true }
  })

  it('debounces and calls projectsAPI.list for a >=2-char query', async () => {
    jest.useFakeTimers()
    mockProjectsList.mockResolvedValue({
      items: [
        { id: 'p1', title: 'Alpha Project', description: 'desc a' },
        { id: 'p2', title: 'Beta Project', description: null },
      ],
    })
    render(<Search />)
    expect(capturedConfig).not.toBeNull()

    act(() => {
      capturedConfig.onStateChange({ state: { query: 'pro' } })
    })

    // Not called before the 300ms debounce elapses.
    expect(mockProjectsList).not.toHaveBeenCalled()

    await act(async () => {
      jest.advanceTimersByTime(300)
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(mockProjectsList).toHaveBeenCalledWith(1, 10, 'pro', false)
    jest.useRealTimers()
  })

  it('resets project results (no API call) when the query is shorter than 2 chars', async () => {
    jest.useFakeTimers()
    mockProjectsList.mockResolvedValue({ items: [] })
    render(<Search />)

    act(() => {
      capturedConfig.onStateChange({ state: { query: 'a' } })
    })
    await act(async () => {
      jest.advanceTimersByTime(300)
      await Promise.resolve()
    })

    expect(mockProjectsList).not.toHaveBeenCalled()
    jest.useRealTimers()
  })

  it('swallows a projectsAPI.list rejection and clears results', async () => {
    jest.useFakeTimers()
    const errSpy = jest.spyOn(console, 'error').mockImplementation(() => {})
    mockProjectsList.mockRejectedValue(new Error('search boom'))
    render(<Search />)

    act(() => {
      capturedConfig.onStateChange({ state: { query: 'project' } })
    })
    await act(async () => {
      jest.advanceTimersByTime(300)
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(mockProjectsList).toHaveBeenCalled()
    expect(errSpy).toHaveBeenCalledWith(
      'Project search failed:',
      expect.any(Error)
    )
    errSpy.mockRestore()
    jest.useRealTimers()
  })

  it('does not search projects when there is no authenticated user', async () => {
    jest.useFakeTimers()
    mockUser = null
    mockProjectsList.mockResolvedValue({ items: [] })
    render(<Search />)

    act(() => {
      capturedConfig.onStateChange({ state: { query: 'project' } })
    })
    await act(async () => {
      jest.advanceTimersByTime(300)
      await Promise.resolve()
    })

    // user is null => searchProjects early-returns before hitting the API.
    expect(mockProjectsList).not.toHaveBeenCalled()
    jest.useRealTimers()
  })
})

describe('Search dialog render path', () => {
  let rectSpy: jest.SpyInstance

  beforeEach(() => {
    capturedConfig = null
    mockProjectsList.mockReset()
    mockProjectsList.mockResolvedValue({ items: [] })
    mockUser = { id: '1', username: 'u', email: 'u@e.com', is_superadmin: true }
    mockPush.mockClear()
    // useSearchProps gates opening on a non-zero button rect; jsdom returns all
    // zeros, so stub a measurable box so setOpen(true) is honoured.
    rectSpy = jest
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue({
        width: 100,
        height: 32,
        top: 0,
        left: 0,
        right: 100,
        bottom: 32,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      } as DOMRect)
  })

  afterEach(() => {
    rectSpy.mockRestore()
  })

  it('renders scored page results when typing a matching query', async () => {
    const user = userEvent.setup()
    render(<Search />)

    await user.click(screen.getByRole('button'))
    const input = await screen.findByRole('searchbox')
    await user.type(input, 'projects')

    // SearchResults -> SearchResult render path: the Projects page row appears.
    await waitFor(() => {
      expect(screen.getByText('Projects')).toBeInTheDocument()
    })
  })

  it('renders the no-results panel for a query that matches nothing', async () => {
    const user = userEvent.setup()
    render(<Search />)

    await user.click(screen.getByRole('button'))
    const input = await screen.findByRole('searchbox')
    await user.type(input, 'zzzqqqxyz')

    // SearchResults empty-collection branch: the "no results" panel renders.
    await waitFor(() => {
      expect(screen.getByText(/No results for/)).toBeInTheDocument()
    })
    // The query is echoed (wrapped in typographic quotes) inside the message.
    expect(document.body.textContent).toContain('zzzqqqxyz')
  })

  it('opens the dialog via the Cmd/Ctrl+K global shortcut', async () => {
    render(<Search />)
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument()

    act(() => {
      fireEvent.keyDown(window, { key: 'k', metaKey: true })
    })

    await waitFor(() => {
      expect(screen.getByRole('searchbox')).toBeInTheDocument()
    })
  })

  it('closes the dialog on Escape once the query has been cleared (SearchInput handler)', async () => {
    const user = userEvent.setup()
    render(<Search />)

    await user.click(screen.getByRole('button'))
    const input = await screen.findByRole('searchbox')

    // Type then delete so autocompleteState.query is an explicit '' (the
    // SearchInput Escape branch requires query === '' AND the panel closed).
    await user.type(input, 'a')
    await user.clear(input)
    await waitFor(() => {
      expect((input as HTMLInputElement).value).toBe('')
    })

    fireEvent.keyDown(input, { key: 'Escape' })

    await waitFor(() => {
      expect(screen.queryByRole('searchbox')).not.toBeInTheDocument()
    })
  })
})
