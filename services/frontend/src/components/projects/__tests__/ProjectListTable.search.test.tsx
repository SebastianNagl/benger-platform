/**
 * @jest-environment jsdom
 */

import { useProjectStore } from '@/stores/projectStore'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

jest.mock('@/hooks/useDialogs', () => ({
  useConfirm: () => jest.fn(),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: jest.fn(),
  }),
}))

// Mock i18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'projects.searchPlaceholder': 'Search projects...',
        'projects.noProjects': 'No projects found',
        'projects.loading': 'Loading projects...',
      }
      return translations[key] || key
    },
    currentLanguage: 'en',
  }),
}))
jest.mock('@/components/shared/FilterToolbar', () => {
  const FilterToolbar = ({
    searchValue,
    onSearchChange,
    searchPlaceholder,
    searchLabel,
    clearLabel = 'Clear filters',
    onClearFilters,
    hasActiveFilters,
    leftExtras,
    rightExtras,
    children,
  }: any) => (
    <div data-testid="filter-toolbar">
      {leftExtras}
      {onSearchChange && (
        <input
          data-testid="filter-toolbar-search"
          type="search"
          placeholder={searchPlaceholder}
          title={searchPlaceholder || searchLabel}
          value={searchValue ?? ''}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      )}
      <div data-testid="filter-toolbar-fields">{children}</div>
      {onClearFilters && (
        <button
          data-testid="filter-toolbar-clear"
          onClick={onClearFilters}
          disabled={!hasActiveFilters}
          title={clearLabel}
          aria-label={clearLabel}
        />
      )}
      {rightExtras}
    </div>
  )
  FilterToolbar.Field = ({ children }: any) => <div>{children}</div>
  return { FilterToolbar }
})


