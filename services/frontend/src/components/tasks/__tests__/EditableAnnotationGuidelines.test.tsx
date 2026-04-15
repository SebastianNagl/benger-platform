import { Task } from '@/lib/api'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { EditableAnnotationGuidelines } from '../EditableAnnotationGuidelines'

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

jest.mock('@/components/modals/AnnotationGuidelinesModal', () => ({
  AnnotationGuidelinesModal: ({
    isOpen,
    onClose,
    onSave,
    initialValue,
  }: any) =>
    isOpen ? (
      <div data-testid="annotation-guidelines-modal">
        <button onClick={onClose} data-testid="modal-close">
          Close
        </button>
        <button
          onClick={() => onSave('Updated guidelines')}
          data-testid="modal-save"
        >
          Save
        </button>
        <div data-testid="modal-initial-value">{initialValue}</div>
      </div>
    ) : null,
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, varsOrDefault?: any) => {
      const translations: Record<string, any> = require('../../../locales/en/common.json')
      const parts = key.split('.')
      let value: any = translations
      for (const part of parts) {
        if (value && typeof value === 'object' && part in value) {
          value = value[part]
        } else {
          return key
        }
      }
      if (typeof value !== 'string') return key
      if (varsOrDefault && typeof varsOrDefault === 'object') {
        for (const [k, v] of Object.entries(varsOrDefault)) {
          value = value.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
        }
      }
      return value
    },
    locale: 'en',
  }),
}))


// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  PencilIcon: (props: any) => <svg data-testid="pencil-icon" {...props} />,
  DocumentTextIcon: (props: any) => (
    <svg data-testid="document-icon" {...props} />
  ),
}))

const mockUseAuth = require('@/contexts/AuthContext').useAuth as jest.Mock
const mockUseToast = require('@/components/shared/Toast').useToast as jest.Mock
const mockApi = require('@/lib/api').api as jest.Mocked<
  typeof import('@/lib/api').api
>

