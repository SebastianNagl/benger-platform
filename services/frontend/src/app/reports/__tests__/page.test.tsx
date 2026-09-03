/**
 * Tests for Reports Listing Page
 *
 * - Loading / error / empty states keep the page chrome
 * - Anonymous visitors see the list (public reports) with a sign-in hint
 * - Visibility badge per card ("Öffentlich" / "Organisation")
 * - Cards link to /reports/[id]
 * - No permission gate / redirect
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const mockPush = jest.fn()
const mockReplace = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
    prefetch: jest.fn(),
  }),
  usePathname: () => '/reports',
}))

let mockUser: any = { id: 'test-user', is_superadmin: true }
let mockAuthLoading = false
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: mockUser,
    isLoading: mockAuthLoading,
  }),
}))

jest.mock('@/lib/api/reports', () => ({
  listPublishedReports: jest.fn(),
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <nav data-testid="breadcrumb">
      {items.map((item: any, i: number) => (
        <span key={i}>{item.label}</span>
      ))}
    </nav>
  ),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, fallback?: any) => {
      const translations: Record<string, string> = {
        'common.retry': 'Retry',
        'navigation.dashboard': 'Dashboard',
        'navigation.reports': 'Reports',
        'reports.title': 'Reports',
        'reports.loadFailed': 'Failed to load reports',
        'reports.loadingReports': 'Loading reports...',
        'reports.noReports': 'No Published Reports',
        'reports.noReportsDescription': 'No reports have been published yet.',
        'reports.tasks': 'tasks',
        'reports.annotations': 'annotations',
        'reports.models': 'models evaluated',
        'reports.published': 'Published',
      }
      if (translations[key]) return translations[key]
      return typeof fallback === 'string' ? fallback : key
    },
    locale: 'en',
  }),
}))

import { listPublishedReports } from '@/lib/api/reports'
import ReportsPage from '../page'

const mockList = listPublishedReports as jest.Mock

const mockReports = [
  {
    id: 'report-1',
    project_id: 'project-1',
    project_title: 'Test Project 1',
    published_at: '2025-01-10T10:00:00Z',
    task_count: 100,
    annotation_count: 300,
    model_count: 3,
    is_public: true,
    visibility: 'public',
    organizations: [{ id: 'org-1', name: 'TUM' }],
  },
  {
    id: 'report-2',
    project_id: 'project-2',
    project_title: 'Test Project 2',
    published_at: '2025-01-11T10:00:00Z',
    task_count: 50,
    annotation_count: 0,
    model_count: 2,
    is_public: false,
    visibility: 'organizations',
    organizations: [{ id: 'org-1', name: 'TUM' }],
  },
]

describe('Reports Listing Page', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockUser = { id: 'test-user', is_superadmin: true }
    mockAuthLoading = false
  })

  describe('Loading State', () => {
    it('shows the loading state (with page title) while auth is checked', () => {
      mockAuthLoading = true

      render(<ReportsPage />)

      expect(screen.getByTestId('reports-loading')).toBeInTheDocument()
      expect(
        screen.getByRole('heading', { level: 1, name: 'Reports' })
      ).toBeInTheDocument()
      expect(mockList).not.toHaveBeenCalled()
    })

    it('shows the loading state while fetching reports', async () => {
      mockList.mockImplementation(() => new Promise(() => {}))

      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getByText(/loading reports/i)).toBeInTheDocument()
      })
    })
  })

  describe('No permission gate', () => {
    it('never redirects (annotators, contributors, anonymous all allowed)', async () => {
      mockUser = { id: 'test-user', is_superadmin: false, role: 'ANNOTATOR' }
      mockList.mockResolvedValue([])

      render(<ReportsPage />)

      await waitFor(() => {
        expect(mockList).toHaveBeenCalledTimes(1)
      })
      expect(mockReplace).not.toHaveBeenCalled()
      expect(mockPush).not.toHaveBeenCalled()
    })
  })

  describe('Anonymous visitors', () => {
    beforeEach(() => {
      mockUser = null
    })

    it('loads and shows public reports with a sign-in hint and no breadcrumb', async () => {
      mockList.mockResolvedValue([mockReports[0]])

      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getByText('Test Project 1')).toBeInTheDocument()
      })
      expect(mockList).toHaveBeenCalledTimes(1)
      expect(screen.queryByTestId('breadcrumb')).not.toBeInTheDocument()
      const signIn = screen.getByRole('link', { name: 'Anmelden' })
      expect(signIn).toHaveAttribute('href', '/login?next=%2Freports')
      expect(mockReplace).not.toHaveBeenCalled()
    })

    it('shows the public-specific empty state', async () => {
      mockList.mockResolvedValue([])

      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getByTestId('reports-empty')).toBeInTheDocument()
      })
      expect(
        screen.getByText('Derzeit ist kein Bericht öffentlich freigegeben.')
      ).toBeInTheDocument()
    })
  })

  describe('Empty State', () => {
    it('keeps the page chrome and shows the empty state', async () => {
      mockList.mockResolvedValue([])

      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getByText(/no published reports/i)).toBeInTheDocument()
      })
      expect(
        screen.getByRole('heading', { level: 1, name: 'Reports' })
      ).toBeInTheDocument()
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
      expect(
        screen.getByText('No reports have been published yet.')
      ).toBeInTheDocument()
    })
  })

  describe('Reports Display', () => {
    beforeEach(() => {
      mockList.mockResolvedValue(mockReports)
    })

    it('displays report cards with titles, counts and org chips', async () => {
      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getByText('Test Project 1')).toBeInTheDocument()
      })
      expect(screen.getByText('Test Project 2')).toBeInTheDocument()
      expect(screen.getByText('100 tasks')).toBeInTheDocument()
      expect(screen.getByText('50 tasks')).toBeInTheDocument()
      expect(screen.getByText('300 annotations')).toBeInTheDocument()
      expect(screen.getByText('3 models evaluated')).toBeInTheDocument()
      expect(screen.getByText('2 models evaluated')).toBeInTheDocument()
      expect(screen.getAllByText('TUM').length).toBe(2)
    })

    it('shows the visibility badge per card', async () => {
      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getByTestId('report-card-report-1')).toBeInTheDocument()
      })
      expect(
        within(screen.getByTestId('report-card-report-1')).getByTestId(
          'report-visibility'
        )
      ).toHaveTextContent('Öffentlich')
      expect(
        within(screen.getByTestId('report-card-report-2')).getByTestId(
          'report-visibility'
        )
      ).toHaveTextContent('Organisation')
    })

    it('falls back to is_public when visibility is missing', async () => {
      mockList.mockResolvedValue([
        { ...mockReports[0], visibility: undefined, is_public: true },
      ])

      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getByTestId('report-visibility')).toHaveTextContent(
          'Öffentlich'
        )
      })
    })

    it('shows an intro line', async () => {
      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getByText(/Veröffentlichte Evaluationsberichte/)).toBeInTheDocument()
      })
    })
  })

  describe('Navigation', () => {
    it('cards link to the report detail page', async () => {
      mockList.mockResolvedValue(mockReports)

      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getByTestId('report-card-report-1')).toBeInTheDocument()
      })
      expect(screen.getByTestId('report-card-report-1')).toHaveAttribute(
        'href',
        '/reports/report-1'
      )
      expect(screen.getByTestId('report-card-report-2')).toHaveAttribute(
        'href',
        '/reports/report-2'
      )
    })
  })

  describe('Error Handling', () => {
    it('shows the error card (German message + detail) with an "Erneut laden" button', async () => {
      mockList.mockRejectedValue(new Error('Internal Server Error'))

      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getByTestId('reports-error')).toBeInTheDocument()
      })
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Failed to load reports'
      )
      expect(screen.getByText('Internal Server Error')).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'Erneut laden' })
      ).toBeInTheDocument()
      // Chrome stays
      expect(
        screen.getByRole('heading', { level: 1, name: 'Reports' })
      ).toBeInTheDocument()
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
    })

    it('does not duplicate the generic message when the error has none', async () => {
      mockList.mockRejectedValue({})

      render(<ReportsPage />)

      await waitFor(() => {
        expect(screen.getByTestId('reports-error')).toBeInTheDocument()
      })
      expect(screen.getAllByText('Failed to load reports')).toHaveLength(1)
    })

    it('reloads on button click', async () => {
      mockList
        .mockRejectedValueOnce(new Error('Error'))
        .mockResolvedValueOnce([])

      render(<ReportsPage />)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: 'Erneut laden' })
        ).toBeInTheDocument()
      })

      await userEvent.click(screen.getByRole('button', { name: 'Erneut laden' }))

      await waitFor(() => {
        expect(mockList).toHaveBeenCalledTimes(2)
      })
      expect(screen.getByTestId('reports-empty')).toBeInTheDocument()
    })
  })
})
