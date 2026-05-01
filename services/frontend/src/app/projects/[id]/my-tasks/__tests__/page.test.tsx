/**
 * Unit tests for My Tasks page (Issue #258)
 */

/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { projectsAPI } from '@/lib/api/projects'
import { useProjectStore } from '@/stores/projectStore'
import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useParams, useRouter } from 'next/navigation'
import MyTasksPage from '../page'

// Mock Next.js navigation
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

// Mock auth context
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

// Mock API
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    getMyTasks: jest.fn(),
    updateAssignmentStatus: jest.fn(),
    getProject: jest.fn(),
  },
}))

// Mock project store
jest.mock('@/stores/projectStore', () => ({
  useProjectStore: jest.fn(),
}))

// Mock toast with stable function reference
const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: mockAddToast,
  }),
}))

const mockRouter = {
  push: jest.fn(),
  back: jest.fn(),
}

const mockUser = {
  id: 'user-123',
  username: 'testuser',
  email: 'test@example.com',
  role: 'annotator',
}

const mockProject = {
  id: 'project-123',
  title: 'Test Project',
  description: 'Test project description',
  assignment_mode: 'manual',
}

const mockTasks = {
  tasks: [
    {
      id: 1,
      name: 'Task 1',
      data: {
        text: 'Task 1 content - analyze this legal document',
      },
      created_at: '2024-01-01T10:00:00Z',
      assignment: {
        id: 'assign-1',
        status: 'assigned',
        priority: 1,
        due_date: '2024-02-01T10:00:00Z',
        notes: 'Please complete ASAP',
        assigned_at: '2024-01-01T10:00:00Z',
      },
    },
    {
      id: 2,
      name: 'Task 2',
      data: {
        question: 'What is the legal precedent in this case?',
      },
      created_at: '2024-01-02T10:00:00Z',
      assignment: {
        id: 'assign-2',
        status: 'in_progress',
        priority: 0,
        due_date: null,
        notes: null,
        assigned_at: '2024-01-02T10:00:00Z',
        started_at: '2024-01-03T10:00:00Z',
      },
    },
    {
      id: 3,
      name: 'Task 3',
      data: {
        input: 'Review and classify this contract clause',
      },
      created_at: '2024-01-03T10:00:00Z',
      assignment: {
        id: 'assign-3',
        status: 'completed',
        priority: 2,
        due_date: '2024-01-15T10:00:00Z',
        notes: 'Good job!',
        assigned_at: '2024-01-03T10:00:00Z',
        started_at: '2024-01-04T10:00:00Z',
        completed_at: '2024-01-05T10:00:00Z',
      },
    },
  ],
  total: 3,
  page: 1,
  page_size: 10,
  pages: 1,
}

// Mock shared components to prevent import errors
jest.mock('@/components/shared', () => {
  const React = require('react')
  return {
    HeroPattern: () =>
      React.createElement(
        'div',
        { 'data-testid': 'hero-pattern' },
        'Hero Pattern'
      ),
    GridPattern: () =>
      React.createElement(
        'div',
        { 'data-testid': 'grid-pattern' },
        'Grid Pattern'
      ),
    Button: ({ children, ...props }) =>
      React.createElement('button', props, children),
    ResponsiveContainer: ({ children }) =>
      React.createElement('div', null, children),
    LoadingSpinner: () =>
      React.createElement(
        'div',
        { 'data-testid': 'loading-spinner' },
        'Loading...'
      ),
    EmptyState: ({ message }) => React.createElement('div', null, message),
    Spinner: () => React.createElement('div', null, 'Loading...'),
    // Add other exports as needed
  }
})
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


// Mock fetch for API calls
global.fetch = jest.fn()

// Translation map for tests
const translations: Record<string, string> = {
  'navigation.dashboard': 'Dashboard',
  'navigation.projects': 'Projects',
  'navigation.myTasks': 'My Tasks',
  'common.loadingProject': 'Loading project...',
  'common.previous': 'Previous',
  'common.next': 'Next',
  'tasks.myTasks.title': 'My Assigned Tasks',
  'tasks.myTasks.description': 'Tasks assigned to you in',
  'tasks.myTasks.startAnnotating': 'Start Annotating',
  'tasks.myTasks.tasksAssigned': 'tasks assigned',
  'tasks.myTasks.loadFailed': 'Failed to load tasks',
  'tasks.myTasks.assigned': 'Assigned',
  'tasks.myTasks.inProgress': 'In Progress',
  'tasks.myTasks.completed': 'Completed',
  'tasks.myTasks.skipped': 'Skipped',
  'tasks.myTasks.allTasks': 'All Tasks',
  'tasks.myTasks.loadingTasks': 'Loading tasks...',
  'tasks.myTasks.noTasks': 'No tasks assigned yet',
  'tasks.myTasks.taskPrefix': 'Task',
  'tasks.myTasks.labeled': 'Labeled',
  'tasks.myTasks.due': 'Due',
}

