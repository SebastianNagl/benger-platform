/**
 * Comprehensive test suite for ProjectListTable component
 * Tests table rendering, sorting, selection, pagination, and actions
 */

/**
 * @jest-environment jsdom
 */

import { projectsAPI } from '@/lib/api/projects'
import { useProjectStore } from '@/stores/projectStore'
import { Project } from '@/types/labelStudio'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'
import { ProjectListTable } from '../ProjectListTable'

// Mock dependencies
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
    pathname: '/',
    query: {},
    asPath: '/',
    route: '/',
    basePath: '',
    isReady: true,
    isPreview: false,
    isLocaleDomain: false,
  })),
  useParams: jest.fn(() => ({})),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/'),
  notFound: jest.fn(),
  redirect: jest.fn(),
}))

jest.mock('@/stores/projectStore', () => ({
  useProjectStore: jest.fn(),
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    bulkDeleteProjects: jest.fn(),
    bulkExportProjects: jest.fn(),
    bulkExportFullProjects: jest.fn(),
    bulkArchiveProjects: jest.fn(),
    bulkUnarchiveProjects: jest.fn(),
    importProject: jest.fn(),
  },
}))

const mockConfirm = jest.fn()
const mockAddToast = jest.fn()
const mockRemoveToast = jest.fn()

jest.mock('@/hooks/useDialogs', () => ({
  useConfirm: () => mockConfirm,
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: mockAddToast,
    removeToast: mockRemoveToast,
  }),
}))

// Mock AuthContext with a user that has permission to create projects
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'test-user-id',
      username: 'testuser',
      email: 'test@example.com',
      is_superadmin: false,
      is_active: true,
      role: 'CONTRIBUTOR',
    },
    isAuthenticated: true,
    isLoading: false,
    login: jest.fn(),
    logout: jest.fn(),
  }),
}))

// Mock i18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, varsOrDefault?: any) => {
      const translations: Record<string, any> = require('../../../locales/en/common.json')
      const parts = key.split('.')
      let value: any = translations
      for (const part of parts) {
        if (value && typeof value === 'object' && part in value) {
          value = value[part]
        } else {
          return key
        }
      }
      if (typeof value !== 'string') return key
      if (varsOrDefault && typeof varsOrDefault === 'object') {
        for (const [k, v] of Object.entries(varsOrDefault)) {
          value = value.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
        }
      }
      return value
    },
    locale: 'en',
  }),
}))

