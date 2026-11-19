/**
 * The dashboard's teacher quick actions (import, generation, evaluation)
 * follow the view GET /api/dashboard/stats sends (`scope`): the API counts
 * group teachers and creators of their own projects as teachers too, which
 * the client's org roles cannot tell. Until the answer arrives, or when the
 * request fails, the org roles stand in (ORG_ADMIN or CONTRIBUTOR
 * somewhere). A student only sees the action they can use (creating a
 * private project). The paid e2e run found a student dashboard offering
 * "Daten importieren" and "Generierung starten".
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
import { projectsAPI } from '@/lib/api/projects'

const TEACHER_ONLY = [
  'dashboard.importData.button',
  'dashboard.generation.button',
  'dashboard.evaluation.button',
]

const OVERVIEW = {
  scope: 'overview',
  project_count: 1,
  task_count: 1,
  annotation_count: 0,
  generations_count: 0,
  evaluations_count: 0,
  analyses_count: 0,
}
const PERSONAL = {
  scope: 'personal',
  open_exams: 0,
  open_tasks: 2,
  submitted_answers: 0,
  released_results: 0,
}

function signIn(user: Record<string, unknown>, orgRoles: string[]) {
  ;(useAuth as jest.Mock).mockReturnValue({
    user: { id: 'u1', username: 'u1', is_superadmin: false, ...user },
    organizations: orgRoles.map((role, i) => ({ id: `org-${i}`, role })),
  })
}

async function renderSettled() {
  render(<DashboardPage />)
  await waitFor(() =>
    expect(screen.getByTestId('dashboard-stats')).toHaveAttribute(
      'aria-busy',
      'false',
    ),
  )
}

function expectTeacherActions(shown: boolean) {
  expect(
    screen.getByText('dashboard.createNewProject.button'),
  ).toBeInTheDocument()
  for (const key of TEACHER_ONLY) {
    if (shown) expect(screen.getByText(key)).toBeInTheDocument()
    else expect(screen.queryByText(key)).not.toBeInTheDocument()
  }
}

beforeEach(() => {
  mockGetDashboardStats.mockReset()
  mockGetDashboardStats.mockResolvedValue(OVERVIEW)
})

describe('dashboard quick actions follow the view of the stats', () => {
  it('a student (annotator in every org) sees only "create project"', async () => {
    signIn({ role: 'ANNOTATOR' }, ['ANNOTATOR'])
    mockGetDashboardStats.mockResolvedValue(PERSONAL)
    await renderSettled()

    expectTeacherActions(false)
  })

  it('a user without any organization gets no teacher actions', async () => {
    signIn({ role: null }, [])
    mockGetDashboardStats.mockResolvedValue(PERSONAL)
    await renderSettled()

    expectTeacherActions(false)
  })

  it.each(['CONTRIBUTOR', 'ORG_ADMIN'])(
    'a %s in one of several orgs sees every action',
    async (role) => {
      signIn({ role: 'ANNOTATOR' }, ['ANNOTATOR', role])
      await renderSettled()

      expectTeacherActions(true)
    },
  )

  it('a superadmin sees every action', async () => {
    signIn({ is_superadmin: true, role: 'ANNOTATOR' }, [])
    await renderSettled()

    expectTeacherActions(true)
  })

  it('a group teacher who is only annotator at org level gets the actions back', async () => {
    signIn({ role: 'ANNOTATOR' }, ['ANNOTATOR'])
    await renderSettled()

    expectTeacherActions(true)
  })

  it('the creator of a private project without any organization gets the actions', async () => {
    signIn({ role: null }, [])
    await renderSettled()

    expectTeacherActions(true)
  })

  it('a personal answer hides the actions whatever the org roles say', async () => {
    signIn({ role: 'CONTRIBUTOR' }, ['CONTRIBUTOR'])
    mockGetDashboardStats.mockResolvedValue(PERSONAL)
    await renderSettled()

    expectTeacherActions(false)
  })
})

describe('dashboard quick actions before or without a stats answer', () => {
  it('follow the org roles while the stats load', () => {
    mockGetDashboardStats.mockReturnValue(new Promise(() => {}))
    signIn({ role: 'ANNOTATOR' }, ['ANNOTATOR'])
    const { unmount } = render(<DashboardPage />)
    expectTeacherActions(false)
    unmount()

    signIn({ role: 'CONTRIBUTOR' }, ['CONTRIBUTOR'])
    render(<DashboardPage />)
    expectTeacherActions(true)
  })

  it.each([
    ['ANNOTATOR', false],
    ['CONTRIBUTOR', true],
  ])('follow the org roles when the stats fail (%s)', async (role, shown) => {
    mockGetDashboardStats.mockRejectedValue(new Error('503'))
    signIn({ role }, [role as string])
    await renderSettled()

    expectTeacherActions(shown as boolean)
  })
})

describe('dashboard recent projects task count', () => {
  it('uses the singular for one task and the plural otherwise', async () => {
    signIn({ role: 'ANNOTATOR' }, ['ANNOTATOR'])
    ;(projectsAPI.list as jest.Mock).mockResolvedValueOnce({
      items: [
        {
          id: 'p1',
          title: 'One task',
          created_at: '2026-11-18T07:00:00Z',
          task_count: 1,
        },
        {
          id: 'p2',
          title: 'Three tasks',
          created_at: '2026-11-17T07:00:00Z',
          task_count: 3,
        },
      ],
      total: 2,
      page: 1,
      page_size: 5,
      pages: 1,
    })
    render(<DashboardPage />)

    const one = (await screen.findByText('One task')).closest('a')!
    const three = screen.getByText('Three tasks').closest('a')!
    expect(
      within(one).getByText(/dashboard\.recentProjects\.taskOne/),
    ).toHaveTextContent('1 dashboard.recentProjects.taskOne')
    expect(
      within(three).getByText(/dashboard\.recentProjects\.tasks/),
    ).toHaveTextContent('3 dashboard.recentProjects.tasks')
  })
})
