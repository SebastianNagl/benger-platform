import { projectsAPI } from '@/lib/api/projects'
import { UsersClient } from '@/lib/api/users'
import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { TaskAnnotationComparisonModal } from '../TaskAnnotationComparisonModal'

// Mock the dependencies
jest.mock('@/lib/api/projects')
jest.mock('@/lib/api/users')

// Create stable mock objects outside the mock factory to prevent recreation on each call
const mockUser = {
  id: 'user-123',
  username: 'testuser',
  email: 'test@example.com',
}

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: mockUser,
  }),
}))

// Create stable mock translation function outside the mock factory
const translations: Record<string, string> = {
  'annotation.comparison.modal.title': 'Annotations',
  'annotation.comparison.modal.taskId': 'Task {{taskId}}',
  'annotation.comparison.description':
    'Compare annotations from different annotators',
  'annotation.comparison.modal.close': 'Close',
  'annotation.comparison.modal.retry': 'Retry',
  'annotation.comparison.tabs.createNew': 'Create New Annotation',
  'annotation.comparison.tabs.addYourAnnotation': 'Add Your Annotation',
  'annotation.comparison.tabs.editYourAnnotation': 'Edit Your Annotation',
  'annotation.comparison.tabs.updateExisting':
    'Update your existing annotation',
  'annotation.comparison.tabs.addNew':
    'Add a new annotation to this task',
  'annotation.comparison.empty.noAnnotationsYet':
    'This task has no annotations yet. Start annotating below.',
  'annotation.comparison.empty.noAnnotationsAvailable':
    'No annotations available',
  'annotation.comparison.messages.projectLoadFailed':
    'Failed to load project',
  'annotation.comparison.messages.loadFailed':
    'Failed to load annotations',
  'annotation.comparison.messages.annotationSubmitted':
    'Annotation submitted successfully!',
  'annotation.comparison.messages.annotationUpdated':
    'Annotation updated successfully!',
  'annotation.comparison.messages.loadingUserAnnotation':
    'Loading your annotation...',
  'annotation.comparison.messages.waitingForAnnotation':
    'Please wait while we load your annotation',
  'annotation.comparison.messages.noData': 'No annotation data',
  'annotation.comparison.result.notAnswered': 'Not answered',
  'annotation.comparison.result.yes': 'Yes',
  'annotation.comparison.result.no': 'No',
  'annotation.comparison.result.showFullText': 'Show full text',
  'annotation.comparison.status.draft': 'Draft',
  'annotation.comparison.status.submitted': 'Submitted',
  'annotation.comparison.status.approved': 'Approved',
  'annotation.comparison.status.rejected': 'Rejected',
  'annotation.comparison.info.lastUpdated': 'Last updated: {{date}}',
  'annotation.comparison.info.timeSpent': 'Time spent: {{seconds}}s',
  'annotation.comparison.info.confidence': 'Confidence: {{percent}}%',
  'annotation.comparison.info.showingVersions':
    'Showing {{count}} versions',
  'annotation.comparison.info.versionLabel':
    'Version {{version}} - {{date}}',
  'annotation.comparison.info.annotatorNotes': 'Annotator Notes',
  'annotation.comparison.info.annotatorCount':
    '{{count}} annotator{{plural}}',
  'annotation.comparison.info.totalAnnotations':
    '{{count}} total annotation{{plural}}',
  'annotation.comparison.buttons.addMyAnnotation': 'Add My Annotation',
  'annotation.comparison.buttons.editMyAnnotation': 'Edit My Annotation',
  'annotation.comparison.buttons.loadMore': 'Load {{count}} more',
}

const mockT = (key: string, vars?: Record<string, any>) => {
  let result = translations[key] || key
  if (vars) {
    Object.keys(vars).forEach((varKey) => {
      result = result.replace(`{{${varKey}}}`, String(vars[varKey]))
    })
  }
  return result
}

// Mock I18n context with stable function reference
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: mockT,
  }),
}))

// Mock the AnnotationCreator component
jest.mock('@/components/labeling/AnnotationCreator', () => ({
  AnnotationCreator: ({
    onSubmit,
    onCancel,
  }: {
    onSubmit: (annotation: any) => void
    onCancel?: () => void
  }) => (
    <div data-testid="annotation-creator">
      <button onClick={() => onSubmit({ id: 'new-annotation' })}>Submit</button>
      {onCancel && <button onClick={onCancel}>Cancel</button>}
    </div>
  ),
}))

