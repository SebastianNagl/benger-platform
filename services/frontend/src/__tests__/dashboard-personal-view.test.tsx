/**
 * The dashboard's stat tiles follow the view the API sends. A student
 * (annotator in every organization) gets their own counters: open exams,
 * open tasks, submitted answers and, once there is one, released results.
 * They no longer see the totals of every project of their organization, an
 * annotation count made of other people's answers, or the teachers'
 * generation and evaluation counts. Teachers and admins keep the overview.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  render as rtlRender,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import React from 'react'

const render: typeof rtlRender = (ui, options) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return rtlRender(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
    options,
  )
}

const mockGetDashboardStats = jest.fn()
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: { getDashboardStats: () => mockGetDashboardStats() },
}))
jest.mock('@/contexts/AuthContext', () => ({ useAuth: jest.fn() }))
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    list: jest.fn().mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 5,
      pages: 0,
    }),
  },
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: 'de' }),
}))
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  useSearchParams: () => ({ get: () => null }),
}))
jest.mock('next/link', () => {
  return function MockLink({
    children,
    href,
  }: {
    children: React.ReactNode
    href: string
  }) {
    return <a href={href}>{children}</a>
  }
})

import DashboardPage from '@/app/dashboard/page'
import { useAuth } from '@/contexts/AuthContext'

const OVERVIEW_LABELS = [
  'dashboard.stats.projects',
  'dashboard.stats.issues',
  'dashboard.stats.annotations',
  'dashboard.stats.generations',
  'dashboard.stats.evaluations',
]
const PERSONAL_LABELS = [
  'dashboard.stats.openExams',
  'dashboard.stats.openTasks',
  'dashboard.stats.submittedAnswers',
  'dashboard.stats.releasedResults',
]

const PERSONAL = {
  scope: 'personal',
  open_exams: 2,
  open_tasks: 7,
  submitted_answers: 12,
  released_results: 3,
}
const OVERVIEW = {
  scope: 'overview',
  project_count: 40,
  task_count: 900,
  annotation_count: 5000,
  generations_count: 6,
  evaluations_count: 4,
  analyses_count: 0,
}

function signIn(orgRoles: string[], user: Record<string, unknown> = {}) {
  ;(useAuth as jest.Mock).mockReturnValue({
    user: { id: 'u1', username: 'u1', is_superadmin: false, ...user },
    organizations: orgRoles.map((role, i) => ({ id: `org-${i}`, role })),
  })
}

function tiles() {
  return within(screen.getByTestId('dashboard-stats'))
}

function tile(label: string) {
  return screen.getByText(label).closest('dl') as HTMLElement
}

beforeEach(() => {
  mockGetDashboardStats.mockReset()
})

describe('dashboard stat tiles by view', () => {
  it('a student sees their own counters, no organization totals', async () => {
    signIn(['ANNOTATOR'], { role: 'ANNOTATOR' })
    mockGetDashboardStats.mockResolvedValue(PERSONAL)
    render(<DashboardPage />)

    await waitFor(() =>
      expect(tile('dashboard.stats.openTasks')).toHaveTextContent('7'),
    )
    expect(tile('dashboard.stats.openExams')).toHaveTextContent('2')
    expect(tile('dashboard.stats.submittedAnswers')).toHaveTextContent('12')
    expect(tile('dashboard.stats.releasedResults')).toHaveTextContent('3')
    for (const label of OVERVIEW_LABELS) {
      expect(tiles().queryByText(label)).not.toBeInTheDocument()
    }
    expect(screen.getByTestId('dashboard-stats')).toHaveAttribute(
      'data-scope',
      'personal',
    )
    expect(screen.getByText('dashboard.subtitlePersonal')).toBeInTheDocument()
    expect(screen.queryByText('dashboard.subtitle')).not.toBeInTheDocument()
  })

  it('hides the released results tile while there is none', async () => {
    signIn(['ANNOTATOR'], { role: 'ANNOTATOR' })
    mockGetDashboardStats.mockResolvedValue({
      ...PERSONAL,
      released_results: 0,
    })
    render(<DashboardPage />)

    await waitFor(() =>
      expect(tile('dashboard.stats.openTasks')).toHaveTextContent('7'),
    )
    expect(
      tiles().queryByText('dashboard.stats.releasedResults'),
    ).not.toBeInTheDocument()
    expect(screen.getByTestId('dashboard-stats').className).toContain(
      'md:grid-cols-3',
    )
  })

  it.each([
    ['CONTRIBUTOR', ['ANNOTATOR', 'CONTRIBUTOR']],
    ['ORG_ADMIN', ['ORG_ADMIN']],
  ])('a %s keeps the overview', async (_role, roles) => {
    signIn(roles)
    mockGetDashboardStats.mockResolvedValue(OVERVIEW)
    render(<DashboardPage />)

    await waitFor(() =>
      expect(tile('dashboard.stats.annotations')).toHaveTextContent('5000'),
    )
    expect(tile('dashboard.stats.projects')).toHaveTextContent('40')
    expect(screen.getByText('dashboard.subtitle')).toBeInTheDocument()
    for (const label of PERSONAL_LABELS) {
      expect(tiles().queryByText(label)).not.toBeInTheDocument()
    }
  })

  it('the view the API sent wins over the roles known to the client', async () => {
    // e.g. a membership changed since the client loaded the user
    signIn(['CONTRIBUTOR'])
    mockGetDashboardStats.mockResolvedValue(PERSONAL)
    render(<DashboardPage />)

    await waitFor(() =>
      expect(tile('dashboard.stats.openTasks')).toHaveTextContent('7'),
    )
    expect(
      tiles().queryByText('dashboard.stats.projects'),
    ).not.toBeInTheDocument()
  })

  it('a student waits on and misses their own tiles, not the overview', async () => {
    signIn(['ANNOTATOR'], { role: 'ANNOTATOR' })
    let fail: (e: Error) => void = () => {}
    mockGetDashboardStats.mockReturnValue(
      new Promise((_resolve, reject) => {
        fail = reject
      }),
    )
    render(<DashboardPage />)

    expect(
      await screen.findByTestId('stat-loading-open_exams'),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('stat-loading-project_count')).toBeNull()

    fail(new Error('503'))
    expect(
      await screen.findByTestId('stat-unavailable-open_tasks'),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('stat-unavailable-annotation_count')).toBeNull()
  })
})
