/**
 * Comprehensive tests for Task Detail/Annotation Page
 * Tests rendering, data fetching, editing, error handling, and permissions
 *
 * Coverage target: 90%+
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { projectsAPI } from '@/lib/api/projects'
import { useProjectStore } from '@/stores/projectStore'
import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'
import TaskDetailPage from '../page'

// Mock Next.js navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

// Mock contexts
jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')

// Mock stores
jest.mock('@/stores/projectStore')

// Mock API
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    getTask: jest.fn(),
    getTaskAnnotations: jest.fn(),
    updateTaskData: jest.fn(),
  },
}))

// Mock components
jest.mock('@/components/auth/ProtectedRoute', () => ({
  ProtectedRoute: ({ children }: any) => <div>{children}</div>,
}))

// Mock Toast with stable function references
const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: mockAddToast,
  }),
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <div data-testid="breadcrumb">
      {items.map((item: any, i: number) => (
        <span key={i}>{item.label}</span>
      ))}
    </div>
  ),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({
    children,
    onClick,
    disabled,
    className,
    variant,
    ...props
  }: any) => (
    <button
      onClick={onClick}
      disabled={disabled}
      className={className}
      data-variant={variant}
      {...props}
    >
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/Textarea', () => ({
  Textarea: (props: any) => <textarea {...props} />,
}))

const mockRouter = {
  push: jest.fn(),
  back: jest.fn(),
  replace: jest.fn(),
  forward: jest.fn(),
  refresh: jest.fn(),
  prefetch: jest.fn(),
}

const mockUser = {
  id: 'user-123',
  username: 'testuser',
  email: 'test@example.com',
  role: 'annotator',
  is_superadmin: false,
}

const mockSuperadmin = {
  ...mockUser,
  is_superadmin: true,
}

const mockProject = {
  id: 'project-123',
  title: 'Test Project',
  description: 'Test project description',
  created_by: 'user-123',
  show_skip_button: true,
}

const mockTask = {
  id: 'task-456',
  project_id: 'project-123',
  data: {
    text: 'This is sample task text',
    metadata: 'Some metadata',
  },
  is_labeled: false,
  total_annotations: 0,
  cancelled_annotations: 0,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-02T00:00:00Z',
}

const mockTaskWithAnnotations = {
  ...mockTask,
  is_labeled: true,
  total_annotations: 2,
}

const mockAnnotations = [
  {
    id: 'annotation-1',
    task_id: 456,
    project_id: 'project-123',
    completed_by: 'user-123',
    result: [
      {
        value: { text: ['Label1'] },
        from_name: 'label',
        to_name: 'text',
        type: 'choices',
      },
    ],
    was_cancelled: false,
    ground_truth: false,
    created_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'annotation-2',
    task_id: 456,
    project_id: 'project-123',
    completed_by: 'user-456',
    result: [
      {
        value: { text: ['Label2'] },
        from_name: 'label',
        to_name: 'text',
        type: 'choices',
      },
    ],
    was_cancelled: false,
    ground_truth: false,
    created_at: '2024-01-02T00:00:00Z',
  },
]

// Translation map for tests
const translations: Record<string, string> = {
  'tasks.detail.loading': 'Loading...',
  'tasks.detail.notFound': 'Task not found',
  'tasks.detail.notFoundDescription':
    "The task you're looking for doesn't exist.",
  'tasks.detail.backToDataManager': 'Back to Data Manager',
  'tasks.detail.taskData': 'Task Data',
  'tasks.detail.edit': 'Edit',
  'tasks.detail.save': 'Save',
  'tasks.detail.saving': 'Saving...',
  'tasks.detail.cancel': 'Cancel',
  'tasks.detail.editDataPlaceholder': 'Enter valid JSON data...',
  'tasks.detail.editHelpText': 'Edit the task data in JSON format',
  'tasks.detail.status': 'Status',
  'tasks.detail.labeled': 'Labeled',
  'tasks.detail.unlabeled': 'Unlabeled',
  'tasks.detail.annotations': 'Annotations',
  'tasks.detail.startLabeling': 'Start Labeling',
  'tasks.detail.viewAnnotations': 'View Annotations',
  'tasks.detail.skipTask': 'Skip Task',
  'tasks.detail.existingAnnotations': 'Existing Annotations',
  'tasks.detail.dataUpdated': 'Task data updated successfully',
  'tasks.detail.invalidJson': 'Invalid JSON format. Please check your syntax.',
  'tasks.detail.dataUpdateFailed': 'Failed to update task data',
  'tasks.detail.taskBreadcrumb': 'Task {id}',
  'tasks.detail.taskHeading': 'Task #{id}',
  'tasks.detail.generations': 'Generations',
  'tasks.detail.annotationCount': 'This task has {count} annotations',
  'tasks.detail.loadFailed': 'Failed to load task',
  'tasks.detail.noAnnotationsAvailable': 'No annotations available',
  'tasks.detail.taskIdNotAvailable': 'Task ID not available',
  'tasks.detail.loadAnnotationsFailed': 'Failed to load annotations',
  'tasks.detail.projectOrTaskIdNotAvailable': 'Project or task ID not available',
  'navigation.projects': 'Projects',
}

describe('TaskDetailPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockAddToast.mockClear()

    // Mock router
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)

    // Mock auth
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockUser,
    })

    // Mock i18n
    ;(useI18n as jest.Mock).mockReturnValue({
      t: (key: string, vars?: any) => {
        const translation = translations[key] || key
        if (vars) {
          return translation.replace(/\{(\w+)\}/g, (_, k) => vars[k] || '')
        }
        return translation
      },
    })

    // Mock project store
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: mockProject,
      fetchProject: jest.fn(),
    })

    // Mock API calls
    ;(projectsAPI.getTask as jest.Mock).mockResolvedValue(mockTask)
    ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue(
      mockAnnotations
    )
    ;(projectsAPI.updateTaskData as jest.Mock).mockResolvedValue(mockTask)
  })

  describe('Page Rendering', () => {
    it('renders task detail page with task ID', async () => {
      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText(/Task #task-456/)).toBeInTheDocument()
      })
    })

    it('displays loading state initially', async () => {
      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })

    it('displays breadcrumb navigation', async () => {
      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        const breadcrumb = screen.getByTestId('breadcrumb')
        expect(breadcrumb).toBeInTheDocument()
        expect(breadcrumb).toHaveTextContent('Projects')
        expect(breadcrumb).toHaveTextContent('Data Manager')
        expect(breadcrumb).toHaveTextContent('Task task-456')
      })
    })

    it('displays task data in JSON format', async () => {
      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText(/This is sample task text/)).toBeInTheDocument()
        expect(screen.getByText(/Some metadata/)).toBeInTheDocument()
      })
    })

    it('displays task status badge', async () => {
      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Status:')).toBeInTheDocument()
        expect(screen.getByText('Unlabeled')).toBeInTheDocument()
      })
    })

    it('displays labeled status for labeled tasks', async () => {
      ;(projectsAPI.getTask as jest.Mock).mockResolvedValue(
        mockTaskWithAnnotations
      )

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Labeled')).toBeInTheDocument()
      })
    })

    it('displays annotation counts', async () => {
      ;(projectsAPI.getTask as jest.Mock).mockResolvedValue(
        mockTaskWithAnnotations
      )

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText(/Annotations: 2/)).toBeInTheDocument()
      })
    })
  })

  describe('Data Fetching', () => {
    it('fetches task on mount', async () => {
      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(projectsAPI.getTask).toHaveBeenCalledWith('task-456')
      })
    })

    it('fetches project if not loaded', async () => {
      const mockFetchProject = jest.fn()
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: null,
        fetchProject: mockFetchProject,
      })

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(mockFetchProject).toHaveBeenCalledWith('project-123')
      })
    })

    it('does not refetch project if already loaded', async () => {
      const mockFetchProject = jest.fn()
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: mockProject,
        fetchProject: mockFetchProject,
      })

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(projectsAPI.getTask).toHaveBeenCalled()
      })

      expect(mockFetchProject).not.toHaveBeenCalled()
    })
  })

  describe('Error Handling', () => {
    it('shows error message when task fails to load', async () => {
      ;(projectsAPI.getTask as jest.Mock).mockRejectedValue(
        new Error('Task not found')
      )

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Task not found')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      expect(
        screen.getByText("The task you're looking for doesn't exist.")
      ).toBeInTheDocument()
    })

    it('shows not found page when task is null', async () => {
      ;(projectsAPI.getTask as jest.Mock).mockResolvedValue(null)

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Task not found')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )
    })

    it('shows back to data manager button on error', async () => {
      ;(projectsAPI.getTask as jest.Mock).mockRejectedValue(
        new Error('Task not found')
      )

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Back to Data Manager')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )
    })

    it('handles missing task ID gracefully', async () => {
      const params = Promise.resolve({ id: 'project-123', taskId: '' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(projectsAPI.getTask).not.toHaveBeenCalled()
      })
    })
  })

  describe('Navigation', () => {
    it('navigates back to data manager from not found page', async () => {
      const user = userEvent.setup()
      ;(projectsAPI.getTask as jest.Mock).mockRejectedValue(
        new Error('Task not found')
      )

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Back to Data Manager')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const backButton = screen.getByText('Back to Data Manager')
      await user.click(backButton)

      expect(mockRouter.push).toHaveBeenCalledWith('/projects/project-123/data')
    })

    it('navigates to labeling page when clicking Start Labeling', async () => {
      const user = userEvent.setup()
      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Start Labeling')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const labelButton = screen.getByText('Start Labeling')
      await user.click(labelButton)

      expect(mockRouter.push).toHaveBeenCalledWith(
        '/projects/project-123/label'
      )
    })
  })

  describe('Annotations', () => {
    it('displays existing annotations section when task has annotations', async () => {
      ;(projectsAPI.getTask as jest.Mock).mockResolvedValue(
        mockTaskWithAnnotations
      )

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Existing Annotations')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      expect(
        screen.getByText(/This task has 2 annotations/)
      ).toBeInTheDocument()
    })

    it('does not show annotations section when task has no annotations', async () => {
      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Task Data')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      expect(screen.queryByText('Existing Annotations')).not.toBeInTheDocument()
    })

    it('loads annotations when clicking View Annotations', async () => {
      const user = userEvent.setup()
      ;(projectsAPI.getTask as jest.Mock).mockResolvedValue(
        mockTaskWithAnnotations
      )

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('View Annotations')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const viewButton = screen.getByText('View Annotations')
      await user.click(viewButton)

      await waitFor(() => {
        expect(projectsAPI.getTaskAnnotations).toHaveBeenCalledWith('task-456')
      })
    })

    it('disables View Annotations button when no annotations exist', async () => {
      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          const viewButton = screen.getByText('View Annotations')
          expect(viewButton).toBeDisabled()
        },
        { timeout: 3000 }
      )
    })

    it('shows loading state while fetching annotations', async () => {
      const user = userEvent.setup()
      ;(projectsAPI.getTask as jest.Mock).mockResolvedValue(
        mockTaskWithAnnotations
      )
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(() => resolve(mockAnnotations), 100)
          )
      )

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('View Annotations')).toBeInTheDocument()
      })

      const viewButton = screen.getByText('View Annotations')
      await user.click(viewButton)

      expect(screen.getByText('Loading...')).toBeInTheDocument()

      await waitFor(() => {
        expect(projectsAPI.getTaskAnnotations).toHaveBeenCalled()
      })
    })
  })

  describe('Task Data Editing', () => {
    it('shows edit button for superadmins only', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockSuperadmin,
      })

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })
    })

    it('hides edit button for non-superadmins', async () => {
      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.queryByText('Edit')).not.toBeInTheDocument()
      })
    })

    it('enters edit mode when clicking Edit button', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockSuperadmin,
      })

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      await waitFor(() => {
        const textarea = screen.getByPlaceholderText('Enter valid JSON data...')
        expect(textarea).toBeInTheDocument()
        expect(textarea).toHaveValue(JSON.stringify(mockTask.data, null, 2))
      })
    })

    it('shows Save and Cancel buttons in edit mode', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockSuperadmin,
      })

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      await waitFor(() => {
        expect(screen.getByText('Save')).toBeInTheDocument()
        expect(screen.getByText('Cancel')).toBeInTheDocument()
      })
    })

    it('cancels editing when clicking Cancel button', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockSuperadmin,
      })

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Edit')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      const textarea = await screen.findByPlaceholderText(
        'Enter valid JSON data...'
      )
      await user.clear(textarea)
      await user.paste('{"modified": "data"}')

      const cancelButton = screen.getByText('Cancel')
      await user.click(cancelButton)

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
        expect(
          screen.queryByPlaceholderText('Enter valid JSON data...')
        ).not.toBeInTheDocument()
      })
    })

    it('saves edited task data successfully', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockSuperadmin,
      })

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Edit')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      const textarea = await screen.findByPlaceholderText(
        'Enter valid JSON data...'
      )
      const newData = { text: 'Updated text', newField: 'New value' }
      await user.clear(textarea)
      await user.paste(JSON.stringify(newData))

      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(projectsAPI.updateTaskData).toHaveBeenCalledWith(
          'project-123',
          'task-456',
          newData
        )
      })
    })

    it('shows validation error for invalid JSON', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockSuperadmin,
      })

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Edit')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      const textarea = await screen.findByPlaceholderText(
        'Enter valid JSON data...'
      )
      await user.clear(textarea)
      await user.paste('{invalid json}')

      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      expect(projectsAPI.updateTaskData).not.toHaveBeenCalled()
    })

    it('shows saving state during save operation', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockSuperadmin,
      })
      ;(projectsAPI.updateTaskData as jest.Mock).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(mockTask), 100))
      )

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Edit')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      const textarea = await screen.findByPlaceholderText(
        'Enter valid JSON data...'
      )
      await user.clear(textarea)
      await user.paste('{"test": "data"}')

      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      expect(screen.getByText('Saving...')).toBeInTheDocument()

      await waitFor(() => {
        expect(projectsAPI.updateTaskData).toHaveBeenCalled()
      })
    })

    it('disables buttons while saving', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockSuperadmin,
      })
      ;(projectsAPI.updateTaskData as jest.Mock).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(mockTask), 100))
      )

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Edit')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      const textarea = await screen.findByPlaceholderText(
        'Enter valid JSON data...'
      )
      await user.clear(textarea)
      await user.paste('{"test": "data"}')

      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      const savingButton = screen.getByText('Saving...')
      const cancelButton = screen.getByText('Cancel')

      expect(savingButton).toBeDisabled()
      expect(cancelButton).toBeDisabled()

      await waitFor(() => {
        expect(projectsAPI.updateTaskData).toHaveBeenCalled()
      })
    })
  })

  describe('Action Buttons', () => {
    it('displays Start Labeling button', async () => {
      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Start Labeling')).toBeInTheDocument()
      })
    })

    it('displays Skip Task button when enabled in project', async () => {
      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Skip Task')).toBeInTheDocument()
      })
    })

    it('hides Skip Task button when disabled in project', async () => {
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: {
          ...mockProject,
          show_skip_button: false,
        },
        fetchProject: jest.fn(),
      })

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.queryByText('Skip Task')).not.toBeInTheDocument()
      })
    })
  })

  describe('Params Resolution', () => {
    it('resolves params in useEffect', async () => {
      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(projectsAPI.getTask).toHaveBeenCalledWith('task-456')
      })
    })

    it('handles params resolution errors gracefully', async () => {
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      const params = Promise.reject(new Error('Params resolution failed'))

      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Error resolving params:',
          expect.any(Error)
        )
      })

      consoleErrorSpy.mockRestore()
    })
  })

  describe('API Error Handling', () => {
    it('handles updateTaskData API errors', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockSuperadmin,
      })
      ;(projectsAPI.updateTaskData as jest.Mock).mockRejectedValue({
        message: 'Update failed',
      })

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Edit')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      const textarea = await screen.findByPlaceholderText(
        'Enter valid JSON data...'
      )
      await user.clear(textarea)
      await user.paste('{"test": "data"}')

      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(projectsAPI.updateTaskData).toHaveBeenCalled()
      })
    })

    it('handles getTaskAnnotations API errors', async () => {
      const user = userEvent.setup()
      ;(projectsAPI.getTask as jest.Mock).mockResolvedValue(
        mockTaskWithAnnotations
      )
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockRejectedValue(
        new Error('Failed to load annotations')
      )

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('View Annotations')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const viewButton = screen.getByText('View Annotations')
      await user.click(viewButton)

      await waitFor(() => {
        expect(projectsAPI.getTaskAnnotations).toHaveBeenCalled()
      })
    })
  })

  describe('Project Context', () => {
    it('uses project title in breadcrumb when available', async () => {
      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          const breadcrumb = screen.getByTestId('breadcrumb')
          expect(breadcrumb).toHaveTextContent('Test Project')
        },
        { timeout: 3000 }
      )
    })

    it('uses fallback text in breadcrumb when project not loaded', async () => {
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: null,
        fetchProject: jest.fn(),
      })

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          const breadcrumb = screen.getByTestId('breadcrumb')
          expect(breadcrumb).toHaveTextContent('Project')
        },
        { timeout: 3000 }
      )
    })
  })

  describe('Accessibility', () => {
    it('has proper heading hierarchy', async () => {
      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          const heading = screen.getByRole('heading', {
            name: /Task #task-456/,
          })
          expect(heading).toBeInTheDocument()
        },
        { timeout: 3000 }
      )
    })

    it('provides descriptive button text', async () => {
      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Start Labeling')).toBeInTheDocument()
          expect(screen.getByText('View Annotations')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )
    })
  })

  describe('Edge Cases', () => {
    it('handles missing project ID gracefully', async () => {
      const params = Promise.resolve({ id: '', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Loading...')).toBeInTheDocument()
      })
    })

    it('handles saving edit without project ID or task ID', async () => {
      const user = userEvent.setup()

      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockSuperadmin,
      })

      // Render with null resolvedParams to simulate missing IDs
      const params = Promise.resolve({ id: '', taskId: '' })
      render(<TaskDetailPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Loading...')).toBeInTheDocument()
      })

      // Component should not crash without IDs
      expect(mockAddToast).not.toHaveBeenCalledWith(
        'Project ID or Task ID not available',
        'error'
      )
    })

    it('handles handleCancelEdit being called', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockSuperadmin,
      })

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Edit')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText('Enter valid JSON data...')
        ).toBeInTheDocument()
      })

      const cancelButton = screen.getByText('Cancel')
      await user.click(cancelButton)

      await waitFor(() => {
        expect(
          screen.queryByPlaceholderText('Enter valid JSON data...')
        ).not.toBeInTheDocument()
      })
    })

    it('handles successful save with task update', async () => {
      const user = userEvent.setup()

      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockSuperadmin,
      })

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Edit')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      const textarea = await screen.findByPlaceholderText(
        'Enter valid JSON data...'
      )
      const newData = { updated: 'content' }
      await user.clear(textarea)
      await user.paste(JSON.stringify(newData))

      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(projectsAPI.updateTaskData).toHaveBeenCalled()
        expect(mockAddToast).toHaveBeenCalledWith(
          'Task data updated successfully',
          'success'
        )
      })
    })

    it('handles JSON syntax error on save', async () => {
      const user = userEvent.setup()

      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockSuperadmin,
      })

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Edit')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      const textarea = await screen.findByPlaceholderText(
        'Enter valid JSON data...'
      )
      await user.clear(textarea)
      await user.paste('{invalid json')

      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Invalid JSON format. Please check your syntax.',
          'error'
        )
      })
    })

    it('handles API error on save with message', async () => {
      const user = userEvent.setup()

      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockSuperadmin,
      })
      ;(projectsAPI.updateTaskData as jest.Mock).mockRejectedValue({
        message: 'API Error',
      })

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Edit')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      const textarea = await screen.findByPlaceholderText(
        'Enter valid JSON data...'
      )
      await user.clear(textarea)
      await user.paste('{"valid": "json"}')

      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith('API Error', 'error')
      })
    })

    it('handles API error on save without message', async () => {
      const user = userEvent.setup()

      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockSuperadmin,
      })

      // Error object without a message property (empty object)
      ;(projectsAPI.updateTaskData as jest.Mock).mockRejectedValue({})

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Edit')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      const textarea = await screen.findByPlaceholderText(
        'Enter valid JSON data...'
      )
      await user.clear(textarea)
      await user.paste('{"valid": "json"}')

      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      await waitFor(() => {
        // No message property, so fallback message is used
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to update task data',
          'error'
        )
      })
    })

    it('handles handleStartEdit with no task', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockSuperadmin,
      })
      ;(projectsAPI.getTask as jest.Mock).mockResolvedValue(null)

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      render(<TaskDetailPage params={params} />)

      await waitFor(
        () => {
          expect(screen.getByText('Task not found')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      // Edit button should not be present when task is null
      expect(screen.queryByText('Edit')).not.toBeInTheDocument()
    })
  })
})
