import { Task } from '@/lib/api'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EditableTaskDescription } from '../EditableTaskDescription'

// Mock I18nContext
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'tasks.description.clickToEdit': 'Click to edit description',
        'tasks.description.editDescription': 'Edit description',
        'tasks.description.placeholder': 'Enter task description...',
        'tasks.description.save': 'Save',
        'tasks.description.cancel': 'Cancel',
        'tasks.description.saving': 'Saving...',
        'tasks.description.updated': 'Description updated successfully',
        'tasks.description.updateFailed': params?.message
          ? `Failed to update description: ${params.message}`
          : 'Failed to update description',
        'tasks.description.cannotBeEmpty': 'Task description cannot be empty',
        'tasks.description.saveFailed': 'Failed to update description',
        'tasks.description.editInstructions':
          'Press Ctrl+Enter to save, Escape to cancel, or click outside to save',
      }
      return translations[key] || key
    },
  }),
}))

// Mock dependencies
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(),
}))

jest.mock('@/lib/api', () => ({
  ApiClient: jest.fn().mockImplementation(() => ({
    login: jest.fn(),
    signup: jest.fn(),
    logout: jest.fn(),
    getProfile: jest.fn(),
    getOrganizations: jest.fn(),
    clearCache: jest.fn(),
    getCurrentUser: jest.fn(),
  })),
  api: {
    updateTask: jest.fn(),
  },
}))

// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  PencilIcon: (props: any) => <svg data-testid="pencil-icon" {...props} />,
}))

const mockUseAuth = require('@/contexts/AuthContext').useAuth as jest.Mock
const mockUseToast = require('@/components/shared/Toast').useToast as jest.Mock
const mockApi = require('@/lib/api').api as jest.Mocked<
  typeof import('@/lib/api').api
>

