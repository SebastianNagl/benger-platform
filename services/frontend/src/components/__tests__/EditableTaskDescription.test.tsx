/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/api'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useToast } from '../shared/Toast'
import { EditableTaskDescription } from '../tasks/EditableTaskDescription'

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
jest.mock('@/contexts/AuthContext')
jest.mock('../shared/Toast')
jest.mock('@/lib/api')

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>
const mockUseToast = useToast as jest.MockedFunction<typeof useToast>
const mockApi = api as jest.Mocked<typeof api>

const mockAddToast = jest.fn()

// Mock task data
const mockTask = {
  id: 'task-123',
  name: 'Test Task Name',
  description:
    'This is a test task description\nwith multiple lines\nof content.',
  created_by: 'user-123',
  task_type: 'QA',
  template: '<View></View>',
  visibility: 'public',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
}

const mockAdminUser = {
  id: 'admin-123',
  email: 'admin@test.com',
  username: 'admin',
  name: 'Admin User',
  is_superadmin: true,
  is_active: true,
  created_at: '2024-01-01T00:00:00Z',
}

const mockCreatorUser = {
  id: 'user-123',
  email: 'creator@test.com',
  username: 'creator',
  name: 'Creator User',
  is_superadmin: false,
  is_active: true,
  created_at: '2024-01-01T00:00:00Z',
}

const mockRegularUser = {
  id: 'user-456',
  email: 'user@test.com',
  username: 'regularuser',
  name: 'Regular User',
  is_superadmin: false,
  is_active: true,
  created_at: '2024-01-01T00:00:00Z',
}

const mockAuthContext = (user: any = null) => ({
  user,
  login: jest.fn(),
  logout: jest.fn(),
  signup: jest.fn(),
  updateUser: jest.fn(),
  refreshAuth: jest.fn(),
  isLoading: false,
  apiClient: {} as any,
  organizations: [],
  currentOrganization: null,
  setCurrentOrganization: jest.fn(),
  refreshOrganizations: jest.fn(),
})