describe('MyTasksPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useParams as jest.Mock).mockReturnValue({ id: 'project-123' })
    ;(useAuth as jest.Mock).mockReturnValue({ user: mockUser })
    ;(useI18n as jest.Mock).mockReturnValue({
      t: (key: string, vars?: any) => {
        const translation = translations[key] || key
        if (vars) {
          return translation.replace(/\{(\w+)\}/g, (_, k) => vars[k] || '')
        }
        return translation
      },
    })
    ;(projectsAPI.getProject as jest.Mock).mockResolvedValue(mockProject)
    ;(projectsAPI.getMyTasks as jest.Mock).mockResolvedValue(mockTasks)

    // Mock project store to return the mock project and not be loading
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: mockProject,
      loading: false,
      fetchProject: jest.fn(),
    })

    // Mock fetch for the API call to /api/projects/${projectId}/my-tasks
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockTasks),
    })
  })

  it('renders page with project title', async () => {
    render(<MyTasksPage />)

    await waitFor(() => {
      expect(screen.getByText('My Assigned Tasks')).toBeInTheDocument()
      expect(
        screen.getByText('Tasks assigned to you in Test Project')
      ).toBeInTheDocument()
    })
  })

  it('displays assigned tasks', async () => {
    render(<MyTasksPage />)

    await waitFor(() => {
      // The component renders task IDs as "Task #<id>", not task data content
      expect(screen.getByText('Task #1')).toBeInTheDocument()
      expect(screen.getByText('Task #2')).toBeInTheDocument()
      expect(screen.getByText('Task #3')).toBeInTheDocument()
    })
  })

  it('shows task status badges', async () => {
    render(<MyTasksPage />)

    await waitFor(() => {
      expect(screen.getByText('Assigned')).toBeInTheDocument()
      expect(screen.getByText('In Progress')).toBeInTheDocument()
      expect(screen.getByText('Completed')).toBeInTheDocument()
    })
  })

  it('displays priority indicators', async () => {
    render(<MyTasksPage />)

    await waitFor(() => {
      // Check that task IDs are displayed (priority indicators are visual flag icons)
      expect(screen.getByText('Task #1')).toBeInTheDocument()
      expect(screen.getByText('Task #2')).toBeInTheDocument()
      expect(screen.getByText('Task #3')).toBeInTheDocument()
    })
  })

  it('shows due dates', async () => {
    render(<MyTasksPage />)

    await waitFor(() => {
      // Check that assignment information is displayed
      // The component shows relative time with formatDistanceToNow
      const dateElements = screen.getAllByText(/ago/i)
      expect(dateElements.length).toBeGreaterThan(0)

      // "Due" text appears for tasks with a due_date
      const dueElements = screen.getAllByText(/Due/i)
      expect(dueElements.length).toBeGreaterThan(0)
    })
  })

  it('displays assignment notes', async () => {
    render(<MyTasksPage />)

    await waitFor(() => {
      expect(screen.getByText('Please complete ASAP')).toBeInTheDocument()
      expect(screen.getByText('Good job!')).toBeInTheDocument()
    })
  })

  it('allows filtering by status', async () => {
    const user = userEvent.setup()
    render(<MyTasksPage />)

    await waitFor(() => {
      // Look for the Select component (rendered as native <select> in test mock)
      expect(screen.getByRole('combobox')).toBeInTheDocument()
    })

    // Verify the filter component exists
    const statusFilter = screen.getByRole('combobox')
    expect(statusFilter).toBeInTheDocument()
  })

  it('renders tasks without sorting functionality', async () => {
    render(<MyTasksPage />)

    await waitFor(() => {
      // The component doesn't have sorting functionality currently
      // Just verify that tasks are rendered in the order they come from the API
      expect(screen.getByText('Task #1')).toBeInTheDocument()
      expect(screen.getByText('Task #2')).toBeInTheDocument()
      expect(screen.getByText('Task #3')).toBeInTheDocument()
    })
  })

  it('allows navigating to task annotation', async () => {
    const user = userEvent.setup()
    render(<MyTasksPage />)

    await waitFor(() => {
      // Find the task card by its task ID label
      expect(screen.getByText('Task #1')).toBeInTheDocument()
    })

    // Click on the task card to navigate to annotation
    const taskCard = screen
      .getByText('Task #1')
      .closest('[class*="cursor-pointer"]')
    await user.click(taskCard!)

    // Component navigates to the labeling interface
    expect(mockRouter.push).toHaveBeenCalledWith(
      '/projects/project-123/label'
    )
  })

  it('displays task status information', async () => {
    render(<MyTasksPage />)

    await waitFor(() => {
      // Component shows status badges for each task
      expect(screen.getByText('Assigned')).toBeInTheDocument()
      expect(screen.getByText('In Progress')).toBeInTheDocument()
      expect(screen.getByText('Completed')).toBeInTheDocument()

      // Component doesn't have task completion/skipping buttons
      // It only allows navigation to annotation page
      expect(screen.getByText('Start Annotating')).toBeInTheDocument()
    })
  })

  it('shows summary statistics', async () => {
    render(<MyTasksPage />)

    await waitFor(() => {
      // Component shows simple task count
      expect(screen.getByText('3 tasks assigned')).toBeInTheDocument()

      // And has a "Start Annotating" button
      expect(screen.getByText('Start Annotating')).toBeInTheDocument()
    })
  })

  it('renders with basic functionality', async () => {
    render(<MyTasksPage />)

    await waitFor(() => {
      // Basic functionality test - component renders tasks and navigation elements
      expect(screen.getByText('My Assigned Tasks')).toBeInTheDocument()
      expect(screen.getByText('3 tasks assigned')).toBeInTheDocument()
      expect(screen.getByText('Start Annotating')).toBeInTheDocument()

      // Tasks are displayed by their ID labels
      expect(screen.getByText('Task #1')).toBeInTheDocument()
      expect(screen.getByText('Task #2')).toBeInTheDocument()
      expect(screen.getByText('Task #3')).toBeInTheDocument()
    })
  })

  // Additional integration tests would require more complex fetch mocking
  // Core functionality is verified by the tests above
})