describe('EditableTaskDescription', () => {
  const mockAddToast = jest.fn()
  const mockOnTaskUpdated = jest.fn()

  const baseTask: Task = {
    id: 'task-1',
    title: 'Test Task',
    description: 'This is a test task description with some content.',
    created_by: 'user-1',
    status: 'active',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  } as Task

  const shortDescriptionTask: Task = {
    ...baseTask,
    description: 'Short description',
  }

  const longDescriptionTask: Task = {
    ...baseTask,
    description:
      'This is a very long task description that spans multiple lines and contains a lot of detailed information about what the task should accomplish. It includes specific instructions, requirements, and expectations for the annotators who will be working on this task.',
  }

  const superadminUser = {
    id: 'user-2',
    is_superadmin: true,
    email: 'admin@test.com',
  }

  const regularUser = {
    id: 'user-3',
    is_superadmin: false,
    email: 'user@test.com',
  }

  const taskCreatorUser = {
    id: 'user-1',
    is_superadmin: false,
    email: 'creator@test.com',
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockUseToast.mockReturnValue({ addToast: mockAddToast })
    mockApi.updateTask.mockResolvedValue({
      ...baseTask,
      description: 'Updated description',
    })
  })

  describe('basic rendering', () => {
    it('renders task description', () => {
      mockUseAuth.mockReturnValue({ user: regularUser })

      render(<EditableTaskDescription task={baseTask} />)

      expect(
        screen.getByText('This is a test task description with some content.')
      ).toBeInTheDocument()
    })

    it('preserves whitespace and line breaks in description', () => {
      const taskWithWhitespace = {
        ...baseTask,
        description: 'Line 1\n\nLine 3\n    Indented line',
      }
      mockUseAuth.mockReturnValue({ user: regularUser })

      const { container } = render(
        <EditableTaskDescription task={taskWithWhitespace} />
      )

      const descriptionElement = container.querySelector('.whitespace-pre-wrap')
      expect(descriptionElement).toBeInTheDocument()
      expect(descriptionElement?.textContent).toBe(
        'Line 1\n\nLine 3\n    Indented line'
      )
      expect(descriptionElement).toHaveClass('whitespace-pre-wrap')
    })

    it('applies custom className', () => {
      mockUseAuth.mockReturnValue({ user: regularUser })
      const { container } = render(
        <EditableTaskDescription task={baseTask} className="custom-class" />
      )

      const component = container.querySelector('.custom-class')
      expect(component).toBeInTheDocument()
    })

    it('renders description with correct styling classes', () => {
      mockUseAuth.mockReturnValue({ user: regularUser })

      render(<EditableTaskDescription task={baseTask} />)

      const descriptionElement = screen.getByText(
        'This is a test task description with some content.'
      )
      expect(descriptionElement).toHaveClass('whitespace-pre-wrap')
    })
  })

  describe('permissions - superadmin', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: superadminUser })
    })

    it('shows edit button for superadmin', () => {
      render(<EditableTaskDescription task={baseTask} />)

      expect(screen.getByTestId('pencil-icon')).toBeInTheDocument()
      expect(screen.getByTitle('Edit description')).toBeInTheDocument()
    })

    it('shows clickable description area for superadmin', () => {
      render(<EditableTaskDescription task={baseTask} />)

      const descriptionArea = screen.getByTitle('Click to edit description')
      expect(descriptionArea).toBeInTheDocument()
      expect(descriptionArea).toHaveClass('cursor-pointer')
    })

    it('shows hover effects for superadmin', () => {
      render(<EditableTaskDescription task={baseTask} />)

      const descriptionArea = screen.getByTitle('Click to edit description')
      expect(descriptionArea).toHaveClass(
        'hover:text-zinc-800',
        'dark:hover:text-zinc-200'
      )
    })

    it('enters edit mode when edit button is clicked', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      expect(screen.getByTestId('description-textarea')).toBeInTheDocument()
      expect(
        screen.getByDisplayValue(
          'This is a test task description with some content.'
        )
      ).toBeInTheDocument()
    })

    it('enters edit mode when description area is clicked', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const descriptionArea = screen.getByTitle('Click to edit description')
      await user.click(descriptionArea)

      expect(screen.getByTestId('description-textarea')).toBeInTheDocument()
    })
  })

  describe('permissions - task creator', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: taskCreatorUser })
    })

    it('shows edit functionality for task creator', () => {
      render(<EditableTaskDescription task={baseTask} />)

      expect(screen.getByTestId('pencil-icon')).toBeInTheDocument()
      expect(screen.getByTitle('Edit description')).toBeInTheDocument()
    })

    it('allows task creator to edit description', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      expect(screen.getByTestId('description-textarea')).toBeInTheDocument()
    })
  })

  describe('permissions - regular user', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: regularUser })
    })

    it('hides edit functionality for regular user', () => {
      render(<EditableTaskDescription task={baseTask} />)

      expect(screen.queryByTestId('pencil-icon')).not.toBeInTheDocument()
      expect(screen.queryByTitle('Edit description')).not.toBeInTheDocument()
    })

    it('does not show clickable styling for regular user', () => {
      render(<EditableTaskDescription task={baseTask} />)

      const descriptionElement = screen.getByText(
        'This is a test task description with some content.'
      )
      const parentDiv = descriptionElement.closest('div')
      expect(parentDiv).not.toHaveClass('cursor-pointer')
    })

    it('does not show edit title for regular user', () => {
      render(<EditableTaskDescription task={baseTask} />)

      expect(
        screen.queryByTitle('Click to edit description')
      ).not.toBeInTheDocument()
    })

    it('does not enter edit mode when description is clicked', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const descriptionElement = screen.getByText(
        'This is a test task description with some content.'
      )
      await user.click(descriptionElement)

      expect(
        screen.queryByTestId('description-textarea')
      ).not.toBeInTheDocument()
    })
  })

  describe('permissions - no user', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: null })
    })

    it('hides edit functionality when no user', () => {
      render(<EditableTaskDescription task={baseTask} />)

      expect(screen.queryByTestId('pencil-icon')).not.toBeInTheDocument()
      expect(screen.queryByTitle('Edit description')).not.toBeInTheDocument()
    })

    it('shows description content even without user', () => {
      render(<EditableTaskDescription task={baseTask} />)

      expect(
        screen.getByText('This is a test task description with some content.')
      ).toBeInTheDocument()
    })
  })

  describe('edit mode functionality', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: superadminUser })
    })

    it('shows textarea with current description value', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      expect(textarea).toHaveValue(
        'This is a test task description with some content.'
      )
    })

    it('focuses textarea when entering edit mode', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      expect(textarea).toHaveFocus()
    })

    it('positions cursor at end when entering edit mode', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId(
        'description-textarea'
      ) as HTMLTextAreaElement
      expect(textarea.selectionStart).toBe(textarea.value.length)
      expect(textarea.selectionEnd).toBe(textarea.value.length)
    })

    it('shows help text in edit mode', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      expect(
        screen.getByText(
          'Press Ctrl+Enter to save, Escape to cancel, or click outside to save'
        )
      ).toBeInTheDocument()
    })

    it('auto-resizes textarea height based on content', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId(
        'description-textarea'
      ) as HTMLTextAreaElement
      const initialHeight = textarea.style.height

      // Add more content
      await user.clear(textarea)
      await user.type(textarea, 'Line 1\nLine 2\nLine 3\nLine 4\nLine 5')

      // Auto-resize should have updated the height
      expect(textarea.style.height).toBe(`${textarea.scrollHeight}px`)
    })

    it('updates text value as user types', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, 'Updated description text')

      expect(textarea).toHaveValue('Updated description text')
    })

    it('applies correct styling classes to textarea', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      expect(textarea).toHaveClass(
        'w-full',
        'text-zinc-600',
        'dark:text-zinc-400',
        'bg-transparent',
        'border-2',
        'border-emerald-500',
        'rounded-lg',
        'px-3',
        'py-2',
        'focus:outline-none',
        'focus:ring-2',
        'focus:ring-emerald-500/20',
        'resize-none',
        'min-h-[80px]'
      )
    })
  })

  describe('keyboard shortcuts', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: superadminUser })
    })

    it('saves description when Ctrl+Enter is pressed', async () => {
      const user = userEvent.setup()
      render(
        <EditableTaskDescription
          task={baseTask}
          onTaskUpdated={mockOnTaskUpdated}
        />
      )

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, 'Updated via Ctrl+Enter')

      await user.keyboard('{Control>}{Enter}{/Control}')

      await waitFor(() => {
        expect(mockApi.updateTask).toHaveBeenCalledWith('task-1', {
          description: 'Updated via Ctrl+Enter',
        })
      })
    })

    it('saves description when Cmd+Enter is pressed (Mac)', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, 'Updated via Cmd+Enter')

      await user.keyboard('{Meta>}{Enter}{/Meta}')

      await waitFor(() => {
        expect(mockApi.updateTask).toHaveBeenCalledWith('task-1', {
          description: 'Updated via Cmd+Enter',
        })
      })
    })

    it('cancels edit mode when Escape is pressed', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, 'This should be canceled')

      await user.keyboard('{Escape}')

      // Should exit edit mode without saving
      expect(
        screen.queryByTestId('description-textarea')
      ).not.toBeInTheDocument()
      expect(
        screen.getByText('This is a test task description with some content.')
      ).toBeInTheDocument()
      expect(mockApi.updateTask).not.toHaveBeenCalled()
    })

    it('prevents default behavior for keyboard shortcuts', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')

      // Mock preventDefault to verify it's called
      const preventDefaultSpy = jest.spyOn(Event.prototype, 'preventDefault')

      await user.keyboard('{Control>}{Enter}{/Control}')

      expect(preventDefaultSpy).toHaveBeenCalled()

      preventDefaultSpy.mockRestore()
    })
  })

  describe('blur to save functionality', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: superadminUser })
    })

    it('saves description when textarea loses focus', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, 'Updated via blur')

      // Click outside to trigger blur
      await user.click(document.body)

      await waitFor(() => {
        expect(mockApi.updateTask).toHaveBeenCalledWith('task-1', {
          description: 'Updated via blur',
        })
      })
    })

    it('does not save on blur when already submitting', async () => {
      const user = userEvent.setup()

      // Mock a slow API call
      mockApi.updateTask.mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 1000))
      )

      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, 'Updated content')

      // Trigger save via keyboard
      await user.keyboard('{Control>}{Enter}{/Control}')

      // Immediately trigger blur while still submitting
      fireEvent.blur(textarea)

      // Should only call updateTask once
      await waitFor(() => {
        expect(mockApi.updateTask).toHaveBeenCalledTimes(1)
      })
    })
  })

  describe('save functionality', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: superadminUser })
    })

    it('saves description and exits edit mode on successful update', async () => {
      const user = userEvent.setup()
      render(
        <EditableTaskDescription
          task={baseTask}
          onTaskUpdated={mockOnTaskUpdated}
        />
      )

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, 'Successfully updated description')

      await user.keyboard('{Control>}{Enter}{/Control}')

      await waitFor(() => {
        expect(mockApi.updateTask).toHaveBeenCalledWith('task-1', {
          description: 'Successfully updated description',
        })
      })

      await waitFor(() => {
        expect(
          screen.queryByTestId('description-textarea')
        ).not.toBeInTheDocument()
      })
    })

    it('shows success toast on successful update', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, 'Updated description')

      await user.keyboard('{Control>}{Enter}{/Control}')

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Description updated successfully',
          'success'
        )
      })
    })

    it('calls onTaskUpdated callback with updated task', async () => {
      const user = userEvent.setup()
      const updatedTask = { ...baseTask, description: 'Updated description' }
      mockApi.updateTask.mockResolvedValue(updatedTask)

      render(
        <EditableTaskDescription
          task={baseTask}
          onTaskUpdated={mockOnTaskUpdated}
        />
      )

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, 'Updated description')

      await user.keyboard('{Control>}{Enter}{/Control}')

      await waitFor(() => {
        expect(mockOnTaskUpdated).toHaveBeenCalledWith(updatedTask)
      })
    })

    it('trims whitespace from description before saving', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, '   Trimmed description   ')

      await user.keyboard('{Control>}{Enter}{/Control}')

      await waitFor(() => {
        expect(mockApi.updateTask).toHaveBeenCalledWith('task-1', {
          description: 'Trimmed description',
        })
      })
    })

    it('does not save if description is unchanged', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      // Don't change the description
      await user.keyboard('{Control>}{Enter}{/Control}')

      // Should exit edit mode without calling API
      await waitFor(() => {
        expect(
          screen.queryByTestId('description-textarea')
        ).not.toBeInTheDocument()
      })
      expect(mockApi.updateTask).not.toHaveBeenCalled()
    })

    it('works without onTaskUpdated callback', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, 'Updated without callback')

      await user.keyboard('{Control>}{Enter}{/Control}')

      await waitFor(() => {
        expect(mockApi.updateTask).toHaveBeenCalled()
      })
      // Should not throw error when callback is undefined
    })
  })

  describe('validation', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: superadminUser })
    })

    it('shows error toast for empty description', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)

      await user.keyboard('{Control>}{Enter}{/Control}')

      expect(mockAddToast).toHaveBeenCalledWith(
        'Task description cannot be empty',
        'error'
      )
      expect(mockApi.updateTask).not.toHaveBeenCalled()

      // Should stay in edit mode
      expect(screen.getByTestId('description-textarea')).toBeInTheDocument()
    })

    it('shows error toast for whitespace-only description', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, '   \n\t   ')

      await user.keyboard('{Control>}{Enter}{/Control}')

      expect(mockAddToast).toHaveBeenCalledWith(
        'Task description cannot be empty',
        'error'
      )
      expect(mockApi.updateTask).not.toHaveBeenCalled()
    })
  })

  describe('error handling', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: superadminUser })
    })

    it('shows error toast on API failure', async () => {
      const user = userEvent.setup()
      mockApi.updateTask.mockRejectedValue(new Error('API Error'))

      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, 'Updated description')

      await user.keyboard('{Control>}{Enter}{/Control}')

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to update description: API Error',
          'error'
        )
      })
    })

    it('logs error to console on failure', async () => {
      const user = userEvent.setup()
      const consoleSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})
      mockApi.updateTask.mockRejectedValue(new Error('API Error'))

      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, 'Updated description')

      await user.keyboard('{Control>}{Enter}{/Control}')

      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith(
          'Error updating description:',
          expect.any(Error)
        )
      })

      consoleSpy.mockRestore()
    })

    it('handles non-Error exceptions', async () => {
      const user = userEvent.setup()
      mockApi.updateTask.mockRejectedValue('String error')

      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, 'Updated description')

      await user.keyboard('{Control>}{Enter}{/Control}')

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to update description: Failed to update description',
          'error'
        )
      })
    })

    it('stays in edit mode on API failure', async () => {
      const user = userEvent.setup()
      mockApi.updateTask.mockRejectedValue(new Error('API Error'))

      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, 'Updated description')

      await user.keyboard('{Control>}{Enter}{/Control}')

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalled()
      })

      // Should still be in edit mode
      expect(screen.getByTestId('description-textarea')).toBeInTheDocument()
    })
  })

  describe('loading states', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: superadminUser })
    })

    it('disables textarea during submission', async () => {
      const user = userEvent.setup()

      // Mock a slow API call
      mockApi.updateTask.mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 1000))
      )

      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, 'Updated description')

      await user.keyboard('{Control>}{Enter}{/Control}')

      // Should be disabled during submission
      expect(textarea).toBeDisabled()
    })

    it('re-enables textarea after submission completes', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, 'Updated description')

      await user.keyboard('{Control>}{Enter}{/Control}')

      await waitFor(() => {
        expect(
          screen.queryByTestId('description-textarea')
        ).not.toBeInTheDocument()
      })
    })

    it('re-enables textarea after failed submission', async () => {
      const user = userEvent.setup()
      mockApi.updateTask.mockRejectedValue(new Error('API Error'))

      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      await user.clear(textarea)
      await user.type(textarea, 'Updated description')

      await user.keyboard('{Control>}{Enter}{/Control}')

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalled()
      })

      // Should be re-enabled after error
      expect(textarea).not.toBeDisabled()
    })
  })

  describe('styling and layout', () => {
    it('applies group styling for hover effects', () => {
      mockUseAuth.mockReturnValue({ user: superadminUser })
      const { container } = render(<EditableTaskDescription task={baseTask} />)

      const groupContainer = container.querySelector('.group')
      expect(groupContainer).toBeInTheDocument()
      expect(groupContainer).toHaveClass('mt-2')
    })

    it('shows edit button on group hover', () => {
      mockUseAuth.mockReturnValue({ user: superadminUser })
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      expect(editButton).toHaveClass('opacity-0', 'group-hover:opacity-100')
    })

    it('applies correct transition classes', () => {
      mockUseAuth.mockReturnValue({ user: superadminUser })
      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      expect(editButton).toHaveClass('transition-all')

      const descriptionArea = screen.getByTitle('Click to edit description')
      expect(descriptionArea).toHaveClass('transition-colors')
    })

    it('applies correct dark mode classes', () => {
      mockUseAuth.mockReturnValue({ user: regularUser })

      render(<EditableTaskDescription task={baseTask} />)

      const descriptionText = screen.getByText(
        'This is a test task description with some content.'
      )
      expect(descriptionText.closest('div')).toHaveClass(
        'text-zinc-600',
        'dark:text-zinc-400'
      )
    })

    it('applies correct edit button styling', () => {
      mockUseAuth.mockReturnValue({ user: superadminUser })

      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      expect(editButton).toHaveClass(
        'absolute',
        'top-0',
        'right-0',
        'p-1',
        'text-zinc-500',
        'hover:text-zinc-600',
        'dark:text-zinc-400',
        'dark:hover:text-zinc-300'
      )
    })
  })

  describe('dark mode support', () => {
    it('includes dark mode classes for description text', () => {
      mockUseAuth.mockReturnValue({ user: regularUser })

      render(<EditableTaskDescription task={baseTask} />)

      const descriptionArea = screen
        .getByText('This is a test task description with some content.')
        .closest('div')
      expect(descriptionArea).toHaveClass('text-zinc-600', 'dark:text-zinc-400')
    })

    it('includes dark mode classes for editable hover state', () => {
      mockUseAuth.mockReturnValue({ user: superadminUser })

      render(<EditableTaskDescription task={baseTask} />)

      const descriptionArea = screen.getByTitle('Click to edit description')
      expect(descriptionArea).toHaveClass(
        'hover:text-zinc-800',
        'dark:hover:text-zinc-200'
      )
    })

    it('includes dark mode classes for edit button', () => {
      mockUseAuth.mockReturnValue({ user: superadminUser })

      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      expect(editButton).toHaveClass(
        'dark:text-zinc-400',
        'dark:hover:text-zinc-300'
      )
    })

    it('includes dark mode classes for textarea', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({ user: superadminUser })

      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      expect(textarea).toHaveClass('dark:text-zinc-400')
    })
  })

  describe('accessibility', () => {
    it('provides proper button titles and aria labels', () => {
      mockUseAuth.mockReturnValue({ user: superadminUser })

      render(<EditableTaskDescription task={baseTask} />)

      expect(screen.getByTitle('Edit description')).toBeInTheDocument()
      expect(screen.getByTitle('Click to edit description')).toBeInTheDocument()
      expect(screen.getByLabelText('Edit description')).toBeInTheDocument()
    })

    it('provides proper textarea attributes', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({ user: superadminUser })

      render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      const textarea = screen.getByTestId('description-textarea')
      expect(textarea).toHaveAttribute(
        'placeholder',
        'Enter task description...'
      )
      expect(textarea).toHaveAttribute('rows', '3')
    })

    it('provides keyboard navigation', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({ user: superadminUser })

      render(<EditableTaskDescription task={baseTask} />)

      // Tab to edit button
      await user.tab()
      expect(screen.getByTitle('Edit description')).toHaveFocus()

      // Enter to activate
      await user.keyboard('{Enter}')
      expect(screen.getByTestId('description-textarea')).toHaveFocus()
    })
  })

  describe('edge cases', () => {
    it('handles very long descriptions', () => {
      mockUseAuth.mockReturnValue({ user: regularUser })

      render(<EditableTaskDescription task={longDescriptionTask} />)

      expect(
        screen.getByText(longDescriptionTask.description)
      ).toBeInTheDocument()
    })

    it('handles very short descriptions', () => {
      mockUseAuth.mockReturnValue({ user: regularUser })

      render(<EditableTaskDescription task={shortDescriptionTask} />)

      expect(screen.getByText('Short description')).toBeInTheDocument()
    })

    it('handles special characters in description', () => {
      const specialTask = {
        ...baseTask,
        description: 'Description with <>&"\' special chars & symbols',
      }
      mockUseAuth.mockReturnValue({ user: regularUser })

      render(<EditableTaskDescription task={specialTask} />)

      expect(
        screen.getByText('Description with <>&"\' special chars & symbols')
      ).toBeInTheDocument()
    })

    it('handles empty string description', () => {
      const emptyTask = { ...baseTask, description: '' }
      mockUseAuth.mockReturnValue({ user: regularUser })

      const { container } = render(<EditableTaskDescription task={emptyTask} />)

      // Should render without crashing
      const descriptionElement = container.querySelector('.whitespace-pre-wrap')
      expect(descriptionElement).toBeInTheDocument()
      expect(descriptionElement?.textContent).toBe('')
    })

    it('stops propagation on edit button click', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({ user: superadminUser })

      const mockParentClick = jest.fn()

      render(
        <div onClick={mockParentClick}>
          <EditableTaskDescription task={baseTask} />
        </div>
      )

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      // Parent click should not be triggered
      expect(mockParentClick).not.toHaveBeenCalled()
    })

    it('maintains edit state across re-renders', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({ user: superadminUser })

      const { rerender } = render(<EditableTaskDescription task={baseTask} />)

      const editButton = screen.getByTitle('Edit description')
      await user.click(editButton)

      expect(screen.getByTestId('description-textarea')).toBeInTheDocument()

      // Re-render with same props
      rerender(<EditableTaskDescription task={baseTask} />)

      // Should still be in edit mode
      expect(screen.getByTestId('description-textarea')).toBeInTheDocument()
    })
  })
})
