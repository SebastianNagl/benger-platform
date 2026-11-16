/**
 * The dashboard must not present failed requests as real zeros.
 *
 * Reproduction (local dev stack, project_summaries empty): the stats and
 * project-list requests ran past the database statement timeout. The stats
 * endpoint answered 200 with every counter at 0 and the project list failed,
 * so the dashboard showed five tiles at 0 and "No projects created yet"
 * while 48 projects existed. The stats endpoint now answers 503 on failure;
 * the page must show the affected tiles as unavailable and the recent
 * projects box as failed, each with a retry.
 */

import DashboardPage from '@/app/dashboard/page'
import api from '@/lib/api'
import { projectsAPI } from '@/lib/api/projects'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

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
    user: { id: 'user-1', username: 'admin', is_superadmin: true },
    organizations: [{ id: 'org-1', name: 'Test Org' }],
    loading: false,
  }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: 'en',
    t: (key: string) => key,
    setLocale: jest.fn(),
  }),
}))

jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: { getDashboardStats: jest.fn() },
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: { list: jest.fn() },
}))

const STAT_KEYS = [
  'project_count',
  'task_count',
  'annotation_count',
  'projects_with_generations',
  'projects_with_evaluations',
]

const stats = {
  project_count: 48,
  task_count: 1200,
  annotation_count: 530,
  projects_with_generations: 86000,
  projects_with_evaluations: 250,
}

const projectPage = {
  items: [
    {
      id: 'p1',
      title: 'Big project',
      description: '',
      created_at: '2026-11-14T00:00:00Z',
      task_count: 531,
    },
  ],
  total: 48,
  page: 1,
  page_size: 5,
  pages: 10,
}

const unavailableError = () =>
  Object.assign(
    new Error('Dashboard statistics are temporarily unavailable.'),
    {
      status: 503,
    },
  )

const renderDashboard = () =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: { queries: { retry: false, gcTime: 0 } },
        })
      }
    >
      <DashboardPage />
    </QueryClientProvider>,
  )

const waitForLoaded = () =>
  waitFor(() =>
    expect(screen.queryByText('common.loading')).not.toBeInTheDocument(),
  )

describe('Dashboard error states', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(api.getDashboardStats as jest.Mock).mockResolvedValue(stats)
    ;(projectsAPI.list as jest.Mock).mockResolvedValue(projectPage)
  })

  it('shows every stat tile as unavailable, not 0, when the stats request fails', async () => {
    ;(api.getDashboardStats as jest.Mock).mockRejectedValue(unavailableError())

    renderDashboard()
    await waitForLoaded()

    for (const key of STAT_KEYS) {
      expect(screen.getByTestId(`stat-unavailable-${key}`)).toHaveTextContent(
        'dashboard.stats.unavailable',
      )
    }
    expect(screen.queryByText('0')).not.toBeInTheDocument()
    expect(screen.getByText('dashboard.statsUnavailable')).toBeInTheDocument()
    // The project list is independent and still renders.
    expect(screen.getByText('Big project')).toBeInTheDocument()
  })

  it('fills the tiles after a successful retry', async () => {
    ;(api.getDashboardStats as jest.Mock)
      .mockRejectedValueOnce(unavailableError())
      .mockResolvedValueOnce(stats)

    renderDashboard()
    await waitForLoaded()
    expect(
      screen.getByTestId('stat-unavailable-project_count'),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'dashboard.retry' }))

    expect(await screen.findByText('48')).toBeInTheDocument()
    expect(
      screen.queryByTestId('stat-unavailable-project_count'),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByText('dashboard.statsUnavailable'),
    ).not.toBeInTheDocument()
  })

  it('shows the recent projects as failed, not as "no projects yet", when the list fails', async () => {
    ;(projectsAPI.list as jest.Mock).mockRejectedValue(
      Object.assign(new Error('Failed to fetch projects.'), { status: 500 }),
    )

    renderDashboard()
    await waitForLoaded()

    expect(
      screen.getByText('dashboard.recentProjects.loadFailed'),
    ).toBeInTheDocument()
    expect(
      screen.queryByText('dashboard.recentProjects.noProjects'),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByText('dashboard.recentProjects.createFirst'),
    ).not.toBeInTheDocument()
    // The stats are independent and still show their real values.
    expect(screen.getByText('48')).toBeInTheDocument()
  })

  it('loads the recent projects after a retry of a failed list', async () => {
    ;(projectsAPI.list as jest.Mock)
      .mockRejectedValueOnce(new Error('Failed to fetch projects.'))
      .mockResolvedValueOnce(projectPage)

    renderDashboard()
    await waitForLoaded()

    fireEvent.click(screen.getByRole('button', { name: 'dashboard.retry' }))

    expect(await screen.findByText('Big project')).toBeInTheDocument()
    expect(
      screen.queryByText('dashboard.recentProjects.loadFailed'),
    ).not.toBeInTheDocument()
  })

  it('still shows real zero counts as 0', async () => {
    ;(api.getDashboardStats as jest.Mock).mockResolvedValue({
      ...stats,
      projects_with_evaluations: 0,
    })

    renderDashboard()
    await waitForLoaded()

    expect(screen.getByText('0')).toBeInTheDocument()
    expect(screen.queryByTestId(/stat-unavailable-/)).not.toBeInTheDocument()
  })
})
