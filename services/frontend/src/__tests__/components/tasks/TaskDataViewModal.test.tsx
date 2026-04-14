/**
 * Unit tests for TaskDataViewModal component
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TaskDataViewModal } from '../../../components/tasks/TaskDataViewModal'
import { Task } from '../../../types/labelStudio'

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'tasks.dataView.taskDataId': `Task Data - ID ${params?.id || ''}`,
        'tasks.dataView.taskType': `Task Type: ${params?.type || 'Unknown'}`,
        'tasks.dataView.viewFormatted': 'Formatted',
        'tasks.dataView.viewJson': 'JSON',
        'tasks.dataView.copy': 'Copy',
        'tasks.dataView.copied': 'Copied!',
        'tasks.dataView.searchPlaceholder': 'Search fields and values...',
        'tasks.dataView.noDataAvailable': 'No data available',
        'tasks.dataView.noFieldsMatch': 'No fields match your search',
        'tasks.dataView.fieldsCount': `${params?.count || 0} fields`,
        'tasks.dataView.fieldsCountFiltered': `${params?.count || 0} fields (${params?.filtered || 0} filtered)`,
        'tasks.dataView.created': `Created: ${params?.date || ''}`,
      }
      return translations[key] || key
    },
    locale: 'en',
    isReady: true,
  }),
}))

// Clipboard API will be mocked below

const mockTask: Task = {
  id: 123,
  project_id: 'test-project-id',
  data: {
    title: 'Sample Document Title',
    question: 'What is the main topic of this legal document?',
    category: 'legal',
    priority: 5,
    active: true,
    created_date: '2024-01-15',
    fallnummer: 'CASE-2024-001',
    tags: ['important', 'urgent', 'contract'],
    metadata: {
      author: 'John Doe',
      version: 2,
      department: 'Legal Affairs',
    },
    long_description:
      'This is a comprehensive legal document that requires detailed analysis and annotation. It contains multiple clauses and provisions that need to be carefully reviewed.',
    status: 'pending_review',
  },
  is_labeled: false,
  total_annotations: 3,
  cancelled_annotations: 1,
  total_predictions: 2,
  created_at: '2024-01-15T14:30:00Z',
  updated_at: '2024-01-16T09:15:00Z',
}

const mockOnClose = jest.fn()

// Use user-event's built-in clipboard mocking
const mockWriteText = jest.fn(() => Promise.resolve())

// Mock the clipboard API in a way that works with user-event
beforeAll(() => {
  Object.defineProperty(window.navigator, 'clipboard', {
    value: {
      writeText: mockWriteText,
    },
    configurable: true,
  })
})

describe('TaskDataViewModal', () => {
  beforeEach(() => {
    mockOnClose.mockClear()
    mockWriteText.mockClear()
  })

  it('should not render when task is null', async () => {
    render(
      <TaskDataViewModal task={null} isOpen={true} onClose={mockOnClose} />
    )

    expect(screen.queryByText(/Task Data/)).not.toBeInTheDocument()
  })

  it('should render modal when open with task data', async () => {
    await act(async () => {
      render(
        <TaskDataViewModal
          task={mockTask}
          isOpen={true}
          onClose={mockOnClose}
        />
      )
    })

    expect(screen.getByText('Task Data - ID 123')).toBeInTheDocument()
    expect(screen.getByText('Formatted')).toBeInTheDocument()
    expect(screen.getByText('JSON')).toBeInTheDocument()
  })

  it('should display formatted view by default', async () => {
    render(
      <TaskDataViewModal task={mockTask} isOpen={true} onClose={mockOnClose} />
    )

    // Should show formatted fields
    expect(screen.getByText('title')).toBeInTheDocument()
    expect(screen.getByText('Sample Document Title')).toBeInTheDocument()
    expect(screen.getByText('question')).toBeInTheDocument()
    expect(screen.getByText('priority')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('should switch to JSON view', async () => {
    const user = userEvent.setup()

    render(
      <TaskDataViewModal task={mockTask} isOpen={true} onClose={mockOnClose} />
    )

    const jsonButton = screen.getByText('JSON')
    await user.click(jsonButton)

    // Should show JSON content
    await waitFor(() => {
      expect(screen.getByText(/"title":/)).toBeInTheDocument()
      expect(screen.getByText(/"Sample Document Title"/)).toBeInTheDocument()
    })
  })

  it('should handle search in formatted view', async () => {
    const user = userEvent.setup()

    render(
      <TaskDataViewModal task={mockTask} isOpen={true} onClose={mockOnClose} />
    )

    const searchInput = screen.getByPlaceholderText(
      'Search fields and values...'
    )
    await user.type(searchInput, 'legal')

    // Should filter and highlight matching fields
    expect(screen.getByText('category')).toBeInTheDocument()
    expect(screen.getByText('question')).toBeInTheDocument()

    // Should not show non-matching fields
    expect(screen.queryByText('priority')).not.toBeInTheDocument()
  })

  it('should copy to clipboard in formatted mode', async () => {
    const user = userEvent.setup()

    await act(async () => {
      render(
        <TaskDataViewModal
          task={mockTask}
          isOpen={true}
          onClose={mockOnClose}
        />
      )
    })

    const copyButton = screen.getByText('Copy')

    await act(async () => {
      await user.click(copyButton)
    })

    // Should show success message indicating copy operation completed
    await waitFor(() => {
      expect(screen.getByText('Copied!')).toBeInTheDocument()
    })
  })

  it('should copy to clipboard in JSON mode', async () => {
    const user = userEvent.setup()

    await act(async () => {
      render(
        <TaskDataViewModal
          task={mockTask}
          isOpen={true}
          onClose={mockOnClose}
        />
      )
    })

    // Switch to JSON view
    const jsonButton = screen.getByText('JSON')
    await act(async () => {
      await user.click(jsonButton)
    })

    const copyButton = screen.getByText('Copy')
    await act(async () => {
      await user.click(copyButton)
    })

    // Should show success message indicating copy operation completed
    await waitFor(() => {
      expect(screen.getByText('Copied!')).toBeInTheDocument()
    })
  })

  it('should close modal when close button is clicked', async () => {
    const user = userEvent.setup()

    render(
      <TaskDataViewModal task={mockTask} isOpen={true} onClose={mockOnClose} />
    )

    const closeButton = screen.getByRole('button', { name: '' }) // Close button with X icon
    await user.click(closeButton)

    expect(mockOnClose).toHaveBeenCalled()
  })

  it('should display field count and creation date', async () => {
    render(
      <TaskDataViewModal task={mockTask} isOpen={true} onClose={mockOnClose} />
    )

    // Should show field count
    const fieldCount = Object.keys(mockTask.data).length
    expect(screen.getByText(`${fieldCount} fields`)).toBeInTheDocument()

    // Should show creation date
    expect(screen.getByText(/Created:/)).toBeInTheDocument()

    // Handle potential multiple date renderings in CI (React StrictMode double-render)
    const dateElements = screen.getAllByText(
      /1\/15\/2024|15\/1\/2024|2024-01-15/
    )
    expect(dateElements.length).toBeGreaterThanOrEqual(1)
    expect(dateElements[0]).toBeInTheDocument()
  })

  it('should handle different data types in formatted view', async () => {
    const taskWithVariousTypes: Task = {
      ...mockTask,
      data: {
        text_field: 'Simple text',
        number_field: 42,
        boolean_field: true,
        null_field: null,
        array_field: ['item1', 'item2', 'item3'],
        object_field: {
          nested_key: 'nested_value',
          nested_number: 100,
        },
        empty_string: '',
      },
    }

    await act(async () => {
      render(
        <TaskDataViewModal
          task={taskWithVariousTypes}
          isOpen={true}
          onClose={mockOnClose}
        />
      )
    })

    // Should show field names
    expect(screen.getByText('text_field')).toBeInTheDocument()
    expect(screen.getByText('number_field')).toBeInTheDocument()
    expect(screen.getByText('boolean_field')).toBeInTheDocument()

    // Should show field values
    expect(screen.getByText('Simple text')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText('true')).toBeInTheDocument()
  })

  it('should highlight search matches', async () => {
    const user = userEvent.setup()

    render(
      <TaskDataViewModal task={mockTask} isOpen={true} onClose={mockOnClose} />
    )

    const searchInput = screen.getByPlaceholderText(
      'Search fields and values...'
    )
    await user.type(searchInput, 'Sample')

    // Should highlight matching text
    const highlightedElements = screen.getAllByText('Sample')
    expect(highlightedElements[0].tagName).toBe('MARK')
  })

  it('should show filtered count when searching', async () => {
    const user = userEvent.setup()

    render(
      <TaskDataViewModal task={mockTask} isOpen={true} onClose={mockOnClose} />
    )

    const searchInput = screen.getByPlaceholderText(
      'Search fields and values...'
    )
    await user.type(searchInput, 'legal')

    // Should show filtered count in footer
    expect(screen.getByText(/fields \(\d+ filtered\)/)).toBeInTheDocument()
  })

  it('should handle empty search results', async () => {
    const user = userEvent.setup()

    render(
      <TaskDataViewModal task={mockTask} isOpen={true} onClose={mockOnClose} />
    )

    const searchInput = screen.getByPlaceholderText(
      'Search fields and values...'
    )
    await user.type(searchInput, 'nonexistent')

    expect(screen.getByText('No fields match your search')).toBeInTheDocument()
  })

  it('should handle tasks with empty data', async () => {
    const taskWithEmptyData: Task = {
      ...mockTask,
      data: {},
    }

    render(
      <TaskDataViewModal
        task={taskWithEmptyData}
        isOpen={true}
        onClose={mockOnClose}
      />
    )

    expect(screen.getByText('0 fields')).toBeInTheDocument()
    expect(screen.getByText('No data available')).toBeInTheDocument()
  })

  it('should handle clipboard copy failure gracefully', async () => {
    const user = userEvent.setup()

    // Replace the navigator.clipboard completely to ensure it throws
    const originalClipboard = Object.getOwnPropertyDescriptor(
      window.navigator,
      'clipboard'
    )
    Object.defineProperty(window.navigator, 'clipboard', {
      value: {
        writeText: jest.fn(() => Promise.reject(new Error('Clipboard failed'))),
      },
      configurable: true,
    })

    await act(async () => {
      render(
        <TaskDataViewModal
          task={mockTask}
          isOpen={true}
          onClose={mockOnClose}
        />
      )
    })

    const copyButton = screen.getByText('Copy')
    await act(async () => {
      await user.click(copyButton)
    })

    // Wait for the error to be handled
    await waitFor(() => {
      // Should not show success message when clipboard fails
      expect(screen.queryByText('Copied!')).not.toBeInTheDocument()
    })

    // Restore original clipboard
    if (originalClipboard) {
      Object.defineProperty(window.navigator, 'clipboard', originalClipboard)
    }
  })

  it('should maintain view mode when switching tasks', async () => {
    const user = userEvent.setup()

    const { rerender } = render(
      <TaskDataViewModal task={mockTask} isOpen={true} onClose={mockOnClose} />
    )

    // Switch to JSON view
    const jsonButton = screen.getByText('JSON')
    await user.click(jsonButton)

    // Change task
    const newTask: Task = { ...mockTask, id: 456, data: { different: 'data' } }

    rerender(
      <TaskDataViewModal task={newTask} isOpen={true} onClose={mockOnClose} />
    )

    // Should still be in JSON view
    expect(screen.getByText(/"different":/)).toBeInTheDocument()
  })

  it('should reset search when switching to JSON view', async () => {
    const user = userEvent.setup()

    await act(async () => {
      render(
        <TaskDataViewModal
          task={mockTask}
          isOpen={true}
          onClose={mockOnClose}
        />
      )
    })

    // Add search term
    const searchInput = screen.getByPlaceholderText(
      'Search fields and values...'
    )
    await act(async () => {
      await user.type(searchInput, 'legal')
    })

    // Switch to JSON view
    const jsonButton = screen.getByText('JSON')
    await act(async () => {
      await user.click(jsonButton)
    })

    // Switch back to formatted view
    const formattedButton = screen.getByText('Formatted')
    await act(async () => {
      await user.click(formattedButton)
    })

    // Search should be cleared (all fields visible)
    const fieldCount = Object.keys(mockTask.data).length
    await waitFor(() => {
      expect(
        screen.getByText(new RegExp(`${fieldCount} fields`))
      ).toBeInTheDocument()
    })
  })
})

describe('TaskDataViewModal Accessibility', () => {
  it('should have proper ARIA labels and roles', async () => {
    await act(async () => {
      render(
        <TaskDataViewModal
          task={mockTask}
          isOpen={true}
          onClose={mockOnClose}
        />
      )
    })

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Copy')).toBeInTheDocument()
    expect(
      screen.getByPlaceholderText('Search fields and values...')
    ).toBeInTheDocument()
  })

  it('should support keyboard navigation', async () => {
    const user = userEvent.setup()

    render(
      <TaskDataViewModal task={mockTask} isOpen={true} onClose={mockOnClose} />
    )

    // Should be able to tab through interactive elements
    await user.tab()
    expect(screen.getByText('Formatted')).toHaveFocus()

    await user.tab()
    expect(screen.getByText('JSON')).toHaveFocus()

    await user.tab()
    expect(screen.getByText('Copy')).toHaveFocus()
  })

  it('should close on Escape key', async () => {
    const user = userEvent.setup()

    render(
      <TaskDataViewModal task={mockTask} isOpen={true} onClose={mockOnClose} />
    )

    await user.keyboard('{Escape}')
    expect(mockOnClose).toHaveBeenCalled()
  })
})
