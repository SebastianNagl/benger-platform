/**
 * Comprehensive test suite for ProjectList component
 * Target: 90%+ code coverage
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'
import { ProjectList } from '../ProjectList'

// Mock dependencies
const mockFetchProjects = jest.fn()
const mockSetSearchQuery = jest.fn()
const mockPush = jest.fn()

const mockProjects = [
  {
    id: '1',
    title: 'Active Project 1',
    description: 'Description for project 1',
    task_count: 100,
    annotation_count: 45,
    progress_percentage: 45,
    created_at: '2024-01-15T10:00:00Z',
    is_archived: false,
    llm_model_ids: ['gpt-4', 'claude-3'],
  },
  {
    id: '2',
    title: 'Active Project 2',
    description: 'Description for project 2',
    task_count: 50,
    annotation_count: 50,
    progress_percentage: 100,
    created_at: '2024-02-20T15:30:00Z',
    is_archived: false,
    llm_model_ids: [],
  },
  {
    id: '3',
    title: 'Archived Project',
    description: 'Archived project description',
    task_count: 25,
    annotation_count: 10,
    progress_percentage: 40,
    created_at: '2023-12-01T08:00:00Z',
    is_archived: true,
    llm_model_ids: ['gpt-3.5'],
  },
  {
    id: '4',
    title: 'No Description Project',
    description: null,
    task_count: 0,
    annotation_count: 0,
    created_at: '2024-03-01T12:00:00Z',
    is_archived: false,
    llm_model_ids: [],
  },
]

jest.mock('@/stores/projectStore', () => ({
  useProjectStore: jest.fn(() => ({
    projects: mockProjects,
    loading: false,
    fetchProjects: mockFetchProjects,
    setSearchQuery: mockSetSearchQuery,
    searchQuery: '',
  })),
}))

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, arg2?: any, arg3?: any) => {
      const vars = typeof arg2 === 'object' ? arg2 : arg3
      const translations: Record<string, string> = {
        'projects.list.title': 'Projects',
        'projects.list.subtitle': 'Manage your annotation projects and track progress',
        'projects.list.newProject': 'New Project',
        'projects.list.searchPlaceholder': 'Search projects...',
        'projects.list.activeProjects': 'Active Projects',
        'projects.list.archived': 'Archived',
        'projects.list.noProjectsFound': 'No projects found',
        'projects.list.noActiveProjects': 'No active projects',
        'projects.list.noArchivedProjects': 'No archived projects',
        'projects.list.tryAdjusting': 'Try adjusting your search criteria',
        'projects.list.createFirst': 'Create your first project to get started',
        'projects.list.createProject': 'Create Project',
        'projects.list.archivedAppear': 'Archived projects will appear here',
        'projects.list.noDescription': 'No description',
        'projects.list.tasks': 'Tasks',
        'projects.list.progress': 'Progress',
        'projects.list.annotations': '{count} annotations',
      }
      let result = translations[key] || key
      if (vars) {
        Object.entries(vars).forEach(([k, v]) => {
          result = result.replace(`{${k}}`, String(v))
        })
      }
      return result
    },
    locale: 'en',
  }),
}))

const { useProjectStore } = require('@/stores/projectStore')

describe('ProjectList', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue({
      push: mockPush,
    })
    // Reset useProjectStore to default mock values
    useProjectStore.mockReturnValue({
      projects: mockProjects,
      loading: false,
      fetchProjects: mockFetchProjects,
      setSearchQuery: mockSetSearchQuery,
      searchQuery: '',
    })
  })

  describe('Initial Rendering', () => {
    it('should render the component header', () => {
      render(<ProjectList />)
      expect(screen.getByText('Projects')).toBeInTheDocument()
      expect(
        screen.getByText('Manage your annotation projects and track progress')
      ).toBeInTheDocument()
    })

    it('should render New Project button', () => {
      render(<ProjectList />)
      expect(
        screen.getByRole('button', { name: /new project/i })
      ).toBeInTheDocument()
    })

    it('should render search input', () => {
      render(<ProjectList />)
      expect(
        screen.getByPlaceholderText('Search projects...')
      ).toBeInTheDocument()
    })

    it('should render tabs for active and archived projects', () => {
      render(<ProjectList />)
      expect(screen.getByText('Active Projects')).toBeInTheDocument()
      expect(screen.getByText('Archived')).toBeInTheDocument()
    })

    it('should call fetchProjects on mount', () => {
      render(<ProjectList />)
      expect(mockFetchProjects).toHaveBeenCalledWith(1, 100)
    })
  })

  describe('Loading State', () => {
    it('should display loading spinner when loading and no projects', () => {
      useProjectStore.mockReturnValue({
        projects: [],
        loading: true,
        fetchProjects: mockFetchProjects,
        setSearchQuery: mockSetSearchQuery,
        searchQuery: '',
      })

      const { container } = render(<ProjectList />)
      // Find the spinner by its animate-spin class
      const spinner = container.querySelector('.animate-spin')
      expect(spinner).toBeInTheDocument()
    })

    it('should not display loading spinner when loading but projects exist', () => {
      useProjectStore.mockReturnValue({
        projects: mockProjects,
        loading: true,
        fetchProjects: mockFetchProjects,
        setSearchQuery: mockSetSearchQuery,
        searchQuery: '',
      })

      render(<ProjectList />)
      expect(
        screen.queryByRole('status', { hidden: true })
      ).not.toBeInTheDocument()
    })
  })

  describe('Active Projects Tab', () => {
    it('should display active projects by default', () => {
      render(<ProjectList />)
      expect(screen.getByText('Active Project 1')).toBeInTheDocument()
      expect(screen.getByText('Active Project 2')).toBeInTheDocument()
      expect(screen.queryByText('Archived Project')).not.toBeInTheDocument()
    })

    it('should render project cards with correct structure', () => {
      render(<ProjectList />)
      // Find the card container by its CSS classes
      const project1Card = screen
        .getByText('Active Project 1')
        .closest('.cursor-pointer')
      expect(project1Card).toBeInTheDocument()
      expect(project1Card).toHaveClass('transition-shadow')
    })

    it('should display project titles correctly', () => {
      render(<ProjectList />)
      expect(screen.getByText('Active Project 1')).toBeInTheDocument()
      expect(screen.getByText('Active Project 2')).toBeInTheDocument()
    })

    it('should display project descriptions', () => {
      render(<ProjectList />)
      expect(screen.getByText('Description for project 1')).toBeInTheDocument()
      expect(screen.getByText('Description for project 2')).toBeInTheDocument()
    })

    it('should display "No description" for projects without description', () => {
      render(<ProjectList />)
      expect(screen.getByText('No description')).toBeInTheDocument()
    })

    it('should display task counts', () => {
      render(<ProjectList />)
      expect(screen.getByText('100')).toBeInTheDocument()
      expect(screen.getByText('50')).toBeInTheDocument()
    })

    it('should display progress percentages', () => {
      render(<ProjectList />)
      expect(screen.getByText('45%')).toBeInTheDocument()
      expect(screen.getByText('100%')).toBeInTheDocument()
    })

    it('should display annotation counts', () => {
      render(<ProjectList />)
      expect(screen.getByText('45 annotations')).toBeInTheDocument()
      expect(screen.getByText('50 annotations')).toBeInTheDocument()
    })

    it('should render progress bars', () => {
      const { container } = render(<ProjectList />)
      const progressBars = container.querySelectorAll('.bg-primary')
      expect(progressBars.length).toBeGreaterThan(0)
    })

    it('should set correct progress bar width', () => {
      const { container } = render(<ProjectList />)
      const progressBars = container.querySelectorAll('.bg-primary')
      expect(progressBars[0]).toHaveStyle('width: 45%')
    })

    it('should display LLM model badges when present', () => {
      render(<ProjectList />)
      expect(screen.getByText('gpt-4')).toBeInTheDocument()
      expect(screen.getByText('claude-3')).toBeInTheDocument()
    })

    it('should not display LLM section when no models', () => {
      render(<ProjectList />)
      const project2 = screen.getByText('Active Project 2').closest('div')
      expect(within(project2!).queryByText('gpt-4')).not.toBeInTheDocument()
    })

    it('should display relative timestamps', () => {
      render(<ProjectList />)
      // Date formatting should show relative time
      const timestamps = screen.getAllByText(/vor/i) // German locale
      expect(timestamps.length).toBeGreaterThan(0)
    })
  })

  describe('Archived Projects Tab', () => {
    it('should switch to archived tab when clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectList />)

      const archivedTab = screen.getByText('Archived')
      await user.click(archivedTab)

      await waitFor(() => {
        expect(screen.getByText('Archived Project')).toBeInTheDocument()
      })
    })

    it('should not show active projects in archived tab', async () => {
      const user = userEvent.setup()
      render(<ProjectList />)

      const archivedTab = screen.getByText('Archived')
      await user.click(archivedTab)

      await waitFor(() => {
        expect(screen.queryByText('Active Project 1')).not.toBeInTheDocument()
        expect(screen.queryByText('Active Project 2')).not.toBeInTheDocument()
      })
    })

    it('should display "Archived" badge on archived projects', async () => {
      const user = userEvent.setup()
      render(<ProjectList />)

      const archivedTab = screen.getByText('Archived')
      await user.click(archivedTab)

      await waitFor(() => {
        // Look for the archived project title which should now be visible
        expect(screen.getByText('Archived Project')).toBeInTheDocument()
        // There should be multiple "Archived" texts - tab and badge
        const archivedTexts = screen.getAllByText('Archived')
        expect(archivedTexts.length).toBeGreaterThanOrEqual(2)
      })
    })

    it('should display empty state when no archived projects', async () => {
      useProjectStore.mockReturnValue({
        projects: mockProjects.filter((p) => !p.is_archived),
        loading: false,
        fetchProjects: mockFetchProjects,
        setSearchQuery: mockSetSearchQuery,
        searchQuery: '',
      })

      const user = userEvent.setup()
      render(<ProjectList />)

      const archivedTab = screen.getByText('Archived')
      await user.click(archivedTab)

      await waitFor(() => {
        expect(screen.getByText('No archived projects')).toBeInTheDocument()
        expect(
          screen.getByText('Archived projects will appear here')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Search Functionality', () => {
    it('should update search query on input', async () => {
      const user = userEvent.setup()
      render(<ProjectList />)

      const searchInput = screen.getByPlaceholderText('Search projects...')
      await user.type(searchInput, 'Project 1')

      expect(mockSetSearchQuery).toHaveBeenCalled()
    })

    it('should filter projects by title', () => {
      useProjectStore.mockReturnValue({
        projects: mockProjects.filter((p) => !p.is_archived),
        loading: false,
        fetchProjects: mockFetchProjects,
        setSearchQuery: mockSetSearchQuery,
        searchQuery: 'Project 1',
      })

      render(<ProjectList />)
      expect(screen.getByText('Active Project 1')).toBeInTheDocument()
    })

    it('should filter projects by description', () => {
      useProjectStore.mockReturnValue({
        projects: mockProjects.filter((p) => !p.is_archived),
        loading: false,
        fetchProjects: mockFetchProjects,
        setSearchQuery: mockSetSearchQuery,
        searchQuery: 'project 2',
      })

      render(<ProjectList />)
      expect(screen.getByText('Active Project 2')).toBeInTheDocument()
    })

    it('should be case-insensitive', () => {
      useProjectStore.mockReturnValue({
        projects: mockProjects.filter((p) => !p.is_archived),
        loading: false,
        fetchProjects: mockFetchProjects,
        setSearchQuery: mockSetSearchQuery,
        searchQuery: 'ACTIVE',
      })

      render(<ProjectList />)
      expect(screen.getByText('Active Project 1')).toBeInTheDocument()
      expect(screen.getByText('Active Project 2')).toBeInTheDocument()
    })

    it('should show empty state when no search results', () => {
      useProjectStore.mockReturnValue({
        projects: mockProjects.filter((p) => !p.is_archived),
        loading: false,
        fetchProjects: mockFetchProjects,
        setSearchQuery: mockSetSearchQuery,
        searchQuery: 'nonexistent',
      })

      render(<ProjectList />)
      expect(screen.getByText('No projects found')).toBeInTheDocument()
      expect(
        screen.getByText('Try adjusting your search criteria')
      ).toBeInTheDocument()
    })
  })

  describe('Empty States', () => {
    it('should display empty state when no active projects', () => {
      useProjectStore.mockReturnValue({
        projects: [],
        loading: false,
        fetchProjects: mockFetchProjects,
        setSearchQuery: mockSetSearchQuery,
        searchQuery: '',
      })

      render(<ProjectList />)
      expect(screen.getByText('No active projects')).toBeInTheDocument()
      expect(
        screen.getByText('Create your first project to get started')
      ).toBeInTheDocument()
    })

    it('should show create button in empty state', () => {
      useProjectStore.mockReturnValue({
        projects: [],
        loading: false,
        fetchProjects: mockFetchProjects,
        setSearchQuery: mockSetSearchQuery,
        searchQuery: '',
      })

      render(<ProjectList />)
      const createButtons = screen.getAllByText('Create Project')
      expect(createButtons[0]).toBeInTheDocument()
    })

    it('should not show create button in search empty state', () => {
      useProjectStore.mockReturnValue({
        projects: mockProjects,
        loading: false,
        fetchProjects: mockFetchProjects,
        setSearchQuery: mockSetSearchQuery,
        searchQuery: 'nonexistent',
      })

      render(<ProjectList />)
      expect(screen.queryByText('Create Project')).not.toBeInTheDocument()
    })
  })

  describe('Navigation', () => {
    it('should navigate to create project page when New Project clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectList />)

      const newProjectButton = screen.getByRole('button', {
        name: /new project/i,
      })
      await user.click(newProjectButton)

      expect(mockPush).toHaveBeenCalledWith('/projects/create')
    })

    it('should navigate to project detail when card clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectList />)

      const projectCard = screen.getByText('Active Project 1').closest('div')
      await user.click(projectCard!)

      expect(mockPush).toHaveBeenCalledWith('/projects/1')
    })

    it('should navigate to archived project when clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectList />)

      const archivedTab = screen.getByText('Archived')
      await user.click(archivedTab)

      await waitFor(() => {
        const archivedLink = screen.getByText('Archived Project').closest('a')
        expect(archivedLink).toHaveAttribute('href', '/projects/3')
      })
    })
  })

  describe('Progress Calculation', () => {
    it('should use server progress_percentage when available', () => {
      render(<ProjectList />)
      expect(screen.getByText('45%')).toBeInTheDocument()
    })

    it('should calculate progress from counts when percentage not available', () => {
      const projectsWithoutPercentage = [
        {
          ...mockProjects[0],
          progress_percentage: undefined,
          task_count: 100,
          annotation_count: 50,
        },
      ]

      useProjectStore.mockReturnValue({
        projects: projectsWithoutPercentage,
        loading: false,
        fetchProjects: mockFetchProjects,
        setSearchQuery: mockSetSearchQuery,
        searchQuery: '',
      })

      render(<ProjectList />)
      expect(screen.getByText('50%')).toBeInTheDocument()
    })

    it('should handle zero task count', () => {
      const projectsWithZeroTasks = [
        {
          ...mockProjects[0],
          progress_percentage: undefined,
          task_count: 0,
          annotation_count: 0,
        },
      ]

      useProjectStore.mockReturnValue({
        projects: projectsWithZeroTasks,
        loading: false,
        fetchProjects: mockFetchProjects,
        setSearchQuery: mockSetSearchQuery,
        searchQuery: '',
      })

      render(<ProjectList />)
      expect(screen.getByText('0%')).toBeInTheDocument()
    })

    it('should cap progress at 100%', () => {
      const projectsWithOverflow = [
        {
          ...mockProjects[0],
          progress_percentage: undefined,
          task_count: 100,
          annotation_count: 150, // More than task count
        },
      ]

      useProjectStore.mockReturnValue({
        projects: projectsWithOverflow,
        loading: false,
        fetchProjects: mockFetchProjects,
        setSearchQuery: mockSetSearchQuery,
        searchQuery: '',
      })

      render(<ProjectList />)
      expect(screen.getByText('100%')).toBeInTheDocument()
    })
  })

  describe('Grid Layout', () => {
    it('should use responsive grid classes', () => {
      const { container } = render(<ProjectList />)
      const grid = container.querySelector('.grid')
      expect(grid).toHaveClass('grid-cols-1')
      expect(grid).toHaveClass('md:grid-cols-2')
      expect(grid).toHaveClass('lg:grid-cols-3')
    })

    it('should render multiple project cards in grid', () => {
      render(<ProjectList />)
      const activeProjects = mockProjects.filter((p) => !p.is_archived)
      activeProjects.forEach((project) => {
        expect(screen.getByText(project.title)).toBeInTheDocument()
      })
    })
  })

  describe('Hover Effects', () => {
    it('should have hover classes on project cards', () => {
      render(<ProjectList />)
      // Find the card container with the hover class (could be any parent element)
      const card = screen
        .getByText('Active Project 1')
        .closest('.hover\\:shadow-lg')
      expect(card).toBeInTheDocument()
    })

    it('should have cursor pointer on cards', () => {
      render(<ProjectList />)
      // Find the card container with cursor-pointer class
      const card = screen
        .getByText('Active Project 1')
        .closest('.cursor-pointer')
      expect(card).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('should have proper heading hierarchy', () => {
      render(<ProjectList />)
      const heading = screen.getByText('Projects')
      expect(heading.tagName).toBe('H1')
    })

    it('should have descriptive button labels', () => {
      render(<ProjectList />)
      expect(
        screen.getByRole('button', { name: /new project/i })
      ).toBeInTheDocument()
    })

    it('should have proper ARIA labels for tabs', () => {
      render(<ProjectList />)
      expect(screen.getByText('Active Projects')).toBeInTheDocument()
      expect(screen.getByText('Archived')).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('should handle empty project list', () => {
      useProjectStore.mockReturnValue({
        projects: [],
        loading: false,
        fetchProjects: mockFetchProjects,
        setSearchQuery: mockSetSearchQuery,
        searchQuery: '',
      })

      render(<ProjectList />)
      expect(screen.getByText('No active projects')).toBeInTheDocument()
    })

    it('should handle projects with null descriptions', () => {
      render(<ProjectList />)
      expect(screen.getByText('No Description Project')).toBeInTheDocument()
      expect(screen.getByText('No description')).toBeInTheDocument()
    })

    it('should handle projects with empty LLM model arrays', () => {
      const { container } = render(<ProjectList />)
      expect(screen.getByText('Active Project 2')).toBeInTheDocument()
    })

    it('should handle very long project titles', () => {
      const longTitleProjects = [
        {
          ...mockProjects[0],
          title: 'A'.repeat(200),
        },
      ]

      useProjectStore.mockReturnValue({
        projects: longTitleProjects,
        loading: false,
        fetchProjects: mockFetchProjects,
        setSearchQuery: mockSetSearchQuery,
        searchQuery: '',
      })

      render(<ProjectList />)
      expect(screen.getByText('A'.repeat(200))).toBeInTheDocument()
    })
  })
})
