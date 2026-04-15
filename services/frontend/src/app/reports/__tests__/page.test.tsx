/**
 * Tests for Reports Listing Page
 *
 * Tests the reports grid display including:
 * - Loading states
 * - Empty state when no reports
 * - Report cards display
 * - Navigation to report details
 * - Permission checks
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock next/navigation
const mockPush = jest.fn()
const mockReplace = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
    prefetch: jest.fn(),
  }),
}))

// Mock auth context - default to superadmin
let mockUser: any = { id: 'test-user', is_superadmin: true }
let mockAuthLoading = false
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: mockUser,
    isLoading: mockAuthLoading,
  }),
}))

// Mock permissions
jest.mock('@/utils/permissions', () => ({
  canAccessReports: (user: any) =>
    user?.is_superadmin ||
    user?.org_memberships?.some((m: any) => m.role === 'admin'),
}))

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'common.loading': 'Loading...',
        'common.accessDenied': 'Access Denied',
        'common.backToProjects': 'Back to Projects',
        'common.retry': 'Retry',
        'reports.title': 'Reports',
        'reports.loadFailed': 'Failed to load reports',
        'reports.accessDeniedMessage': 'Only superadmins and organization admins can access reports.',
        'reports.loadingReports': 'Loading reports...',
        'reports.noReports': 'No Published Reports',
        'reports.noReportsDescription': 'No reports have been published yet.',
        'reports.tasks': 'tasks',
        'reports.annotations': 'annotations',
        'reports.models': 'models evaluated',
        'reports.published': 'Published',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))

// Store fetch mock for tests
let mockFetch: jest.Mock

describe('Reports Listing Page', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    // Reset user to superadmin
    mockUser = { id: 'test-user', is_superadmin: true }
    mockAuthLoading = false

    // Setup fetch mock
    mockFetch = jest.fn()
    global.fetch = mockFetch
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('Loading State', () => {
    it('shows loading state while checking auth', async () => {
      mockAuthLoading = true

      const ReportsPage = (await import('../page')).default

      render(<ReportsPage />)

      expect(screen.getByText(/loading/i)).toBeInTheDocument()
    })

    it('shows loading state while fetching reports', async () => {
      // Never resolving fetch
      mockFetch.mockImplementation(() => new Promise(() => {}))

      const ReportsPage = (await import('../page')).default

      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getByText(/loading reports/i)).toBeInTheDocument()
      })
    })
  })

  describe('Permission Checks', () => {
    it('redirects non-authorized users', async () => {
      mockUser = { id: 'test-user', is_superadmin: false }

      const ReportsPage = (await import('../page')).default

      render(<ReportsPage />)

      await waitFor(() => {
        expect(mockReplace).toHaveBeenCalledWith(
          '/projects?error=no-permission'
        )
      })
    })

    it('allows superadmins to access', async () => {
      mockUser = { id: 'test-user', is_superadmin: true }
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => [],
      })

      const ReportsPage = (await import('../page')).default

      render(<ReportsPage />)

      await waitFor(() => {
        expect(mockReplace).not.toHaveBeenCalled()
      })
    })

    it('allows org admins to access', async () => {
      mockUser = {
        id: 'test-user',
        is_superadmin: false,
        org_memberships: [{ organization_id: 'org-1', role: 'admin' }],
      }
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => [],
      })

      const ReportsPage = (await import('../page')).default

      render(<ReportsPage />)

      await waitFor(() => {
        expect(mockReplace).not.toHaveBeenCalled()
      })
    })
  })

  describe('Empty State', () => {
    it('shows empty state when no reports exist', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => [],
      })

      const ReportsPage = (await import('../page')).default

      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getByText(/no published reports/i)).toBeInTheDocument()
      })
    })
  })

  describe('Reports Display', () => {
    const mockReports = [
      {
        id: 'report-1',
        project_id: 'project-1',
        project_title: 'Test Project 1',
        published_at: '2025-01-10T10:00:00Z',
        task_count: 100,
        annotation_count: 300,
        model_count: 3,
        organizations: [{ id: 'org-1', name: 'TUM' }],
      },
      {
        id: 'report-2',
        project_id: 'project-2',
        project_title: 'Test Project 2',
        published_at: '2025-01-11T10:00:00Z',
        task_count: 50,
        annotation_count: 150,
        model_count: 2,
        organizations: [{ id: 'org-1', name: 'TUM' }],
      },
    ]

    it('displays report cards with correct information', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockReports,
      })

      const ReportsPage = (await import('../page')).default

      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getByText('Test Project 1')).toBeInTheDocument()
        expect(screen.getByText('Test Project 2')).toBeInTheDocument()
      })
    })

    it('shows task counts on report cards', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockReports,
      })

      const ReportsPage = (await import('../page')).default

      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getByText('100 tasks')).toBeInTheDocument()
        expect(screen.getByText('50 tasks')).toBeInTheDocument()
      })
    })

    it('shows organization badges', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockReports,
      })

      const ReportsPage = (await import('../page')).default

      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getAllByText('TUM').length).toBeGreaterThan(0)
      })
    })

    it('shows model counts', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockReports,
      })

      const ReportsPage = (await import('../page')).default

      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getByText('3 models evaluated')).toBeInTheDocument()
        expect(screen.getByText('2 models evaluated')).toBeInTheDocument()
      })
    })
  })

  describe('Navigation', () => {
    it('navigates to report detail on card click', async () => {
      const mockReports = [
        {
          id: 'report-1',
          project_id: 'project-1',
          project_title: 'Clickable Project',
          published_at: '2025-01-10T10:00:00Z',
          task_count: 100,
          annotation_count: 300,
          model_count: 3,
          organizations: [],
        },
      ]

      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockReports,
      })

      const ReportsPage = (await import('../page')).default

      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getByText('Clickable Project')).toBeInTheDocument()
      })

      // Click on the report card
      const reportCard = screen
        .getByText('Clickable Project')
        .closest('div[class*="cursor-pointer"]')
      if (reportCard) {
        await userEvent.click(reportCard)
      }

      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/reports/report-1')
      })
    })
  })

  describe('Error Handling', () => {
    it('shows error message on API failure', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        statusText: 'Internal Server Error',
      })

      const ReportsPage = (await import('../page')).default

      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getByText(/failed to load reports/i)).toBeInTheDocument()
      })
    })

    it('shows retry button on error', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        statusText: 'Internal Server Error',
      })

      const ReportsPage = (await import('../page')).default

      render(<ReportsPage />)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /retry/i })
        ).toBeInTheDocument()
      })
    })

    it('retries on button click', async () => {
      // First call fails
      mockFetch
        .mockResolvedValueOnce({
          ok: false,
          statusText: 'Error',
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => [],
        })

      const ReportsPage = (await import('../page')).default

      render(<ReportsPage />)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /retry/i })
        ).toBeInTheDocument()
      })

      await userEvent.click(screen.getByRole('button', { name: /retry/i }))

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledTimes(2)
      })
    })
  })
})
