/**
 * Test suite for dashboard organization warning feature
 * Tests the display of warning message for users without organization assignment
 */

import { render, screen, waitFor } from '@testing-library/react'
import React from 'react'

// Mock ApiClient before any imports that might use it
jest.mock('@/lib/api', () => ({
  ApiClient: jest.fn().mockImplementation(() => ({
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
  })),
  default: {
    getDashboardStats: jest.fn().mockResolvedValue({
      project_count: 5,
      task_count: 10,
      projects_with_generations: 2,
      projects_with_evaluations: 1,
    }),
  },
}))

// Mock dependencies
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))
jest.mock('@/stores/projectStore', () => ({
  useProjectStore: jest.fn(),
}))
jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlags: jest.fn(),
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

// Mock Next.js Link component
jest.mock('next/link', () => {
  return function MockLink({ children, href }: { children: React.ReactNode; href: string }) {
    return <a href={href}>{children}</a>
  }
})

// Import components and hooks after all mocks are set up
import DashboardPage from '@/app/dashboard/page'
import { useAuth } from '@/contexts/AuthContext'
import { useFeatureFlags } from '@/contexts/FeatureFlagContext'
import { useI18n } from '@/contexts/I18nContext'
import { useProjectStore } from '@/stores/projectStore'

describe('Dashboard Organization Warning', () => {
  const mockT = (key: string) => {
    const translations: Record<string, string> = {
      'navigation.dashboard': 'Dashboard',
      'dashboard.title': 'Dashboard',
      'dashboard.subtitle':
        'Manage your annotation projects and track progress',
      'dashboard.organizationWarning.title': 'No Organization Assignment',
      'dashboard.organizationWarning.message':
        'You are not currently assigned to any organization. This limits your access to features. Please contact your organization administrator to be assigned to an organization.',
      'dashboard.stats.projects': 'Projects',
      'dashboard.stats.issues': 'Tasks',
      'dashboard.stats.generations': 'Generations',
      'dashboard.stats.evaluations': 'Evaluations',
      'dashboard.recentProjects.title': 'Recent Projects',
      'dashboard.recentProjects.viewAll': 'View All',
      'dashboard.recentProjects.noProjects': 'No projects created yet',
      'dashboard.recentProjects.createFirst': 'Create Your First Project',
      'dashboard.quickActions': 'Quick Actions',
      'dashboard.createNewProject.title': 'Create New Project',
      'dashboard.createNewProject.description':
        'Start a new annotation project with custom labeling interface',
      'dashboard.createNewProject.button': 'Create Project',
      'dashboard.importData.title': 'Import Data',
      'dashboard.importData.description':
        'Upload JSON, CSV, or other data formats to start annotating',
      'dashboard.importData.button': 'Import Data',
      'common.loading': 'Loading...',
    }
    return translations[key] || key
  }

  const mockProjects = [
    {
      id: '1',
      title: 'Test Project 1',
      description: 'Description 1',
      created_at: '2024-01-01T00:00:00Z',
      task_count: 5,
    },
    {
      id: '2',
      title: 'Test Project 2',
      description: 'Description 2',
      created_at: '2024-01-02T00:00:00Z',
      task_count: 3,
    },
  ]

  beforeEach(() => {
    // Reset all mocks before each test
    jest.clearAllMocks()

    // Setup default mock implementations
    ;(useI18n as jest.Mock).mockReturnValue({
      t: mockT,
    })
    ;(useProjectStore as jest.Mock).mockReturnValue({
      projects: mockProjects,
      fetchProjects: jest.fn().mockResolvedValue(undefined),
      loading: false,
    })
    ;(useFeatureFlags as jest.Mock).mockReturnValue({
      flags: {
        data: true,
        generations: false,
        evaluations: false,
      },
    })
  })

  describe('when user has no organizations', () => {
    beforeEach(() => {
      ;(useAuth as jest.Mock).mockReturnValue({
        organizations: [], // User has no organizations
      })
    })

    it('should display the organization warning alert', async () => {
      render(<DashboardPage />)

      await waitFor(() => {
        const warningTitle = screen.getByText('No Organization Assignment')
        expect(warningTitle).toBeInTheDocument()
      })

      const warningMessage = screen.getByText(
        /You are not currently assigned to any organization/
      )
      expect(warningMessage).toBeInTheDocument()
    })

    it('should display warning with correct styling', async () => {
      const { container } = render(<DashboardPage />)

      await waitFor(() => {
        // Check for Alert component with warning variant
        const alertElement = container.querySelector('.bg-amber-50')
        expect(alertElement).toBeInTheDocument()
      })
    })

    it('should display warning above stats cards', async () => {
      const { container } = render(<DashboardPage />)

      await waitFor(() => {
        const warningTitle = screen.getByText('No Organization Assignment')
        expect(warningTitle).toBeInTheDocument()
      })

      // Get the warning element and stats section
      const warningElement = screen
        .getByText('No Organization Assignment')
        .closest('[class*="Alert"]')
      const statsSection = container.querySelector('.grid.grid-cols-1.gap-6')

      // Warning should appear before stats in the DOM
      if (warningElement && statsSection) {
        expect(
          warningElement.compareDocumentPosition(statsSection) &
            Node.DOCUMENT_POSITION_FOLLOWING
        ).toBeTruthy()
      }
    })
  })

  describe('when user has organizations', () => {
    beforeEach(() => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', username: 'testuser', is_superadmin: false, role: 'CONTRIBUTOR' },
        organizations: [
          {
            id: '1',
            name: 'Test Organization',
            display_name: 'Test Org',
          },
        ], // User has at least one organization
      })
    })

    it('should NOT display the organization warning alert', async () => {
      render(<DashboardPage />)

      await waitFor(() => {
        const dashboardTitle = screen.getByText('Dashboard')
        expect(dashboardTitle).toBeInTheDocument()
      })

      // Warning should not be present
      const warningTitle = screen.queryByText('No Organization Assignment')
      expect(warningTitle).not.toBeInTheDocument()

      const warningMessage = screen.queryByText(
        /You are not currently assigned to any organization/
      )
      expect(warningMessage).not.toBeInTheDocument()
    })

    it('should display dashboard content normally', async () => {
      render(<DashboardPage />)

      await waitFor(() => {
        // Check that normal dashboard content is displayed
        expect(screen.getByText('Projects')).toBeInTheDocument()
        expect(screen.getByText('Tasks')).toBeInTheDocument()
        expect(screen.getByText('Recent Projects')).toBeInTheDocument()
        expect(screen.getByText('Quick Actions')).toBeInTheDocument()
      })
    })
  })

  describe('when organizations is null or undefined', () => {
    it('should NOT display warning when organizations is null', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        organizations: null,
      })

      render(<DashboardPage />)

      await waitFor(() => {
        const dashboardTitle = screen.getByText('Dashboard')
        expect(dashboardTitle).toBeInTheDocument()
      })

      const warningTitle = screen.queryByText('No Organization Assignment')
      expect(warningTitle).not.toBeInTheDocument()
    })

    it('should NOT display warning when organizations is undefined', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        organizations: undefined,
      })

      render(<DashboardPage />)

      await waitFor(() => {
        const dashboardTitle = screen.getByText('Dashboard')
        expect(dashboardTitle).toBeInTheDocument()
      })

      const warningTitle = screen.queryByText('No Organization Assignment')
      expect(warningTitle).not.toBeInTheDocument()
    })
  })

  describe('loading states', () => {
    it('should not show warning during loading', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        organizations: [],
      })
      ;(useProjectStore as jest.Mock).mockReturnValue({
        projects: [],
        fetchProjects: jest.fn(),
        loading: true, // Still loading
      })

      render(<DashboardPage />)

      // Should show loading state
      expect(screen.getByText('Loading...')).toBeInTheDocument()

      // Warning should not be shown during loading
      const warningTitle = screen.queryByText('No Organization Assignment')
      expect(warningTitle).not.toBeInTheDocument()
    })
  })

  describe('internationalization', () => {
    it('should use translated text for warning', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        organizations: [],
      })

      const germanTranslations = {
        'dashboard.organizationWarning.title': 'Keine Organisationszuweisung',
        'dashboard.organizationWarning.message':
          'Sie sind derzeit keiner Organisation zugewiesen. Dies schränkt Ihren Zugriff auf Funktionen ein. Bitte kontaktieren Sie Ihren Organisationsadministrator, um einer Organisation zugewiesen zu werden.',
      }

      ;(useI18n as jest.Mock).mockReturnValue({
        t: (key: string) => germanTranslations[key] || mockT(key),
      })

      render(<DashboardPage />)

      await waitFor(() => {
        // Check for German translations
        expect(
          screen.getByText('Keine Organisationszuweisung')
        ).toBeInTheDocument()
        expect(
          screen.getByText(/Sie sind derzeit keiner Organisation zugewiesen/)
        ).toBeInTheDocument()
      })
    })
  })
})
