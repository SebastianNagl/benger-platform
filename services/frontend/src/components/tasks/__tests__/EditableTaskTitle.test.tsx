import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EditableTaskTitle } from '../EditableTaskTitle'

// Mock the dependencies
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'tasks.editTitle.enterTaskName': 'Enter task name',
        'tasks.editTitle.clickToEdit': 'Click to edit task name',
        'tasks.editTitle.editTaskName': 'Edit task name',
        'tasks.editTitle.taskNameEmpty': 'Task name cannot be empty',
        'tasks.editTitle.taskRenamed': 'Task renamed successfully',
        'tasks.editTitle.taskRenameFailed': 'Failed to rename task',
      }
      return translations[key] || key
    },
    locale: 'en',
    isReady: true,
  }),
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

const mockUseAuth = require('@/contexts/AuthContext').useAuth
const mockUseToast = require('@/components/shared/Toast').useToast
const mockApi = require('@/lib/api').api

describe('EditableTaskTitle', () => {
  const mockTask = {
    id: '1',
    name: 'Test Task',
    created_by: 'user-1',
  }

  const mockAddToast = jest.fn()
  const mockOnTaskUpdated = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    mockUseToast.mockReturnValue({ addToast: mockAddToast })
  })

  describe('rendering', () => {
    it('renders task title for non-editable users', () => {
      mockUseAuth.mockReturnValue({
        user: { id: 'other-user', is_superadmin: false },
      })

      render(<EditableTaskTitle task={mockTask} />)

      expect(screen.getByText('Test Task')).toBeInTheDocument()
      expect(screen.queryByLabelText('Edit task name')).not.toBeInTheDocument()
    })

    it('renders editable title for admin users', () => {
      mockUseAuth.mockReturnValue({
        user: { id: 'admin-user', is_superadmin: true },
      })

      render(<EditableTaskTitle task={mockTask} />)

      expect(screen.getByText('Test Task')).toBeInTheDocument()
      expect(screen.getByLabelText('Edit task name')).toBeInTheDocument()
    })

    it('renders editable title for task creator', () => {
      mockUseAuth.mockReturnValue({
        user: { id: 'user-1', is_superadmin: false },
      })

      render(<EditableTaskTitle task={mockTask} />)

      expect(screen.getByText('Test Task')).toBeInTheDocument()
      expect(screen.getByLabelText('Edit task name')).toBeInTheDocument()
    })

    it('applies custom className', () => {
      mockUseAuth.mockReturnValue({
        user: { id: 'user-1', is_superadmin: false },
      })

      const { container } = render(
        <EditableTaskTitle task={mockTask} className="custom-class" />
      )

      expect(container.firstChild).toHaveClass('custom-class')
    })
  })

  describe('editing functionality', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: { id: 'user-1', is_superadmin: false },
      })
    })

    it('enters edit mode when clicking the title', async () => {
      const user = userEvent.setup()
      render(<EditableTaskTitle task={mockTask} />)

      await user.click(screen.getByText('Test Task'))

      expect(screen.getByDisplayValue('Test Task')).toBeInTheDocument()
      expect(screen.queryByText('Test Task')).not.toBeInTheDocument()
    })

    it('enters edit mode when clicking the edit button', async () => {
      const user = userEvent.setup()
      render(<EditableTaskTitle task={mockTask} />)

      await user.click(screen.getByLabelText('Edit task name'))

      expect(screen.getByDisplayValue('Test Task')).toBeInTheDocument()
    })

    it('focuses and selects text when entering edit mode', async () => {
      const user = userEvent.setup()
      render(<EditableTaskTitle task={mockTask} />)

      await user.click(screen.getByText('Test Task'))

      const input = screen.getByDisplayValue('Test Task')
      expect(input).toHaveFocus()
    })

    it('saves changes on Enter key press', async () => {
      const user = userEvent.setup()
      const updatedTask = { ...mockTask, name: 'Updated Task' }
      mockApi.updateTask.mockResolvedValue(updatedTask)

      render(
        <EditableTaskTitle task={mockTask} onTaskUpdated={mockOnTaskUpdated} />
      )

      await user.click(screen.getByText('Test Task'))
      const input = screen.getByDisplayValue('Test Task')

      await user.clear(input)
      await user.type(input, 'Updated Task')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(mockApi.updateTask).toHaveBeenCalledWith('1', {
          name: 'Updated Task',
        })
      })
    })

    it('cancels changes on Escape key press', async () => {
      const user = userEvent.setup()
      render(<EditableTaskTitle task={mockTask} />)

      await user.click(screen.getByText('Test Task'))
      const input = screen.getByDisplayValue('Test Task')

      await user.clear(input)
      await user.type(input, 'Modified Task')
      await user.keyboard('{Escape}')

      await waitFor(() => {
        expect(screen.getByText('Test Task')).toBeInTheDocument()
      })
      expect(mockApi.updateTask).not.toHaveBeenCalled()
    })

    it('saves changes on blur', async () => {
      const user = userEvent.setup()
      const updatedTask = { ...mockTask, name: 'Blurred Task' }
      mockApi.updateTask.mockResolvedValue(updatedTask)

      render(<EditableTaskTitle task={mockTask} />)

      await user.click(screen.getByText('Test Task'))
      const input = screen.getByDisplayValue('Test Task')

      await user.clear(input)
      await user.type(input, 'Blurred Task')

      // Trigger blur by focusing another element
      fireEvent.blur(input)

      await waitFor(() => {
        expect(mockApi.updateTask).toHaveBeenCalledWith('1', {
          name: 'Blurred Task',
        })
      })
    })

    it('shows error toast for empty task name', async () => {
      const user = userEvent.setup()
      render(<EditableTaskTitle task={mockTask} />)

      await user.click(screen.getByText('Test Task'))
      const input = screen.getByDisplayValue('Test Task')

      await user.clear(input)
      await user.keyboard('{Enter}')

      expect(mockAddToast).toHaveBeenCalledWith(
        'Task name cannot be empty',
        'error'
      )
      expect(mockApi.updateTask).not.toHaveBeenCalled()
    })

    it('does not save if name unchanged', async () => {
      const user = userEvent.setup()
      render(<EditableTaskTitle task={mockTask} />)

      await user.click(screen.getByText('Test Task'))
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(screen.getByText('Test Task')).toBeInTheDocument()
      })
      expect(mockApi.updateTask).not.toHaveBeenCalled()
    })

    it('calls onTaskUpdated when task is successfully updated', async () => {
      const user = userEvent.setup()
      const updatedTask = { ...mockTask, name: 'New Name' }
      mockApi.updateTask.mockResolvedValue(updatedTask)

      render(
        <EditableTaskTitle task={mockTask} onTaskUpdated={mockOnTaskUpdated} />
      )

      await user.click(screen.getByText('Test Task'))
      const input = screen.getByDisplayValue('Test Task')

      await user.clear(input)
      await user.type(input, 'New Name')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(mockOnTaskUpdated).toHaveBeenCalledWith(updatedTask)
      })
    })

    it('shows success toast when task is updated', async () => {
      const user = userEvent.setup()
      const updatedTask = { ...mockTask, name: 'New Name' }
      mockApi.updateTask.mockResolvedValue(updatedTask)

      render(<EditableTaskTitle task={mockTask} />)

      await user.click(screen.getByText('Test Task'))
      const input = screen.getByDisplayValue('Test Task')

      await user.clear(input)
      await user.type(input, 'New Name')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Task renamed successfully',
          'success'
        )
      })
    })

    it('handles API error gracefully', async () => {
      const user = userEvent.setup()
      const error = new Error('API Error')
      mockApi.updateTask.mockRejectedValue(error)

      render(<EditableTaskTitle task={mockTask} />)

      await user.click(screen.getByText('Test Task'))
      const input = screen.getByDisplayValue('Test Task')

      await user.clear(input)
      await user.type(input, 'Failed Update')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to rename task: API Error',
          'error'
        )
      })
    })

    it('disables input while submitting', async () => {
      const user = userEvent.setup()
      // Make API call hang
      mockApi.updateTask.mockImplementation(() => new Promise(() => {}))

      render(<EditableTaskTitle task={mockTask} />)

      await user.click(screen.getByText('Test Task'))
      const input = screen.getByDisplayValue('Test Task')

      await user.clear(input)
      await user.type(input, 'Submitting')
      await user.keyboard('{Enter}')

      // Input should be disabled while submitting
      expect(input).toBeDisabled()
    })

    it('trims whitespace from task name', async () => {
      const user = userEvent.setup()
      const updatedTask = { ...mockTask, name: 'Trimmed Task' }
      mockApi.updateTask.mockResolvedValue(updatedTask)

      render(<EditableTaskTitle task={mockTask} />)

      await user.click(screen.getByText('Test Task'))
      const input = screen.getByDisplayValue('Test Task')

      await user.clear(input)
      await user.type(input, '  Trimmed Task  ')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(mockApi.updateTask).toHaveBeenCalledWith('1', {
          name: 'Trimmed Task',
        })
      })
    })
  })

  describe('permissions', () => {
    it('does not allow editing for unauthorized users', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({
        user: { id: 'other-user', is_superadmin: false },
      })

      render(<EditableTaskTitle task={mockTask} />)

      await user.click(screen.getByText('Test Task'))

      // Should not enter edit mode
      expect(screen.queryByDisplayValue('Test Task')).not.toBeInTheDocument()
      expect(screen.getByText('Test Task')).toBeInTheDocument()
    })

    it('shows hover styles only for editable titles', () => {
      mockUseAuth.mockReturnValue({
        user: { id: 'user-1', is_superadmin: false },
      })

      const { rerender } = render(<EditableTaskTitle task={mockTask} />)
      const title = screen.getByText('Test Task')
      expect(title).toHaveClass('cursor-pointer')

      mockUseAuth.mockReturnValue({
        user: { id: 'other-user', is_superadmin: false },
      })

      rerender(<EditableTaskTitle task={mockTask} />)
      const nonEditableTitle = screen.getByText('Test Task')
      expect(nonEditableTitle).not.toHaveClass('cursor-pointer')
    })
  })
})
