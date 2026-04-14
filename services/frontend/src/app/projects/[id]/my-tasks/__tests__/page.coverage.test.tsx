/**
 * Coverage-focused tests for MyTasksPage
 *
 * Targets uncovered branches:
 * - Loading state when projectLoading is true
 * - Empty tasks list state
 * - Status filter with non-'all' value in empty message
 * - Priority icon branches (>=3, >=2, >=1, <1)
 * - Status badge default branch
 * - Task without assignment
 * - Task with is_labeled flag
 * - Task using inner_id vs id fallback
 * - Pagination visibility (totalPages > 1)
 * - Fetch error branch
 * - localStorage set for task id on startAnnotating
 */

/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useProjectStore } from '@/stores/projectStore'
import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useParams, useRouter } from 'next/navigation'

// Mock navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
  })),
  useParams: jest.fn(() => ({ id: 'proj-1' })),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/'),
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

jest.mock('@/stores/projectStore', () => ({
  useProjectStore: jest.fn(),
}))

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

jest.mock('@/components/shared', () => {
  const React = require('react')
  return {
    HeroPattern: () => React.createElement('div'),
    GridPattern: () => React.createElement('div'),
    Button: ({ children, ...props }: any) => React.createElement('button', props, children),
    ResponsiveContainer: ({ children }: any) => React.createElement('div', null, children),
    LoadingSpinner: () => React.createElement('div', null, 'Loading...'),
    EmptyState: ({ message }: any) => React.createElement('div', null, message),
    Spinner: () => React.createElement('div', null, 'Loading...'),
  }
})

// Mock fetch
global.fetch = jest.fn()

// Translations
const translations: Record<string, string> = {
  'navigation.dashboard': 'Dashboard',
  'navigation.projects': 'Projects',
  'navigation.myTasks': 'My Tasks',
  'common.loadingProject': 'Loading project...',
  'common.previous': 'Previous',
  'common.next': 'Next',
  'common.pageOf': 'Page {page} of {totalPages}',
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
  'tasks.myTasks.noTasksWithStatus': 'No tasks with status: {status}',
  'tasks.myTasks.taskPrefix': 'Task',
  'tasks.myTasks.labeled': 'Labeled',
  'tasks.myTasks.due': 'Due',
}

import MyTasksPage from '../page'

