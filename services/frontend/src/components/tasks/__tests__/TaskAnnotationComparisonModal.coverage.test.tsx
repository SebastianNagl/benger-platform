/**
 * @jest-environment jsdom
 */
import { projectsAPI } from '@/lib/api/projects'
import { UsersClient } from '@/lib/api/users'
import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { TaskAnnotationComparisonModal } from '../TaskAnnotationComparisonModal'

jest.mock('@/lib/api/projects')
jest.mock('@/lib/api/users')

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

const translations: Record<string, string> = {
  'annotation.comparison.modal.title': 'Annotations',
  'annotation.comparison.modal.taskId': 'Task {{taskId}}',
  'annotation.comparison.description': 'Compare annotations from different annotators',
  'annotation.comparison.modal.close': 'Close',
  'annotation.comparison.modal.retry': 'Retry',
  'annotation.comparison.tabs.createNew': 'Create New Annotation',
  'annotation.comparison.tabs.addYourAnnotation': 'Add Your Annotation',
  'annotation.comparison.tabs.editYourAnnotation': 'Edit Your Annotation',
  'annotation.comparison.tabs.updateExisting': 'Update your existing annotation',
  'annotation.comparison.tabs.addNew': 'Add a new annotation to this task',
  'annotation.comparison.empty.noAnnotationsYet': 'This task has no annotations yet.',
  'annotation.comparison.empty.noAnnotationsAvailable': 'No annotations available',
  'annotation.comparison.messages.projectLoadFailed': 'Failed to load project',
  'annotation.comparison.messages.loadFailed': 'Failed to load annotations',
  'annotation.comparison.messages.annotationSubmitted': 'Annotation submitted successfully!',
  'annotation.comparison.messages.annotationUpdated': 'Annotation updated successfully!',
  'annotation.comparison.messages.loadingUserAnnotation': 'Loading your annotation...',
  'annotation.comparison.messages.waitingForAnnotation': 'Please wait',
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
  'annotation.comparison.info.showingVersions': 'Showing {{count}} versions',
  'annotation.comparison.info.versionLabel': 'Version {{version}} - {{date}}',
  'annotation.comparison.info.annotatorNotes': 'Annotator Notes',
  'annotation.comparison.info.annotatorCount': '{{count}} annotator{{plural}}',
  'annotation.comparison.info.totalAnnotations': '{{count}} total annotation{{plural}}',
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

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: mockT,
  }),
}))

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

jest.mock('@/components/labeling/DynamicAnnotationInterface', () => ({
  DynamicAnnotationInterface: () => <div data-testid="dynamic-annotation-interface" />,
}))