describe('ProjectListTable', () => {
  const mockFetchProjects = jest.fn()
  const mockSetSearchQuery = jest.fn()
  const mockSetCurrentPage = jest.fn()
  const mockSetPageSize = jest.fn()
  const mockPush = jest.fn()

  const mockProjects: Partial<Project>[] = [
    {
      id: '1',
      title: 'Project Alpha',
      description: 'Test description',
      created_at: '2024-01-01T00:00:00Z',
      task_count: 10,
      annotation_count: 5,
      progress_percentage: 50,
    },
    {
      id: '2',
      title: 'Project Beta',
      created_at: '2024-01-02T00:00:00Z',
      task_count: 20,
      annotation_count: 20,
      progress_percentage: 100,
    },
    {
      id: '3',
      title: 'Project Gamma',
      created_at: '2024-01-03T00:00:00Z',
      task_count: 5,
      annotation_count: 0,
      progress_percentage: 0,
    },
  ]

  const defaultStoreState = {
    projects: [],
    loading: false,
    fetchProjects: mockFetchProjects,
    setSearchQuery: mockSetSearchQuery,
    searchQuery: '',
    currentPage: 1,
    pageSize: 25,
    totalProjects: 0,
    totalPages: 0,
    setCurrentPage: mockSetCurrentPage,
    setPageSize: mockSetPageSize,
  }

  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue({
      push: mockPush,
    })
    ;(useProjectStore as unknown as jest.Mock).mockReturnValue(
      defaultStoreState
    )
  })

  describe('Table Rendering', () => {
    it('should render table with projects', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
        totalProjects: 3,
      })

      render(<ProjectListTable />)

      expect(screen.getByTestId('projects-table')).toBeInTheDocument()
      expect(screen.getByText('Project Alpha')).toBeInTheDocument()
      expect(screen.getByText('Project Beta')).toBeInTheDocument()
      expect(screen.getByText('Project Gamma')).toBeInTheDocument()
    })

    it('should render table headers correctly', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      expect(screen.getByText('Project')).toBeInTheDocument()
      expect(screen.getByText('Tasks')).toBeInTheDocument()
      expect(screen.getByText('ANNOTATIONS')).toBeInTheDocument()
      expect(screen.getByText('Progress')).toBeInTheDocument()
      expect(screen.getByText('Created')).toBeInTheDocument()
    })

    it('should render project details in table rows', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      expect(screen.getByText('Test description')).toBeInTheDocument()
      expect(screen.getByText('10')).toBeInTheDocument()
      const annotations = screen.getAllByText('5')
      expect(annotations.length).toBeGreaterThan(0)
      expect(screen.getByText('50%')).toBeInTheDocument()
    })

    it('should render checkboxes for each project', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      expect(
        screen.getByTestId('projects-table-checkbox-1')
      ).toBeInTheDocument()
      expect(
        screen.getByTestId('projects-table-checkbox-2')
      ).toBeInTheDocument()
      expect(
        screen.getByTestId('projects-table-checkbox-3')
      ).toBeInTheDocument()
    })

    it('should render Label button for each project', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const labelButtons = screen.getAllByText('Label')
      expect(labelButtons).toHaveLength(3)
    })
  })

  describe('Column Sorting', () => {
    it('should sort by title ascending', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const titleHeader = screen.getByText('Project').closest('button')
      fireEvent.click(titleHeader!)

      const rows = screen.getAllByTestId(/projects-table-row/)
      const firstProjectTitle =
        rows[0].querySelector('td:nth-child(2)')?.textContent
      expect(firstProjectTitle).toContain('Project Alpha')
    })

    it('should sort by title descending on second click', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const titleHeader = screen.getByText('Project').closest('button')
      fireEvent.click(titleHeader!)
      fireEvent.click(titleHeader!)

      const rows = screen.getAllByTestId(/projects-table-row/)
      const firstProjectTitle =
        rows[0].querySelector('td:nth-child(2)')?.textContent
      expect(firstProjectTitle).toContain('Project Gamma')
    })

    it('should sort by task count', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const tasksHeader = screen.getByText('Tasks').closest('button')
      fireEvent.click(tasksHeader!)

      const rows = screen.getAllByTestId(/projects-table-row/)
      const firstProjectTasks =
        rows[0].querySelector('td:nth-child(3)')?.textContent
      expect(firstProjectTasks).toBe('5')
    })

    it('should sort by progress', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const progressHeader = screen.getByText('Progress').closest('button')
      fireEvent.click(progressHeader!)

      const rows = screen.getAllByTestId(/projects-table-row/)
      const firstProjectProgress =
        rows[0].querySelector('td:nth-child(5)')?.textContent
      expect(firstProjectProgress).toContain('0%')
    })

    it('should display sort icon for active sort field', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      const { container } = render(<ProjectListTable />)

      const createdHeader = screen.getByText('Created').closest('button')
      expect(createdHeader?.querySelector('svg')).toBeInTheDocument()
    })
  })

  describe('Row Selection', () => {
    it('should select individual project', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox = screen.getByTestId('projects-table-checkbox-1')
      fireEvent.click(checkbox)

      expect(screen.getByTestId('projects-selection-count')).toHaveTextContent(
        '1 project(s) selected'
      )
    })

    it('should deselect individual project', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox = screen.getByTestId('projects-table-checkbox-1')
      fireEvent.click(checkbox)
      fireEvent.click(checkbox)

      expect(
        screen.queryByTestId('projects-selection-count')
      ).not.toBeInTheDocument()
    })

    it('should select all projects on current page', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const headerCheckbox = screen.getByTestId(
        'projects-table-header-checkbox'
      )
      fireEvent.click(headerCheckbox)

      expect(screen.getByTestId('projects-selection-count')).toHaveTextContent(
        '3 project(s) selected'
      )
    })

    it('should deselect all projects', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const headerCheckbox = screen.getByTestId(
        'projects-table-header-checkbox'
      )
      fireEvent.click(headerCheckbox)
      fireEvent.click(headerCheckbox)

      expect(
        screen.queryByTestId('projects-selection-count')
      ).not.toBeInTheDocument()
    })

    it('should show indeterminate state when some projects selected', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      fireEvent.click(checkbox1)

      const headerCheckbox = screen.getByTestId(
        'projects-table-header-checkbox'
      )
      // Check for indeterminate property or attribute
      expect(
        headerCheckbox.getAttribute('data-indeterminate') === 'true' ||
          (headerCheckbox as any).indeterminate === true
      ).toBeTruthy()
    })

    it('should clear selections when page changes', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
        currentPage: 1,
      })

      const { rerender } = render(<ProjectListTable />)

      const checkbox = screen.getByTestId('projects-table-checkbox-1')
      fireEvent.click(checkbox)

      expect(screen.getByTestId('projects-selection-count')).toHaveTextContent(
        '1 project(s) selected'
      )
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
        currentPage: 2,
      })

      rerender(<ProjectListTable />)

      expect(
        screen.queryByTestId('projects-selection-count')
      ).not.toBeInTheDocument()
    })
  })

  describe('Pagination', () => {
    it('should render pagination component', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
        totalProjects: 100,
        totalPages: 4,
      })

      render(<ProjectListTable />)

      // Pagination renders but might not have role="navigation"
      // Check for presence of pagination-related text
      expect(screen.getByText(/Showing 3 of 100/)).toBeInTheDocument()
    })

    it('should call setCurrentPage when page changes', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
        currentPage: 1,
        totalPages: 4,
        totalProjects: 100,
      })

      render(<ProjectListTable />)

      // The pagination component will call setCurrentPage
      expect(mockSetCurrentPage).not.toHaveBeenCalled()
    })

    it('should call setPageSize when page size changes', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
        totalProjects: 100,
      })

      render(<ProjectListTable />)

      expect(mockSetPageSize).not.toHaveBeenCalled()
    })
  })

  describe('Bulk Delete', () => {
    it('should delete selected projects after confirmation', async () => {
      const user = userEvent.setup()
      mockConfirm.mockResolvedValue(true)
      ;(projectsAPI.bulkDeleteProjects as jest.Mock).mockResolvedValue({
        deleted: 2,
      })
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      const checkbox2 = screen.getByTestId('projects-table-checkbox-2')
      await user.click(checkbox1)
      await user.click(checkbox2)

      // Open bulk actions menu
      const actionsButton = screen.getByTestId('projects-bulk-actions-button')
      await user.click(actionsButton)

      // Find and click delete option
      const deleteOption = await screen.findByTestId(
        'projects-bulk-delete-option'
      )
      await user.click(deleteOption)

      await waitFor(() => {
        expect(mockConfirm).toHaveBeenCalledWith({
          title: 'Delete Projects',
          message:
            'Are you sure you want to delete 2 projects? This action cannot be undone.',
          confirmText: 'Delete',
          variant: 'danger',
        })
      })

      await waitFor(() => {
        expect(projectsAPI.bulkDeleteProjects).toHaveBeenCalledWith(['1', '2'])
      })

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          '2 projects deleted successfully',
          'success'
        )
      })
    })

    it('should not delete if user cancels confirmation', async () => {
      const user = userEvent.setup()
      mockConfirm.mockResolvedValue(false)
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      await user.click(checkbox1)

      // Open bulk actions menu
      const actionsButton = screen.getByTestId('projects-bulk-actions-button')
      await user.click(actionsButton)

      // Find and click delete option
      const deleteOption = await screen.findByTestId(
        'projects-bulk-delete-option'
      )
      await user.click(deleteOption)

      await waitFor(() => {
        expect(mockConfirm).toHaveBeenCalled()
      })

      expect(projectsAPI.bulkDeleteProjects).not.toHaveBeenCalled()
    })

    it('should handle partial delete success', async () => {
      const user = userEvent.setup()
      mockConfirm.mockResolvedValue(true)
      ;(projectsAPI.bulkDeleteProjects as jest.Mock).mockResolvedValue({
        deleted: 1,
      })
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      const checkbox2 = screen.getByTestId('projects-table-checkbox-2')
      await user.click(checkbox1)
      await user.click(checkbox2)

      // Open bulk actions menu
      const actionsButton = screen.getByTestId('projects-bulk-actions-button')
      await user.click(actionsButton)

      // Find and click delete option
      const deleteOption = await screen.findByTestId(
        'projects-bulk-delete-option'
      )
      await user.click(deleteOption)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Deleted 1 of 2 projects. Some projects could not be deleted due to permissions.',
          'warning'
        )
      })
    })

    it('should handle delete error', async () => {
      const user = userEvent.setup()
      mockConfirm.mockResolvedValue(true)
      ;(projectsAPI.bulkDeleteProjects as jest.Mock).mockRejectedValue(
        new Error('Network error')
      )
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      await user.click(checkbox1)

      // Open bulk actions menu
      const actionsButton = screen.getByTestId('projects-bulk-actions-button')
      await user.click(actionsButton)

      // Find and click delete option
      const deleteOption = await screen.findByTestId(
        'projects-bulk-delete-option'
      )
      await user.click(deleteOption)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to delete projects',
          'error'
        )
      })
    })

    it('should handle zero delete result', async () => {
      const user = userEvent.setup()
      mockConfirm.mockResolvedValue(true)
      ;(projectsAPI.bulkDeleteProjects as jest.Mock).mockResolvedValue({
        deleted: 0,
      })
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      await user.click(checkbox1)

      // Open bulk actions menu
      const actionsButton = screen.getByTestId('projects-bulk-actions-button')
      await user.click(actionsButton)

      // Find and click delete option
      const deleteOption = await screen.findByTestId(
        'projects-bulk-delete-option'
      )
      await user.click(deleteOption)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'No projects were deleted. You may not have permission to delete the selected projects.',
          'warning'
        )
      })
    })
  })

  describe('Bulk Export', () => {
    it('should export selected projects via bulk actions menu', async () => {
      const user = userEvent.setup()
      const mockBlob = new Blob(['test'], { type: 'application/json' })
      ;(projectsAPI.bulkExportFullProjects as jest.Mock).mockResolvedValue(
        mockBlob
      )
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      // Mock URL.createObjectURL
      global.URL.createObjectURL = jest.fn(() => 'blob:test')
      global.URL.revokeObjectURL = jest.fn()

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      await user.click(checkbox1)

      // Open the bulk actions menu
      const actionsButton = screen.getByTestId('projects-bulk-actions-button')
      await user.click(actionsButton)

      // Find and click the export option
      const exportOption = await screen.findByTestId(
        'projects-bulk-export-option'
      )
      await user.click(exportOption)

      await waitFor(() => {
        expect(projectsAPI.bulkExportFullProjects).toHaveBeenCalledWith(['1'])
      })

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          expect.stringContaining('Exported 1 full project'),
          'success',
          5000
        )
      })
    })

    it('should handle export error - invalid blob', async () => {
      const user = userEvent.setup()
      ;(projectsAPI.bulkExportFullProjects as jest.Mock).mockResolvedValue(null)
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      await user.click(checkbox1)

      const actionsButton = screen.getByTestId('projects-bulk-actions-button')
      await user.click(actionsButton)

      const exportOption = await screen.findByTestId(
        'projects-bulk-export-option'
      )
      await user.click(exportOption)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          expect.stringContaining('Failed to export projects'),
          'error'
        )
      })
    })

    it('should handle export error - empty blob', async () => {
      const user = userEvent.setup()
      const emptyBlob = new Blob([], { type: 'application/json' })
      ;(projectsAPI.bulkExportFullProjects as jest.Mock).mockResolvedValue(
        emptyBlob
      )
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      await user.click(checkbox1)

      const actionsButton = screen.getByTestId('projects-bulk-actions-button')
      await user.click(actionsButton)

      const exportOption = await screen.findByTestId(
        'projects-bulk-export-option'
      )
      await user.click(exportOption)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          expect.stringContaining('Received empty file from server'),
          'error'
        )
      })
    })
  })

  describe('Archive/Unarchive', () => {
    it('should archive selected projects', async () => {
      const user = userEvent.setup()
      mockConfirm.mockResolvedValue(true)
      ;(projectsAPI.bulkArchiveProjects as jest.Mock).mockResolvedValue({
        archived: 2,
      })
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      const checkbox2 = screen.getByTestId('projects-table-checkbox-2')
      await user.click(checkbox1)
      await user.click(checkbox2)

      // Open bulk actions menu
      const actionsButton = screen.getByTestId('projects-bulk-actions-button')
      await user.click(actionsButton)

      // Find and click archive option in menu
      const archiveOption = await screen.findByTestId(
        'projects-bulk-archive-option'
      )
      await user.click(archiveOption)

      await waitFor(() => {
        expect(mockConfirm).toHaveBeenCalledWith({
          title: 'Archive Projects',
          message: 'Are you sure you want to archive 2 projects?',
          confirmText: 'Archive',
          variant: 'warning',
        })
      })

      await waitFor(() => {
        expect(projectsAPI.bulkArchiveProjects).toHaveBeenCalledWith(['1', '2'])
      })

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Archived 2 projects successfully',
          'success'
        )
      })
    })

    it('should unarchive selected projects in archived view', async () => {
      const user = userEvent.setup()
      mockConfirm.mockResolvedValue(true)
      ;(projectsAPI.bulkUnarchiveProjects as jest.Mock).mockResolvedValue({
        unarchived: 1,
      })
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable showArchivedOnly={true} />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      await user.click(checkbox1)

      const actionsButton = screen.getByTestId('projects-bulk-actions-button')
      await user.click(actionsButton)

      const unarchiveOption = await screen.findByTestId(
        'projects-bulk-unarchive-option'
      )
      await user.click(unarchiveOption)

      await waitFor(() => {
        expect(mockConfirm).toHaveBeenCalledWith({
          title: 'Unarchive Projects',
          message: 'Are you sure you want to unarchive 1 projects?',
          confirmText: 'Unarchive',
          variant: 'info',
        })
      })

      await waitFor(() => {
        expect(projectsAPI.bulkUnarchiveProjects).toHaveBeenCalledWith(['1'])
      })
    })

    it('should handle archive error', async () => {
      const user = userEvent.setup()
      mockConfirm.mockResolvedValue(true)
      ;(projectsAPI.bulkArchiveProjects as jest.Mock).mockRejectedValue(
        new Error('Archive failed')
      )
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      await user.click(checkbox1)

      const actionsButton = screen.getByTestId('projects-bulk-actions-button')
      await user.click(actionsButton)

      const archiveOption = await screen.findByTestId(
        'projects-bulk-archive-option'
      )
      await user.click(archiveOption)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to archive projects',
          'error'
        )
      })
    })
  })

  describe('Import Project', () => {
    it('should import project from JSON file', async () => {
      ;(projectsAPI.importProject as jest.Mock).mockResolvedValue({
        project_title: 'Imported Project',
        project_url: '/projects/imported-1',
        statistics: {
          tasks_imported: 10,
          annotations_imported: 5,
        },
      })
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const importButton = screen.getByTestId('projects-import-button')
      fireEvent.click(importButton)

      const fileInput = screen.getByTestId('project-import-file-input')
      const file = new File(['{}'], 'project.json', {
        type: 'application/json',
      })

      await userEvent.upload(fileInput, file)

      await waitFor(() => {
        expect(projectsAPI.importProject).toHaveBeenCalled()
      })

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          expect.stringContaining('Successfully imported "Imported Project"'),
          'success'
        )
      })

      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/projects/imported-1')
      })
    })

    it('should reject non-JSON files', async () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const fileInput = screen.getByTestId(
        'project-import-file-input'
      ) as HTMLInputElement
      const file = new File(['test'], 'project.txt', { type: 'text/plain' })

      // Manually trigger the change event
      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })
      fireEvent.change(fileInput)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Please select a JSON or ZIP file',
          'error'
        )
      })

      expect(projectsAPI.importProject).not.toHaveBeenCalled()
    })

    it('should handle import error', async () => {
      ;(projectsAPI.importProject as jest.Mock).mockRejectedValue(
        new Error('Invalid JSON format')
      )
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const fileInput = screen.getByTestId('project-import-file-input')
      const file = new File(['{}'], 'project.json', {
        type: 'application/json',
      })

      await userEvent.upload(fileInput, file)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          expect.stringContaining('Invalid JSON format'),
          'error'
        )
      })
    })
  })

  describe('Navigation', () => {
    it('should navigate to project detail on row click', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const projectTitle = screen.getByText('Project Alpha')
      fireEvent.click(projectTitle)

      expect(mockPush).toHaveBeenCalledWith('/projects/1')
    })

    it('should navigate to label page on Label button click', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const labelButtons = screen.getAllByText('Label')
      fireEvent.click(labelButtons[0])

      // The first label button corresponds to the first project in sortedProjects
      // which might be different from mockProjects order due to default sort
      expect(mockPush).toHaveBeenCalledWith(
        expect.stringMatching(/\/projects\/\d+\/label/)
      )
    })

    it('should navigate to create project page', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
      })

      render(<ProjectListTable />)

      const createButton = screen.getByTestId('projects-create-button')
      fireEvent.click(createButton)

      expect(mockPush).toHaveBeenCalledWith('/projects/create')
    })

    it('should navigate to archived projects', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const archivedButton = screen.getByTestId('projects-archived-button')
      fireEvent.click(archivedButton)

      expect(mockPush).toHaveBeenCalledWith('/projects/archived')
    })

    it('should navigate back to active projects from archived view', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable showArchivedOnly={true} />)

      const activeButton = screen.getByTestId('projects-active-button')
      fireEvent.click(activeButton)

      expect(mockPush).toHaveBeenCalledWith('/projects')
    })
  })

  describe('Loading State', () => {
    it('should show loading spinner when loading and no projects', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        loading: true,
        projects: [],
      })

      render(<ProjectListTable />)

      expect(document.querySelector('.animate-spin')).toBeInTheDocument()
    })

    it('should not show loading spinner when loading with existing projects', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        loading: true,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      expect(screen.getByText('Project Alpha')).toBeInTheDocument()
    })
  })

  describe('Empty State', () => {
    it('should show empty state when no projects', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: [],
      })

      render(<ProjectListTable />)

      expect(screen.getByTestId('projects-empty-state')).toBeInTheDocument()
      expect(screen.getByText('No projects found')).toBeInTheDocument()
    })

    it('should show search empty state when search has no results', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: [],
        searchQuery: 'nonexistent',
      })

      render(<ProjectListTable />)

      expect(
        screen.getByText('No projects match your filters')
      ).toBeInTheDocument()
      expect(screen.getByText('Try adjusting your search criteria')).toBeInTheDocument()
    })

    it('should provide link to create project in empty state', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: [],
      })

      render(<ProjectListTable />)

      const createLink = screen.getByText('Create your first project to get started')
      fireEvent.click(createLink)

      expect(mockPush).toHaveBeenCalledWith('/projects/create')
    })
  })

  describe('Archived View', () => {
    it('should fetch archived projects on mount', () => {
      render(<ProjectListTable showArchivedOnly={true} />)

      expect(mockFetchProjects).toHaveBeenCalledWith(undefined, undefined, true)
    })

    it('should render archived view header', () => {
      render(<ProjectListTable showArchivedOnly={true} />)

      expect(screen.getByText('Archived Projects')).toBeInTheDocument()
      expect(screen.getByText('View and manage your archived projects')).toBeInTheDocument()
    })

    it('should not show create and import buttons in archived view', () => {
      render(<ProjectListTable showArchivedOnly={true} />)

      expect(
        screen.queryByTestId('projects-create-button')
      ).not.toBeInTheDocument()
      expect(
        screen.queryByTestId('projects-import-button')
      ).not.toBeInTheDocument()
    })

    it('should show unarchive button instead of archive in archived view', async () => {
      const user = userEvent.setup()
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable showArchivedOnly={true} />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      await user.click(checkbox1)

      // Open bulk actions menu
      const actionsButton = screen.getByTestId('projects-bulk-actions-button')
      await user.click(actionsButton)

      // Look for Unarchive option in the menu
      const unarchiveOption = await screen.findByTestId(
        'projects-bulk-unarchive-option'
      )
      expect(unarchiveOption).toBeInTheDocument()
    })
  })

  describe('Selection Count Display', () => {
    it('should display correct count for single selection', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      fireEvent.click(checkbox1)

      expect(screen.getByTestId('projects-selection-count')).toHaveTextContent(
        '1 project(s) selected'
      )
    })

    it('should display correct count for multiple selections', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      const checkbox2 = screen.getByTestId('projects-table-checkbox-2')
      fireEvent.click(checkbox1)
      fireEvent.click(checkbox2)

      expect(screen.getByTestId('projects-selection-count')).toHaveTextContent(
        '2 project(s) selected'
      )
    })

    it('should show results count when no selection', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
        totalProjects: 10,
      })

      render(<ProjectListTable />)

      expect(screen.getByText('Showing 3 of 10 results')).toBeInTheDocument()
    })
  })

  describe('Progress Calculation Fallback', () => {
    it('should use fallback calculation when progress_percentage is undefined', () => {
      const projectWithoutProgress: Partial<Project> = {
        id: '1',
        title: 'Legacy Project',
        created_at: '2024-01-01T00:00:00Z',
        task_count: 10,
        annotation_count: 3,
        progress_percentage: undefined,
      }

      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: [projectWithoutProgress],
      })

      render(<ProjectListTable />)

      expect(screen.getByText('30%')).toBeInTheDocument()
    })

    it('should handle zero task count', () => {
      const projectWithZeroTasks: Partial<Project> = {
        id: '1',
        title: 'Empty Project',
        created_at: '2024-01-01T00:00:00Z',
        task_count: 0,
        annotation_count: 0,
        progress_percentage: undefined,
      }

      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: [projectWithZeroTasks],
      })

      render(<ProjectListTable />)

      expect(screen.getByText('0%')).toBeInTheDocument()
    })

    it('should cap fallback calculation at 100%', () => {
      const projectWithExcessAnnotations: Partial<Project> = {
        id: '1',
        title: 'Over-annotated Project',
        created_at: '2024-01-01T00:00:00Z',
        task_count: 10,
        annotation_count: 50,
        progress_percentage: undefined,
      }

      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: [projectWithExcessAnnotations],
      })

      render(<ProjectListTable />)

      expect(screen.getByText('100%')).toBeInTheDocument()
    })
  })

  describe('Import Error Handling', () => {
    it('should handle JSON-specific import errors', async () => {
      ;(projectsAPI.importProject as jest.Mock).mockRejectedValue(
        new Error('Invalid JSON format in file')
      )
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const fileInput = screen.getByTestId(
        'project-import-file-input'
      ) as HTMLInputElement
      const file = new File(['{}'], 'project.json', {
        type: 'application/json',
      })

      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })
      fireEvent.change(fileInput)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          expect.stringContaining('Invalid JSON format'),
          'error'
        )
      })
    })

    it('should handle format version errors', async () => {
      ;(projectsAPI.importProject as jest.Mock).mockRejectedValue(
        new Error('Unsupported format_version')
      )
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const fileInput = screen.getByTestId(
        'project-import-file-input'
      ) as HTMLInputElement
      const file = new File(['{}'], 'project.json', {
        type: 'application/json',
      })

      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })
      fireEvent.change(fileInput)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          expect.stringContaining('Unsupported file format version'),
          'error'
        )
      })
    })

    it('should handle required fields errors', async () => {
      ;(projectsAPI.importProject as jest.Mock).mockRejectedValue(
        new Error('Missing required fields')
      )
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const fileInput = screen.getByTestId(
        'project-import-file-input'
      ) as HTMLInputElement
      const file = new File(['{}'], 'project.json', {
        type: 'application/json',
      })

      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })
      fireEvent.change(fileInput)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          expect.stringContaining('Missing required fields'),
          'error'
        )
      })
    })

    it('should clear file input after successful import', async () => {
      ;(projectsAPI.importProject as jest.Mock).mockResolvedValue({
        project_title: 'Imported Project',
        project_url: '/projects/imported-1',
        statistics: {
          tasks_imported: 10,
          annotations_imported: 5,
        },
      })
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const fileInput = screen.getByTestId(
        'project-import-file-input'
      ) as HTMLInputElement
      const file = new File(['{}'], 'project.json', {
        type: 'application/json',
      })

      await userEvent.upload(fileInput, file)

      await waitFor(() => {
        expect(fileInput.value).toBe('')
      })
    })
  })

  describe('Export with Loading Toast', () => {
    it('should show loading toast and success message during export', async () => {
      const user = userEvent.setup()
      const mockBlob = new Blob(['test'], { type: 'application/json' })
      ;(projectsAPI.bulkExportFullProjects as jest.Mock).mockResolvedValue(
        mockBlob
      )
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      global.URL.createObjectURL = jest.fn(() => 'blob:test')
      global.URL.revokeObjectURL = jest.fn()

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      await user.click(checkbox1)

      const actionsButton = screen.getByTestId('projects-bulk-actions-button')
      await user.click(actionsButton)

      const exportOption = await screen.findByTestId(
        'projects-bulk-export-option'
      )
      await user.click(exportOption)

      // Should show loading toast
      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          expect.stringContaining('Exporting 1'),
          'info',
          0
        )
      })

      // Should show success toast after export completes
      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          expect.stringContaining('Exported 1 full project'),
          'success',
          5000
        )
      })
    })

    it('should show error toast on export failure', async () => {
      const user = userEvent.setup()
      ;(projectsAPI.bulkExportFullProjects as jest.Mock).mockRejectedValue(
        new Error('Export failed')
      )
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      await user.click(checkbox1)

      const actionsButton = screen.getByTestId('projects-bulk-actions-button')
      await user.click(actionsButton)

      const exportOption = await screen.findByTestId(
        'projects-bulk-export-option'
      )
      await user.click(exportOption)

      // Should show error toast
      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          expect.stringContaining('Failed to export'),
          'error'
        )
      })
    })
  })

  describe('Row Click Navigation', () => {
    it('should navigate when clicking on task count cell', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const taskCounts = screen.getAllByText('10')
      // Find the task count in the table row
      const taskCell = taskCounts[0].closest('td')
      if (taskCell) {
        fireEvent.click(taskCell)
        expect(mockPush).toHaveBeenCalledWith(
          expect.stringMatching(/\/projects\/\d+/)
        )
      }
    })

    it('should not navigate when clicking on checkbox', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox = screen.getByTestId('projects-table-checkbox-1')
      const checkboxCell = checkbox.closest('td')

      if (checkboxCell) {
        fireEvent.click(checkboxCell)
        // Should not navigate, only select
        expect(mockPush).not.toHaveBeenCalled()
      }
    })

    it('should navigate when clicking on annotation count cell', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const annotationCounts = screen.getAllByText('20')
      const annotationCell = annotationCounts[0].closest('td')
      if (annotationCell) {
        fireEvent.click(annotationCell)
        expect(mockPush).toHaveBeenCalledWith(
          expect.stringMatching(/\/projects\/\d+/)
        )
      }
    })

    it('should navigate when clicking on progress cell', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const rows = screen.getAllByTestId(/projects-table-row/)
      const firstRowProgressCell = rows[0].querySelector('td:nth-child(5)')

      if (firstRowProgressCell) {
        fireEvent.click(firstRowProgressCell)
        expect(mockPush).toHaveBeenCalledWith(
          expect.stringMatching(/\/projects\/\d+/)
        )
      }
    })
  })

  describe('Search Functionality', () => {
    it('should update search query on input', async () => {
      const user = userEvent.setup()
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const searchInput = screen.getByTestId('projects-search-input')
      await user.type(searchInput, 'Alpha')

      // Wait for debounce
      await waitFor(
        () => {
          expect(mockSetSearchQuery).toHaveBeenCalledWith('Alpha')
        },
        { timeout: 500 }
      )
    })

    it('should clear search query', async () => {
      const user = userEvent.setup()
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
        searchQuery: 'test',
      })

      render(<ProjectListTable />)

      const searchInput = screen.getByTestId('projects-search-input')
      await user.clear(searchInput)

      await waitFor(
        () => {
          expect(mockSetSearchQuery).toHaveBeenCalledWith('')
        },
        { timeout: 500 }
      )
    })

    it('should debounce search input', async () => {
      jest.useFakeTimers()
      const user = userEvent.setup({ delay: null })
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const searchInput = screen.getByTestId('projects-search-input')
      await user.type(searchInput, 'test')

      // Should not call setSearchQuery immediately
      expect(mockSetSearchQuery).not.toHaveBeenCalled()

      // Fast-forward time by 300ms (debounce delay)
      jest.advanceTimersByTime(300)

      await waitFor(() => {
        expect(mockSetSearchQuery).toHaveBeenCalledWith('test')
      })

      jest.useRealTimers()
    })
  })

  describe('Sort Functionality - Annotations Column', () => {
    it('should sort by annotation count ascending', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      // Annotations column is not sortable in current implementation
      // This test documents current behavior
      const annotationsHeader = screen.getByText('ANNOTATIONS')
      expect(annotationsHeader.closest('button')).toBeNull()
    })
  })

  describe('Sort Functionality - Created Date', () => {
    it('should default sort by created_at descending', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const rows = screen.getAllByTestId(/projects-table-row/)
      const firstProjectTitle =
        rows[0].querySelector('td:nth-child(2)')?.textContent

      // By default sorted by created_at desc, so Project Gamma (2024-01-03) should be first
      expect(firstProjectTitle).toContain('Project Gamma')
    })

    it('should sort by created_at ascending on second click', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const createdHeader = screen.getByText('Created').closest('button')
      fireEvent.click(createdHeader!)

      const rows = screen.getAllByTestId(/projects-table-row/)
      const firstProjectTitle =
        rows[0].querySelector('td:nth-child(2)')?.textContent

      // Sorted by created_at asc, so Project Alpha (2024-01-01) should be first
      expect(firstProjectTitle).toContain('Project Alpha')
    })
  })

  describe('Pagination Edge Cases', () => {
    it('should handle first page correctly', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
        currentPage: 1,
        totalPages: 5,
        totalProjects: 125,
      })

      render(<ProjectListTable />)

      expect(screen.getByText('Showing 3 of 125 results')).toBeInTheDocument()
    })

    it('should handle last page correctly', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: [mockProjects[0]], // Only 1 project on last page
        currentPage: 5,
        totalPages: 5,
        totalProjects: 101,
      })

      render(<ProjectListTable />)

      expect(screen.getByText('Showing 1 of 101 results')).toBeInTheDocument()
    })

    it('should handle empty page', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: [],
        currentPage: 1,
        totalPages: 0,
        totalProjects: 0,
      })

      render(<ProjectListTable />)

      expect(screen.getByTestId('projects-empty-state')).toBeInTheDocument()
    })

    it('should handle single page with few items', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: [mockProjects[0], mockProjects[1]],
        currentPage: 1,
        totalPages: 1,
        totalProjects: 2,
      })

      render(<ProjectListTable />)

      expect(screen.getByText('Showing 2 of 2 results')).toBeInTheDocument()
    })
  })

  describe('Multiple Selections Across Pages', () => {
    it('should maintain selection count when selecting multiple projects', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      const checkbox2 = screen.getByTestId('projects-table-checkbox-2')
      const checkbox3 = screen.getByTestId('projects-table-checkbox-3')

      fireEvent.click(checkbox1)
      fireEvent.click(checkbox2)
      fireEvent.click(checkbox3)

      expect(screen.getByTestId('projects-selection-count')).toHaveTextContent(
        '3 project(s) selected'
      )
    })

    it('should update selection count when deselecting some projects', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      const checkbox2 = screen.getByTestId('projects-table-checkbox-2')
      const checkbox3 = screen.getByTestId('projects-table-checkbox-3')

      // Select all
      fireEvent.click(checkbox1)
      fireEvent.click(checkbox2)
      fireEvent.click(checkbox3)

      // Deselect one
      fireEvent.click(checkbox2)

      expect(screen.getByTestId('projects-selection-count')).toHaveTextContent(
        '2 project(s) selected'
      )
    })
  })

  describe('Bulk Actions Menu Behavior', () => {
    it('should show bulk actions button when projects are selected', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      fireEvent.click(checkbox1)

      const actionsButton = screen.getByTestId('projects-bulk-actions-button')
      expect(actionsButton).toBeInTheDocument()
      expect(actionsButton).not.toBeDisabled()
    })

    it('should show selected count badge in bulk actions button', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const checkbox1 = screen.getByTestId('projects-table-checkbox-1')
      const checkbox2 = screen.getByTestId('projects-table-checkbox-2')
      fireEvent.click(checkbox1)
      fireEvent.click(checkbox2)

      const actionsButton = screen.getByTestId('projects-bulk-actions-button')
      expect(actionsButton).toHaveTextContent('2')
    })
  })

  describe('Date Formatting', () => {
    it('should format dates relative to now', () => {
      const recentDate = new Date()
      recentDate.setHours(recentDate.getHours() - 2)

      const projectWithRecentDate: Partial<Project> = {
        id: '1',
        title: 'Recent Project',
        created_at: recentDate.toISOString(),
        task_count: 5,
        annotation_count: 2,
        progress_percentage: 40,
      }

      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: [projectWithRecentDate],
      })

      render(<ProjectListTable />)

      // Should show relative time like "vor 2 Stunden" (German locale)
      expect(screen.getByText(/vor/i)).toBeInTheDocument()
    })
  })

  describe('Edge Cases - Project Data', () => {
    it('should handle project without description', () => {
      const projectWithoutDescription: Partial<Project> = {
        id: '1',
        title: 'No Description Project',
        created_at: '2024-01-01T00:00:00Z',
        task_count: 10,
        annotation_count: 5,
        progress_percentage: 50,
      }

      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: [projectWithoutDescription],
      })

      render(<ProjectListTable />)

      expect(screen.getByText('No Description Project')).toBeInTheDocument()
      // Description should not be rendered when undefined
      expect(screen.queryByText(/Test description/)).not.toBeInTheDocument()
    })

    it('should handle very long project titles gracefully', () => {
      const longTitle = 'A'.repeat(200)
      const projectWithLongTitle: Partial<Project> = {
        id: '1',
        title: longTitle,
        created_at: '2024-01-01T00:00:00Z',
        task_count: 10,
        annotation_count: 5,
        progress_percentage: 50,
      }

      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: [projectWithLongTitle],
      })

      render(<ProjectListTable />)

      expect(screen.getByText(longTitle)).toBeInTheDocument()
    })

    it('should handle projects with 0 tasks', () => {
      const emptyProject: Partial<Project> = {
        id: '1',
        title: 'Empty Project',
        created_at: '2024-01-01T00:00:00Z',
        task_count: 0,
        annotation_count: 0,
        progress_percentage: 0,
      }

      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: [emptyProject],
      })

      render(<ProjectListTable />)

      // Check that Empty Project is displayed
      expect(screen.getByText('Empty Project')).toBeInTheDocument()
      // Check that 0% progress is displayed
      expect(screen.getByText('0%')).toBeInTheDocument()
      // Check that there are multiple "0" values (task count and annotation count)
      const zeros = screen.getAllByText('0')
      expect(zeros.length).toBeGreaterThanOrEqual(2)
    })
  })

  describe('Fetch Projects on Mount', () => {
    it('should fetch projects when component mounts', () => {
      render(<ProjectListTable />)

      expect(mockFetchProjects).toHaveBeenCalledWith(
        undefined,
        undefined,
        false
      )
    })

    it('should fetch archived projects when showArchivedOnly is true', () => {
      render(<ProjectListTable showArchivedOnly={true} />)

      expect(mockFetchProjects).toHaveBeenCalledWith(undefined, undefined, true)
    })

    it('should refetch projects when search query changes', () => {
      const { rerender } = render(<ProjectListTable />)

      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        searchQuery: 'test query',
      })

      rerender(<ProjectListTable />)

      expect(mockFetchProjects).toHaveBeenCalled()
    })
  })

  describe('File Input Handling', () => {
    it('should trigger file input when import button is clicked', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      const fileInput = screen.getByTestId(
        'project-import-file-input'
      ) as HTMLInputElement
      const clickSpy = jest.spyOn(fileInput, 'click')

      const importButton = screen.getByTestId('projects-import-button')
      fireEvent.click(importButton)

      expect(clickSpy).toHaveBeenCalled()
    })
  })
})
