/**
 * Tests for Task Metadata Page - View and edit task metadata
 *
 * Coverage target: 85%+
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock React.use() BEFORE any imports that use it
jest.mock('react', () => {
  const actualReact = jest.requireActual('react')
  return {
    ...actualReact,
    use: jest.fn((value: any) => value),
  }
})

// Mock Next.js navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

// Mock contexts
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import apiClient from '@/lib/api'
import { useProjectStore } from '@/stores/projectStore'
import { useRouter } from 'next/navigation'
import * as React from 'react'
import TaskMetadataPage from '../page'

// Mock stores
jest.mock('@/stores/projectStore')

// Mock API
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    patch: jest.fn(),
  },
}))

// Mock components
jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(),
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
  Button: ({ children, onClick, disabled, variant, className }: any) => (
    <button
      onClick={onClick}
      disabled={disabled}
      data-variant={variant}
      className={className}
    >
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/Textarea', () => ({
  Textarea: (props: any) => <textarea {...props} />,
}))

// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  CheckIcon: () => <div data-testid="check-icon" />,
  PencilIcon: () => <div data-testid="pencil-icon" />,
  XMarkIcon: () => <div data-testid="xmark-icon" />,
}))

const mockRouter = {
  push: jest.fn(),
  back: jest.fn(),
  replace: jest.fn(),
  forward: jest.fn(),
  refresh: jest.fn(),
  prefetch: jest.fn(),
}

const mockAddToast = jest.fn()

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
}

const mockTask = {
  id: 'task-456',
  project_id: 'project-123',
  data: {
    text: 'Sample text',
    field: 'value',
  },
  meta: {
    source: 'test',
    version: '1.0',
    tags: ['tag1', 'tag2'],
  },
  is_labeled: false,
  total_annotations: 0,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-02T00:00:00Z',
}

const mockLabeledTask = {
  ...mockTask,
  is_labeled: true,
  total_annotations: 3,
}

describe('TaskMetadataPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()

    // Setup React.use mock to unwrap promises
    ;(React.use as jest.Mock).mockImplementation((value: any) => {
      if (value && typeof value.then === 'function') {
        // For Promises, return resolved value
        return { id: 'project-123', taskId: 'task-456' }
      }
      return value
    })

    // Mock router
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)

    // Mock auth
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockUser,
    })

    // Mock i18n
    const metadataTranslations: Record<string, string> = {
      'tasks.metadata.loading': 'Loading task...',
      'tasks.metadata.heading': 'Task #{id} - Metadata',
      'tasks.metadata.title': 'Metadata',
      'tasks.metadata.edit': 'Edit',
      'tasks.metadata.save': 'Save',
      'tasks.metadata.saving': 'Saving...',
      'tasks.metadata.cancel': 'Cancel',
      'tasks.metadata.jsonPlaceholder': 'Enter valid JSON data...',
      'tasks.metadata.jsonHelpText': 'Edit the metadata as JSON. Ensure proper JSON formatting.',
      'tasks.metadata.status': 'Status:',
      'tasks.metadata.completed': 'Completed',
      'tasks.metadata.unlabeled': 'Unlabeled',
      'tasks.metadata.annotations': 'Annotations: {count}',
      'tasks.metadata.generations': 'Generations: {count}',
      'tasks.metadata.notFound': 'Task not found',
      'tasks.metadata.notFoundDescription': "The task you're looking for doesn't exist.",
      'tasks.metadata.backToDataManager': 'Back to Data Manager',
      'tasks.metadata.loadFailed': 'Failed to load task',
      'tasks.metadata.updated': 'Metadata updated successfully',
      'tasks.metadata.invalidJson': 'Invalid JSON format. Please check your syntax.',
      'tasks.metadata.updateFailed': 'Failed to update metadata',
    }
    ;(useI18n as jest.Mock).mockReturnValue({
      t: (key: string, params?: Record<string, any>) => {
        let result = metadataTranslations[key] || key
        if (params) {
          Object.entries(params).forEach(([k, v]) => {
            result = result.replace(`{${k}}`, String(v))
          })
        }
        return result
      },
    })

    // Mock toast
    ;(useToast as jest.Mock).mockReturnValue({
      addToast: mockAddToast,
    })

    // Mock project store
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: mockProject,
      fetchProject: jest.fn(),
    })

    // Mock API calls
    ;(apiClient.get as jest.Mock).mockResolvedValue(mockTask)
    ;(apiClient.patch as jest.Mock).mockResolvedValue({ success: true })
  })

  describe('Page Rendering', () => {
    it('renders task metadata page', async () => {
      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(
          screen.getByText(/Task #task-456 - Metadata/)
        ).toBeInTheDocument()
      })
    })

    it('displays loading state initially', async () => {
      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      expect(screen.getByText('Loading task...')).toBeInTheDocument()
    })

    it('displays breadcrumb navigation', async () => {
      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        const breadcrumb = screen.getByTestId('breadcrumb')
        expect(breadcrumb).toBeInTheDocument()
        expect(breadcrumb).toHaveTextContent('navigation.projects')
        expect(breadcrumb).toHaveTextContent('Test Project')
        expect(breadcrumb).toHaveTextContent('navigation.projectData')
        expect(breadcrumb).toHaveTextContent('task-456')
        expect(breadcrumb).toHaveTextContent('navigation.metadata')
      })
    })

    it('displays task metadata in JSON format', async () => {
      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(screen.getByText(/source/)).toBeInTheDocument()
        expect(screen.getByText(/test/)).toBeInTheDocument()
        expect(screen.getByText(/version/)).toBeInTheDocument()
        expect(screen.getByText(/1.0/)).toBeInTheDocument()
      })
    })

    it('displays task status info', async () => {
      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(screen.getByText('Status:')).toBeInTheDocument()
        expect(screen.getByText('Unlabeled')).toBeInTheDocument()
        expect(screen.getByText('Annotations: 0')).toBeInTheDocument()
      })
    })

    it('displays completed status for labeled tasks', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue(mockLabeledTask)

      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(screen.getByText('Completed')).toBeInTheDocument()
        expect(screen.getByText('Annotations: 3')).toBeInTheDocument()
      })
    })

    it('shows edit button', async () => {
      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })
    })
  })

  describe('Data Fetching', () => {
    it('fetches task on mount', async () => {
      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalledWith(
          '/api/projects/tasks/task-456'
        )
      })
    })

    it('fetches project if not loaded', async () => {
      const mockFetchProject = jest.fn()
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: null,
        fetchProject: mockFetchProject,
      })

      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

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

      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalled()
      })

      expect(mockFetchProject).not.toHaveBeenCalled()
    })

    it('handles empty metadata gracefully', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue({
        ...mockTask,
        meta: {},
      })

      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(
          screen.getByText(/Task #task-456 - Metadata/)
        ).toBeInTheDocument()
      })
    })

    it('handles null metadata gracefully', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue({
        ...mockTask,
        meta: null,
      })

      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(
          screen.getByText(/Task #task-456 - Metadata/)
        ).toBeInTheDocument()
      })
    })
  })

  describe('Error Handling', () => {
    it('shows error toast when task fails to load', async () => {
      ;(apiClient.get as jest.Mock).mockRejectedValue(
        new Error('Failed to load')
      )

      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to load task',
          'error'
        )
      })
    })

    it('shows not found page when task is null', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue(null)

      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(screen.getByText('Task not found')).toBeInTheDocument()
        expect(
          screen.getByText("The task you're looking for doesn't exist.")
        ).toBeInTheDocument()
      })
    })

    it('shows back to data manager button on not found', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue(null)

      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(screen.getByText('Back to Data Manager')).toBeInTheDocument()
      })
    })
  })

  describe('Navigation', () => {
    it('navigates back to data manager from not found page', async () => {
      const user = userEvent.setup()
      ;(apiClient.get as jest.Mock).mockResolvedValue(null)

      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(screen.getByText('Back to Data Manager')).toBeInTheDocument()
      })

      const backButton = screen.getByText('Back to Data Manager')
      await user.click(backButton)

      expect(mockRouter.push).toHaveBeenCalledWith('/projects/project-123/data')
    })
  })

  describe('Metadata Editing', () => {
    it('enters edit mode when clicking Edit button', async () => {
      const user = userEvent.setup()
      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      await waitFor(() => {
        const textarea = screen.getByPlaceholderText('Enter valid JSON data...')
        expect(textarea).toBeInTheDocument()
        expect(textarea).toHaveValue(JSON.stringify(mockTask.meta, null, 2))
      })
    })

    it('shows Save and Cancel buttons in edit mode', async () => {
      const user = userEvent.setup()
      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

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
      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })

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

    it('saves edited metadata successfully', async () => {
      const user = userEvent.setup()
      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      const textarea = await screen.findByPlaceholderText(
        'Enter valid JSON data...'
      )
      const newMetadata = { updated: 'metadata', newField: 'value' }
      await user.clear(textarea)
      await user.paste(JSON.stringify(newMetadata))

      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(apiClient.patch).toHaveBeenCalledWith(
          '/api/projects/tasks/task-456/metadata',
          newMetadata
        )
      })

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Metadata updated successfully',
          'success'
        )
      })
    })

    it('shows validation error for invalid JSON', async () => {
      const user = userEvent.setup()
      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      const textarea = await screen.findByPlaceholderText(
        'Enter valid JSON data...'
      )
      await user.clear(textarea)
      await user.paste('{invalid json}')

      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Invalid JSON format. Please check your syntax.',
          'error'
        )
      })

      expect(apiClient.patch).not.toHaveBeenCalled()
    })

    it('shows saving state during save operation', async () => {
      const user = userEvent.setup()
      ;(apiClient.patch as jest.Mock).mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(() => resolve({ success: true }), 100)
          )
      )

      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })

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
        expect(apiClient.patch).toHaveBeenCalled()
      })
    })

    it('disables buttons while saving', async () => {
      const user = userEvent.setup()
      ;(apiClient.patch as jest.Mock).mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(() => resolve({ success: true }), 100)
          )
      )

      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })

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
        expect(apiClient.patch).toHaveBeenCalled()
      })
    })

    it('handles API error during save', async () => {
      const user = userEvent.setup()
      ;(apiClient.patch as jest.Mock).mockRejectedValue({
        message: 'Update failed',
      })

      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })

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
        expect(mockAddToast).toHaveBeenCalledWith('Update failed', 'error')
      })
    })

    it('handles API error without message', async () => {
      const user = userEvent.setup()
      ;(apiClient.patch as jest.Mock).mockRejectedValue(new Error())

      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })

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
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to update metadata',
          'error'
        )
      })
    })

    it('updates local state after successful save', async () => {
      const user = userEvent.setup()
      const newMetadata = { updated: 'metadata' }

      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      const textarea = await screen.findByPlaceholderText(
        'Enter valid JSON data...'
      )
      await user.clear(textarea)
      await user.paste(JSON.stringify(newMetadata))

      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(apiClient.patch).toHaveBeenCalled()
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })
    })
  })

  describe('Project Context', () => {
    it('uses project title in breadcrumb when available', async () => {
      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        const breadcrumb = screen.getByTestId('breadcrumb')
        expect(breadcrumb).toHaveTextContent('Test Project')
      })
    })

    it('uses fallback text in breadcrumb when project not loaded', async () => {
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: null,
        fetchProject: jest.fn(),
      })

      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        const breadcrumb = screen.getByTestId('breadcrumb')
        expect(breadcrumb).toHaveTextContent('Project')
      })
    })
  })

  describe('Edge Cases', () => {
    it('displays help text in edit mode', async () => {
      const user = userEvent.setup()
      const params = { id: 'project-123', taskId: 'task-456' }
      render(<TaskMetadataPage params={Promise.resolve(params)} />)

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      await waitFor(() => {
        expect(
          screen.getByText(
            'Edit the metadata as JSON. Ensure proper JSON formatting.'
          )
        ).toBeInTheDocument()
      })
    })

    it('returns early if no task during save', async () => {
      const user = userEvent.setup()
      ;(apiClient.get as jest.Mock).mockResolvedValue(mockTask)

      const params = Promise.resolve({ id: 'project-123', taskId: 'task-456' })
      const { rerender } = render(<TaskMetadataPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })

      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      // Simulate task becoming null
      ;(apiClient.get as jest.Mock).mockResolvedValue(null)

      const textarea = await screen.findByPlaceholderText(
        'Enter valid JSON data...'
      )
      await user.clear(textarea)
      await user.paste('{"test": "data"}')

      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      // Should not crash
      expect(screen.getByText('Edit')).toBeInTheDocument()
    })
  })
})
