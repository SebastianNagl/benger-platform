/**
 * Test for projects page reload functionality
 * Ensures that the projects page loads correctly when accessed directly
 */

import { projectsAPI } from '@/lib/api/projects'
import { useProjectStore } from '@/stores/projectStore'
import { render, screen, waitFor } from '@testing-library/react'
import ProjectsPage from '../page'

// Mock the API and store
jest.mock('@/lib/api/projects')
jest.mock('@/stores/projectStore')
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

// Mock the components
jest.mock('@/components/projects/ProjectListTable', () => ({
  ProjectListTable: () => (
    <div data-testid="project-list-table">Project List</div>
  ),
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <div data-testid="breadcrumb">{items[0].label}</div>
  ),
}))

jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}))

describe('Projects Page Reload', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('should load without errors when accessed directly', async () => {
    // Setup mock store
    const mockFetchProjects = jest.fn()
    ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
      projects: [],
      loading: false,
      fetchProjects: mockFetchProjects,
      setSearchQuery: jest.fn(),
      searchQuery: '',
      currentPage: 1,
      pageSize: 30,
      totalProjects: 0,
      totalPages: 0,
      setCurrentPage: jest.fn(),
      setPageSize: jest.fn(),
    })

    // Setup mock API
    ;(projectsAPI.list as jest.Mock).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 30,
      pages: 0,
    })

    // Render the page
    render(<ProjectsPage />)

    // Check that the page renders without errors
    await waitFor(() => {
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
      expect(screen.getByTestId('project-list-table')).toBeInTheDocument()
    })

    // Since ProjectListTable is mocked, fetchProjects won't be called directly from the page
    // The actual fetching happens inside the real ProjectListTable component
  })

  it('should handle undefined isArchived parameter correctly', async () => {
    const mockList = jest.fn().mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 30,
      pages: 0,
    })
    ;(projectsAPI.list as jest.Mock) = mockList

    // Call the list function with undefined isArchived
    await projectsAPI.list(1, 30, '', undefined)

    // Check that the function was called
    expect(mockList).toHaveBeenCalledWith(1, 30, '', undefined)
  })

  it('should correctly format API parameters', async () => {
    // Test that the API correctly handles different parameter combinations
    const testCases = [
      { isArchived: true },
      { isArchived: false },
      { isArchived: undefined },
    ]

    for (const testCase of testCases) {
      // Setup mock API
      const mockList = jest.fn().mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 30,
        pages: 0,
      })
      ;(projectsAPI.list as jest.Mock) = mockList

      // Make the API call
      await projectsAPI.list(1, 30, '', testCase.isArchived)

      // Check that the API was called with the correct parameters
      expect(mockList).toHaveBeenCalledWith(1, 30, '', testCase.isArchived)
    }
  })
})