describe('EditableTaskDescription', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockUseToast.mockReturnValue({
      addToast: mockAddToast,
      removeToast: jest.fn(),
    })
  })

  describe('rendering', () => {
    it('renders task description for non-editable users', async () => {
      mockUseAuth.mockReturnValue(mockAuthContext(mockRegularUser))

      render(<EditableTaskDescription task={mockTask} />)

      expect(
        screen.getByText(/This is a test task description/)
      ).toBeInTheDocument()
      expect(
        screen.queryByRole('button', { name: /edit description/i })
      ).not.toBeInTheDocument()
    })

    it('renders editable description for admin users', async () => {
      mockUseAuth.mockReturnValue(mockAuthContext(mockAdminUser))

      render(<EditableTaskDescription task={mockTask} />)

      expect(
        screen.getByText(/This is a test task description/)
      ).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /edit description/i })
      ).toBeInTheDocument()
    })

    it('renders editable description for task creator', async () => {
      mockUseAuth.mockReturnValue(mockAuthContext(mockCreatorUser))

      render(<EditableTaskDescription task={mockTask} />)

      expect(
        screen.getByText(/This is a test task description/)
      ).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /edit description/i })
      ).toBeInTheDocument()
    })

    it('preserves whitespace and line breaks in description', async () => {
      mockUseAuth.mockReturnValue(mockAuthContext(mockRegularUser))

      const { container } = render(<EditableTaskDescription task={mockTask} />)

      const descriptionElement = container.querySelector('.whitespace-pre-wrap')
      expect(descriptionElement).toBeInTheDocument()
      expect(descriptionElement?.textContent).toBe(mockTask.description)
    })

    it('applies custom className', async () => {
      mockUseAuth.mockReturnValue(mockAuthContext(mockAdminUser))

      const { container } = render(
        <EditableTaskDescription task={mockTask} className="custom-class" />
      )

      expect(container.firstChild).toHaveClass('custom-class')
    })
  })

  describe('editing functionality', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue(mockAuthContext(mockAdminUser))
    })

    it('enters edit mode when clicking the description', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={mockTask} />)

      await user.click(screen.getByText(/This is a test task description/))

      expect(screen.getByTestId('description-textarea')).toHaveValue(
        mockTask.description
      )
      // Check that we're now in edit mode by looking for the keyboard shortcuts hint
      expect(
        screen.getByText(/Press Ctrl\+Enter to save, Escape to cancel/)
      ).toBeInTheDocument()
    })

    it('enters edit mode when clicking the edit button', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={mockTask} />)

      await user.click(
        screen.getByRole('button', { name: /edit description/i })
      )

      expect(screen.getByTestId('description-textarea')).toHaveValue(
        mockTask.description
      )
    })

    it('focuses and positions cursor at end when entering edit mode', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={mockTask} />)

      await user.click(screen.getByText(/This is a test task description/))

      const textarea = screen.getByTestId('description-textarea')
      expect(textarea).toHaveFocus()
    })

    it('shows keyboard shortcuts hint in edit mode', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={mockTask} />)

      await user.click(screen.getByText(/This is a test task description/))

      expect(
        screen.getByText(
          /Press Ctrl\+Enter to save, Escape to cancel, or click outside to save/
        )
      ).toBeInTheDocument()
    })

    it('cancels editing on Escape key', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={mockTask} />)

      await user.click(screen.getByText(/This is a test task description/))
      const textarea = screen.getByTestId('description-textarea')

      await user.clear(textarea)
      await user.type(textarea, 'Modified description')
      await user.keyboard('{Escape}')

      expect(
        screen.getByText(/This is a test task description/)
      ).toBeInTheDocument()
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    })

    it('saves on Ctrl+Enter key combination', async () => {
      const user = userEvent.setup()
      const updatedTask = {
        ...mockTask,
        description: 'Updated description via Ctrl+Enter',
      }
      mockApi.updateTask.mockResolvedValue(updatedTask)

      const mockOnTaskUpdated = jest.fn()
      render(
        <EditableTaskDescription
          task={mockTask}
          onTaskUpdated={mockOnTaskUpdated}
        />
      )

      await user.click(screen.getByText(/This is a test task description/))
      const textarea = screen.getByTestId('description-textarea')

      await user.clear(textarea)
      await user.type(textarea, 'Updated description via Ctrl+Enter')
      await user.keyboard('{Control>}{Enter}{/Control}')

      await waitFor(() => {
        expect(mockApi.updateTask).toHaveBeenCalledWith('task-123', {
          description: 'Updated description via Ctrl+Enter',
        })
      })
    })

    it('saves on Cmd+Enter key combination (Mac)', async () => {
      const user = userEvent.setup()
      const updatedTask = {
        ...mockTask,
        description: 'Updated description via Cmd+Enter',
      }
      mockApi.updateTask.mockResolvedValue(updatedTask)

      render(<EditableTaskDescription task={mockTask} />)

      await user.click(screen.getByText(/This is a test task description/))
      const textarea = screen.getByTestId('description-textarea')

      await user.clear(textarea)
      await user.type(textarea, 'Updated description via Cmd+Enter')
      await user.keyboard('{Meta>}{Enter}{/Meta}')

      await waitFor(() => {
        expect(mockApi.updateTask).toHaveBeenCalledWith('task-123', {
          description: 'Updated description via Cmd+Enter',
        })
      })
    })

    it('saves on blur', async () => {
      const user = userEvent.setup()
      const updatedTask = {
        ...mockTask,
        description: 'Blur updated description',
      }
      mockApi.updateTask.mockResolvedValue(updatedTask)

      render(<EditableTaskDescription task={mockTask} />)

      await user.click(screen.getByText(/This is a test task description/))
      const textarea = screen.getByTestId('description-textarea')

      await user.clear(textarea)
      await user.type(textarea, 'Blur updated description')
      await user.tab() // This will blur the textarea

      await waitFor(() => {
        expect(mockApi.updateTask).toHaveBeenCalledWith('task-123', {
          description: 'Blur updated description',
        })
      })
    })

    it('auto-resizes textarea on input', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={mockTask} />)

      await user.click(screen.getByText(/This is a test task description/))
      const textarea = screen.getByTestId(
        'description-textarea'
      ) as HTMLTextAreaElement

      // Mock scrollHeight to simulate content growth
      Object.defineProperty(textarea, 'scrollHeight', {
        value: 120,
        configurable: true,
      })

      await user.type(
        textarea,
        '\nThis is additional content that should make the textarea grow'
      )

      // The auto-resize functionality sets height to scrollHeight
      expect(textarea.style.height).toBe('120px')
    })
  })

  describe('validation', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue(mockAuthContext(mockAdminUser))
    })

    it('prevents saving empty description', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={mockTask} />)

      await user.click(screen.getByText(/This is a test task description/))
      const textarea = screen.getByTestId('description-textarea')

      await user.clear(textarea)
      await user.keyboard('{Control>}{Enter}{/Control}')

      // API should not be called for empty description
      expect(mockApi.updateTask).not.toHaveBeenCalled()
    })

    it('prevents saving whitespace-only description', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={mockTask} />)

      await user.click(screen.getByText(/This is a test task description/))
      const textarea = screen.getByTestId('description-textarea')

      await user.clear(textarea)
      await user.type(textarea, '   \n\n   ')
      await user.keyboard('{Control>}{Enter}{/Control}')

      // API should not be called for whitespace-only description
      expect(mockApi.updateTask).not.toHaveBeenCalled()
    })

    it('does not save if description is unchanged', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={mockTask} />)

      await user.click(screen.getByText(/This is a test task description/))

      // Don't change the value
      await user.keyboard('{Control>}{Enter}{/Control}')

      expect(mockApi.updateTask).not.toHaveBeenCalled()
      expect(
        screen.getByText(/This is a test task description/)
      ).toBeInTheDocument() // Should exit edit mode
    })

    it('trims whitespace from description', async () => {
      const user = userEvent.setup()
      const updatedTask = { ...mockTask, description: 'Trimmed description' }
      mockApi.updateTask.mockResolvedValue(updatedTask)

      render(<EditableTaskDescription task={mockTask} />)

      await user.click(screen.getByText(/This is a test task description/))
      const textarea = screen.getByTestId('description-textarea')

      await user.clear(textarea)
      await user.type(textarea, '  Trimmed description  ')
      await user.keyboard('{Control>}{Enter}{/Control}')

      await waitFor(() => {
        expect(mockApi.updateTask).toHaveBeenCalledWith('task-123', {
          description: 'Trimmed description',
        })
      })
    })
  })

  describe('error handling', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue(mockAuthContext(mockAdminUser))
    })

    it('prevents blur save during submission', async () => {
      const user = userEvent.setup()
      let resolveUpdate: (value: any) => void
      const updatePromise = new Promise<any>((resolve) => {
        resolveUpdate = resolve
      })
      mockApi.updateTask.mockReturnValue(updatePromise as any)

      render(<EditableTaskDescription task={mockTask} />)

      await user.click(screen.getByText(/This is a test task description/))
      const textarea = screen.getByTestId('description-textarea')

      await user.clear(textarea)
      await user.type(textarea, 'Saving description')
      await user.keyboard('{Control>}{Enter}{/Control}')

      // Try to blur while submitting
      fireEvent.blur(textarea)

      // Should not trigger additional API call
      expect(mockApi.updateTask).toHaveBeenCalledTimes(1)

      // Resolve the promise to complete the test
      resolveUpdate!({ ...mockTask, description: 'Saving description' })
    })
  })

  describe('accessibility', () => {
    it('provides proper hover hints for editable users', async () => {
      mockUseAuth.mockReturnValue(mockAuthContext(mockAdminUser))

      render(<EditableTaskDescription task={mockTask} />)

      const descriptionContainer = screen
        .getByText(/This is a test task description/)
        .closest('div')
      expect(descriptionContainer).toHaveAttribute(
        'title',
        'Click to edit description'
      )
    })

    it('does not provide hover hints for non-editable users', async () => {
      mockUseAuth.mockReturnValue(mockAuthContext(mockRegularUser))

      render(<EditableTaskDescription task={mockTask} />)

      const descriptionContainer = screen
        .getByText(/This is a test task description/)
        .closest('div')
      expect(descriptionContainer).not.toHaveAttribute('title')
    })

    it('provides proper aria labels for edit button', async () => {
      mockUseAuth.mockReturnValue(mockAuthContext(mockAdminUser))

      render(<EditableTaskDescription task={mockTask} />)

      const editButton = screen.getByRole('button', {
        name: /edit description/i,
      })
      expect(editButton).toHaveAttribute('title', 'Edit description')
    })

    it('has proper placeholder text in edit mode', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue(mockAuthContext(mockAdminUser))

      render(<EditableTaskDescription task={mockTask} />)

      await user.click(screen.getByText(/This is a test task description/))

      const textarea = screen.getByPlaceholderText('Enter task description...')
      expect(textarea).toBeInTheDocument()
    })
  })

  describe('no user scenarios', () => {
    it('does not show edit functionality when no user is logged in', async () => {
      mockUseAuth.mockReturnValue(mockAuthContext(null))

      render(<EditableTaskDescription task={mockTask} />)

      expect(
        screen.getByText(/This is a test task description/)
      ).toBeInTheDocument()
      expect(
        screen.queryByRole('button', { name: /edit description/i })
      ).not.toBeInTheDocument()
    })
  })

  describe('enter key behavior', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue(mockAuthContext(mockAdminUser))
    })

    it('allows regular Enter key for new lines', async () => {
      const user = userEvent.setup()
      render(<EditableTaskDescription task={mockTask} />)

      await user.click(screen.getByText(/This is a test task description/))

      // Wait for edit mode to activate and textarea to appear
      const textarea = await screen.findByTestId('description-textarea')

      await user.clear(textarea)
      await user.type(textarea, 'Line 1')
      await user.keyboard('{Enter}')
      await user.type(textarea, 'Line 2')

      expect(textarea).toHaveValue('Line 1\nLine 2')
      expect(mockApi.updateTask).not.toHaveBeenCalled() // Should not save on regular Enter
    })
  })
})
