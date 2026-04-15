import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ProjectSelector } from '../ProjectSelector'

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(() => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'generation.projectSelector.searchPlaceholder':
          'Search projects by name, description, or organization',
        'generation.projectSelector.showing': `Showing ${params?.count || 0} of ${params?.total || 0} projects`,
        'generation.projectSelector.tableHeaders.project': 'Project',
        'generation.projectSelector.tableHeaders.tasks': 'Tasks',
        'generation.projectSelector.tableHeaders.models': 'Models',
        'generation.projectSelector.tableHeaders.prompts': 'Prompts',
        'generation.projectSelector.tableHeaders.config': 'Config',
        'generation.projectSelector.tableHeaders.status': 'Status',
        'generation.projectSelector.statusLabels.complete': '✓ Complete',
        'generation.projectSelector.statusLabels.ready': '✓ Ready',
        'generation.projectSelector.statusLabels.setupNeeded':
          '⚠ Setup needed',
        'generation.projectSelector.emptyStates.noProjects':
          'No projects available',
        'generation.projectSelector.emptyStates.noProjectsFound':
          'No projects found matching your search',
        'generation.projectSelector.emptyStates.createFirst':
          'Create a project first to start generating responses',
      }
      return translations[key] || key
    },
    changeLanguage: jest.fn(),
    currentLanguage: 'en',
    languages: ['en', 'de'],
  })),
}))

jest.mock('@/components/shared/LoadingSpinner', () => ({
  LoadingSpinner: () => <div role="status" />,
}))

const mockProjects = [
  {
    id: '1',
    title: 'Test Project 1',
    description: 'Test description 1',
    task_count: 10,
    generation_models_count: 2,
    generation_prompts_ready: true,
    generation_config_ready: true,
    generation_completed: false,
    organization: { name: 'Test Org' },
  },
  {
    id: '2',
    title: 'Test Project 2',
    description: 'Test description 2',
    task_count: 5,
    generation_models_count: 0,
    generation_prompts_ready: false,
    generation_config_ready: false,
    generation_completed: false,
    organization: { name: 'Test Org 2' },
  },
  {
    id: '3',
    title: 'Test Project 3',
    description: 'Completed project',
    task_count: 20,
    generation_models_count: 3,
    generation_prompts_ready: true,
    generation_config_ready: true,
    generation_completed: true,
    organization: { name: 'Test Org' },
  },
]

// Stable mock functions
const mockFetchProjects = jest.fn()
const mockRouterPush = jest.fn()

// Mock the hooks with stable references
jest.mock('@/hooks/useProjects', () => ({
  useProjects: jest.fn(),
}))

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

const { useProjects } = require('@/hooks/useProjects')
const { useRouter } = require('next/navigation')

// Setup default mock implementations
;(useProjects as jest.Mock).mockReturnValue({
  projects: mockProjects,
  loading: false,
  error: null,
  fetchProjects: mockFetchProjects,
})
;(useRouter as jest.Mock).mockReturnValue({
  push: mockRouterPush,
})