// Mock the DynamicAnnotationInterface component
jest.mock('@/components/labeling/DynamicAnnotationInterface', () => ({
  DynamicAnnotationInterface: ({
    onSubmit,
    onSkip,
  }: {
    onSubmit: (results: any[]) => void
    onSkip?: () => void
    onChange?: (results: any[]) => void
  }) => {
    return (
      <div data-testid="dynamic-annotation-interface">
        <button
          onClick={() => onSubmit([{ from_name: 'test', value: 'value' }])}
        >
          Submit
        </button>
        {onSkip && <button onClick={onSkip}>Skip</button>}
      </div>
    )
  },
}))

describe('TaskAnnotationComparisonModal', () => {
  const mockTask = {
    id: '1',
    data: { text: 'Sample task text' },
    meta: {},
    created_at: '2024-01-01',
    updated_at: '2024-01-01',
  }

  const mockProject = {
    id: 'project-1',
    title: 'Test Project',
    label_config: '<View><Text name="text" value="$text"/></View>',
    created_at: '2024-01-01',
    updated_at: '2024-01-01',
  }

  const mockAnnotations = [
    {
      id: 'ann-1',
      completed_by: 'user-456',
      result: [{ from_name: 'text', value: 'Annotation 1' }],
      created_at: '2024-01-01',
      updated_at: '2024-01-01',
      was_cancelled: false,
      ground_truth: false,
    },
  ]

  beforeEach(() => {
    jest.clearAllMocks()
    ;(projectsAPI.get as jest.Mock).mockResolvedValue(mockProject)
    ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([])
    ;(UsersClient.prototype.getAllUsers as jest.Mock).mockResolvedValue([
      {
        id: 'user-456',
        username: 'annotator1',
        email: 'annotator1@example.com',
      },
    ])
  })

  describe('Empty Task Behavior', () => {
    it('should automatically show annotation creation interface for empty tasks', async () => {
      render(
        <TaskAnnotationComparisonModal
          task={mockTask}
          isOpen={true}
          onClose={jest.fn()}
          projectId="project-1"
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Create New Annotation')).toBeInTheDocument()
        expect(
          screen.getByText(
            'This task has no annotations yet. Start annotating below.'
          )
        ).toBeInTheDocument()
        expect(screen.getByTestId('annotation-creator')).toBeInTheDocument()
      })
    })

    it('should close modal when cancel is clicked on empty task', async () => {
      const onClose = jest.fn()
      render(
        <TaskAnnotationComparisonModal
          task={mockTask}
          isOpen={true}
          onClose={onClose}
          projectId="project-1"
        />
      )

      await waitFor(() => {
        const cancelButton = screen.getByText('Cancel')
        fireEvent.click(cancelButton)
      })

      expect(onClose).toHaveBeenCalled()
    })

    it('should switch to view mode after successful annotation submission', async () => {
      ;(projectsAPI.createAnnotation as jest.Mock).mockResolvedValue({
        id: 'new-ann',
        completed_by: 'user-123',
        result: [{ from_name: 'text', value: 'New annotation' }],
      })

      render(
        <TaskAnnotationComparisonModal
          task={mockTask}
          isOpen={true}
          onClose={jest.fn()}
          projectId="project-1"
        />
      )

      await waitFor(() => {
        const submitButton = screen.getByText('Submit')
        fireEvent.click(submitButton)
      })

      await waitFor(() => {
        expect(
          screen.getByText('Annotation submitted successfully!')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Task with Annotations', () => {
    beforeEach(() => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue(
        mockAnnotations
      )
    })

    it('should display tabs for each annotator', async () => {
      render(
        <TaskAnnotationComparisonModal
          task={mockTask}
          isOpen={true}
          onClose={jest.fn()}
          projectId="project-1"
        />
      )

      await waitFor(() => {
        // Use getAllByText since annotator1 appears in both tab and content
        const annotatorElements = screen.getAllByText('annotator1')
        expect(annotatorElements.length).toBeGreaterThan(0)
        expect(annotatorElements[0]).toBeInTheDocument()
      })
    })

    it('should show Add My Annotation button when user has not annotated', async () => {
      render(
        <TaskAnnotationComparisonModal
          task={mockTask}
          isOpen={true}
          onClose={jest.fn()}
          projectId="project-1"
        />
      )

      await waitFor(() => {
        const addButton = screen.getByText('Add My Annotation')
        expect(addButton).toBeInTheDocument()
        expect(addButton.closest('button')).toHaveClass('bg-blue-600')
      })
    })

    it('should show Edit My Annotation button when user has already annotated', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
        ...mockAnnotations,
        {
          id: 'ann-2',
          completed_by: 'user-123',
          result: [{ from_name: 'text', value: 'My annotation' }],
          created_at: '2024-01-02',
          updated_at: '2024-01-02',
        },
      ])

      render(
        <TaskAnnotationComparisonModal
          task={mockTask}
          isOpen={true}
          onClose={jest.fn()}
          projectId="project-1"
        />
      )

      await waitFor(() => {
        const editButton = screen.getByText('Edit My Annotation')
        expect(editButton).toBeInTheDocument()
        expect(editButton.closest('button')).toHaveClass('bg-amber-600')
      })
    })

    it('should display annotation statistics in footer', async () => {
      render(
        <TaskAnnotationComparisonModal
          task={mockTask}
          isOpen={true}
          onClose={jest.fn()}
          projectId="project-1"
        />
      )

      await waitFor(() => {
        expect(screen.getByText('1 annotator')).toBeInTheDocument()
        expect(screen.getByText('1 total annotation')).toBeInTheDocument()
      })
    })
  })

  describe('Modal Controls', () => {
    it('should close modal when close button is clicked', async () => {
      const onClose = jest.fn()
      render(
        <TaskAnnotationComparisonModal
          task={mockTask}
          isOpen={true}
          onClose={onClose}
          projectId="project-1"
        />
      )

      await waitFor(() => {
        const closeButton = screen.getByText('Close')
        fireEvent.click(closeButton)
      })

      expect(onClose).toHaveBeenCalled()
    })

    it('should not render when isOpen is false', () => {
      const { container } = render(
        <TaskAnnotationComparisonModal
          task={mockTask}
          isOpen={false}
          onClose={jest.fn()}
          projectId="project-1"
        />
      )

      expect(container.firstChild).toBeNull()
    })

    it('should not render when task is null', () => {
      const { container } = render(
        <TaskAnnotationComparisonModal
          task={null}
          isOpen={true}
          onClose={jest.fn()}
          projectId="project-1"
        />
      )

      expect(container.firstChild).toBeNull()
    })
  })

  describe('Error Handling', () => {
    it('should display error message when annotation fetch fails', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockRejectedValue(
        new Error('Failed to fetch')
      )

      render(
        <TaskAnnotationComparisonModal
          task={mockTask}
          isOpen={true}
          onClose={jest.fn()}
          projectId="project-1"
        />
      )

      await waitFor(() => {
        expect(
          screen.getByText('Failed to load annotations')
        ).toBeInTheDocument()
        expect(screen.getByText('Retry')).toBeInTheDocument()
      })
    })

    it('should retry fetching annotations when retry button is clicked', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock)
        .mockRejectedValueOnce(new Error('Failed'))
        .mockResolvedValueOnce(mockAnnotations)

      render(
        <TaskAnnotationComparisonModal
          task={mockTask}
          isOpen={true}
          onClose={jest.fn()}
          projectId="project-1"
        />
      )

      const retryButton = await screen.findByText('Retry')
      fireEvent.click(retryButton)

      await waitFor(() => {
        expect(projectsAPI.getTaskAnnotations).toHaveBeenCalledTimes(2)
      })
    })
  })

  describe('Auto-save Functionality', () => {
    it('should use AnnotationCreator with auto-save enabled for new annotations', async () => {
      render(
        <TaskAnnotationComparisonModal
          task={mockTask}
          isOpen={true}
          onClose={jest.fn()}
          projectId="project-1"
        />
      )

      await waitFor(() => {
        const annotationCreator = screen.getByTestId('annotation-creator')
        expect(annotationCreator).toBeInTheDocument()
      })
    })
  })
})
