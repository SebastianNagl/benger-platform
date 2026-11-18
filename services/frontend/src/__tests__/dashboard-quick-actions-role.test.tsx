/**
 * The dashboard's quick actions follow the user's role: import, generation
 * and evaluation need ORG_ADMIN or CONTRIBUTOR somewhere (the same gate that
 * greys out those sidebar entries), so a student only sees the action they
 * can use (creating a private project). The paid e2e run found a student
 * dashboard offering "Daten importieren" and "Generierung starten".
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render as rtlRender, screen, within } from '@testing-library/react'
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

jest.mock('@/lib/api', () => ({
  default: {
    getDashboardStats: jest.fn().mockResolvedValue({
      project_count: 1,
      task_count: 1,
      annotation_count: 0,
      projects_with_generations: 0,
      projects_with_evaluations: 0,
    }),
  },
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

function signIn(user: Record<string, unknown>, orgRoles: string[]) {
  ;(useAuth as jest.Mock).mockReturnValue({
    user: { id: 'u1', username: 'u1', is_superadmin: false, ...user },
    organizations: orgRoles.map((role, i) => ({ id: `org-${i}`, role })),
  })
}

describe('dashboard quick actions by role', () => {
  it('a student (annotator in every org) sees only "create project"', () => {
    signIn({ role: 'ANNOTATOR' }, ['ANNOTATOR'])
    render(<DashboardPage />)

    expect(
      screen.getByText('dashboard.createNewProject.button'),
    ).toBeInTheDocument()
    for (const key of TEACHER_ONLY) {
      expect(screen.queryByText(key)).not.toBeInTheDocument()
    }
  })

  it('a user without any organization gets no teacher actions', () => {
    signIn({ role: null }, [])
    render(<DashboardPage />)

    for (const key of TEACHER_ONLY) {
      expect(screen.queryByText(key)).not.toBeInTheDocument()
    }
  })

  it.each(['CONTRIBUTOR', 'ORG_ADMIN'])(
    'a %s in one of several orgs sees every action',
    (role) => {
      signIn({ role: 'ANNOTATOR' }, ['ANNOTATOR', role])
      render(<DashboardPage />)

      expect(
        screen.getByText('dashboard.createNewProject.button'),
      ).toBeInTheDocument()
      for (const key of TEACHER_ONLY) {
        expect(screen.getByText(key)).toBeInTheDocument()
      }
    },
  )

  it('a superadmin sees every action', () => {
    signIn({ is_superadmin: true, role: 'ANNOTATOR' }, [])
    render(<DashboardPage />)

    for (const key of TEACHER_ONLY) {
      expect(screen.getByText(key)).toBeInTheDocument()
    }
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