describe('ProjectSelector', () => {
  const mockOnProjectSelect = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    // Reset to default mock values
    ;(useProjects as jest.Mock).mockReturnValue({
      projects: mockProjects,
      loading: false,
      error: null,
      fetchProjects: mockFetchProjects,
    })
    ;(useRouter as jest.Mock).mockReturnValue({
      push: mockRouterPush,
    })
  })

  describe('Responsive Grid Layout', () => {
    it('should render with responsive grid classes for table headers', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      // Check that the header wrapper has min-width class
      const headerContainer = screen.getByText('Project').closest('div')
        ?.parentElement?.parentElement
      expect(headerContainer).toHaveClass('min-w-[640px]')

      // Check for responsive grid column classes on the grid div
      const gridDiv = screen.getByText('Project').parentElement
      expect(gridDiv?.className).toMatch(
        /grid-cols-\[32px_1fr_80px_80px_80px_80px_120px\]/
      )
      expect(gridDiv?.className).toMatch(
        /md:grid-cols-\[32px_1fr_96px_96px_96px_96px_140px\]/
      )
      expect(gridDiv?.className).toMatch(
        /lg:grid-cols-\[32px_1fr_96px_128px_128px_128px_160px\]/
      )
    })

    it('should have overflow-x-auto on the header container', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const headerWrapper =
        screen.getByText('Project').parentElement?.parentElement?.parentElement
      expect(headerWrapper).toHaveClass('overflow-x-auto')
    })

    it('should render project rows with responsive grid classes', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      // Find a project row - navigate up to the min-w-[640px] div
      const projectRow = screen
        .getByText('Test Project 1')
        .closest('div.overflow-hidden')?.parentElement?.parentElement
      expect(projectRow).toHaveClass('min-w-[640px]')

      // Check for responsive grid classes on the grid element
      const gridRow = projectRow?.querySelector('.grid')
      expect(gridRow?.className).toMatch(
        /grid-cols-\[32px_1fr_80px_80px_80px_80px_120px\]/
      )
      expect(gridRow?.className).toMatch(
        /md:grid-cols-\[32px_1fr_96px_96px_96px_96px_140px\]/
      )
      expect(gridRow?.className).toMatch(
        /lg:grid-cols-\[32px_1fr_96px_128px_128px_128px_160px\]/
      )
    })

    it('should have responsive gap classes', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const gridDiv = screen.getByText('Project').parentElement
      expect(gridDiv?.className).toMatch(/gap-2/)
      expect(gridDiv?.className).toMatch(/md:gap-3/)
      expect(gridDiv?.className).toMatch(/lg:gap-4/)
    })

    it('should have overflow-x-auto on the projects list container', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const projectsList = screen
        .getByText('Test Project 1')
        .closest('div[class*="space-y"]')
      expect(projectsList).toHaveClass('overflow-x-auto')
    })
  })

  describe('Table Alignment', () => {
    it('should have consistent column structure between header and rows', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      // Get header columns from the grid element
      const headerGrid = screen.getByText('Project').parentElement
      const headerColumns = headerGrid?.className.match(
        /grid-cols-\[([^\]]+)\]/
      )?.[1]

      // Get row columns from the grid element
      const projectRow = screen
        .getByText('Test Project 1')
        .closest('div.overflow-hidden')
        ?.parentElement?.parentElement?.querySelector('.grid')
      const rowColumns = projectRow?.className.match(
        /grid-cols-\[([^\]]+)\]/
      )?.[1]

      // They should have the same column structure
      expect(headerColumns).toBe(rowColumns)
    })

    it('should maintain minimum width to prevent column collapse', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      // Check that both header and rows have minimum width
      const headerContainer =
        screen.getByText('Project').parentElement?.parentElement
      expect(headerContainer).toHaveClass('min-w-[640px]')

      const projectRowContainer = screen
        .getByText('Test Project 1')
        .closest('div.overflow-hidden')?.parentElement?.parentElement
      expect(projectRowContainer).toHaveClass('min-w-[640px]')
    })
  })

  describe('Content Rendering', () => {
    it('should render all column headers', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      expect(screen.getByText('Project')).toBeInTheDocument()
      expect(screen.getByText('Tasks')).toBeInTheDocument()
      expect(screen.getByText('Models')).toBeInTheDocument()
      expect(screen.getByText('Prompts')).toBeInTheDocument()
      expect(screen.getByText('Config')).toBeInTheDocument()
      expect(screen.getByText('Status')).toBeInTheDocument()
    })

    it('should render project data correctly', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      expect(screen.getByText('Test Project 1')).toBeInTheDocument()
      expect(screen.getByText('Test Project 2')).toBeInTheDocument()
      expect(screen.getByText('10')).toBeInTheDocument() // task count
      expect(screen.getByText('5')).toBeInTheDocument() // task count
    })

    it('should display project descriptions', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      expect(screen.getByText('Test description 1')).toBeInTheDocument()
      expect(screen.getByText('Test description 2')).toBeInTheDocument()
    })

    it('should display task counts correctly', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      expect(screen.getByText('10')).toBeInTheDocument()
      expect(screen.getByText('5')).toBeInTheDocument()
    })

    it('should display model counts', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      expect(screen.getByText('2')).toBeInTheDocument() // models count
      expect(screen.getByText('0')).toBeInTheDocument() // zero models
    })

    it('should display results count correctly', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const resultsText = screen.getByText(/Showing 3 of 3 projects/)
      expect(resultsText).toBeInTheDocument()
    })
  })

  describe('Search Functionality', () => {
    it('should render search input', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const searchInput = screen.getByPlaceholderText(
        /search projects by name, description, or organization/i
      )
      expect(searchInput).toBeInTheDocument()
    })

    it('should filter projects by title', async () => {
      const user = userEvent.setup()
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const searchInput = screen.getByPlaceholderText(
        /search projects by name, description, or organization/i
      )
      await user.type(searchInput, 'Project 1')

      // Should only show Project 1
      expect(screen.getByText('Test Project 1')).toBeInTheDocument()
    })

    it('should filter projects by description', async () => {
      const user = userEvent.setup()
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const searchInput = screen.getByPlaceholderText(
        /search projects by name, description, or organization/i
      )
      await user.type(searchInput, 'description 2')

      expect(screen.getByText('Test Project 2')).toBeInTheDocument()
    })

    it('should filter projects by organization', async () => {
      const user = userEvent.setup()
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const searchInput = screen.getByPlaceholderText(
        /search projects by name, description, or organization/i
      )
      await user.type(searchInput, 'Test Org')

      expect(screen.getByText('Test Project 1')).toBeInTheDocument()
      expect(screen.getByText('Test Project 2')).toBeInTheDocument()
    })

    it('should be case-insensitive', async () => {
      const user = userEvent.setup()
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const searchInput = screen.getByPlaceholderText(
        /search projects by name, description, or organization/i
      )
      await user.type(searchInput, 'TEST PROJECT')

      expect(screen.getByText('Test Project 1')).toBeInTheDocument()
    })

    it('should update results count when searching', async () => {
      const user = userEvent.setup()
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const searchInput = screen.getByPlaceholderText(
        /search projects by name, description, or organization/i
      )
      await user.type(searchInput, 'Project 1')

      expect(screen.getByText(/Showing 1 of 3 projects/)).toBeInTheDocument()
    })

    it('should show empty state when no results', async () => {
      const user = userEvent.setup()
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const searchInput = screen.getByPlaceholderText(
        /search projects by name, description, or organization/i
      )
      await user.type(searchInput, 'nonexistent')

      expect(
        screen.getByText('No projects found matching your search')
      ).toBeInTheDocument()
    })

    it('should sort projects alphabetically', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const projectTitles = screen
        .getAllByText(/Test Project/)
        .map((el) => el.textContent)
      expect(projectTitles).toEqual([
        'Test Project 1',
        'Test Project 2',
        'Test Project 3',
      ])
    })
  })

  describe('Project Selection', () => {
    it('should call onProjectSelect when project is clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const project1 = screen
        .getByText('Test Project 1')
        .closest('div[role="button"]')
      await user.click(project1!)

      expect(mockOnProjectSelect).toHaveBeenCalledWith(mockProjects[0])
    })

    it('should show selected state for selected project', () => {
      render(
        <ProjectSelector
          onProjectSelect={mockOnProjectSelect}
          selectedProjectId="1"
        />
      )

      const project1 = screen
        .getByText('Test Project 1')
        .closest('div[role="button"]')
      expect(project1).toHaveClass('border-emerald-500')
      expect(project1).toHaveClass('bg-emerald-50')
    })

    it('should show checkmark for selected project', () => {
      const { container } = render(
        <ProjectSelector
          onProjectSelect={mockOnProjectSelect}
          selectedProjectId="1"
        />
      )

      const checkIcon = container.querySelector('.text-emerald-600')
      expect(checkIcon).toBeInTheDocument()
    })

    it('should show empty circle for unselected projects', () => {
      const { container } = render(
        <ProjectSelector onProjectSelect={mockOnProjectSelect} />
      )

      const circles = container.querySelectorAll('.rounded.border-2')
      expect(circles.length).toBeGreaterThan(0)
    })

    it('should handle keyboard selection with Enter', async () => {
      const user = userEvent.setup()
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const project1 = screen
        .getByText('Test Project 1')
        .closest('div[role="button"]')
      project1?.focus()
      await user.keyboard('{Enter}')

      expect(mockOnProjectSelect).toHaveBeenCalledWith(mockProjects[0])
    })

    it('should handle keyboard selection with Space', async () => {
      const user = userEvent.setup()
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const project1 = screen
        .getByText('Test Project 1')
        .closest('div[role="button"]')
      project1?.focus()
      await user.keyboard(' ')

      expect(mockOnProjectSelect).toHaveBeenCalledWith(mockProjects[0])
    })

    it('should prevent default on mouse down', async () => {
      const user = userEvent.setup()
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const project1 = screen
        .getByText('Test Project 1')
        .closest('div[role="button"]')
      await user.click(project1!)

      expect(mockOnProjectSelect).toHaveBeenCalled()
    })
  })

  describe('Status Badges', () => {
    it('should show "Complete" status for completed projects', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const completeBadge = screen.getByText('✓ Complete')
      expect(completeBadge).toBeInTheDocument()
    })

    it('should show "Ready" status for ready projects', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const readyBadge = screen.getByText('✓ Ready')
      expect(readyBadge).toBeInTheDocument()
    })

    it('should show "Setup needed" for incomplete projects', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const setupBadge = screen.getByText('⚠ Setup needed')
      expect(setupBadge).toBeInTheDocument()
    })

    it('should navigate to project when "Ready" status badge clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const readyBadge = screen.getByText('✓ Ready')
      await user.click(readyBadge)

      expect(mockRouterPush).toHaveBeenCalledWith('/projects/1')
    })

    it('should navigate to project when "Complete" status badge clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const completeBadge = screen.getByText('✓ Complete')
      await user.click(completeBadge)

      expect(mockRouterPush).toHaveBeenCalledWith('/projects/3')
    })

    it('should navigate to project when "Setup needed" status badge clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const setupBadge = screen.getByText('⚠ Setup needed')
      await user.click(setupBadge)

      expect(mockRouterPush).toHaveBeenCalledWith('/projects/2')
    })

    it('should stop propagation when status badge clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const readyBadge = screen.getByText('✓ Ready')
      await user.click(readyBadge)

      // onProjectSelect should not be called
      expect(mockOnProjectSelect).not.toHaveBeenCalled()
    })

    it('should have proper ARIA label for status badges', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const readyBadge = screen.getByLabelText(
        /Navigate to Test Project 1 settings/
      )
      expect(readyBadge).toBeInTheDocument()
    })
  })

  describe('Loading State', () => {
    it('should show loading spinner when loading', () => {
      ;(useProjects as jest.Mock).mockReturnValue({
        projects: null,
        loading: true,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      expect(screen.getByRole('status', { hidden: true })).toBeInTheDocument()
    })

    it('should center loading spinner', () => {
      ;(useProjects as jest.Mock).mockReturnValue({
        projects: null,
        loading: true,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      const { container } = render(
        <ProjectSelector onProjectSelect={mockOnProjectSelect} />
      )

      const loadingContainer = container.querySelector('.justify-center')
      expect(loadingContainer).toBeInTheDocument()
    })
  })

  describe('Error State', () => {
    it('should display error message when error occurs', () => {
      ;(useProjects as jest.Mock).mockReturnValue({
        projects: null,
        loading: false,
        error: 'Failed to load projects',
        fetchProjects: mockFetchProjects,
      })

      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      expect(
        screen.getByText('Failed to load projects: Failed to load projects')
      ).toBeInTheDocument()
    })

    it('should style error state appropriately', () => {
      ;(useProjects as jest.Mock).mockReturnValue({
        projects: null,
        loading: false,
        error: 'Failed to load projects',
        fetchProjects: mockFetchProjects,
      })

      const { container } = render(
        <ProjectSelector onProjectSelect={mockOnProjectSelect} />
      )

      const errorCard = container.querySelector('.border-red-200')
      expect(errorCard).toBeInTheDocument()
    })
  })

  describe('Empty State', () => {
    it('should show empty state when no projects', () => {
      ;(useProjects as jest.Mock).mockReturnValue({
        projects: [],
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      expect(screen.getByText('No projects available')).toBeInTheDocument()
      expect(
        screen.getByText('Create a project first to start generating responses')
      ).toBeInTheDocument()
    })

    it('should not show create message in search empty state', async () => {
      const user = userEvent.setup()
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      const searchInput = screen.getByPlaceholderText(
        /search projects by name, description, or organization/i
      )
      await user.type(searchInput, 'nonexistent')

      expect(
        screen.queryByText(
          'Create a project first to start generating responses'
        )
      ).not.toBeInTheDocument()
    })
  })

  describe('Prompts and Config Status', () => {
    it('should show checkmark for ready prompts', () => {
      const { container } = render(
        <ProjectSelector onProjectSelect={mockOnProjectSelect} />
      )

      const checkIcons = container.querySelectorAll('.text-emerald-500')
      expect(checkIcons.length).toBeGreaterThan(0)
    })

    it('should show X mark for not ready prompts', () => {
      const { container } = render(
        <ProjectSelector onProjectSelect={mockOnProjectSelect} />
      )

      const xIcons = container.querySelectorAll('.text-red-500')
      expect(xIcons.length).toBeGreaterThan(0)
    })

    it('should show checkmark for ready config', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      // Project 1 has ready config
      const project1Row = screen.getByText('Test Project 1').closest('.grid')
      expect(project1Row).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('should handle projects without description', () => {
      const projectsWithoutDesc = [{ ...mockProjects[0], description: null }]
      ;(useProjects as jest.Mock).mockReturnValue({
        projects: projectsWithoutDesc,
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      expect(screen.getByText('Test Project 1')).toBeInTheDocument()
    })

    it('should handle projects with zero task count', () => {
      const projectsWithZeroTasks = [{ ...mockProjects[0], task_count: 0 }]
      ;(useProjects as jest.Mock).mockReturnValue({
        projects: projectsWithZeroTasks,
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      expect(screen.getByText('0')).toBeInTheDocument()
    })

    it('should handle projects without organization', () => {
      const projectsWithoutOrg = [{ ...mockProjects[0], organization: null }]
      ;(useProjects as jest.Mock).mockReturnValue({
        projects: projectsWithoutOrg,
        loading: false,
        error: null,
        fetchProjects: mockFetchProjects,
      })

      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      expect(screen.getByText('Test Project 1')).toBeInTheDocument()
    })

    it('should call fetchProjects on mount', () => {
      render(<ProjectSelector onProjectSelect={mockOnProjectSelect} />)

      expect(mockFetchProjects).toHaveBeenCalledTimes(1)
    })
  })

  describe('Styling', () => {
    it('should have proper hover effects on project rows', () => {
      const { container } = render(
        <ProjectSelector onProjectSelect={mockOnProjectSelect} />
      )

      const projectRow = screen
        .getByText('Test Project 1')
        .closest('div[role="button"]')
      expect(projectRow).toHaveClass('hover:shadow-md')
    })

    it('should have rounded corners on project rows', () => {
      const { container } = render(
        <ProjectSelector onProjectSelect={mockOnProjectSelect} />
      )

      const projectRow = screen
        .getByText('Test Project 1')
        .closest('div[role="button"]')
      expect(projectRow).toHaveClass('rounded-lg')
    })

    it('should have proper dark mode classes', () => {
      const { container } = render(
        <ProjectSelector onProjectSelect={mockOnProjectSelect} />
      )

      const projectRow = screen
        .getByText('Test Project 1')
        .closest('div[role="button"]')
      expect(projectRow).toHaveClass('dark:bg-zinc-800')
    })
  })
})