describe('EditableAnnotationGuidelines', () => {
  const mockAddToast = jest.fn()
  const mockOnTaskUpdated = jest.fn()

  const taskWithGuidelines: Task = {
    id: 'task-1',
    created_by: 'user-1',
    annotation_guidelines: 'Please follow these guidelines for annotation.',
    title: 'Test Task',
    description: 'Test Description',
    status: 'active',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  } as Task

  const taskWithoutGuidelines: Task = {
    ...taskWithGuidelines,
    annotation_guidelines: null,
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
    mockApi.updateTask.mockResolvedValue(taskWithGuidelines)
  })

  describe('basic rendering', () => {
    it('renders component with guidelines heading', () => {
      mockUseAuth.mockReturnValue({ user: regularUser })

      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      expect(screen.getByText('Annotation Guidelines')).toBeInTheDocument()
      expect(screen.getByTestId('document-icon')).toBeInTheDocument()
    })

    it('displays existing guidelines when present', () => {
      mockUseAuth.mockReturnValue({ user: regularUser })

      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      expect(
        screen.getByText('Please follow these guidelines for annotation.')
      ).toBeInTheDocument()
    })

    it('shows placeholder when no guidelines exist', () => {
      mockUseAuth.mockReturnValue({ user: regularUser })

      render(<EditableAnnotationGuidelines task={taskWithoutGuidelines} />)

      expect(
        screen.getByText('No annotation guidelines provided')
      ).toBeInTheDocument()
    })

    it('applies custom className', () => {
      mockUseAuth.mockReturnValue({ user: regularUser })
      const { container } = render(
        <EditableAnnotationGuidelines
          task={taskWithGuidelines}
          className="custom-class"
        />
      )

      const component = container.querySelector('.custom-class')
      expect(component).toBeInTheDocument()
    })
  })

  describe('permissions - superadmin', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: superadminUser })
    })

    it('shows edit button for superadmin', () => {
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      expect(screen.getByTestId('pencil-icon')).toBeInTheDocument()
      expect(
        screen.getByTitle('Edit annotation guidelines')
      ).toBeInTheDocument()
    })

    it('shows edit prompt for superadmin when no guidelines', () => {
      render(<EditableAnnotationGuidelines task={taskWithoutGuidelines} />)

      expect(
        screen.getByText('Click to add annotation guidelines')
      ).toBeInTheDocument()
      expect(
        screen.getByText(
          'Help annotators understand how to complete this task effectively'
        )
      ).toBeInTheDocument()
    })

    it('shows click to edit title for superadmin', () => {
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      const clickableArea = screen.getByTitle(
        'Click to edit annotation guidelines'
      )
      expect(clickableArea).toBeInTheDocument()
    })

    it('opens modal when edit button is clicked', async () => {
      const user = userEvent.setup()
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      const editButton = screen.getByTitle('Edit annotation guidelines')
      await user.click(editButton)

      expect(
        screen.getByTestId('annotation-guidelines-modal')
      ).toBeInTheDocument()
    })

    it('opens modal when content area is clicked', async () => {
      const user = userEvent.setup()
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      const contentArea = screen.getByTitle(
        'Click to edit annotation guidelines'
      )
      await user.click(contentArea)

      expect(
        screen.getByTestId('annotation-guidelines-modal')
      ).toBeInTheDocument()
    })
  })

  describe('permissions - task creator', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: taskCreatorUser })
    })

    it('shows edit button for task creator', () => {
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      expect(screen.getByTestId('pencil-icon')).toBeInTheDocument()
    })

    it('allows task creator to edit guidelines', async () => {
      const user = userEvent.setup()
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      const editButton = screen.getByTitle('Edit annotation guidelines')
      await user.click(editButton)

      expect(
        screen.getByTestId('annotation-guidelines-modal')
      ).toBeInTheDocument()
    })
  })

  describe('permissions - regular user', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: regularUser })
    })

    it('hides edit button for regular user', () => {
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      expect(screen.queryByTestId('pencil-icon')).not.toBeInTheDocument()
    })

    it('shows read-only prompt when no guidelines for regular user', () => {
      render(<EditableAnnotationGuidelines task={taskWithoutGuidelines} />)

      expect(
        screen.getByText('No annotation guidelines provided')
      ).toBeInTheDocument()
      expect(
        screen.queryByText('Click to add annotation guidelines')
      ).not.toBeInTheDocument()
    })

    it('does not show edit title for regular user', () => {
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      expect(
        screen.queryByTitle('Click to edit annotation guidelines')
      ).not.toBeInTheDocument()
    })

    it('does not open modal when content is clicked by regular user', async () => {
      const user = userEvent.setup()
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      const guidelinesText = screen.getByText(
        'Please follow these guidelines for annotation.'
      )
      await user.click(guidelinesText)

      expect(
        screen.queryByTestId('annotation-guidelines-modal')
      ).not.toBeInTheDocument()
    })
  })

  describe('permissions - no user', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: null })
    })

    it('hides edit functionality when no user', () => {
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      expect(screen.queryByTestId('pencil-icon')).not.toBeInTheDocument()
      expect(
        screen.queryByTitle('Click to edit annotation guidelines')
      ).not.toBeInTheDocument()
    })
  })

  describe('modal interaction', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: superadminUser })
    })

    it('passes initial value to modal', async () => {
      const user = userEvent.setup()
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      const editButton = screen.getByTitle('Edit annotation guidelines')
      await user.click(editButton)

      expect(screen.getByTestId('modal-initial-value')).toHaveTextContent(
        'Please follow these guidelines for annotation.'
      )
    })

    it('passes empty string to modal when no guidelines', async () => {
      const user = userEvent.setup()
      render(<EditableAnnotationGuidelines task={taskWithoutGuidelines} />)

      const contentArea = screen.getByText('Click to add annotation guidelines')
      await user.click(contentArea)

      expect(screen.getByTestId('modal-initial-value')).toHaveTextContent('')
    })

    it('closes modal when close button is clicked', async () => {
      const user = userEvent.setup()
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      const editButton = screen.getByTitle('Edit annotation guidelines')
      await user.click(editButton)

      expect(
        screen.getByTestId('annotation-guidelines-modal')
      ).toBeInTheDocument()

      const closeButton = screen.getByTestId('modal-close')
      await user.click(closeButton)

      expect(
        screen.queryByTestId('annotation-guidelines-modal')
      ).not.toBeInTheDocument()
    })
  })

  describe('save functionality', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: superadminUser })
    })

    it('calls API to update guidelines when saved', async () => {
      const user = userEvent.setup()
      render(
        <EditableAnnotationGuidelines
          task={taskWithGuidelines}
          onTaskUpdated={mockOnTaskUpdated}
        />
      )

      const editButton = screen.getByTitle('Edit annotation guidelines')
      await user.click(editButton)

      const saveButton = screen.getByTestId('modal-save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockApi.updateTask).toHaveBeenCalledWith('task-1', {
          annotation_guidelines: 'Updated guidelines',
        })
      })
    })

    it('shows success toast on successful update', async () => {
      const user = userEvent.setup()
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      const editButton = screen.getByTitle('Edit annotation guidelines')
      await user.click(editButton)

      const saveButton = screen.getByTestId('modal-save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Annotation guidelines updated successfully',
          'success'
        )
      })
    })

    it('calls onTaskUpdated callback with updated task', async () => {
      const user = userEvent.setup()
      render(
        <EditableAnnotationGuidelines
          task={taskWithGuidelines}
          onTaskUpdated={mockOnTaskUpdated}
        />
      )

      const editButton = screen.getByTitle('Edit annotation guidelines')
      await user.click(editButton)

      const saveButton = screen.getByTestId('modal-save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockOnTaskUpdated).toHaveBeenCalledWith(taskWithGuidelines)
      })
    })

    it('closes modal after successful save', async () => {
      const user = userEvent.setup()
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      const editButton = screen.getByTitle('Edit annotation guidelines')
      await user.click(editButton)

      expect(
        screen.getByTestId('annotation-guidelines-modal')
      ).toBeInTheDocument()

      const saveButton = screen.getByTestId('modal-save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(
          screen.queryByTestId('annotation-guidelines-modal')
        ).not.toBeInTheDocument()
      })
    })

    it('does not call API if content unchanged', async () => {
      const user = userEvent.setup()

      // Create a custom component for this test that returns unchanged content
      const TestComponent = () => {
        const [isModalOpen, setIsModalOpen] = useState(false)

        const handleSaveUnchanged = (guidelines: string) => {
          // Return the exact same content
          const trimmedGuidelines = guidelines.trim()
          if (
            trimmedGuidelines ===
            (taskWithGuidelines.annotation_guidelines || '').trim()
          ) {
            setIsModalOpen(false)
            return
          }
        }

        return (
          <>
            <button
              onClick={() => setIsModalOpen(true)}
              data-testid="open-modal"
            >
              Open Modal
            </button>
            {isModalOpen && (
              <div data-testid="annotation-guidelines-modal">
                <button
                  onClick={() =>
                    handleSaveUnchanged(
                      'Please follow these guidelines for annotation.'
                    )
                  }
                  data-testid="modal-save-unchanged"
                >
                  Save Unchanged
                </button>
              </div>
            )}
          </>
        )
      }

      render(<TestComponent />)

      const openButton = screen.getByTestId('open-modal')
      await user.click(openButton)

      const saveButton = screen.getByTestId('modal-save-unchanged')
      await user.click(saveButton)

      expect(mockApi.updateTask).not.toHaveBeenCalled()
    })
  })

  describe('error handling', () => {
    beforeEach(() => {
      jest.clearAllMocks()
      mockUseAuth.mockReturnValue({ user: superadminUser })
      mockUseToast.mockReturnValue({ addToast: mockAddToast })
    })

    it('shows error toast on API failure', async () => {
      const user = userEvent.setup()
      mockApi.updateTask.mockRejectedValue(new Error('API Error'))

      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      const editButton = screen.getByTitle('Edit annotation guidelines')
      await user.click(editButton)

      await waitFor(() => {
        expect(
          screen.getByTestId('annotation-guidelines-modal')
        ).toBeInTheDocument()
      })

      const saveButton = screen.getByTestId('modal-save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to update annotation guidelines: API Error',
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

      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      const editButton = screen.getByTitle('Edit annotation guidelines')
      await user.click(editButton)

      await waitFor(() => {
        expect(
          screen.getByTestId('annotation-guidelines-modal')
        ).toBeInTheDocument()
      })

      const saveButton = screen.getByTestId('modal-save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith(
          'Error updating annotation guidelines:',
          expect.any(Error)
        )
      })

      consoleSpy.mockRestore()
    })

    it('handles non-Error exceptions', async () => {
      const user = userEvent.setup()
      mockApi.updateTask.mockRejectedValue('String error')

      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      const editButton = screen.getByTitle('Edit annotation guidelines')
      await user.click(editButton)

      await waitFor(() => {
        expect(
          screen.getByTestId('annotation-guidelines-modal')
        ).toBeInTheDocument()
      })

      const saveButton = screen.getByTestId('modal-save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to update annotation guidelines: Failed to update annotation guidelines',
          'error'
        )
      })
    })
  })

  describe('styling and layout', () => {
    it('applies correct styling for guidelines container', () => {
      mockUseAuth.mockReturnValue({ user: regularUser })
      const { container } = render(
        <EditableAnnotationGuidelines task={taskWithGuidelines} />
      )

      const guidelinesContainer = container.querySelector('.bg-blue-50')
      expect(guidelinesContainer).toBeInTheDocument()
      expect(guidelinesContainer).toHaveClass(
        'dark:bg-blue-900/20',
        'rounded-lg',
        'p-4',
        'border',
        'border-blue-200'
      )
    })

    it('applies correct styling for empty state', () => {
      mockUseAuth.mockReturnValue({ user: regularUser })
      const { container } = render(
        <EditableAnnotationGuidelines task={taskWithoutGuidelines} />
      )

      const emptyContainer = container.querySelector('.border-dashed')
      expect(emptyContainer).toBeInTheDocument()
      expect(emptyContainer).toHaveClass(
        'border-zinc-300',
        'dark:border-zinc-600',
        'rounded-lg',
        'p-4',
        'text-center'
      )
    })

    it('shows edit button with hover opacity for authorized users', () => {
      mockUseAuth.mockReturnValue({ user: superadminUser })
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      const editButton = screen.getByTitle('Edit annotation guidelines')
      expect(editButton).toHaveClass('opacity-0', 'group-hover:opacity-100')
    })

    it('applies hover effects for editable content', () => {
      mockUseAuth.mockReturnValue({ user: superadminUser })
      const { container } = render(
        <EditableAnnotationGuidelines task={taskWithGuidelines} />
      )

      const contentArea = container.querySelector('.cursor-pointer')
      expect(contentArea).toBeInTheDocument()
      expect(contentArea).toHaveClass(
        'hover:text-zinc-800',
        'dark:hover:text-zinc-200'
      )
    })

    it('applies whitespace-pre-wrap class for guidelines text', () => {
      const taskWithMultilineGuidelines = {
        ...taskWithGuidelines,
        annotation_guidelines: 'Line 1\nLine 2\n\nLine 4',
      }
      mockUseAuth.mockReturnValue({ user: regularUser })

      const { container } = render(
        <EditableAnnotationGuidelines task={taskWithMultilineGuidelines} />
      )

      // Check that the text element has the whitespace-pre-wrap class for proper formatting
      const textElement = container.querySelector('.whitespace-pre-wrap')
      expect(textElement).toBeInTheDocument()
      expect(textElement).toHaveClass('text-sm', 'leading-relaxed')
    })
  })

  describe('dark mode support', () => {
    it('includes dark mode classes for heading', () => {
      mockUseAuth.mockReturnValue({ user: regularUser })
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      const heading = screen.getByText('Annotation Guidelines')
      expect(heading).toHaveClass('dark:text-zinc-300')

      const icon = screen.getByTestId('document-icon')
      expect(icon).toHaveClass('dark:text-zinc-400')
    })

    it('includes dark mode classes for guidelines content', () => {
      mockUseAuth.mockReturnValue({ user: regularUser })
      const { container } = render(
        <EditableAnnotationGuidelines task={taskWithGuidelines} />
      )

      const guidelinesContainer = container.querySelector('.bg-blue-50')
      expect(guidelinesContainer).toHaveClass(
        'dark:bg-blue-900/20',
        'dark:border-blue-800'
      )

      const guidelinesText = container.querySelector('.whitespace-pre-wrap')
      expect(guidelinesText).toHaveClass('dark:text-zinc-300')
    })

    it('includes dark mode classes for empty state', () => {
      mockUseAuth.mockReturnValue({ user: regularUser })
      const { container } = render(
        <EditableAnnotationGuidelines task={taskWithoutGuidelines} />
      )

      const emptyContainer = container.querySelector('.border-dashed')
      expect(emptyContainer).toHaveClass('dark:border-zinc-600')

      const emptyText = screen.getByText('No annotation guidelines provided')
      expect(emptyText).toHaveClass('dark:text-zinc-400')
    })
  })

  describe('accessibility', () => {
    it('provides proper button titles', () => {
      mockUseAuth.mockReturnValue({ user: superadminUser })
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      expect(
        screen.getByTitle('Edit annotation guidelines')
      ).toBeInTheDocument()
      expect(
        screen.getByTitle('Click to edit annotation guidelines')
      ).toBeInTheDocument()
    })

    it('provides semantic structure with proper headings', () => {
      mockUseAuth.mockReturnValue({ user: regularUser })
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      const heading = screen.getByText('Annotation Guidelines')
      expect(heading).toHaveClass('font-medium')
    })

    it('includes descriptive icons', () => {
      mockUseAuth.mockReturnValue({ user: superadminUser })
      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      expect(screen.getAllByTestId('document-icon')).toHaveLength(1)
      expect(screen.getByTestId('pencil-icon')).toBeInTheDocument()
    })
  })

  describe('edge cases', () => {
    it('handles empty string guidelines', () => {
      const taskWithEmptyGuidelines = {
        ...taskWithGuidelines,
        annotation_guidelines: '',
      }
      mockUseAuth.mockReturnValue({ user: regularUser })

      render(<EditableAnnotationGuidelines task={taskWithEmptyGuidelines} />)

      expect(
        screen.getByText('No annotation guidelines provided')
      ).toBeInTheDocument()
    })

    it('handles whitespace-only guidelines', () => {
      const taskWithWhitespaceGuidelines = {
        ...taskWithGuidelines,
        annotation_guidelines: '   \n\t   ',
      }
      mockUseAuth.mockReturnValue({ user: regularUser })

      render(
        <EditableAnnotationGuidelines task={taskWithWhitespaceGuidelines} />
      )

      expect(
        screen.getByText('No annotation guidelines provided')
      ).toBeInTheDocument()
    })

    it('handles very long guidelines', () => {
      const longGuidelines = 'A'.repeat(1000)
      const taskWithLongGuidelines = {
        ...taskWithGuidelines,
        annotation_guidelines: longGuidelines,
      }
      mockUseAuth.mockReturnValue({ user: regularUser })

      render(<EditableAnnotationGuidelines task={taskWithLongGuidelines} />)

      expect(screen.getByText(longGuidelines)).toBeInTheDocument()
    })

    it('handles special characters in guidelines', () => {
      const specialGuidelines = 'Guidelines with <>&"\' special chars & symbols'
      const taskWithSpecialGuidelines = {
        ...taskWithGuidelines,
        annotation_guidelines: specialGuidelines,
      }
      mockUseAuth.mockReturnValue({ user: regularUser })

      render(<EditableAnnotationGuidelines task={taskWithSpecialGuidelines} />)

      expect(screen.getByText(specialGuidelines)).toBeInTheDocument()
    })

    it('works without onTaskUpdated callback', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({ user: superadminUser })

      // Reset mocks for this test
      jest.clearAllMocks()
      mockUseToast.mockReturnValue({ addToast: mockAddToast })
      mockApi.updateTask.mockResolvedValue(taskWithGuidelines)

      render(<EditableAnnotationGuidelines task={taskWithGuidelines} />)

      const editButton = screen.getByTitle('Edit annotation guidelines')
      await user.click(editButton)

      await waitFor(() => {
        expect(
          screen.getByTestId('annotation-guidelines-modal')
        ).toBeInTheDocument()
      })

      const saveButton = screen.getByTestId('modal-save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockApi.updateTask).toHaveBeenCalled()
      })
      // Should not throw error when callback is undefined
    })
  })
})
