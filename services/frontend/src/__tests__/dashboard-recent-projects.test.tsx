/**
 * "Aktuelle Projekte" on the dashboard must not depend on the projects page.
 *
 * Reproduction: search and filter on the projects page, then open the
 * dashboard. The dashboard used the shared project store's fetchProjects,
 * which inherits the projects page's search, archive and visibility filters,
 * and rendered the store's list, so the recent projects showed only the
 * filtered projects. The dashboard now requests its own unfiltered list and
 * leaves the store alone.
 */

import DashboardPage from '@/app/dashboard/page'
import { projectsAPI } from '@/lib/api/projects'
import { useProjectStore } from '@/stores/projectStore'
import { Project } from '@/types/labelStudio'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'
import { render, screen, waitFor, within } from '@testing-library/react'

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
  }),
  usePathname: () => '/dashboard',
  useSearchParams: () => ({ get: jest.fn().mockReturnValue(null) }),
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'user-1', username: 'testuser', is_superadmin: true },
    organizations: [{ id: 'org-1', name: 'Test Org' }],
    loading: false,
  }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: 'de',
    t: (key: string) =>
      key === 'dashboard.recentProjects.title' ? 'Aktuelle Projekte' : key,
    setLocale: jest.fn(),
  }),
}))

jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    getDashboardStats: jest.fn().mockResolvedValue({
      project_count: 7,
      task_count: 0,
      annotation_count: 0,
      generations_count: 0,
      evaluations_count: 0,
      analyses_count: 0,
    }),
  },
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: { list: jest.fn() },
}))

const project = (id: string, title: string, createdAt: string): Project =>
  ({
    id,
    title,
    description: '',
    created_at: createdAt,
    task_count: 0,
  }) as Project

// What the projects page leaves in the store after a search for
// "Benchathon" in the archived, all-private view.
const filteredList = [
  project('b1', 'Benchathon', '2026-11-10T00:00:00Z'),
  project('b2', 'Benchathon Rerun', '2026-11-09T00:00:00Z'),
]

// The unfiltered newest projects, deliberately not in date order.
const recentResponse = [
  project('p3', 'Third newest', '2026-11-12T00:00:00Z'),
  project('p1', 'Newest', '2026-11-14T00:00:00Z'),
  project('p5', 'Fifth newest', '2026-11-08T00:00:00Z'),
  project('p2', 'Second newest', '2026-11-13T00:00:00Z'),
  project('p4', 'Fourth newest', '2026-11-11T00:00:00Z'),
]

const renderDashboard = (
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  }),
) =>
  render(
    <QueryClientProvider client={queryClient}>
      <DashboardPage />
    </QueryClientProvider>,
  )

const recentTitles = async () => {
  const heading = await screen.findByText('Aktuelle Projekte')
  const section = heading.closest('div.px-6') as HTMLElement
  await waitFor(() =>
    expect(
      within(section).getAllByRole('heading', { level: 4 }),
    ).not.toHaveLength(0),
  )
  return within(section)
    .getAllByRole('heading', { level: 4 })
    .map((h) => h.textContent)
}

describe('Dashboard recent projects', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    useProjectStore.setState({
      projects: filteredList,
      searchQuery: 'Benchathon',
      lastIsArchived: true,
      lastIncludeAllPrivate: true,
      currentPage: 1,
      pageSize: 50,
    })
    ;(projectsAPI.list as jest.Mock).mockResolvedValue({
      items: recentResponse,
      total: 7,
      page: 1,
      page_size: 5,
      pages: 2,
    })
  })

  it('ignores the projects page filters and shows the five newest projects', async () => {
    renderDashboard()

    expect(await recentTitles()).toEqual([
      'Newest',
      'Second newest',
      'Third newest',
      'Fourth newest',
      'Fifth newest',
    ])
    expect(screen.queryByText('Benchathon')).not.toBeInTheDocument()

    // Its own request: no search, active projects, default visibility.
    expect(projectsAPI.list).toHaveBeenCalledTimes(1)
    expect(projectsAPI.list).toHaveBeenCalledWith(1, 5, undefined, false, false)
  })

  it('leaves the projects page list and filters in the store untouched', async () => {
    renderDashboard()
    await recentTitles()

    const state = useProjectStore.getState()
    expect(state.projects).toBe(filteredList)
    expect(state.projects.map((p) => p.id)).toEqual(['b1', 'b2'])
    expect(state.searchQuery).toBe('Benchathon')
    expect(state.lastIsArchived).toBe(true)
    expect(state.lastIncludeAllPrivate).toBe(true)
    expect(state.pageSize).toBe(50)
  })

  it('does not reorder the fetched list in place', async () => {
    renderDashboard()
    await recentTitles()

    expect(recentResponse.map((p) => p.id)).toEqual([
      'p3',
      'p1',
      'p5',
      'p2',
      'p4',
    ])
  })

  it('refreshes the list on a return visit after a project was created elsewhere', async () => {
    // The app's real cache settings: data stays fresh for 60 s.
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
    })
    const first = renderDashboard(queryClient)
    expect(await recentTitles()).toHaveLength(5)
    first.unmount()

    const created = project('p0', 'Just created', '2026-11-14T12:00:00Z')
    ;(projectsAPI.list as jest.Mock).mockResolvedValue({
      items: [created, ...recentResponse.filter((p) => p.id !== 'p5')],
      total: 8,
      page: 1,
      page_size: 5,
      pages: 2,
    })

    renderDashboard(queryClient)
    await waitFor(() => expect(projectsAPI.list).toHaveBeenCalledTimes(2))
    await waitFor(async () =>
      expect(await recentTitles()).toEqual([
        'Just created',
        'Newest',
        'Second newest',
        'Third newest',
        'Fourth newest',
      ]),
    )
  })
})
