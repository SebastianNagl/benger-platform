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

import { setMockFeatureFlags } from '@/test-utils/featureFlagsMock'
import DashboardPage from '@/app/dashboard/page'
import api from '@/lib/api'
import { projectsAPI } from '@/lib/api/projects'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

jest.mock('@/lib/featureFlags', () =>
  jest.requireActual('@/test-utils/featureFlagsMock').featureFlagsMockModule(),
)
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
  'generations_count',
  'evaluations_count',
  'analyses_count',
]

const stats = {
  project_count: 48,
  task_count: 1200,
  annotation_count: 530,
  generations_count: 86000,
  evaluations_count: 250,
  analyses_count: 0,
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
    // The analyses tile belongs to variant_experiments.
    setMockFeatureFlags({ variant_experiments: true })
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

  it('asks for the stats once after a 503 and shows the failure without retrying', async () => {
    ;(api.getDashboardStats as jest.Mock).mockRejectedValue(unavailableError())

    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { gcTime: 0 } } })}
      >
        <DashboardPage />
      </QueryClientProvider>,
    )

    expect(
      await screen.findByText('dashboard.statsUnavailable'),
    ).toBeInTheDocument()
    expect(api.getDashboardStats).toHaveBeenCalledTimes(1)
  })

  it('renders the recent projects while the stats request is still pending', async () => {
    ;(api.getDashboardStats as jest.Mock).mockReturnValue(new Promise(() => {}))

    renderDashboard()

    expect(await screen.findByText('Big project')).toBeInTheDocument()
    for (const key of STAT_KEYS) {
      expect(screen.getByTestId(`stat-loading-${key}`)).toBeInTheDocument()
      expect(
        screen.queryByTestId(`stat-unavailable-${key}`),
      ).not.toBeInTheDocument()
    }
    expect(screen.queryByText('0')).not.toBeInTheDocument()
  })

  it('renders the stats while the recent projects are still pending', async () => {
    ;(projectsAPI.list as jest.Mock).mockReturnValue(new Promise(() => {}))

    renderDashboard()

    expect(await screen.findByText('48')).toBeInTheDocument()
    expect(screen.getByText('common.loading')).toBeInTheDocument()
    expect(
      screen.queryByText('dashboard.recentProjects.noProjects'),
    ).not.toBeInTheDocument()
  })

  it('still shows real zero counts as 0', async () => {
    ;(api.getDashboardStats as jest.Mock).mockResolvedValue({
      ...stats,
      evaluations_count: 0,
    })

    renderDashboard()
    await waitForLoaded()

    expect(screen.getByText('0')).toBeInTheDocument()
    expect(screen.queryByTestId(/stat-unavailable-/)).not.toBeInTheDocument()
  })
})

describe('Dashboard error states with variant_experiments off', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    setMockFeatureFlags({})
    ;(projectsAPI.list as jest.Mock).mockResolvedValue(projectPage)
  })

  it('shows the five classic tiles as unavailable and no analyses tile', async () => {
    ;(api.getDashboardStats as jest.Mock).mockRejectedValue(unavailableError())

    renderDashboard()
    await waitForLoaded()

    for (const key of STAT_KEYS.filter((k) => k !== 'analyses_count')) {
      expect(screen.getByTestId(`stat-unavailable-${key}`)).toBeInTheDocument()
    }
    expect(
      screen.queryByTestId('stat-unavailable-analyses_count'),
    ).not.toBeInTheDocument()
  })

  it('shows no analyses tile while the stats are pending', async () => {
    ;(api.getDashboardStats as jest.Mock).mockReturnValue(new Promise(() => {}))

    renderDashboard()

    await waitFor(() => {
      expect(screen.getByTestId('stat-loading-task_count')).toBeInTheDocument()
    })
    expect(
      screen.queryByTestId('stat-loading-analyses_count'),
    ).not.toBeInTheDocument()
  })
})