describe('ProjectListTable Search Functionality', () => {
  const mockFetchProjects = jest.fn()
  const mockSetSearchQuery = jest.fn()
  const mockSetCurrentPage = jest.fn()
  const mockSetPageSize = jest.fn()

  const defaultStoreState = {
    projects: [],
    loading: false,
    fetchProjects: mockFetchProjects,
    setSearchQuery: mockSetSearchQuery,
    searchQuery: '',
    currentPage: 1,
    pageSize: 10,
    totalProjects: 0,
    totalPages: 0,
    setCurrentPage: mockSetCurrentPage,
    setPageSize: mockSetPageSize,
  }

  beforeEach(() => {
    jest.clearAllMocks()

    // Mock shared components to prevent import errors
    jest.mock('@/components/shared', () => {
      const React = require('react')
      return {
        HeroPattern: () =>
          React.createElement(
            'div',
            { 'data-testid': 'hero-pattern' },
            'Hero Pattern'
          )('div', { 'data-testid': 'hero-pattern' }, 'Hero Pattern'),
        GridPattern: () =>
          React.createElement(
            'div',
            { 'data-testid': 'grid-pattern' },
            'Grid Pattern'
          )('div', { 'data-testid': 'grid-pattern' }, 'Grid Pattern'),
        Button: ({ children, ...props }) =>
          React.createElement('button', props, children),
        ResponsiveContainer: ({ children }) =>
          React.createElement('div', null, children),
        LoadingSpinner: () =>
          React.createElement(
            'div',
            { 'data-testid': 'loading-spinner' },
            'Loading...'
          )('div', null, 'Loading...'),
        EmptyState: ({ message }) => React.createElement('div', null, message),
        Spinner: () => React.createElement('div', null, 'Loading...'),
        // Add other exports as needed
      }
    })
    ;(useRouter as jest.Mock).mockReturnValue({
      push: jest.fn(),
    })
    ;(useProjectStore as unknown as jest.Mock).mockReturnValue(
      defaultStoreState
    )
  })

  describe('Search Input Rendering', () => {
    it('should render search input with correct placeholder', async () => {
      render(<ProjectListTable />)

      const searchInput = screen.getByTestId('filter-toolbar-search')
      expect(searchInput).toBeInTheDocument()
      expect(searchInput).toHaveAttribute('placeholder', 'Search projects...')
    })

    it('should have search icon visible', async () => {
      const { container } = render(<ProjectListTable />)

      const searchIcon = container.querySelector('svg')
      expect(searchIcon).toBeInTheDocument()
    })
  })

  describe('Search Functionality', () => {
    it('should update search query on input', async () => {
      jest.useFakeTimers()
      render(<ProjectListTable />)

      const searchInput = screen.getByTestId('filter-toolbar-search')
      fireEvent.change(searchInput, { target: { value: 'test project' } })

      // The SearchInput component in ProjectListTable has debounceMs={0}
      // So it should call immediately
      await waitFor(() => {
        expect(searchInput).toHaveValue('test project')
      })

      jest.useRealTimers()
    })

    it('should debounce search query updates to store', async () => {
      jest.useFakeTimers()
      render(<ProjectListTable />)

      const searchInput = screen.getByTestId('filter-toolbar-search')

      // Type in the search box
      fireEvent.change(searchInput, { target: { value: 'project 1' } })

      // The local state updates immediately (debounceMs=0 for SearchInput)
      // But ProjectListTable has its own 300ms debounce for the store update
      expect(mockSetSearchQuery).not.toHaveBeenCalled()

      // Advance timers by 299ms
      jest.advanceTimersByTime(299)
      expect(mockSetSearchQuery).not.toHaveBeenCalled()

      // Advance by 1 more ms (total 300ms)
      jest.advanceTimersByTime(1)
      expect(mockSetSearchQuery).toHaveBeenCalledWith('project 1')

      jest.useRealTimers()
    })

    it('should handle rapid typing correctly', async () => {
      jest.useFakeTimers()
      render(<ProjectListTable />)

      const searchInput = screen.getByTestId('filter-toolbar-search')

      // Simulate rapid typing
      fireEvent.change(searchInput, { target: { value: 'p' } })
      jest.advanceTimersByTime(100)

      fireEvent.change(searchInput, { target: { value: 'pr' } })
      jest.advanceTimersByTime(100)

      fireEvent.change(searchInput, { target: { value: 'pro' } })
      jest.advanceTimersByTime(100)

      fireEvent.change(searchInput, { target: { value: 'proj' } })

      // Should not have called setSearchQuery yet
      expect(mockSetSearchQuery).not.toHaveBeenCalled()

      // Wait for the debounce to complete
      jest.advanceTimersByTime(300)

      // Should only be called once with the final value
      expect(mockSetSearchQuery).toHaveBeenCalledTimes(1)
      expect(mockSetSearchQuery).toHaveBeenCalledWith('proj')

      jest.useRealTimers()
    })

    it('should clear search when input is emptied', async () => {
      jest.useFakeTimers()
      render(<ProjectListTable />)

      const searchInput = screen.getByTestId('filter-toolbar-search')

      // First set a search value
      fireEvent.change(searchInput, { target: { value: 'test' } })
      jest.advanceTimersByTime(300)
      expect(mockSetSearchQuery).toHaveBeenCalledWith('test')

      // Clear the search
      fireEvent.change(searchInput, { target: { value: '' } })
      jest.advanceTimersByTime(300)
      expect(mockSetSearchQuery).toHaveBeenCalledWith('')

      jest.useRealTimers()
    })

    it('should trigger fetchProjects when search query changes', async () => {
      jest.useFakeTimers()

      // Start with a search query
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        searchQuery: 'initial',
      })

      const { rerender } = render(<ProjectListTable />)

      // Verify initial fetch
      expect(mockFetchProjects).toHaveBeenCalledWith(
        undefined,
        undefined,
        false
      )

      // Clear mock to track new calls
      mockFetchProjects.mockClear()

      // Update search query to empty
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        searchQuery: '',
      })

      rerender(<ProjectListTable />)

      // Should trigger fetchProjects when searchQuery changes
      expect(mockFetchProjects).toHaveBeenCalledWith(
        undefined,
        undefined,
        false
      )

      jest.useRealTimers()
    })

    it('should auto-refresh project list when search is cleared', async () => {
      jest.useFakeTimers()

      // Mock projects that will be filtered
      const allProjects = [
        {
          id: '1',
          title: 'Legal Analysis Project',
          created_at: '2024-01-01T00:00:00Z',
          task_count: 10,
          annotation_count: 5,
          progress: 50,
        },
        {
          id: '2',
          title: 'Test Project',
          created_at: '2024-01-02T00:00:00Z',
          task_count: 20,
          annotation_count: 20,
          progress: 100,
        },
      ]

      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: allProjects,
        searchQuery: '',
      })

      render(<ProjectListTable />)

      const searchInput = screen.getByTestId('filter-toolbar-search')

      // Type in search to filter projects
      fireEvent.change(searchInput, { target: { value: 'Test' } })

      // Wait for debounce
      jest.advanceTimersByTime(300)

      // Verify search query was set
      expect(mockSetSearchQuery).toHaveBeenCalledWith('Test')

      // Clear the search field
      fireEvent.change(searchInput, { target: { value: '' } })

      // Wait for debounce
      jest.advanceTimersByTime(300)

      // Verify search query was cleared
      expect(mockSetSearchQuery).toHaveBeenCalledWith('')

      // Verify fetchProjects was called to refresh the list
      expect(mockFetchProjects).toHaveBeenCalled()

      jest.useRealTimers()
    })

    it('should preserve search value when switching between archived and active projects', () => {
      const { rerender } = render(<ProjectListTable showArchivedOnly={false} />)

      const searchInput = screen.getByTestId('filter-toolbar-search')
      fireEvent.change(searchInput, { target: { value: 'archived test' } })

      // Switch to archived view
      rerender(<ProjectListTable showArchivedOnly={true} />)

      // Search value should still be present
      const updatedInput = screen.getByTestId('filter-toolbar-search')
      expect(updatedInput).toHaveValue('archived test')
    })
  })

  describe('Search with Project Data', () => {
    const mockProjects = [
      {
        id: '1',
        title: 'Legal Analysis Project',
        created_at: '2024-01-01T00:00:00Z',
        task_count: 10,
        annotation_count: 5,
        progress: 50,
      },
      {
        id: '2',
        title: 'Contract Review',
        created_at: '2024-01-02T00:00:00Z',
        task_count: 20,
        annotation_count: 20,
        progress: 100,
      },
      {
        id: '3',
        title: 'Document Classification',
        created_at: '2024-01-03T00:00:00Z',
        task_count: 15,
        annotation_count: 0,
        progress: 0,
      },
    ]

    it('should display projects when not searching', () => {
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
        ...defaultStoreState,
        projects: mockProjects,
      })

      render(<ProjectListTable />)

      expect(screen.getByText('Legal Analysis Project')).toBeInTheDocument()
      expect(screen.getByText('Contract Review')).toBeInTheDocument()
      expect(screen.getByText('Document Classification')).toBeInTheDocument()
    })

    it('should trigger fetchProjects on mount', () => {
      render(<ProjectListTable />)
      expect(mockFetchProjects).toHaveBeenCalledWith(
        undefined,
        undefined,
        false
      )
    })

    it('should trigger fetchProjects with archived flag when showing archived', () => {
      render(<ProjectListTable showArchivedOnly={true} />)
      expect(mockFetchProjects).toHaveBeenCalledWith(undefined, undefined, true)
    })
  })

  describe('Search Input Wiring', () => {
    it('should render a search-typed input', () => {
      render(<ProjectListTable />)

      const searchInput = screen.getByTestId('filter-toolbar-search')
      expect(searchInput).toBeInTheDocument()
      expect(searchInput).toHaveAttribute('type', 'search')
    })
  })

  describe('Accessibility', () => {
    it('should have accessible search input', () => {
      render(<ProjectListTable />)

      const searchInput = screen.getByTestId('filter-toolbar-search')

      // Check for search type
      expect(searchInput).toHaveAttribute('type', 'search')

      // Check for placeholder
      expect(searchInput).toHaveAttribute('placeholder', 'Search projects...')

      // Should be focusable
      searchInput.focus()
      expect(searchInput).toHaveFocus()
    })

    it('should support keyboard navigation', () => {
      render(<ProjectListTable />)

      const searchInput = screen.getByTestId('filter-toolbar-search')

      // Tab to focus
      searchInput.focus()
      expect(searchInput).toHaveFocus()

      // Type in the field
      fireEvent.change(searchInput, { target: { value: 'keyboard test' } })
      expect(searchInput).toHaveValue('keyboard test')
    })
  })
})
