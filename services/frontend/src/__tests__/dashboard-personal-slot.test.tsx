/**
 * Dashboard — extended `DashboardPersonalSection` slot (personal learning
 * analytics) rendered between the stat boxes and the project sections.
 */

import DashboardPage from '@/app/dashboard/page'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'
import { render as rtlRender, screen, waitFor } from '@testing-library/react'
import React from 'react'
import { registerSlot } from '@/lib/extensions/slots'

// Phase 3 wrapped the app in a global QueryClientProvider; the dashboard
// page now uses `useQuery`, so tests must provide a client. Local wrapper
// (vs. importing from test-utils) keeps the mock graph small.
const render: typeof rtlRender = (ui, options) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return rtlRender(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
    options
  )
}

// Mock the Next.js hooks
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
  }),
  usePathname: () => '/dashboard',
  useSearchParams: () => ({
    get: jest.fn().mockReturnValue(null),
  }),
}))

// Mock the auth context
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'test-user-1',
      username: 'testuser',
      email: 'test@example.com',
      is_superadmin: false,
    },
    organizations: [{ id: 'org-1', name: 'Test Org' }],
    loading: false,
  }),
}))

// Mock the I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: 'en',
    t: (key: string) => {
      const translations: Record<string, string> = {
        'navigation.dashboard': 'Dashboard',
        'dashboard.title': 'Dashboard',
        'dashboard.subtitle':
          'Manage your annotation projects and track progress',
        'dashboard.stats.projects': 'Projects',
        'dashboard.stats.issues': 'Tasks',
        'dashboard.stats.annotations': 'Annotations',
        'dashboard.stats.generations': 'Generations',
        'dashboard.stats.evaluations': 'Evaluations',
        'dashboard.recentProjects.title': 'Recent Projects',
        'dashboard.recentProjects.viewAll': 'View All',
        'dashboard.recentProjects.noProjects': 'No projects created yet',
        'dashboard.recentProjects.createFirst': 'Create Your First Project',
        'dashboard.quickActions': 'Quick Actions',
        'common.loading': 'Loading...',
      }
      return translations[key] || key
    },
    setLocale: jest.fn(),
  }),
}))

// Mock the feature flags context
jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlags: () => ({
    flags: {
      data: true,
      generations: true,
      evaluations: true,
    },
    loading: false,
  }),
}))

// Mock the project store
jest.mock('@/stores/projectStore', () => ({
  useProjectStore: () => ({
    projects: [],
    fetchProjects: jest.fn(),
    loading: false,
  }),
}))

// Mock the API
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    getDashboardStats: jest.fn().mockResolvedValue({
      project_count: 12,
      task_count: 296,
      annotation_count: 850,
      projects_with_generations: 0,
      projects_with_evaluations: 0,
    }),
  },
}))

describe('Dashboard personal section slot', () => {
  afterEach(() => registerSlot('DashboardPersonalSection', null as any))

  it('renders nothing without the slot', async () => {
    render(<DashboardPage />)
    await waitFor(() => expect(screen.queryByTestId('dashboard-personal-section')).not.toBeInTheDocument())
  })

  it('renders the slot after the stats grid', async () => {
    registerSlot('DashboardPersonalSection', () => <div data-testid="personal-stub">Lernstatistik</div>)
    render(<DashboardPage />)
    const host = await screen.findByTestId('dashboard-personal-section')
    expect(host).toContainElement(screen.getByTestId('personal-stub'))
    const stats = document.querySelector('.lg\\:grid-cols-5') as HTMLElement
    expect(stats).not.toBeNull()
    expect(stats.compareDocumentPosition(host) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})
