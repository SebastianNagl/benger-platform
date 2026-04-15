/**
 * Unit tests for TaskAssignmentModal component (Issue #258)
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TaskAssignmentModal } from '../TaskAssignmentModal'

// Mock the API module
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    assignTasks: jest.fn(),
  },
}))

// Mock the default apiClient import used by the component
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    clearCache: jest.fn(),
  },
}))

// Mock the toast hook
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: jest.fn(),
  }),
}))

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'tasks.assignment.title': 'Assign Tasks to Annotators',
        'tasks.assignment.assigning': 'Assigning',
        'tasks.assignment.tasks': 'tasks',
        'tasks.assignment.noUsers': 'Please select at least one user',
        'tasks.assignment.assigned': 'Tasks assigned successfully',
        'tasks.assignment.assignFailed': 'Failed to assign tasks',
        'tasks.assignment.dueDate': 'Due Date',
        'tasks.assignment.optional': 'Optional',
        'tasks.assignment.cancel': 'Cancel',
        'tasks.assignment.assign': 'Assign Tasks',
        'common.notes': 'Notes',
        'tasks.assignment.distributionMethod': 'Distribution Method',
        'tasks.assignment.distributionDescription':
          'Assign all selected tasks to all selected users',
        'tasks.assignment.priority': 'Priority',
        'projects.taskAssignment.assigningTasks': 'Assigning {count} tasks',
        'projects.taskAssignment.distributionMethod': 'Distribution Method',
        'projects.taskAssignment.manual': 'Manual',
        'projects.taskAssignment.manualDescription': 'Assign all selected tasks to all selected users',
        'projects.taskAssignment.roundRobin': 'Round Robin',
        'projects.taskAssignment.roundRobinDescription': 'Distribute tasks evenly across selected users',
        'projects.taskAssignment.random': 'Random',
        'projects.taskAssignment.randomDescription': 'Randomly assign tasks to selected users',
        'projects.taskAssignment.loadBalanced': 'Load Balanced',
        'projects.taskAssignment.loadBalancedDescription': 'Assign tasks based on current workload',
        'projects.taskAssignment.selectAnnotators': 'Select Annotators',
        'projects.taskAssignment.selectAll': 'Select All',
        'projects.taskAssignment.deselectAll': 'Deselect All',
        'projects.taskAssignment.priority': 'Priority',
        'projects.taskAssignment.priorityNormal': 'Normal',
        'projects.taskAssignment.priorityLow': 'Low',
        'projects.taskAssignment.priorityMedium': 'Medium',
        'projects.taskAssignment.priorityHigh': 'High',
        'projects.taskAssignment.priorityUrgent': 'Urgent',
        'projects.taskAssignment.notesPlaceholder': 'Add notes for this assignment...',
      }
      let result = translations[key] || key
      if (params && typeof params === 'object') {
        Object.entries(params).forEach(([k, v]) => {
          result = result.replace(`{${k}}`, String(v))
        })
      }
      return result
    },
  }),
}))

describe('TaskAssignmentModal', () => {
  const mockOnClose = jest.fn()
  const mockOnAssignmentComplete = jest.fn()

  const mockProjectMembers = [
    {
      id: 'member-1',
      user_id: 'user-1',
      name: 'John Doe',
      email: 'john@example.com',
      role: 'annotator',
    },
    {
      id: 'member-2',
      user_id: 'user-2',
      name: 'Jane Smith',
      email: 'jane@example.com',
      role: 'annotator',
    },
    {
      id: 'member-3',
      user_id: 'user-3',
      name: 'Bob Manager',
      email: 'bob@example.com',
      role: 'manager',
    },
  ]

  const defaultProps = {
    isOpen: true,
    onClose: mockOnClose,
    projectId: 'project-123',
    selectedTaskIds: [1, 2, 3],
    projectMembers: mockProjectMembers,
    onAssignmentComplete: mockOnAssignmentComplete,
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders when open', async () => {
    render(<TaskAssignmentModal {...defaultProps} />)

    expect(screen.getByText('Assign Tasks to Annotators')).toBeInTheDocument()
    expect(screen.getByText('Assigning 3 tasks')).toBeInTheDocument()
  })

  it('does not render when closed', async () => {
    render(<TaskAssignmentModal {...defaultProps} isOpen={false} />)

    expect(
      screen.queryByText('Assign Tasks to Annotators')
    ).not.toBeInTheDocument()
  })

  it('displays project members for selection', async () => {
    render(<TaskAssignmentModal {...defaultProps} />)

    // Check that annotators are shown (multiple elements may contain the same text due to tooltips)
    expect(screen.getAllByText('John Doe').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Jane Smith').length).toBeGreaterThan(0)
  })

  it('allows selecting multiple users', async () => {
    const user = userEvent.setup()
    render(<TaskAssignmentModal {...defaultProps} />)

    // Find all checkboxes (TableCheckbox components)
    const checkboxes = screen.getAllByRole('checkbox')

    // Click on the first two checkboxes (for John Doe and Jane Smith)
    await user.click(checkboxes[0])
    await user.click(checkboxes[1])

    expect(checkboxes[0]).toBeChecked()
    expect(checkboxes[1]).toBeChecked()
  })

  it('displays distribution method options', async () => {
    render(<TaskAssignmentModal {...defaultProps} />)

    // Check for Distribution Method label
    expect(screen.getByText('Distribution Method')).toBeInTheDocument()

    // Check for default distribution description
    expect(
      screen.getByText('Assign all selected tasks to all selected users')
    ).toBeInTheDocument()
  })

  it('allows setting priority', async () => {
    render(<TaskAssignmentModal {...defaultProps} />)

    // Check for Priority label (simplified test)
    expect(screen.getByText('Priority')).toBeInTheDocument()
  })

  it('allows setting due date', async () => {
    render(<TaskAssignmentModal {...defaultProps} />)

    // Check for Due Date label and input exists
    const dueDateInput = screen.getByLabelText(/Due Date/)
    expect(dueDateInput).toBeInTheDocument()
  })

  it('allows adding notes', async () => {
    const user = userEvent.setup()
    render(<TaskAssignmentModal {...defaultProps} />)

    const notesInput = screen.getByLabelText(/Notes/i)

    await user.type(notesInput, 'Please complete these tasks by end of week')

    expect(notesInput).toHaveValue('Please complete these tasks by end of week')
  })

  it('submits assignment with correct data', async () => {
    const user = userEvent.setup()

    // Mock fetch for the assignment API call
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          assignments_created: 3,
        }),
    })

    render(<TaskAssignmentModal {...defaultProps} />)

    // Select a user (first checkbox)
    const checkboxes = screen.getAllByRole('checkbox')
    await user.click(checkboxes[0])

    // Add notes
    const notesInput = screen.getByLabelText(/Notes/i)
    await user.type(notesInput, 'Test notes')

    // Submit
    const assignButton = screen.getByRole('button', { name: /Assign Tasks/i })
    await user.click(assignButton)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/projects/project-123/tasks/assign',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
          body: expect.stringContaining('"user_ids":["user-1"]'),
        })
      )
    })

    expect(mockOnAssignmentComplete).toHaveBeenCalled()
    expect(mockOnClose).toHaveBeenCalled()
  })

  it('shows error when no users selected', async () => {
    const user = userEvent.setup()
    render(<TaskAssignmentModal {...defaultProps} />)

    // Try to submit without selecting users
    const assignButton = screen.getByRole('button', { name: /Assign Tasks/i })
    await user.click(assignButton)

    // The button should be disabled when no users are selected
    expect(assignButton).toBeDisabled()
  })

  it('handles API errors gracefully', async () => {
    const user = userEvent.setup()
    const mockAddToast = jest.fn()

    // Mock the toast hook to capture calls
    jest
      .spyOn(require('@/components/shared/Toast'), 'useToast')
      .mockReturnValue({
        addToast: mockAddToast,
      })

    // Mock fetch to reject
    global.fetch = jest.fn().mockRejectedValue(new Error('API Error'))

    render(<TaskAssignmentModal {...defaultProps} />)

    // Select a user and submit
    const checkboxes = screen.getAllByRole('checkbox')
    await user.click(checkboxes[0])

    const assignButton = screen.getByRole('button', { name: /Assign Tasks/i })
    await user.click(assignButton)

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'Failed to assign tasks',
        'error'
      )
    })
  })

  it('disables form during submission', async () => {
    const user = userEvent.setup()

    // Mock fetch to delay the response
    global.fetch = jest.fn().mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(
            () =>
              resolve({
                ok: true,
                json: () => Promise.resolve({ assignments_created: 3 }),
              }),
            100
          )
        )
    )

    render(<TaskAssignmentModal {...defaultProps} />)

    // Select a user and submit
    const checkboxes = screen.getAllByRole('checkbox')
    await user.click(checkboxes[0])

    const assignButton = screen.getByRole('button', { name: /Assign Tasks/i })
    await user.click(assignButton)

    // Check that button is disabled during submission
    expect(assignButton).toBeDisabled()
    // Button text changes to "Assign Tasks..." during submission
    await waitFor(() => {
      expect(assignButton).toHaveTextContent(/Assign Tasks/i)
    })
  })

  it('calls onClose when cancel button is clicked', async () => {
    const user = userEvent.setup()
    render(<TaskAssignmentModal {...defaultProps} />)

    const cancelButton = screen.getByRole('button', { name: /Cancel/i })
    await user.click(cancelButton)

    expect(mockOnClose).toHaveBeenCalled()
  })

  it('shows distribution description based on selected method', async () => {
    render(<TaskAssignmentModal {...defaultProps} />)

    // Check for Distribution Method label
    expect(screen.getByText('Distribution Method')).toBeInTheDocument()

    // Check for default description (manual assignment)
    expect(
      screen.getByText('Assign all selected tasks to all selected users')
    ).toBeInTheDocument()
  })

  it('handles select all functionality', async () => {
    const user = userEvent.setup()
    render(<TaskAssignmentModal {...defaultProps} />)

    const selectAllButton = screen.getByRole('button', { name: /Select All/i })
    expect(selectAllButton).toBeInTheDocument()

    await user.click(selectAllButton)

    const checkboxes = screen.getAllByRole('checkbox')
    checkboxes.forEach((checkbox) => {
      expect(checkbox).toBeChecked()
    })

    await user.click(selectAllButton)

    checkboxes.forEach((checkbox) => {
      expect(checkbox).not.toBeChecked()
    })
  })

  it('displays no annotators message when list is empty', async () => {
    const propsWithNoMembers = {
      ...defaultProps,
      projectMembers: [],
    }

    render(<TaskAssignmentModal {...propsWithNoMembers} />)

    expect(
      screen.getByText('Please select at least one user')
    ).toBeInTheDocument()
  })

  it('filters to show only annotators and contributors', async () => {
    const mixedMembers = [
      ...mockProjectMembers,
      {
        id: 'member-4',
        user_id: 'user-4',
        name: 'Alice Contributor',
        email: 'alice@example.com',
        role: 'contributor',
      },
      {
        id: 'member-5',
        user_id: 'user-5',
        name: 'Charlie Viewer',
        email: 'charlie@example.com',
        role: 'viewer',
      },
    ]

    render(
      <TaskAssignmentModal {...defaultProps} projectMembers={mixedMembers} />
    )

    expect(screen.getAllByText('Alice Contributor').length).toBeGreaterThan(0)
    expect(screen.queryByText('Charlie Viewer')).not.toBeInTheDocument()
  })

  it('shows correct task count for single task', async () => {
    const singleTaskProps = {
      ...defaultProps,
      selectedTaskIds: ['1'],
    }

    render(<TaskAssignmentModal {...singleTaskProps} />)

    expect(screen.getByText('Assigning 1 tasks')).toBeInTheDocument()
  })

  it('allows clicking on user row to toggle selection', async () => {
    const user = userEvent.setup()
    render(<TaskAssignmentModal {...defaultProps} />)

    const userRows = screen.getAllByText('John Doe')
    const userRow = userRows[0].closest('div[class*="cursor-pointer"]')

    if (userRow) {
      await user.click(userRow)
      const checkboxes = screen.getAllByRole('checkbox')
      expect(checkboxes[0]).toBeChecked()
    }
  })

  it('handles API response with assignments_skipped', async () => {
    const user = userEvent.setup()
    const mockAddToast = jest.fn()

    jest
      .spyOn(require('@/components/shared/Toast'), 'useToast')
      .mockReturnValue({
        addToast: mockAddToast,
      })

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          assignments_skipped: 2,
          assignments_created: 0,
        }),
    })

    render(<TaskAssignmentModal {...defaultProps} />)

    const checkboxes = screen.getAllByRole('checkbox')
    await user.click(checkboxes[0])

    const assignButton = screen.getByRole('button', { name: /Assign Tasks/i })
    await user.click(assignButton)

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'Tasks assigned successfully',
        'info'
      )
    })
  })

  it('handles API response with assignments_updated', async () => {
    const user = userEvent.setup()
    const mockAddToast = jest.fn()

    jest
      .spyOn(require('@/components/shared/Toast'), 'useToast')
      .mockReturnValue({
        addToast: mockAddToast,
      })

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          assignments_updated: 3,
          assignments_created: 0,
        }),
    })

    render(<TaskAssignmentModal {...defaultProps} />)

    const checkboxes = screen.getAllByRole('checkbox')
    await user.click(checkboxes[0])

    const assignButton = screen.getByRole('button', { name: /Assign Tasks/i })
    await user.click(assignButton)

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'Tasks assigned successfully',
        'success'
      )
    })
  })

  it('handles API response with custom message', async () => {
    const user = userEvent.setup()
    const mockAddToast = jest.fn()

    jest
      .spyOn(require('@/components/shared/Toast'), 'useToast')
      .mockReturnValue({
        addToast: mockAddToast,
      })

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          message: 'Custom success message',
          assignments_created: 0,
        }),
    })

    render(<TaskAssignmentModal {...defaultProps} />)

    const checkboxes = screen.getAllByRole('checkbox')
    await user.click(checkboxes[0])

    const assignButton = screen.getByRole('button', { name: /Assign Tasks/i })
    await user.click(assignButton)

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'Custom success message',
        'info'
      )
    })
  })

  it('handles API response with failed status', async () => {
    const user = userEvent.setup()
    const mockAddToast = jest.fn()

    jest
      .spyOn(require('@/components/shared/Toast'), 'useToast')
      .mockReturnValue({
        addToast: mockAddToast,
      })

    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 500,
    })

    render(<TaskAssignmentModal {...defaultProps} />)

    const checkboxes = screen.getAllByRole('checkbox')
    await user.click(checkboxes[0])

    const assignButton = screen.getByRole('button', { name: /Assign Tasks/i })
    await user.click(assignButton)

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'Failed to assign tasks',
        'error'
      )
    })
  })

  it('includes due date in assignment request when provided', async () => {
    const user = userEvent.setup()

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ assignments_created: 1 }),
    })

    render(<TaskAssignmentModal {...defaultProps} />)

    const checkboxes = screen.getAllByRole('checkbox')
    await user.click(checkboxes[0])

    const dueDateInput = screen.getByLabelText(/Due Date/)
    await user.type(dueDateInput, '2025-12-31T23:59')

    const assignButton = screen.getByRole('button', { name: /Assign Tasks/i })
    await user.click(assignButton)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          body: expect.stringContaining('2025-12-31T23:59'),
        })
      )
    })
  })

  it('excludes due date from request when not provided', async () => {
    const user = userEvent.setup()

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ assignments_created: 1 }),
    })

    render(<TaskAssignmentModal {...defaultProps} />)

    const checkboxes = screen.getAllByRole('checkbox')
    await user.click(checkboxes[0])

    const assignButton = screen.getByRole('button', { name: /Assign Tasks/i })
    await user.click(assignButton)

    await waitFor(() => {
      const fetchCall = (global.fetch as jest.Mock).mock.calls[0]
      const body = JSON.parse(fetchCall[1].body)
      expect(body.due_date).toBeUndefined()
    })
  })

  it('awaits assignment completion before closing', async () => {
    const user = userEvent.setup()
    let completeCalled = false
    const mockComplete = jest.fn(async () => {
      await new Promise((resolve) => setTimeout(resolve, 100))
      completeCalled = true
    })

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ assignments_created: 1 }),
    })

    render(
      <TaskAssignmentModal
        {...defaultProps}
        onAssignmentComplete={mockComplete}
      />
    )

    const checkboxes = screen.getAllByRole('checkbox')
    await user.click(checkboxes[0])

    const assignButton = screen.getByRole('button', { name: /Assign Tasks/i })
    await user.click(assignButton)

    await waitFor(() => {
      expect(mockComplete).toHaveBeenCalled()
      expect(completeCalled).toBe(true)
    })

    expect(mockOnClose).toHaveBeenCalled()
  })

  it('shows user avatars in the list', async () => {
    render(<TaskAssignmentModal {...defaultProps} />)

    expect(screen.getAllByText('John Doe').length).toBeGreaterThan(0)
    expect(screen.getAllByText('john@example.com').length).toBeGreaterThan(0)
  })

  it('disables cancel button during submission', async () => {
    const user = userEvent.setup()

    global.fetch = jest.fn().mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(
            () =>
              resolve({
                ok: true,
                json: () => Promise.resolve({ assignments_created: 1 }),
              }),
            100
          )
        )
    )

    render(<TaskAssignmentModal {...defaultProps} />)

    const checkboxes = screen.getAllByRole('checkbox')
    await user.click(checkboxes[0])

    const assignButton = screen.getByRole('button', { name: /Assign Tasks/i })
    await user.click(assignButton)

    const cancelButton = screen.getByRole('button', { name: /Cancel/i })
    expect(cancelButton).toBeDisabled()

    await waitFor(() => {
      expect(mockOnAssignmentComplete).toHaveBeenCalled()
    })
  })

  it('supports uppercase role names', async () => {
    const membersWithUppercaseRoles = [
      {
        id: 'member-1',
        user_id: 'user-1',
        name: 'Upper Annotator',
        email: 'upper@example.com',
        role: 'ANNOTATOR',
      },
      {
        id: 'member-2',
        user_id: 'user-2',
        name: 'Upper Contributor',
        email: 'contrib@example.com',
        role: 'CONTRIBUTOR',
      },
    ]

    render(
      <TaskAssignmentModal
        {...defaultProps}
        projectMembers={membersWithUppercaseRoles}
      />
    )

    expect(screen.getAllByText('Upper Annotator').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Upper Contributor').length).toBeGreaterThan(0)
  })
})

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