describe('MyTasksPage - branch coverage', () => {
  const mockPush = jest.fn()
  const mockFetchProject = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue({ push: mockPush })
    ;(useParams as jest.Mock).mockReturnValue({ id: 'proj-1' })
    ;(useAuth as jest.Mock).mockReturnValue({
      user: { id: 'u1', username: 'test', email: 'test@example.com' },
    })
    ;(useI18n as jest.Mock).mockReturnValue({
      t: (key: string, vars?: any) => {
        const translation = translations[key] || key
        if (vars) {
          return Object.entries(vars).reduce(
            (acc, [k, v]) => acc.replace(`{${k}}`, String(v)),
            translation
          )
        }
        return translation
      },
    })
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: { id: 'proj-1', title: 'Test Project' },
      loading: false,
      fetchProject: mockFetchProject,
    })
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          tasks: [],
          total: 0,
          page: 1,
          page_size: 20,
          pages: 1,
        }),
    })
  })

  it('shows loading spinner when projectLoading is true', () => {
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: null,
      loading: true,
      fetchProject: mockFetchProject,
    })

    render(<MyTasksPage />)
    expect(screen.getByText('Loading project...')).toBeInTheDocument()
  })

  it('shows loading spinner when currentProject is null', () => {
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: null,
      loading: false,
      fetchProject: mockFetchProject,
    })

    render(<MyTasksPage />)
    expect(screen.getByText('Loading project...')).toBeInTheDocument()
  })

  it('shows empty tasks message with "all" filter', async () => {
    render(<MyTasksPage />)

    await waitFor(() => {
      // When statusFilter is 'all', both h3 and p show noTasks text
      const elements = screen.getAllByText('No tasks assigned yet')
      expect(elements.length).toBeGreaterThanOrEqual(2)
    })
  })

  it('shows error toast when fetch fails', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      status: 500,
    })

    render(<MyTasksPage />)

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith('Failed to load tasks', 'error')
    })
  })

  it('renders tasks with high priority (>=3) icon', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          tasks: [
            {
              id: '1',
              inner_id: 42,
              assignment: {
                status: 'assigned',
                priority: 3,
                assigned_at: '2024-01-01T10:00:00Z',
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
          pages: 1,
        }),
    })

    render(<MyTasksPage />)

    await waitFor(() => {
      // Uses inner_id when available
      expect(screen.getByText('Task #42')).toBeInTheDocument()
    })
  })

  it('renders tasks with medium priority (>=2, <3) icon', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          tasks: [
            {
              id: '2',
              assignment: {
                status: 'in_progress',
                priority: 2,
                assigned_at: '2024-01-01T10:00:00Z',
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
          pages: 1,
        }),
    })

    render(<MyTasksPage />)

    await waitFor(() => {
      expect(screen.getByText('Task #2')).toBeInTheDocument()
      expect(screen.getAllByText('In Progress').length).toBeGreaterThanOrEqual(1)
    })
  })

  it('renders tasks with low priority (>=1, <2) icon', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          tasks: [
            {
              id: '3',
              assignment: {
                status: 'completed',
                priority: 1,
                assigned_at: '2024-01-01T10:00:00Z',
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
          pages: 1,
        }),
    })

    render(<MyTasksPage />)

    await waitFor(() => {
      expect(screen.getByText('Task #3')).toBeInTheDocument()
      expect(screen.getAllByText('Completed').length).toBeGreaterThanOrEqual(1)
    })
  })

  it('renders tasks with zero priority (no icon)', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          tasks: [
            {
              id: '4',
              assignment: {
                status: 'skipped',
                priority: 0,
                assigned_at: '2024-01-01T10:00:00Z',
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
          pages: 1,
        }),
    })

    render(<MyTasksPage />)

    await waitFor(() => {
      expect(screen.getByText('Task #4')).toBeInTheDocument()
      expect(screen.getAllByText('Skipped').length).toBeGreaterThanOrEqual(1)
    })
  })

  it('renders default status badge for unknown status', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          tasks: [
            {
              id: '5',
              assignment: {
                status: 'custom_status',
                priority: 0,
                assigned_at: '2024-01-01T10:00:00Z',
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
          pages: 1,
        }),
    })

    render(<MyTasksPage />)

    await waitFor(() => {
      expect(screen.getByText('custom_status')).toBeInTheDocument()
    })
  })

  it('shows is_labeled badge when task is labeled', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          tasks: [
            {
              id: '6',
              is_labeled: true,
              assignment: {
                status: 'completed',
                priority: 0,
                assigned_at: '2024-01-01T10:00:00Z',
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
          pages: 1,
        }),
    })

    render(<MyTasksPage />)

    await waitFor(() => {
      expect(screen.getByText('Labeled')).toBeInTheDocument()
    })
  })

  it('renders task without assignment (no status badge, no priority)', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          tasks: [{ id: '7' }],
          total: 1,
          page: 1,
          page_size: 20,
          pages: 1,
        }),
    })

    render(<MyTasksPage />)

    await waitFor(() => {
      expect(screen.getByText('Task #7')).toBeInTheDocument()
      expect(screen.getByTestId('my-tasks-list')).toBeInTheDocument()
    })
  })

  it('renders task with due_date in assignment', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          tasks: [
            {
              id: '8',
              assignment: {
                status: 'assigned',
                priority: 0,
                assigned_at: '2024-01-01T10:00:00Z',
                due_date: '2024-12-31T23:59:59Z',
                notes: 'Note text here',
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
          pages: 1,
        }),
    })

    render(<MyTasksPage />)

    await waitFor(() => {
      expect(screen.getByText('Note text here')).toBeInTheDocument()
    })
  })

  it('renders pagination when totalPages > 1', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          tasks: [{ id: '1', assignment: { status: 'assigned', priority: 0, assigned_at: '2024-01-01T10:00:00Z' } }],
          total: 40,
          page: 1,
          page_size: 20,
          pages: 2,
        }),
    })

    render(<MyTasksPage />)

    await waitFor(() => {
      expect(screen.getByText('Previous')).toBeInTheDocument()
      expect(screen.getByText('Next')).toBeInTheDocument()
      expect(screen.getByText('Page 1 of 2')).toBeInTheDocument()
    })
  })

  it('navigates to label page and sets localStorage on task click', async () => {
    const setItemSpy = jest.spyOn(Storage.prototype, 'setItem')

    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          tasks: [{ id: 'task-99' }],
          total: 1,
          page: 1,
          page_size: 20,
          pages: 1,
        }),
    })

    const user = userEvent.setup()
    render(<MyTasksPage />)

    await waitFor(() => {
      expect(screen.getByText('Task #task-99')).toBeInTheDocument()
    })

    const card = screen.getByText('Task #task-99').closest('[class*="cursor-pointer"]')
    await user.click(card!)

    expect(setItemSpy).toHaveBeenCalledWith('benger_task_id_proj-1', 'task-99')
    expect(mockPush).toHaveBeenCalledWith('/projects/proj-1/label')

    setItemSpy.mockRestore()
  })

  it('fetches project when currentProject does not match', () => {
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: { id: 'different-project', title: 'Other' },
      loading: false,
      fetchProject: mockFetchProject,
    })

    render(<MyTasksPage />)

    expect(mockFetchProject).toHaveBeenCalledWith('proj-1')
  })
})