describe('TaskAnnotationComparisonModal - coverage', () => {
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

  beforeEach(() => {
    jest.clearAllMocks()
    ;(projectsAPI.get as jest.Mock).mockResolvedValue(mockProject)
    ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([])
    ;(UsersClient.prototype.getAllUsers as jest.Mock).mockResolvedValue([
      { id: 'user-456', username: 'annotator1', email: 'annotator1@example.com' },
    ])
  })

  describe('renderAnnotationValue - various types', () => {
    it('should render boolean true value as Yes', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
        {
          id: 'ann-1',
          completed_by: 'user-456',
          result: [{ from_name: 'choice', type: 'boolean', value: true }],
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
          was_cancelled: false,
          ground_truth: false,
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
        expect(screen.getByText('Yes')).toBeInTheDocument()
      })
    })

    it('should render boolean false value as No', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
        {
          id: 'ann-1',
          completed_by: 'user-456',
          result: [{ from_name: 'choice', type: 'boolean', value: false }],
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
          was_cancelled: false,
          ground_truth: false,
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
        expect(screen.getByText('No')).toBeInTheDocument()
      })
    })

    it('should render array values as list items', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
        {
          id: 'ann-1',
          completed_by: 'user-456',
          result: [
            { from_name: 'labels', type: 'labels', value: ['Option A', 'Option B', 'Option C'] },
          ],
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
          was_cancelled: false,
          ground_truth: false,
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
        expect(screen.getByText('Option A')).toBeInTheDocument()
        expect(screen.getByText('Option B')).toBeInTheDocument()
        expect(screen.getByText('Option C')).toBeInTheDocument()
      })
    })

    it('should render object values as JSON', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
        {
          id: 'ann-1',
          completed_by: 'user-456',
          result: [
            {
              from_name: 'data',
              type: 'object',
              value: { key: 'value', nested: { deep: true } },
            },
          ],
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
          was_cancelled: false,
          ground_truth: false,
        },
      ])

      const { container } = render(
        <TaskAnnotationComparisonModal
          task={mockTask}
          isOpen={true}
          onClose={jest.fn()}
          projectId="project-1"
        />
      )

      await waitFor(() => {
        // Dialog renders in a portal, so use document.querySelector
        const preElement = document.querySelector('pre')
        expect(preElement).toBeInTheDocument()
        expect(preElement?.textContent).toContain('"key": "value"')
      })
    })

    it('should render number values with mono font', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
        {
          id: 'ann-1',
          completed_by: 'user-456',
          result: [{ from_name: 'rating', type: 'number', value: 42 }],
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
          was_cancelled: false,
          ground_truth: false,
        },
      ])

      const { container } = render(
        <TaskAnnotationComparisonModal
          task={mockTask}
          isOpen={true}
          onClose={jest.fn()}
          projectId="project-1"
        />
      )

      await waitFor(() => {
        // Dialog renders in a portal, so use document.querySelector
        const monoSpan = document.querySelector('.font-mono')
        expect(monoSpan).toBeInTheDocument()
        expect(monoSpan?.textContent).toBe('42')
      })
    })

    it('should render long string with truncation and expand toggle', async () => {
      const longString = 'A'.repeat(250)
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
        {
          id: 'ann-1',
          completed_by: 'user-456',
          result: [{ from_name: 'text', type: 'text', value: longString }],
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
          was_cancelled: false,
          ground_truth: false,
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
        expect(screen.getByText('Show full text')).toBeInTheDocument()
      })
    })

    it('should render null/undefined values as "Not answered"', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
        {
          id: 'ann-1',
          completed_by: 'user-456',
          result: [{ from_name: 'answer', type: 'text', value: null }],
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
          was_cancelled: false,
          ground_truth: false,
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
        expect(screen.getByText('Not answered')).toBeInTheDocument()
      })
    })

    it('should render empty results as "No annotation data"', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
        {
          id: 'ann-1',
          completed_by: 'user-456',
          result: [],
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
          was_cancelled: false,
          ground_truth: false,
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
        expect(screen.getByText('No annotation data')).toBeInTheDocument()
      })
    })
  })

  describe('Multiple annotations per user', () => {
    it('should show version labels when user has multiple annotations', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
        {
          id: 'ann-1',
          completed_by: 'user-456',
          result: [{ from_name: 'text', type: 'text', value: 'First version' }],
          created_at: '2024-01-01T10:00:00Z',
          updated_at: '2024-01-01T10:00:00Z',
          was_cancelled: false,
          ground_truth: false,
        },
        {
          id: 'ann-2',
          completed_by: 'user-456',
          result: [{ from_name: 'text', type: 'text', value: 'Second version' }],
          created_at: '2024-01-02T10:00:00Z',
          updated_at: '2024-01-02T10:00:00Z',
          was_cancelled: false,
          ground_truth: false,
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
        expect(screen.getByText(/Showing 2 versions/)).toBeInTheDocument()
      })
    })
  })

  describe('Metadata display', () => {
    it('should show time spent when metadata includes time_spent', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
        {
          id: 'ann-1',
          completed_by: 'user-456',
          result: [{ from_name: 'text', type: 'text', value: 'Answer' }],
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
          was_cancelled: false,
          ground_truth: false,
          metadata: { time_spent: 45000 },
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
        expect(screen.getByText('Time spent: 45s')).toBeInTheDocument()
      })
    })

    it('should show confidence when metadata includes confidence', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
        {
          id: 'ann-1',
          completed_by: 'user-456',
          result: [{ from_name: 'text', type: 'text', value: 'Answer' }],
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
          was_cancelled: false,
          ground_truth: false,
          metadata: { confidence: 0.85 },
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
        expect(screen.getByText('Confidence: 85%')).toBeInTheDocument()
      })
    })

    it('should show annotator notes when available', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
        {
          id: 'ann-1',
          completed_by: 'user-456',
          result: [{ from_name: 'text', type: 'text', value: 'Answer' }],
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
          was_cancelled: false,
          ground_truth: false,
          metadata: { notes: 'This was a tricky question' },
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
        expect(screen.getByText('Annotator Notes')).toBeInTheDocument()
        expect(screen.getByText('This was a tricky question')).toBeInTheDocument()
      })
    })
  })

  describe('Status badge rendering', () => {
    it('should show Draft status for cancelled annotations', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
        {
          id: 'ann-1',
          completed_by: 'user-456',
          result: [{ from_name: 'text', type: 'text', value: 'Draft answer' }],
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
          was_cancelled: true,
          ground_truth: false,
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
        expect(screen.getByText('Draft')).toBeInTheDocument()
      })
    })

    it('should show Approved status for ground_truth annotations', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
        {
          id: 'ann-1',
          completed_by: 'user-456',
          result: [{ from_name: 'text', type: 'text', value: 'Approved answer' }],
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
          was_cancelled: false,
          ground_truth: true,
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
        expect(screen.getByText('Approved')).toBeInTheDocument()
      })
    })
  })

  describe('Edit annotation flow', () => {
    it('should show edit button and open editor when current user has annotated', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
        {
          id: 'ann-1',
          completed_by: 'user-123',
          result: [{ from_name: 'text', type: 'text', value: 'My answer' }],
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
          was_cancelled: false,
          ground_truth: false,
        },
      ])
      ;(UsersClient.prototype.getAllUsers as jest.Mock).mockResolvedValue([
        { id: 'user-123', username: 'testuser', email: 'test@example.com' },
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
      })

      // Click the edit button
      fireEvent.click(screen.getByText('Edit My Annotation'))

      await waitFor(() => {
        expect(screen.getByText('Edit Your Annotation')).toBeInTheDocument()
        expect(screen.getByTestId('annotation-creator')).toBeInTheDocument()
      })
    })
  })

  describe('Error and fallback handling', () => {
    it('should show project load error when projectsAPI.get fails', async () => {
      ;(projectsAPI.get as jest.Mock).mockRejectedValue(new Error('Project not found'))

      render(
        <TaskAnnotationComparisonModal
          task={mockTask}
          isOpen={true}
          onClose={jest.fn()}
          projectId="project-1"
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Failed to load project')).toBeInTheDocument()
      })
    })

    it('should handle users fetch failure gracefully', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
        {
          id: 'ann-1',
          completed_by: 'user-789',
          result: [{ from_name: 'text', type: 'text', value: 'Answer' }],
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
          was_cancelled: false,
          ground_truth: false,
        },
      ])
      ;(UsersClient.prototype.getAllUsers as jest.Mock).mockRejectedValue(
        new Error('Unauthorized')
      )

      render(
        <TaskAnnotationComparisonModal
          task={mockTask}
          isOpen={true}
          onClose={jest.fn()}
          projectId="project-1"
        />
      )

      // Should still render with fallback username (appears in tab + content area)
      await waitFor(() => {
        const matches = screen.getAllByText(/Annotator user-789/)
        expect(matches.length).toBeGreaterThan(0)
      })
    })
  })
})
