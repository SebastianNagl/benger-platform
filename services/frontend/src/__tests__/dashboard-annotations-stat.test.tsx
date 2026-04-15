/**
 * Tests for the Annotations stat box on the dashboard
 * Issue #580: Add Annotations stat box to dashboard between Tasks and Generations
 */

import DashboardPage from '@/app/dashboard/page'
import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'

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

describe('Dashboard Annotations Stat Box', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('should render the annotations stat box between tasks and generations', async () => {
    render(<DashboardPage />)

    // Wait for the dashboard to load
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
    })

    // Check that all stat boxes are rendered in the correct order
    // Query specifically for dt elements to avoid matching headings
    const allDtElements = document.querySelectorAll('dt')
    const statLabels = Array.from(allDtElements).filter((dt) =>
      /Projects|Tasks|Annotations|Generations|Evaluations/.test(
        dt.textContent || ''
      )
    )

    // Verify the order: Projects, Tasks, Annotations, Generations, Evaluations
    expect(statLabels).toHaveLength(5)
    expect(statLabels[0]).toHaveTextContent('Projects')
    expect(statLabels[1]).toHaveTextContent('Tasks')
    expect(statLabels[2]).toHaveTextContent('Annotations')
    expect(statLabels[3]).toHaveTextContent('Generations')
    expect(statLabels[4]).toHaveTextContent('Evaluations')
  })

  it('should display the correct annotation count', async () => {
    render(<DashboardPage />)

    // Wait for the dashboard to load
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
    })

    // Check that the annotation count is displayed
    expect(screen.getByText('850')).toBeInTheDocument()
    expect(screen.getByText('Annotations')).toBeInTheDocument()
  })

  it('should render with 5 columns on large screens', async () => {
    render(<DashboardPage />)

    // Wait for the dashboard to load
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
    })

    // Check that the grid container has the correct classes for 5 columns
    const statsGrid = document.querySelector('.lg\\:grid-cols-5')
    expect(statsGrid).toBeInTheDocument()
  })

  it('should use the pencil icon for the annotations stat box', async () => {
    render(<DashboardPage />)

    // Wait for the dashboard to load
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
    })

    // Check that the SVG path for the pencil icon is present
    // This is the path for the pencil icon used in the annotations stat box
    const pencilPath = document.querySelector(
      'path[d*="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414"]'
    )
    expect(pencilPath).toBeInTheDocument()
  })

  it('should handle API errors gracefully', async () => {
    // Mock API error
    const api = require('@/lib/api').default
    api.getDashboardStats.mockRejectedValueOnce(new Error('API Error'))

    render(<DashboardPage />)

    // Wait for the error to be handled
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
    })

    // The dashboard should still render, potentially with default values
    expect(screen.getByText('Annotations')).toBeInTheDocument()
  })

  it('should display zero annotations when there are none', async () => {
    // Mock API response with zero annotations
    const api = require('@/lib/api').default
    api.getDashboardStats.mockResolvedValueOnce({
      project_count: 5,
      task_count: 10,
      annotation_count: 0,
      projects_with_generations: 0,
      projects_with_evaluations: 0,
    })

    render(<DashboardPage />)

    // Wait for the dashboard to load
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
    })

    // Check that zero is displayed for annotations
    const zeroValues = screen.getAllByText('0')
    // There should be at least one '0' for annotations (might be more for other stats)
    expect(zeroValues.length).toBeGreaterThan(0)
    expect(screen.getByText('Annotations')).toBeInTheDocument()
  })
})
